import os
import psycopg2
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

# НАСТРОЙКИ
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 415300131
PORT = int(os.getenv("PORT", 10000))

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}

# PORT FIX (RENDER)
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_server():
    HTTPServer(("0.0.0.0", PORT), PingHandler).serve_forever()

threading.Thread(target=run_server, daemon=True).start()

# DB
def get_conn():
    return psycopg2.connect(**DB_CONFIG)

def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT
                );
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(id),
                    type TEXT CHECK (type IN ('income','expense')),
                    amount NUMERIC,
                    category TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """)

init_db()

# KEYBOARD
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

# HELPERS
def register_user(user):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (id, username, first_name)
                VALUES (%s,%s,%s)
                ON CONFLICT (id) DO NOTHING
            """, (user.id, user.username, user.first_name))

def stats(user_id):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                  COALESCE(SUM(CASE WHEN type='income' THEN amount END),0),
                  COALESCE(SUM(CASE WHEN type='expense' THEN amount END),0)
                FROM transactions WHERE user_id=%s
            """, (user_id,))
            income, expense = cur.fetchone()
            return float(income - expense), float(income), float(expense)

# COMMANDS 
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user)
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Бот учёта финансов\n\n"
        "Выбирай действие кнопками 👇",
        reply_markup=KEYBOARD,
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Отменено", reply_markup=KEYBOARD)

# ADMIN
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT u.id, u.first_name,
                COALESCE(SUM(CASE WHEN t.type='income' THEN t.amount END),0) -
                COALESCE(SUM(CASE WHEN t.type='expense' THEN t.amount END),0)
                FROM users u
                LEFT JOIN transactions t ON t.user_id=u.id
                GROUP BY u.id
            """)
            text = "👑 Пользователи:\n\n"
            for uid, name, bal in cur.fetchall():
                text += f"{name} ({uid}) — {bal} zł\n"
    await update.message.reply_text(text)

# MAIN HANDLER
async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    uid = user.id
    register_user(user)

    if text in ["👤 Профиль","💰 Принять доход","📊 Показать расходы","💵 Показать остаток","❌ Отмена"]:
        context.user_data.clear()

    if text == "👤 Профиль":
        bal, inc, exp = stats(uid)
        await update.message.reply_text(
            f"👤 {user.first_name}\n"
            f"💰 Доходы: {inc}\n"
            f"📉 Расходы: {exp}\n"
            f"💵 Баланс: {bal}"
        )
        return

    if text == "💰 Принять доход":
        context.user_data["wait_income"] = True
        await update.message.reply_text("Введите сумму дохода:")
        return

    if text == "📊 Показать расходы":
        _, _, exp = stats(uid)
        await update.message.reply_text(f"📊 Расходы: {exp}")
        return

    if text == "💵 Показать остаток":
        bal, _, _ = stats(uid)
        await update.message.reply_text(f"💵 Баланс: {bal}")
        return

    if context.user_data.get("wait_income"):
        try:
            amount = float(text)
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO transactions (user_id,type,amount,category) VALUES (%s,'income',%s,'доход')",
                        (uid, amount),
                    )
            context.user_data.clear()
            await update.message.reply_text("✅ Доход добавлен", reply_markup=KEYBOARD)
        except:
            await update.message.reply_text("❌ Введите корректное число")
        return

    try:
        amount, category = text.split(maxsplit=1)
        amount = float(amount)
        bal, _, _ = stats(uid)
        if bal - amount < 0:
            await update.message.reply_text("🚫 Недостаточно средств")
            return
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO transactions (user_id,type,amount,category) VALUES (%s,'expense',%s,%s)",
                    (uid, amount, category),
                )
        await update.message.reply_text("✅ Расход записан", reply_markup=KEYBOARD)
    except:
        await update.message.reply_text("❌ Формат: `500 еда`", parse_mode="Markdown")

# RUN
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("cancel", cancel))
app.add_handler(CommandHandler("admin", admin))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler))

print("Bot started")
app.run_polling()
