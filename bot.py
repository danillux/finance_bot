from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from datetime import datetime
import psycopg2
import os

# --- Подключение к базе данных ---
conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    database=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD")
)
cursor = conn.cursor()

# Создаём таблицу, если её нет
cursor.execute("""
CREATE TABLE IF NOT EXISTS expenses (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    date TIMESTAMP NOT NULL,
    amount NUMERIC NOT NULL,
    category TEXT NOT NULL
)
""")
conn.commit()

# --- /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Я бот для учета личных расходов 💸\n\n"
        "Просто отправь сообщение в формате:\n"
        "`500 еда`\n"
        "`1200 аренда`\n\n"
        "Или используй /menu для кнопок 📊",
        parse_mode="Markdown"
    )

# --- Меню кнопок ---
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💰 Принять доходы", callback_data="income")],
        [InlineKeyboardButton("📊 Показать расходы с момента доходов", callback_data="expenses")],
        [InlineKeyboardButton("💵 Показать остаток", callback_data="balance")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выбери действие:", reply_markup=reply_markup)

# --- Обработчик кнопок ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    user_id = user.id

    if query.data == "income":
        await query.edit_message_text("💰 Введи сумму дохода:")
        context.user_data['awaiting_income'] = True

    elif query.data == "expenses":
        cursor.execute("SELECT SUM(amount) FROM expenses WHERE user_id=%s", (user_id,))
        total_expenses = cursor.fetchone()[0] or 0
        await query.edit_message_text(f"📊 Расходы с момента доходов: {total_expenses} zł")

    elif query.data == "balance":
        income = context.user_data.get("income", 0)
        cursor.execute("SELECT SUM(amount) FROM expenses WHERE user_id=%s", (user_id,))
        total_expenses = cursor.fetchone()[0] or 0
        balance = income - total_expenses
        await query.edit_message_text(f"💵 Остаток: {balance} zł")

# --- Обработчик сообщений ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    text = update.message.text.strip()

    # --- Если ждем доход ---
    if context.user_data.get("awaiting_income"):
        try:
            income = float(text)
            context.user_data['income'] = income
            context.user_data['awaiting_income'] = False
            await update.message.reply_text(f"✅ Доход записан: {income} zł")
        except:
            await update.message.reply_text("❌ Введите число для дохода")
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

        await update.message.reply_text(f"✅ Записал: {amount} zł — {category}")
    except:
        await update.message.reply_text(
            "❌ Формат неверный\nНапиши так:\n`500 еда`",
            parse_mode='Markdown'
        )

# --- Создание и запуск приложения ---
TOKEN = os.getenv("BOT_TOKEN")
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("menu", menu))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Бот запущен...")
app.run_polling()
