import os
import sqlite3
import json
import subprocess
import re
import time
import hashlib
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
import asyncio

# ===== CONFIG =====
TOKEN = os.getenv("TELEGRAM_TOKEN") or "8256413457:AAGurkdBHnvK7h3CZPx0lleqxEZuGnKm7dA"
BOT_USERNAME = "@ALLINONETOOLV1BOT"
ADMIN_ID = 5510702228  # <-- TERA TELEGRAM ID DAAL

# ===== DATABASE SETUP =====
conn = sqlite3.connect("sokydex.db", check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    key_type TEXT DEFAULT 'trial',
    key_created TEXT,
    key_expiry TEXT,
    trial_used INTEGER DEFAULT 0,
    total_requests INTEGER DEFAULT 0,
    is_banned INTEGER DEFAULT 0
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
    target TEXT,
    timestamp TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS patches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    original_url TEXT,
    patched_url TEXT,
    file_hash TEXT,
    timestamp TEXT
)''')

conn.commit()

# ===== HELPER FUNCTIONS =====
def log_action(user_id, action, target=""):
    c.execute("INSERT INTO logs (user_id, action, target, timestamp) VALUES (?, ?, ?, ?)",
              (user_id, action, target, datetime.now().isoformat()))
    conn.commit()

def get_user(user_id):
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    return c.fetchone()

def create_user(user_id, username):
    expiry = (datetime.now() + timedelta(days=1)).isoformat()
    c.execute("INSERT INTO users (user_id, username, key_type, key_created, key_expiry) VALUES (?, ?, ?, ?, ?)",
              (user_id, username, 'trial', datetime.now().isoformat(), expiry))
    conn.commit()
    log_action(user_id, "REGISTER", "trial")

def check_access(user_id):
    user = get_user(user_id)
    if not user:
        return False, "Not registered. Use /start"
    if user[6] == 1:
        return False, "Banned"
    if datetime.now() > datetime.fromisoformat(user[4]):
        return False, "Key expired"
    return True, ""

def generate_key(key_type, admin_id):
    key = hashlib.md5(f"{key_type}{time.time()}{admin_id}".encode()).hexdigest()[:16]
    c.execute("INSERT INTO keys (key, type, created_by, created_at) VALUES (?, ?, ?, ?)",
              (key, key_type, admin_id, datetime.now().isoformat()))
    conn.commit()
    return key

# ===== BOT COMMANDS =====
app = Client("sokydex_bot", bot_token=TOKEN, in_memory=True)

@app.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    username = message.from_user.username or "unknown"
    if not get_user(user_id):
        create_user(user_id, username)
    log_action(user_id, "START")
    await message.reply_text(
        f"🗡️ Welcome to **SOKY-DEX MASTER**\n\n"
        f"Your key type: `{get_user(user_id)[2]}`\n"
        f"Expires: `{get_user(user_id)[4]}`\n\n"
        f"🔥 Features:\n"
        f"• /analyze <file> - Extract Firebase URLs, API keys\n"
        f"• /patch <url> - Patch .so file with new URL\n"
        f"• /flags <flag> - Toggle flags (verify_active, etc.)\n"
        f"• /frida <function> - Generate Frida hook\n"
        f"• /inject <data> - Inject data via Frida\n"
        f"• /mykey - Show your key status\n"
        f"• /buy - Get pricing info",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Dashboard", url="https://mn-rohan.web.app")],
            [InlineKeyboardButton("💳 Buy Subscription", callback_data="buy")]
        ])
    )

@app.on_message(filters.command("analyze") & filters.document)
async def analyze_so(client, message):
    user_id = message.from_user.id
    access, msg = check_access(user_id)
    if not access:
        await message.reply_text(f"⛔ {msg}")
        return
    
    file = await client.download_media(message.document)
    log_action(user_id, "ANALYZE", file)
    
    try:
        with open(file, 'rb') as f:
            data = f.read().decode('utf-8', errors='ignore')
        
        # Extract Firebase URLs
        firebase_pattern = r'https://[a-zA-Z0-9-]+\.firebaseio\.com'
        firebase_urls = re.findall(firebase_pattern, data)
        
        # Extract API keys
        api_key_pattern = r'AIza[0-9A-Za-z_-]{35}'
        api_keys = re.findall(api_key_pattern, data)
        
        # Extract flags
        flags = {}
        for flag in ['verify_active', 'access_hours', 'maintenance']:
            match = re.search(rf'{flag}\s*=\s*([0-9]+)', data)
            if match:
                flags[flag] = match.group(1)
        
        result = f"🔍 **Analysis Report:**\n\n"
        result += f"📡 **Firebase URLs:**\n{chr(10).join(firebase_urls) if firebase_urls else 'None'}\n\n"
        result += f"🔑 **API Keys:**\n{chr(10).join(api_keys) if api_keys else 'None'}\n\n"
        result += f"🚩 **Flags:**\n{json.dumps(flags, indent=2) if flags else 'None'}\n\n"
        result += f"📁 File: `{os.path.basename(file)}`"
        
        await message.reply_text(result)
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")
    finally:
        os.remove(file)

@app.on_message(filters.command("patch") & filters.document)
async def patch_so(client, message):
    user_id = message.from_user.id
    access, msg = check_access(user_id)
    if not access:
        await message.reply_text(f"⛔ {msg}")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("Usage: /patch <new_url> (reply to .so file)")
        return
    
    new_url = args[1]
    file = await client.download_media(message.document)
    log_action(user_id, "PATCH", new_url)
    
    try:
        with open(file, 'rb') as f:
            data = f.read()
        
        # Replace URL
        text_data = data.decode('utf-8', errors='ignore')
        old_urls = re.findall(r'https://[a-zA-Z0-9-]+\.firebaseio\.com', text_data)
        
        if old_urls:
            patched_data = text_data.replace(old_urls[0], new_url)
            with open(file, 'wb') as f:
                f.write(patched_data.encode())
            
            file_hash = hashlib.md5(open(file, 'rb').read()).hexdigest()
            c.execute("INSERT INTO patches (user_id, original_url, patched_url, file_hash, timestamp) VALUES (?, ?, ?, ?, ?)",
                      (user_id, old_urls[0], new_url, file_hash, datetime.now().isoformat()))
            conn.commit()
            
            await message.reply_document(file, caption=f"✅ Patched! Old: `{old_urls[0]}`\nNew: `{new_url}`\nHash: `{file_hash}`")
        else:
            await message.reply_text("❌ No Firebase URL found in .so file")
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")
    finally:
        os.remove(file)

@app.on_message(filters.command("flags"))
async def toggle_flag(client, message):
    user_id = message.from_user.id
    access, msg = check_access(user_id)
    if not access:
        await message.reply_text(f"⛔ {msg}")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("Usage: /flags <flag_name> <0|1>\nExample: /flags verify_active 0")
        return
    
    flag_name = args[1]
    value = args[2] if len(args) > 2 else "1"
    
    await message.reply_text(
        f"🔧 Flag `{flag_name}` set to `{value}`\n"
        f"✅ Use this in Frida injection or manual patch.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔧 Generate Frida Script", callback_data=f"frida_{flag_name}_{value}")]
        ])
    )
    log_action(user_id, "FLAG_TOGGLE", f"{flag_name}={value}")

@app.on_message(filters.command("frida"))
async def generate_frida(client, message):
    user_id = message.from_user.id
    access, msg = check_access(user_id)
    if not access:
        await message.reply_text(f"⛔ {msg}")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("Usage: /frida <function_name>\nExample: /frida verify_active")
        return
    
    func = args[1]
    script = f"""
// SOKY-DEX FRIDA HOOK
Java.perform(function() {{
    var targetClass = Java.use("com.your.app.MainActivity");
    targetClass.{func}.implementation = function() {{
        console.log("[*] {func} called");
        // Modify return value
        return 1;
    }};
}});
"""
    await message.reply_document(
        document=script.encode(),
        file_name=f"hook_{func}.js",
        caption=f"✅ Frida script for `{func}`\nInject with: `frida -U -f com.your.app -l hook_{func}.js`"
    )
    log_action(user_id, "FRIDA_GEN", func)

@app.on_message(filters.command("inject"))
async def inject_data(client, message):
    user_id = message.from_user.id
    access, msg = check_access(user_id)
    if not access:
        await message.reply_text(f"⛔ {msg}")
        return
    
    args = message.text.split()
    if len(args) < 3:
        await message.reply_text("Usage: /inject <function> <value>\nExample: /inject setApiKey AIzaSyXXX")
        return
    
    func = args[1]
    value = args[2]
    
    script = f"""
Java.perform(function() {{
    var cls = Java.use("com.your.app.Config");
    cls.{func}.implementation = function() {{
        return "{value}";
    }};
}});
"""
    await message.reply_document(
        document=script.encode(),
        file_name=f"inject_{func}.js",
        caption=f"✅ Injection script for `{func}` -> `{value}`"
    )
    log_action(user_id, "INJECT", f"{func}={value}")

@app.on_message(filters.command("mykey"))
async def mykey(client, message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user:
        await message.reply_text("❌ Not registered. Use /start")
        return
    
    await message.reply_text(
        f"🔑 **Your Key Info**\n"
        f"Type: `{user[2]}`\n"
        f"Created: `{user[3]}`\n"
        f"Expires: `{user[4]}`\n"
        f"Requests: `{user[5]}`\n"
        f"Banned: `{'Yes' if user[6] else 'No'}`"
    )

@app.on_message(filters.command("buy"))
async def buy(client, message):
    await message.reply_text(
        "💳 **Subscription Plans**\n\n"
        "🔥 **Trial** — 1 Day (FREE)\n"
        "🔥 **Basic** — $5 (7 Days)\n"
        "🔥 **Pro** — $15 (30 Days)\n"
        "🔥 **Lifetime** — $50 (Forever)\n\n"
        "Contact @SokyDex_Admin to purchase"
    )

# ===== ADMIN COMMANDS =====
@app.on_message(filters.command("genkey") & filters.user(ADMIN_ID))
async def genkey(client, message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("Usage: /genkey <trial|basic|pro|lifetime>")
        return
    
    key_type = args[1]
    key = generate_key(key_type, ADMIN_ID)
    await message.reply_text(f"✅ Key generated: `{key}`\nType: {key_type}")
    log_action(ADMIN_ID, "GENKEY", f"{key_type}:{key}")

@app.on_message(filters.command("revoke") & filters.user(ADMIN_ID))
async def revoke_key(client, message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("Usage: /revoke <key>")
        return
    
    key = args[1]
    c.execute("DELETE FROM keys WHERE key=?", (key,))
    conn.commit()
    await message.reply_text(f"✅ Key revoked: `{key}`")
    log_action(ADMIN_ID, "REVOKE", key)

@app.on_message(filters.command("users") & filters.user(ADMIN_ID))
async def list_users(client, message):
    c.execute("SELECT user_id, username, key_type, key_expiry FROM users")
    users = c.fetchall()
    if not users:
        await message.reply_text("No users")
        return
    
    text = "👥 **Users:**\n"
    for u in users[:10]:
        text += f"`{u[0]}` | @{u[1]} | {u[2]} | {u[3][:10]}\n"
    await message.reply_text(text)

@app.on_message(filters.command("logs") & filters.user(ADMIN_ID))
async def show_logs(client, message):
    c.execute("SELECT user_id, action, target, timestamp FROM logs ORDER BY id DESC LIMIT 10")
    logs = c.fetchall()
    if not logs:
        await message.reply_text("No logs")
        return
    
    text = "📜 **Recent Logs:**\n"
    for log in logs:
        text += f"`{log[0]}` | {log[1]} | {log[2]} | {log[3][11:19]}\n"
    await message.reply_text(text)

@app.on_message(filters.command("ban") & filters.user(ADMIN_ID))
async def ban_user(client, message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("Usage: /ban <user_id>")
        return
    
    user_id = int(args[1])
    c.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (user_id,))
    conn.commit()
    await message.reply_text(f"✅ User {user_id} banned")
    log_action(ADMIN_ID, "BAN", str(user_id))

@app.on_message(filters.command("unban") & filters.user(ADMIN_ID))
async def unban_user(client, message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("Usage: /unban <user_id>")
        return
    
    user_id = int(args[1])
    c.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,))
    conn.commit()
    await message.reply_text(f"✅ User {user_id} unbanned")
    log_action(ADMIN_ID, "UNBAN", str(user_id))

# ===== CALLBACK HANDLER =====
@app.on_callback_query()
async def callback(client, callback: CallbackQuery):
    data = callback.data
    user_id = callback.from_user.id
    
    if data == "buy":
        await callback.message.reply_text(
            "💳 **Plans:**\n"
            "Basic: $5 (7 days)\n"
            "Pro: $15 (30 days)\n"
            "Lifetime: $50 (Forever)\n"
            "Contact @SokyDex_Admin"
        )
    elif data.startswith("frida_"):
        parts = data.split("_")
        flag = parts[1]
        value = parts[2]
        await callback.message.reply_text(
            f"🔧 Frida script for `{flag}` = `{value}`:\n\n"
            f"```javascript\nJava.perform(function() {{\n"
            f"    var cls = Java.use(\"com.your.app.FlagManager\");\n"
            f"    cls.{flag}.implementation = function() {{ return {value}; }};\n"
            f"}});\n```"
        )
    
    await callback.answer()

# ===== MAIN =====
print("🗡️ SOKY-DEX MASTER BOT STARTING...")
print(f"🔥 Bot: @{BOT_USERNAME}")
print("✅ All systems operational")

app.run()
