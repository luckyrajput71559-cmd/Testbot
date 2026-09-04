import os
import sqlite3
import hashlib
import random
import string
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ===== CONFIG =====
TOKEN = os.getenv("TELEGRAM_TOKEN") or "8256413457:AAGurkdBHnvK7h3CZPx0lleqxEZuGnKm7dA"
ADMIN_ID = 5510702228  # TERA TELEGRAM ID DAAL

# ===== DATABASE =====
conn = sqlite3.connect("sokydex.db", check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    key_type TEXT DEFAULT 'trial',
    key_value TEXT,
    created_at TEXT,
    expiry TEXT,
    is_banned INTEGER DEFAULT 0,
    used_count INTEGER DEFAULT 0
)''')

c.execute('''CREATE TABLE IF NOT EXISTS keys (
    key TEXT PRIMARY KEY,
    type TEXT,
    created_by INTEGER,
    created_at TEXT,
    used_by INTEGER,
    used_at TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT,
    detail TEXT,
    timestamp TEXT
)''')

conn.commit()

# ===== HELPER FUNCTIONS =====
def log_action(user_id, action, detail=""):
    c.execute("INSERT INTO logs (user_id, action, detail, timestamp) VALUES (?, ?, ?, ?)",
              (user_id, action, detail, datetime.now().isoformat()))
    conn.commit()

def get_user(user_id):
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    return c.fetchone()

def create_user(user_id, username):
    expiry = (datetime.now() + timedelta(days=1)).isoformat()
    c.execute("INSERT INTO users (user_id, username, key_type, key_value, created_at, expiry) VALUES (?, ?, ?, ?, ?, ?)",
              (user_id, username, 'trial', 'TRIAL', datetime.now().isoformat(), expiry))
    conn.commit()
    log_action(user_id, "REGISTER", "trial")
    return True

def check_access(user_id):
    user = get_user(user_id)
    if not user:
        return False, "❌ Not registered. Use /start"
    if user[6] == 1:
        return False, "⛔ You are banned"
    if datetime.now() > datetime.fromisoformat(user[5]):
        return False, "⏳ Key expired. Use /buy or /redeem"
    return True, "✅ Access granted"

def generate_key(key_type, admin_id):
    # Generate random key
    key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
    c.execute("INSERT INTO keys (key, type, created_by, created_at) VALUES (?, ?, ?, ?)",
              (key, key_type, admin_id, datetime.now().isoformat()))
    conn.commit()
    return key

def redeem_key(user_id, key):
    c.execute("SELECT * FROM keys WHERE key=? AND used_by IS NULL", (key,))
    key_data = c.fetchone()
    if not key_data:
        return False, "Invalid or already used key"
    
    key_type = key_data[1]
    days = {'trial': 1, 'basic': 7, 'pro': 30, 'lifetime': 3650}.get(key_type, 1)
    expiry = (datetime.now() + timedelta(days=days)).isoformat()
    
    c.execute("UPDATE users SET key_type=?, key_value=?, expiry=? WHERE user_id=?", 
              (key_type, key, expiry, user_id))
    c.execute("UPDATE keys SET used_by=?, used_at=? WHERE key=?", 
              (user_id, datetime.now().isoformat(), key))
    conn.commit()
    log_action(user_id, "REDEEM", key)
    return True, f"✅ Key redeemed! Type: {key_type}"

# ===== BOT COMMANDS =====
app = Application.builder().token(TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "unknown"
    
    user = get_user(user_id)
    if not user:
        create_user(user_id, username)
        user = get_user(user_id)
    
    keyboard = [
        [InlineKeyboardButton("🔑 Redeem Key", callback_data="redeem")],
        [InlineKeyboardButton("💳 Buy Subscription", callback_data="buy")],
        [InlineKeyboardButton("📊 Dashboard", url="https://mn-rohan.web.app")]
    ]
    
    await update.message.reply_text(
        f"🗡️ **SOKY-DEX MASTER BOT**\n\n"
        f"👤 User: @{username}\n"
        f"🔑 Key Type: `{user[2]}`\n"
        f"⏳ Expires: `{user[5][:10]}`\n"
        f"📊 Used: `{user[7]}` times\n\n"
        f"**Available Commands:**\n"
        f"/start - Show this menu\n"
        f"/redeem <key> - Activate subscription\n"
        f"/mykey - Check key status\n"
        f"/buy - Get pricing info\n"
        f"/analyze - Analyze .so file\n"
        f"/patch - Patch .so file\n"
        f"/frida - Generate Frida hook",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    log_action(user_id, "START")

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text("❌ Usage: /redeem <KEY>\nExample: /redeem ABC123XYZ")
        return
    
    key = args[0].upper()
    success, msg = redeem_key(user_id, key)
    await update.message.reply_text(msg)
    log_action(user_id, "REDEEM_ATTEMPT", key)

async def mykey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Not registered. Use /start")
        return
    
    await update.message.reply_text(
        f"🔑 **Your Key Info**\n\n"
        f"Type: `{user[2]}`\n"
        f"Key: `{user[3] or 'None'}`\n"
        f"Created: `{user[4][:10]}`\n"
        f"Expires: `{user[5][:10]}`\n"
        f"Used: `{user[7]}` times\n"
        f"Banned: `{'Yes' if user[6] else 'No'}`"
    )

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💳 **Subscription Plans**\n\n"
        "🔥 **Trial** — 1 Day (FREE)\n"
        "🔥 **Basic** — $5 (7 Days)\n"
        "🔥 **Pro** — $15 (30 Days)\n"
        "🔥 **Lifetime** — $50 (Forever)\n\n"
        "To purchase, contact @SokyDex_Admin\n"
        "Or use /redeem if you have a key."
    )

# ===== ADMIN COMMANDS =====
async def genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only")
        return
    
    args = context.args
    if not args or args[0] not in ['trial', 'basic', 'pro', 'lifetime']:
        await update.message.reply_text("Usage: /genkey <trial|basic|pro|lifetime>")
        return
    
    key_type = args[0]
    key = generate_key(key_type, ADMIN_ID)
    await update.message.reply_text(f"✅ Key generated:\n`{key}`\nType: {key_type}")
    log_action(ADMIN_ID, "GENKEY", f"{key_type}:{key}")

async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    c.execute("SELECT user_id, username, key_type, expiry FROM users ORDER BY user_id DESC LIMIT 20")
    users = c.fetchall()
    if not users:
        await update.message.reply_text("No users")
        return
    
    text = "👥 **Recent Users:**\n\n"
    for u in users:
        text += f"`{u[0]}` | @{u[1]} | {u[2]} | {u[3][:10]}\n"
    await update.message.reply_text(text)

async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    c.execute("SELECT user_id, action, detail, timestamp FROM logs ORDER BY id DESC LIMIT 10")
    logs = c.fetchall()
    if not logs:
        await update.message.reply_text("No logs")
        return
    
    text = "📜 **Recent Logs:**\n\n"
    for l in logs:
        text += f"`{l[0]}` | {l[1]} | {l[2][:20]} | {l[3][11:19]}\n"
    await update.message.reply_text(text)

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /ban <user_id>")
        return
    
    user_id = int(args[0])
    c.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (user_id,))
    conn.commit()
    await update.message.reply_text(f"✅ User {user_id} banned")
    log_action(ADMIN_ID, "BAN", str(user_id))

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    
    user_id = int(args[0])
    c.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,))
    conn.commit()
    await update.message.reply_text(f"✅ User {user_id} unbanned")
    log_action(ADMIN_ID, "UNBAN", str(user_id))

# ===== CALLBACK HANDLER =====
async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "redeem":
        await query.message.reply_text("🔑 Send key with: /redeem <KEY>")
    elif query.data == "buy":
        await query.message.reply_text(
            "💳 **Plans:**\n\n"
            "Trial: 1 Day (FREE)\n"
            "Basic: $5 (7 Days)\n"
            "Pro: $15 (30 Days)\n"
            "Lifetime: $50 (Forever)\n\n"
            "Contact @SokyDex_Admin"
        )

# ===== REGISTER COMMANDS =====
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("redeem", redeem))
app.add_handler(CommandHandler("mykey", mykey))
app.add_handler(CommandHandler("buy", buy))
app.add_handler(CommandHandler("genkey", genkey))
app.add_handler(CommandHandler("users", users))
app.add_handler(CommandHandler("logs", logs))
app.add_handler(CommandHandler("ban", ban))
app.add_handler(CommandHandler("unban", unban))
app.add_handler(CallbackQueryHandler(callback))

# ===== RUN =====
print("🗡️ SOKY-DEX SIMPLE BOT STARTING...")
print("🔥 Bot is online!")
app.run_polling()
