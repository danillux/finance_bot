import os
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
import psycopg2

# --- Подключение к базе PostgreSQL ---
conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    database=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD")
)
cursor = conn.cursor()

# --- Создание таблиц ---
cursor.execute("""
CREATE TABLE IF NOT EXISTS expenses (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    date TIMESTAMP NOT NULL,
    amount NUMERIC NOT NULL,
    category TEXT NOT NULL
);
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS income (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    date TIMESTAMP NOT NULL,
    amount NUMERIC NOT NULL
);
""")
conn.commit()

# --- HTTP-сервер для Render ---
PORT = int(os.getenv("PORT", 10000))  # Render автоматически задаёт PORT
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def run_server():
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    server.serve_forever()

Thread(target=run_server, daemon=True).start()  # запускаем сервер в фоне

# --- Функция для кнопок ---
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("💰 Принять доходы", callback_data="income")],
        [InlineKeyboardButton("📊 Показать расходы с момента доходов", callback_data="expenses")],
        [InlineKeyboardButton("💵 Показать остаток", callback_data="balance")],
    ]
    return InlineKeyboardMarkup(keyboard)

# --- /start с кнопками ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Я бот для учета личных расходов 💸\n\n"
        "Просто отправь сообщение в формате:\n"
        "`500 еда`\n"
        "`1200 аренда`\n\n"
        "Выбери действие в меню ниже ⬇️",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

# --- Обработчик кнопок ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "income":
        await query.edit_message_text("💰 Введи сумму дохода:")
        context.user_data['awaiting_income'] = True

    elif query.data == "expenses":
        cursor.execute(
            "SELECT date FROM income WHERE user_id=%s ORDER BY date DESC LIMIT 1",
            (user_id,)
        )
        row = cursor.fetchone()
        if row:
            last_income_date = row[0]
            cursor.execute(
                "SELECT SUM(amount) FROM expenses WHERE user_id=%s AND date >= %s",
                (user_id, last_income_date)
            )
        else:
            cursor.execute(
                "SELECT SUM(amount) FROM expenses WHERE user_id=%s",
                (user_id,)
            )
        total_expenses = cursor.fetchone()[0] or 0
        await query.edit_message_text(
            f"📊 Расходы с момента доходов: {total_expenses} zł",
            reply_markup=get_main_keyboard()
        )

    elif query.data == "balance":
        cursor.execute(
            "SELECT amount, date FROM income WHERE user_id=%s ORDER BY date DESC LIMIT 1",
            (user_id,)
        )
        row = cursor.fetchone()
        if row:
            last_income, last_income_date = row
            cursor.execute(
                "SELECT SUM(amount) FROM expenses WHERE user_id=%s AND date >= %s",
                (user_id, last_income_date)
            )
            total_expenses = cursor.fetchone()[0] or 0
            balance = last_income - total_expenses
            await query.edit_message_text(
                f"💵 Остаток: {balance} zł",
                reply_markup=get_main_keyboard()
            )
        else:
            await query.edit_message_text(
                "❌ Доходы не заданы. Сначала введите доход.",
                reply_markup=get_main_keyboard()
            )

# --- Обработчик сообщений ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # --- Проверка, ждём ли доход ---
    if context.user_data.get("awaiting_income"):
        try:
            income = float(text)
            cursor.execute(
                "INSERT INTO income (user_id, date, amount) VALUES (%s, NOW(), %s)",
                (user_id, income)
            )
            conn.commit()
            context.user_data['awaiting_income'] = False
            await update.message.reply_text(f"✅ Доход записан: {income} zł",
                                            reply_markup=get_main_keyboard())
        except:
            await update.message.reply_text("❌ Введите число для дохода",
                                            reply_markup=get_main_keyboard())
        return

    # --- Иначе считаем расход ---
    try:
        amount, category = text.split(maxsplit=1)
        amount = float(amount)
        cursor.execute(
            "INSERT INTO expenses (user_id, date, amount, category) VALUES (%s, NOW(), %s, %s)",
            (user_id, amount, category)
        )
        conn.commit()
        await update.message.reply_text(f"✅ Записал: {amount} zł — {category}",
                                        reply_markup=get_main_keyboard())
    except:
        await update.message.reply_text(
            "❌ Формат неверный\nНапиши так:\n`500 еда`",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard()
        )

# --- Запуск приложения ---
TOKEN = os.getenv("BOT_TOKEN")
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Бот запущен...")
app.run_polling()
