import os
import psycopg2
from datetime import datetime
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Bot
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# ================== CONFIG ==================
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
PORT = int(os.getenv("PORT", 10000))
bot = Bot(TOKEN)
bot.get_updates(offset=-1)

# ================== HTTP SERVER (FOR RENDER) ==================
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

Thread(
    target=lambda: HTTPServer(("0.0.0.0", PORT), Handler).serve_forever(),
    daemon=True
).start()

# ================== DATABASE ==================
def conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )

def init_db():
    with conn() as c:
        with c.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    amount NUMERIC,
                    category TEXT,
                    created_at TIMESTAMP
                )
            """)

# ================== MIDDLEWARE ==================
def reset_state(ctx):
    ctx.user_data.clear()

async def admin_only(update: Update, ctx):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Только для администратора")
        return False
    return True

# ================== UI ==================
MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["💰 Доход", "📊 Расходы"],
        ["💵 Баланс", "👤 Профиль"]
    ],
    resize_keyboard=True
)

# ================== COMMANDS ==================
async def start(update: Update, ctx):
    reset_state(ctx)
    await update.message.reply_text(
        "👋 Бот учета финансов\n\n"
        "✏️ Расход: `500 еда`\n"
        "💰 Доход — кнопка\n"
        "❌ /cancel — отмена",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU
    )

async def cancel(update: Update, ctx):
    reset_state(ctx)
    await update.message.reply_text("❌ Отменено", reply_markup=MAIN_MENU)

# ================== MENU ==================
async def menu(update: Update, ctx):
    reset_state(ctx)
    text = update.message.text

    if text == "💰 Доход":
        ctx.user_data["await_income"] = True
        await update.message.reply_text("Введите сумму дохода:")
        return

    if text == "📊 Расходы":
        await show_expenses(update, ctx)
        return

    if text == "💵 Баланс":
        await show_balance(update, ctx)
        return

    if text == "👤 Профиль":
        await profile(update, ctx)
        return

# ================== TEXT HANDLER ==================
async def handle_text(update: Update, ctx):
    uid = update.effective_user.id
    text = update.message.text.strip()

    # доход
    if ctx.user_data.get("await_income"):
        try:
            amount = float(text)
            ctx.user_data["income"] = ctx.user_data.get("income", 0) + amount
            ctx.user_data["await_income"] = False
            await update.message.reply_text(f"✅ Доход добавлен: {amount}")
        except:
            await update.message.reply_text("❌ Введите число")
        return

    # расход
    try:
        amount, category = text.split(maxsplit=1)
        amount = float(amount)
    except:
        await update.message.reply_text("❌ Формат: 500 еда")
        return

    with conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "INSERT INTO transactions (user_id, amount, category, created_at) VALUES (%s,%s,%s,%s)",
                (uid, amount, category, datetime.now())
            )

    await update.message.reply_text(f"✅ Расход: {amount} — {category}")

# ================== SHOW ==================
async def show_expenses(update, ctx):
    uid = update.effective_user.id
    kb = []

    with conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "SELECT id, amount, category FROM transactions WHERE user_id=%s ORDER BY id DESC LIMIT 10",
                (uid,)
            )
            rows = cur.fetchall()

    if not rows:
        await update.message.reply_text("📭 Нет расходов")
        return

    for tid, amount, cat in rows:
        kb.append([
            InlineKeyboardButton(f"{amount} — {cat}", callback_data="noop"),
            InlineKeyboardButton("✏️", callback_data=f"edit:{tid}"),
            InlineKeyboardButton("🗑", callback_data=f"del:{tid}")
        ])

    await update.message.reply_text(
        "📊 Последние расходы:",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def show_balance(update, ctx):
    uid = update.effective_user.id

    with conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE user_id=%s",
                (uid,)
            )
            spent = float(cur.fetchone()[0])

    income = ctx.user_data.get("income", 0)
    balance = income - spent

    await update.message.reply_text(
        f"💵 Баланс\n\n"
        f"Доход: {income}\n"
        f"Расходы: {spent}\n"
        f"──────────\n"
        f"Итого: {balance}"
    )

async def profile(update, ctx):
    await update.message.reply_text(
        f"👤 Профиль\n"
        f"ID: {update.effective_user.id}\n"
        f"Баланс — кнопка 💵"
    )

# ================== CALLBACKS ==================
async def callbacks(update: Update, ctx):
    query = update.callback_query
    await query.answer()
    reset_state(ctx)

    uid = query.from_user.id
    data = query.data

    if data.startswith("del:"):
        tid = int(data.split(":")[1])
        with conn() as c:
            with c.cursor() as cur:
                cur.execute(
                    "DELETE FROM transactions WHERE id=%s AND user_id=%s",
                    (tid, uid)
                )
        await query.edit_message_text("🗑 Удалено")

    if data.startswith("edit:"):
        ctx.user_data["edit_id"] = int(data.split(":")[1])
        await query.edit_message_text("✏️ Введите: сумма категория")

# ================== EDIT ==================
async def edit_handler(update: Update, ctx):
    if "edit_id" not in ctx.user_data:
        return

    try:
        amount, category = update.message.text.split(maxsplit=1)
        amount = float(amount)
    except:
        await update.message.reply_text("❌ Формат: 500 еда")
        return

    tid = ctx.user_data.pop("edit_id")
    uid = update.effective_user.id

    with conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "UPDATE transactions SET amount=%s, category=%s WHERE id=%s AND user_id=%s",
                (amount, category, tid, uid)
            )

    await update.message.reply_text("✏️ Обновлено")

# ================== ADMIN ==================
async def admin(update: Update, ctx):
    if not await admin_only(update, ctx):
        return

    with conn() as c:
        with c.cursor() as cur:
            cur.execute(
                "SELECT user_id, SUM(amount) FROM transactions GROUP BY user_id"
            )
            rows = cur.fetchall()

    text = "👮 Админ панель\n\n"
    for uid, total in rows:
        text += f"ID {uid}: {total}\n"

    await update.message.reply_text(text)

# ================== RUN ==================
init_db()

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("cancel", cancel))
app.add_handler(CommandHandler("admin", admin))

app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^(💰|📊|💵|👤)"), menu))
app.add_handler(CallbackQueryHandler(callbacks))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, edit_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

print("✅ Bot is running")
app.run_polling()
