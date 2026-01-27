import os
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
import psycopg2
from datetime import datetime

# -------------------
# Подключение к базе PostgreSQL
# -------------------
conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    database=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD")
)
cursor = conn.cursor()

# Создание таблиц, если их нет
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

# -------------------
# HTTP сервер для Render
# -------------------
PORT = int(os.getenv("PORT", 10000))

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def run_server():
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    server.serve_forever()

Thread(target=run_server, daemon=True).start()

# -------------------
# Клавиатура снизу (ReplyKeyboard)
# -------------------
keyboard = [
    ["💰 Принять доходы", "📊 Показать расходы"],
    ["💵 Показать остаток"]
]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# -------------------
# Команда /start
# -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет!\n"
        "Я бот для учёта расходов 💸\n"
        "Используй кнопки ниже или вводи расходы вручную, например: `500 еда`",
        reply_markup=reply_markup
    )

# -------------------
# Обработчик кнопок ReplyKeyboard
# -------------------
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "💰 Принять доходы":
        await update.message.reply_text("💰 Введи сумму дохода:")
        context.user_data['awaiting_income'] = True

    elif text == "📊 Показать расходы":
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
        await update.message.reply_text(f"📊 Расходы с момента доходов: {total_expenses} zł", reply_markup=reply_markup)

    elif text == "💵 Показать остаток":
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
            await update.message.reply_text(f"💵 Остаток: {balance} zł", reply_markup=reply_markup)
        else:
            await update.message.reply_text("❌ Доходы не заданы. Сначала введите доход.", reply_markup=reply_markup)

# -------------------
# Обработчик сообщений (расходы и доход)
# -------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # Проверка, ждём ли доход
    if context.user_data.get("awaiting_income"):
        try:
            income_value = float(text)
            cursor.execute(
                "INSERT INTO income (user_id, date, amount) VALUES (%s, NOW(), %s)",
                (user_id, income_value)
            )
            conn.commit()
            context.user_data['awaiting_income'] = False
            await update.message.reply_text(f"✅ Доход записан: {income_value} zł", reply_markup=reply_markup)
        except:
            await update.message.reply_text("❌ Введите число для дохода", reply_markup=reply_markup)
        return

    # Иначе считаем расход
    try:
        amount, category = text.split(maxsplit=1)
        amount = float(amount)
        cursor.execute(
            "INSERT INTO expenses (user_id, date, amount, category) VALUES (%s, NOW(), %s, %s)",
            (user_id, amount, category)
        )
        conn.commit()
        await update.message.reply_text(f"✅ Записал: {amount} zł — {category}", reply_markup=reply_markup)
    except:
        await update.message.reply_text("❌ Формат неверный\nНапиши так: `500 еда`", reply_markup=reply_markup)

# -------------------
# Запуск бота
# -------------------
TOKEN = os.getenv("BOT_TOKEN")
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_button))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Бот запущен...")
app.run_polling()
