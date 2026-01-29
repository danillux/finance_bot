import os
import csv
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

# ================== НАСТРОЙКИ ==================
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 123456789  # <-- ВСТАВЬ СВОЙ TELEGRAM ID
PORT = int(os.getenv("PORT", 10000))

# ================== HTTP SERVER (RENDER) ==================
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def run_server():
    server = HTTPServer(("0.0.0.0", PORT), DummyHandler)
    server.serve_forever()

threading.Thread(target=run_server, daemon=True).start()

# ================== КНОПКИ ==================
KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("👤 Профиль")],
        [KeyboardButton("💰 Принять доход")],
        [KeyboardButton("📊 Показать расходы")],
        [KeyboardButton("💵 Показать остаток")],
        [KeyboardButton("❌ Отмена")],
    ],
    resize_keyboard=True,
)

# ================== ФАЙЛЫ ==================
def file_name(user_id):
    return f"finance_{user_id}.csv"

def init_file(user_id):
    if not os.path.exists(file_name(user_id)):
        with open(file_name(user_id), "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["date", "type", "amount", "category"])

def read_data(user_id):
    init_file(user_id)
    with open(file_name(user_id), encoding="utf-8") as f:
        return list(csv.DictReader(f))

def write_row(user_id, row):
    with open(file_name(user_id), "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)

def calc(data):
    balance = income = expenses = 0
    for r in data:
        a = float(r["amount"])
        if r["type"] == "income":
            income += a
            balance += a
        else:
            expenses += a
            balance -= a
    return balance, income, expenses

# ================== КОМАНДЫ ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Бот учёта финансов\n\n"
        "• Доходы\n• Расходы\n• Баланс\n\n"
        "Выбирай кнопками 👇",
        reply_markup=KEYBOARD,
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Отменено", reply_markup=KEYBOARD)

# ================== АДМИН ==================
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    users = [
        f.replace("finance_", "").replace(".csv", "")
        for f in os.listdir()
        if f.startswith("finance_")
    ]

    text = "👑 Пользователи:\n\n"
    for u in users:
        bal, _, _ = calc(read_data(u))
        text += f"ID {u} — {bal:.2f} zł\n"

    await update.message.reply_text(text)

async def user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    uid = context.args[0]
    bal, inc, exp = calc(read_data(uid))
    await update.message.reply_text(
        f"ID {uid}\n💰 {inc}\n📉 {exp}\n💵 {bal}"
    )

async def user_expenses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    uid = context.args[0]
    data = read_data(uid)
    text = "📊 Расходы:\n"
    for r in data:
        if r["type"] == "expense":
            text += f"{r['amount']} — {r['category']}\n"
    await update.message.reply_text(text)

# ================== ОСНОВНАЯ ЛОГИКА ==================
async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user
    uid = user.id
    data = read_data(uid)

    # ---- КНОПКИ (ВСЕГДА ПЕРВЫЕ) ----
    if text in ["👤 Профиль", "💰 Принять доход", "📊 Показать расходы", "💵 Показать остаток", "❌ Отмена"]:
        context.user_data.clear()

    if text == "👤 Профиль":
        bal, inc, exp = calc(data)
        await update.message.reply_text(
            f"👤 {user.first_name}\n"
            f"💰 {inc}\n📉 {exp}\n💵 {bal}",
        )
