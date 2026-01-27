from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from datetime import datetime
import csv
import os

TOKEN = os.getenv("BOT_TOKEN")  # В Render добавь ENV переменную BOT_TOKEN

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

# --- меню кнопок ---
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💰 Принять доходы", callback_data="income")],
        [InlineKeyboardButton("📊 Показать расходы с момента доходов", callback_data="expenses")],
        [InlineKeyboardButton("💵 Показать остаток", callback_data="balance")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выбери действие:", reply_markup=reply_markup)

# --- обработчик кнопок ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    file_name = f"expenses_{user.id}.csv"

    if query.data == "income":
        await query.edit_message_text("💰 Введи сумму дохода:")
        context.user_data['awaiting_income'] = True

    elif query.data == "expenses":
        total_expenses = 0
        if os.path.exists(file_name):
            with open(file_name, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    total_expenses += float(row['amount'])
        await query.edit_message_text(f"📊 Расходы с момента доходов: {total_expenses} zł")

    elif query.data == "balance":
        income = context.user_data.get("income", 0)
        total_expenses = 0
        if os.path.exists(file_name):
            with open(file_name, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    total_expenses += float(row['amount'])
        balance = income - total_expenses
        await query.edit_message_text(f"💵 Остаток: {balance} zł")

# --- обработчик сообщений ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    file_name = f"expenses_{user.id}.csv"

    # --- создаем файл, если его нет ---
    if not os.path.exists(file_name):
        with open(file_name, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['date', 'amount', 'category'])

    text = update.message.text.strip()

    # --- проверка, ждем ли доход ---
    if context.user_data.get("awaiting_income"):
        try:
            income = float(text)
            context.user_data['income'] = income
            context.user_data['awaiting_income'] = False
            await update.message.reply_text(f"✅ Доход записан: {income} zł")
        except:
            await update.message.reply_text("❌ Введите число для дохода")
        return

    # --- запись расходов ---
    try:
        amount, category = text.split(maxsplit=1)
        amount = float(amount)

        with open(file_name, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().strftime('%d-%m-%Y %H:%M'),
                amount,
                category
            ])
        await update.message.reply_text(f"✅ Записал: {amount} zł — {category}")
    except:
        await update.message.reply_text(
            "❌ Формат неверный\nНапиши так:\n`500 еда`",
            parse_mode='Markdown'
        )

# --- создание и запуск приложения ---
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("menu", menu))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Бот запущен...")
app.run_polling()
