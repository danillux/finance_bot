from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters, CallbackContext, CommandHandler
from datetime import datetime
import csv
import os

TOKEN = os.getenv("BOT_TOKEN")
FILE_NAME = f"expenses_{user.id}.csv"
user_id = update.effective_user.id

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Я бот для учета личных расходов 💸\n\n"
        "Просто отправь сообщение в формате:\n"
        "`500 еда`\n"
        "`1200 аренда`\n\n"
        "Я сохраню это в таблицу 📊",
        parse_mode="Markdown"
    )

if not os.path.exists(FILE_NAME):
    with open(FILE_NAME, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['date', 'amount', 'category'])

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    try:
        amount, category = text.split(maxsplit=1)
        amount = float(amount)

        with open(FILE_NAME, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().strftime('%d-%m-%Y %H:%M'),
                amount,
                category
            ])
        await update.message.reply_text(
            f'✅ Записал: {amount} zł — {category}'
        )
    except:
        await update.message.reply_text(
            "❌ Формат неверный\nНапиши так:\n`500 еда`",
            parse_mode = 'Markdown'
        )
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print('Бот запущен...')
app.run_polling()