from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)
from datetime import datetime
import csv
import os

TOKEN = os.getenv("BOT_TOKEN")

# ---------- КНОПКИ ----------
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("👤 Профиль")],
        [KeyboardButton("💰 Принять доход")],
        [KeyboardButton("📊 Показать расходы")],
        [KeyboardButton("💵 Показать остаток")],
        [KeyboardButton("❌ Отмена")],
    ],
    resize_keyboard=True,
)

# ---------- ВСПОМОГАТЕЛЬНЫЕ ----------
def get_file(user_id):
    return f"finance_{user_id}.csv"


def init_file(user_id):
    file = get_file(user_id)
    if not os.path.exists(file):
        with open(file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["date", "type", "amount", "category"])


def read_data(user_id):
    init_file(user_id)
    data = []
    with open(get_file(user_id), encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append(row)
    return data


def write_row(user_id, row):
    init_file(user_id)
    with open(get_file(user_id), "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(row)


def calculate_balance(data):
    balance = 0
    expenses = 0
    income = 0
    for row in data:
        amount = float(row["amount"])
        if row["type"] == "income":
            balance += amount
            income += amount
        else:
            balance -= amount
            expenses += amount
    return balance, income, expenses


# ---------- КОМАНДЫ ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Я бот для учёта финансов 💸\n\n"
        "• Доходы\n"
        "• Расходы\n"
        "• Баланс и статистика\n\n"
        "Выбирай действие кнопками ниже 👇",
        reply_markup=MAIN_KEYBOARD,
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Действие отменено",
        reply_markup=MAIN_KEYBOARD,
    )


# ---------- ОСНОВНОЙ ОБРАБОТЧИК ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user
    user_id = user.id
    data = read_data(user_id)

    # ---------- ОТМЕНА ----------
    if text == "❌ Отмена":
        context.user_data.clear()
        await update.message.reply_text("❌ Всё отменено", reply_markup=MAIN_KEYBOARD)
        return

    # ---------- ПРОФИЛЬ ----------
    if text == "👤 Профиль":
        balance, income, expenses = calculate_balance(data)
        await update.message.reply_text(
            f"👤 *Профиль*\n\n"
            f"Имя: {user.first_name}\n"
            f"💰 Доходы: {income:.2f} zł\n"
            f"📉 Расходы: {expenses:.2f} zł\n"
            f"💵 Баланс: {balance:.2f} zł",
            parse_mode="Markdown",
        )
        return

    # ---------- ПРИНЯТЬ ДОХОД ----------
    if text == "💰 Принять доход":
        context.user_data.clear()
        context.user_data["awaiting_income"] = True
        await update.message.reply_text("💰 Введите сумму дохода:")
        return

    # ---------- ПОКАЗАТЬ РАСХОДЫ ----------
    if text == "📊 Показать расходы":
        _, _, expenses = calculate_balance(data)
        await update.message.reply_text(f"📊 Всего расходов: {expenses:.2f} zł")
        return

    # ---------- ПОКАЗАТЬ ОСТАТОК ----------
    if text == "💵 Показать остаток":
        balance, _, _ = calculate_balance(data)
        await update.message.reply_text(f"💵 Текущий баланс: {balance:.2f} zł")
        return

    # ---------- ВВОД ДОХОДА ----------
    if context.user_data.get("awaiting_income"):
        try:
            amount = float(text)
            if amount <= 0:
                raise ValueError
            write_row(
                user_id,
                [datetime.now(), "income", amount, "доход"],
            )
            context.user_data.clear()
            await update.message.reply_text(
                f"✅ Доход {amount:.2f} zł добавлен",
                reply_markup=MAIN_KEYBOARD,
            )
        except:
            await update.message.reply_text("❌ Введите корректное число")
        return

    # ---------- ВВОД РАСХОДА ----------
    try:
        amount, category = text.split(maxsplit=1)
        amount = float(amount)

        balance, _, _ = calculate_balance(data)
        if amount <= 0:
            raise ValueError

        if balance - amount < 0:
            await update.message.reply_text(
                "🚫 Недостаточно средств.\n"
                f"Текущий баланс: {balance:.2f} zł"
            )
            return

        write_row(
            user_id,
            [datetime.now(), "expense", amount, category],
        )
        await update.message.reply_text(
            f"✅ Расход {amount:.2f} zł — {category}",
            reply_markup=MAIN_KEYBOARD,
        )

    except:
        await update.message.reply_text(
            "❌ Формат расхода:\n`500 еда`",
            parse_mode="Markdown",
        )


# ---------- ЗАПУСК ----------
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("cancel", cancel))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Бот запущен...")
app.run_polling()
