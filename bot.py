import os
import psycopg2
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# ================= CONFIG =================
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 415300131
PORT = int(os.getenv("PORT", 10000))

DB = {
    "host": os.getenv("DB_HOST"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}

# ================= RENDER PORT =================
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

threading.Thread(
    target=lambda: HTTPServer(("0.0.0.0", PORT), Handler).serve_forever(),
    daemon=True
).start()

# ================= DB =================
def conn():
    return psycopg2.connect(**DB)

def init_db():
    with conn() as c:
        with c.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT
            );
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(id),
                type TEXT,
                amount NUMERIC,
                category TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """)

init_db()

# ================= UI =================
KB = ReplyKeyboardMarkup(
    [
        ["👤 Профиль"],
        ["💰 Доход", "💸 Расход"],
        ["📊 Месяц"],
    ],
    resize_keyboard=True
)

# ================= HELPERS =================
def reg(user):
    with conn() as c:
        with c.cursor() as cur:
            cur.execute("""
            INSERT INTO users (id, username, first_name)
            VALUES (%s,%s,%s)
            ON CONFLICT DO NOTHING
            """, (user.id, user.username, user.first_name))

def balance(uid):
    with conn() as c:
        with c.cursor() as cur:
            cur.execute("""
            SELECT
            COALESCE(SUM(CASE WHEN type='income' THEN amount END),0),
            COALESCE(SUM(CASE WHEN type='expense' THEN amount END),0)
            FROM transactions WHERE user_id=%s
            """, (uid,))
            inc, exp = cur.fetchone()
            return float(inc), float(exp), float(inc-exp)

# ================= COMMANDS =================
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reg(update.effective_user)
    ctx.user_data.clear()
    await update.message.reply_text("👋 Учет финансов", reply_markup=KB)

async def history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    with conn() as c:
        with c.cursor() as cur:
            cur.execute("""
            SELECT id, type, amount, category, created_at
            FROM transactions
            WHERE user_id=%s
            ORDER BY id DESC LIMIT 10
            """, (uid,))
            rows = cur.fetchall()

    if not rows:
        await update.message.reply_text("История пуста")
        return

    text = "📜 Последние операции:\n\n"
    for i,t,a,cg,dt in rows:
        text += f"#{i} {t} {a} {cg} ({dt:%d.%m})\n"
    await update.message.reply_text(text)

async def delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    try:
        tid = int(ctx.args[0])
        with conn() as c:
            with c.cursor() as cur:
                cur.execute("DELETE FROM transactions WHERE id=%s AND user_id=%s", (tid, uid))
            await update.message.reply_text("🗑 Операция удалена")
    except Exception as e:
        await update.message.reply_text("❌ Используй: /delete ID")
