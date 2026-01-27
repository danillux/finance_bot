import os
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

import psycopg2
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# НАСТРОЙКИ
TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 10000))

conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    database=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD")
)
cursor = conn.cursor()

# HTTP (Render)
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

Thread(target=lambda: HTTPServer(("0.0.0.0", PORT), Handler).serve_forever(), daemon=True).start()

# БАЗА
cursor.execute("""
CREATE TABLE IF NOT EXISTS profile (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    balance NUMERIC DEFAULT 0,
    month TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS operations (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    date TIMESTAMP,
    amount NUMERIC,
    type TEXT,
    category TEXT
)
""")

conn.commit()

# КЛАВИАТУРА
keyboard = ReplyKeyboardMarkup(
    [
        ["👤 Профиль"],
        ["💰 Принять доходы", "📊 Показать расходы"],
        ["💵 Показать остаток"]
    ],
    resize_keyboard=True
)

# ВСПОМОГАТЕЛЬНОЕ
def current_month():
    return datetime.now().strftime("%Y-%m")

def ensure_profile(user):
    cursor.execute("SELECT month FROM profile WHERE user_id=%s", (user.id,))
    row = cursor.fetchone()

    if not row:
        cursor.execute(
            "INSERT INTO profile VALUES (%s,%s,0,%s)",
            (user.id, user.username, current_month())
        )
        conn.commit()
        return

    if row[0] != current_month():
        cursor.execute(
            "UPDATE profile SET month=%s WHERE user_id=%s",
            (current_month(), user.id)
        )
        cursor.execute(
            "DELETE FROM operations WHERE user_id=%s",
            (user.id,)
        )
        conn.commit()

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_profile(update.effective_user)
    await update.message.reply_text(
        "👋 Добро пожаловать в финансовый бот 💸\n"
        "Расходы вводи так: `500 еда`",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# ОБРАБОТКА ТЕКСТА
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user
    ensure_profile(user)

    # ---- ПРОФИЛЬ ----
    if text == "👤 Профиль":
        cursor.execute("SELECT balance FROM profile WHERE user_id=%s", (user.id,))
        balance = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COALESCE(SUM(amount),0)
            FROM operations
            WHERE user_id=%s AND type='expense'
        """, (user.id,))
        expenses = cursor.fetchone()[0]

        cursor.execute("""
            SELECT date, amount FROM operations
            WHERE user_id=%s AND type='income'
            ORDER BY date DESC
        """, (user.id,))
        incomes = cursor.fetchall()

        history = "\n".join([f"{d:%d.%m} +{a} zł" for d,a in incomes]) or "нет"

        await update.message.reply_text(
            f"👤 @{user.username}\n\n"
            f"💵 Баланс: {balance} zł\n"
            f"📊 Расходы за месяц: {expenses} zł\n\n"
            f"💰 История доходов:\n{history}",
            reply_markup=keyboard
        )
        return

    # ---- ДОХОД ----
    if text == "💰 Принять доходы":
        context.user_data["income"] = True
        await update.message.reply_text("💰 Введите сумму дохода:")
        return

    if context.user_data.get("income"):
        try:
            value = float(text)

            cursor.execute(
                "UPDATE profile SET balance = balance + %s WHERE user_id=%s",
                (value, user.id)
            )
            cursor.execute(
                "INSERT INTO operations VALUES (DEFAULT,%s,NOW(),%s,'income',NULL)",
                (user.id, value)
            )
            conn.commit()

            context.user_data["income"] = False
            await update.message.reply_text(f"✅ Доход +{value} zł", reply_markup=keyboard)
        except:
            await update.message.reply_text("❌ Введите число")
        return

    # ---- РАСХОД ----
    try:
        amount, category = text.split(maxsplit=1)
        amount = float(amount)

        cursor.execute(
            "UPDATE profile SET balance = balance - %s WHERE user_id=%s",
            (amount, user.id)
        )
        cursor.execute(
            "INSERT INTO operations VALUES (DEFAULT,%s,NOW(),%s,'expense',%s)",
            (user.id, amount, category)
        )
        conn.commit()

        await update.message.reply_text(f"✅ Расход: {amount} zł — {category}", reply_markup=keyboard)
    except:
        await update.message.reply_text("❌ Формат: `500 еда`", parse_mode="Markdown")

# ЗАПУСК
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

print("Бот запущен")
app.run_polling()
