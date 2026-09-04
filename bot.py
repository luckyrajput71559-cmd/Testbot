#!/usr/bin/env python3
# ================================================================
# VTX DEX — ULTIMATE REVERSE ENGINEERING BOT
# ================================================================
# DEVELOPER: @VICKYGAMING0
# VERSION: 22.0 FINAL
# LINES: 1500+
# ================================================================

import os
import sys
import re
import json
import sqlite3
import hashlib
import random
import string
import requests
import binascii
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from urllib.parse import urlparse

# ================================================================
# TELEGRAM IMPORTS
# ================================================================
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler
)

# ================================================================
# TIMEZONE
# ================================================================
try:
    import pytz
    IST = pytz.timezone('Asia/Kolkata')
except ImportError:
    from datetime import timezone
    IST = timezone(timedelta(hours=5, minutes=30))

# ================================================================
# CONFIGURATION
# ================================================================
TOKEN = os.getenv("TELEGRAM_TOKEN") or "8256413457:AAGurkdBHnvK7h3CZPx0lleqxEZuGnKm7dA"
ADMIN_ID = int(os.getenv("ADMIN_ID") or "5510702228")
DEV_NAME = "@VICKYGAMING0"
FIREBASE_URL = "https://mn-rohan-default-rtdb.firebaseio.com"
DB_FILE = "vtxdex.db"
DUMP_DIR = "dumps"
PATCH_DIR = "patches"
TEMP_DIR = "temp"
JSON_DIR = "json_data"

for d in [DUMP_DIR, PATCH_DIR, TEMP_DIR, JSON_DIR]:
    os.makedirs(d, exist_ok=True)

# ================================================================
# DATABASE
# ================================================================
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    key_type TEXT DEFAULT 'inactive',
    key_value TEXT,
    login_date TEXT,
    expiry_date TEXT,
    expiry_days INTEGER DEFAULT 0,
    max_devices INTEGER DEFAULT 1,
    is_banned INTEGER DEFAULT 0,
    used_count INTEGER DEFAULT 0,
    total_dumps INTEGER DEFAULT 0,
    total_repacks INTEGER DEFAULT 0,
    total_json_analysis INTEGER DEFAULT 0,
    last_activity TEXT,
    registered_date TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS keys (
    key TEXT PRIMARY KEY,
    type TEXT,
    expiry_days INTEGER,
    max_devices INTEGER,
    created_by INTEGER,
    created_at TEXT,
    used_by INTEGER,
    used_at TEXT,
    is_blacklisted INTEGER DEFAULT 0
)''')

c.execute('''CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT,
    detail TEXT,
    target TEXT,
    timestamp TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS repack_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    original_file TEXT,
    patched_file TEXT,
    old_url TEXT,
    new_url TEXT,
    timestamp TEXT
)''')

conn.commit()

# ================================================================
# HELPERS
# ================================================================
def now_ist():
    try:
        return datetime.now(IST)
    except:
        return datetime.now()

def fmt_ist(dt):
    return dt.strftime("%d-%b-%Y %I:%M %p IST")

def days_left(expiry_str: str) -> str:
    if not expiry_str:
        return "N/A"
    try:
        exp = datetime.fromisoformat(expiry_str)
        diff = (exp - now_ist()).days
        if diff < 0:
            return "Expired"
        return f"{diff} days"
    except:
        return "N/A"

def log_action(user_id: int, action: str, detail: str = "", target: str = ""):
    c.execute(
        "INSERT INTO logs (user_id, action, detail, target, timestamp) VALUES (?, ?, ?, ?, ?)",
        (user_id, action, detail, target, now_ist().isoformat())
    )
    conn.commit()

def get_user(user_id: int):
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    return c.fetchone()

def create_user(user_id: int, username: str):
    now = now_ist().isoformat()
    c.execute(
        """INSERT INTO users 
        (user_id, username, key_type, key_value, login_date, expiry_date, last_activity, registered_date) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, username, 'inactive', None, now, None, now, now)
    )
    conn.commit()
    log_action(user_id, "REGISTER")
    return True

def update_user_activity(user_id: int):
    c.execute("UPDATE users SET used_count = used_count + 1, last_activity = ? WHERE user_id = ?",
              (now_ist().isoformat(), user_id))
    conn.commit()

def update_user_stats(user_id: int, column: str):
    c.execute(f"UPDATE users SET {column} = {column} + 1 WHERE user_id = ?", (user_id,))
    conn.commit()

def check_access(user_id: int) -> Tuple[bool, str]:
    try:
        fb_url = f"{FIREBASE_URL}/users/{user_id}/is_banned.json"
        response = requests.get(fb_url, timeout=5)
        if response.status_code == 200:
            fb_banned = response.json()
            if fb_banned == 1:
                c.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (user_id,))
                conn.commit()
                return False, "⛔ You are banned"
            elif fb_banned == 0:
                c.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,))
                conn.commit()
    except:
        pass
    
    user = get_user(user_id)
    if not user:
        return False, "❌ Not registered. Use /start"
    if user[6] == 1:
        return False, "⛔ You are banned"
    if user[2] == 'inactive' or user[2] is None:
        return False, "🔑 No active key. Use /redeem"
    if user[5]:
        try:
            exp = datetime.fromisoformat(user[5])
            if now_ist() > exp:
                return False, "⏳ Key expired. Use /redeem"
        except:
            pass
    return True, "✅ Access granted"

def redeem_key(user_id: int, key: str) -> Tuple[bool, str]:
    key = key.upper().strip()
    
    fb_data = None
    try:
        resp = requests.get(f"{FIREBASE_URL}/keys/{key}.json", timeout=5)
        if resp.status_code == 200:
            fb_data = resp.json()
    except:
        pass
    
    if fb_data and not fb_data.get('used_by'):
        key_type = fb_data.get('type', 'custom')
        expiry_days = fb_data.get('expiry_days', 30)
        max_devices = fb_data.get('max_devices', 1)
        expiry = (now_ist() + timedelta(days=expiry_days)).isoformat()
        
        c.execute(
            """UPDATE users SET 
            key_type=?, key_value=?, expiry_date=?, login_date=?, expiry_days=?, max_devices=? 
            WHERE user_id=?""",
            (key_type, key, expiry, now_ist().isoformat(), expiry_days, max_devices, user_id)
        )
        conn.commit()
        
        try:
            requests.patch(f"{FIREBASE_URL}/keys/{key}.json", json={'used_by': user_id, 'used_at': now_ist().isoformat()})
        except:
            pass
        
        log_action(user_id, "REDEEM", f"{key_type}:{key}")
        return True, f"✅ Key Redeemed!\n📦 Type: {key_type}\n📅 Expires: {expiry[:10]}"
    
    c.execute("SELECT * FROM keys WHERE key=? AND used_by IS NULL", (key,))
    key_data = c.fetchone()
    if key_data:
        key_type = key_data[1]
        expiry_days = key_data[2] or 30
        max_devices = key_data[3] or 1
        expiry = (now_ist() + timedelta(days=expiry_days)).isoformat()
        
        c.execute(
            """UPDATE users SET 
            key_type=?, key_value=?, expiry_date=?, login_date=?, expiry_days=?, max_devices=? 
            WHERE user_id=?""",
            (key_type, key, expiry, now_ist().isoformat(), expiry_days, max_devices, user_id)
        )
        c.execute("UPDATE keys SET used_by=?, used_at=? WHERE key=?", (user_id, now_ist().isoformat(), key))
        conn.commit()
        
        log_action(user_id, "REDEEM", f"{key_type}:{key}")
        return True, f"✅ Key Redeemed!\n📦 Type: {key_type}\n📅 Expires: {expiry[:10]}"
    
    return False, "❌ Invalid or already used key"

# ================================================================
# DUMP + RADAR 2
# ================================================================
def generate_dump_with_radar(file_path: str) -> Tuple[str, List[str], List[dict]]:
    with open(file_path, 'rb') as f:
        data = f.read()
    
    text_data = data.decode('utf-8', errors='ignore')
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    file_hash = hashlib.md5(data).hexdigest()
    
    all_urls = []
    
    clean_pattern = r'https?://[a-zA-Z0-9\-\.]+(?:\.[a-zA-Z]{2,})+(?:/[a-zA-Z0-9\-\._~:/?#\[\]@!$&\'()*+,;=]*)?'
    matches = re.findall(clean_pattern, text_data)
    for m in matches:
        if len(m) > 10 and ' ' not in m:
            all_urls.append(m)
    
    all_urls = list(set([u for u in all_urls if len(u) > 10]))
    
    url_status = []
    for url in all_urls[:50]:
        try:
            resp = requests.get(url, timeout=5, allow_redirects=True)
            if resp.status_code == 200:
                status = f"✅ 200 OK"
            elif 300 <= resp.status_code < 400:
                status = f"🔄 {resp.status_code} Redirect"
            else:
                status = f"⚠️ {resp.status_code}"
            url_status.append((status, url))
        except:
            url_status.append(("❌ Failed", url))
    
    json_structures = []
    for match in re.findall(r'\{[^{}]*\}', text_data):
        try:
            json_structures.append(json.loads(match))
        except:
            pass
    
    lines = []
    lines.append("=" * 60)
    lines.append("VTX DEX DUMP FILE + RADAR 2 SCAN")
    lines.append("=" * 60)
    lines.append(f"File: {file_name}")
    lines.append(f"Size: {file_size:,} bytes")
    lines.append(f"Hash: {file_hash}")
    lines.append(f"Date: {fmt_ist(now_ist())}")
    lines.append("")
    
    lines.append("━" * 60)
    lines.append("📡 RADAR 2 SCAN — URL STATUS")
    lines.append("━" * 60)
    lines.append("")
    if url_status:
        for status, url in url_status:
            lines.append(f"  {status} → {url}")
        if len(all_urls) > 50:
            lines.append(f"  ... and {len(all_urls) - 50} more")
    else:
        lines.append("  No URLs found")
    lines.append("")
    
    lines.append("━" * 60)
    lines.append("📡 FIREBASE URLs")
    lines.append("━" * 60)
    fb_urls = [u for u in all_urls if 'firebase' in u.lower()]
    for url in fb_urls:
        lines.append(f"  • {url}")
    if not fb_urls:
        lines.append("  None found")
    lines.append("")
    
    lines.append("━" * 60)
    lines.append("🔑 API KEYS")
    lines.append("━" * 60)
    api_keys = list(set(re.findall(r'AIza[0-9A-Za-z_-]{35}', text_data)))
    for key in api_keys:
        lines.append(f"  • {key}")
    if not api_keys:
        lines.append("  None found")
    lines.append("")
    
    lines.append("━" * 60)
    lines.append("📄 JSON STRUCTURES")
    lines.append("━" * 60)
    for js in json_structures[:5]:
        lines.append(json.dumps(js, indent=2))
    if len(json_structures) > 5:
        lines.append(f"  ... and {len(json_structures) - 5} more")
    if not json_structures:
        lines.append("  None found")
    lines.append("")
    
    lines.append("=" * 60)
    lines.append("END OF DUMP")
    lines.append("=" * 60)
    
    return '\n'.join(lines), all_urls, json_structures

# ================================================================
# REPACK
# ================================================================
def repack_so(file_path: str, old_url: str, new_url: str) -> Tuple[bool, Optional[str], str]:
    try:
        with open(file_path, 'rb') as f:
            data = f.read()
        
        text_data = data.decode('utf-8', errors='ignore')
        original = text_data
        
        text_data = text_data.replace(old_url, new_url)
        
        if text_data == original:
            return False, None, "URL not found in file"
        
        output_path = os.path.join(PATCH_DIR, f"repacked_{os.path.basename(file_path)}")
        with open(output_path, 'wb') as f:
            f.write(text_data.encode('utf-8', errors='ignore'))
        
        return True, output_path, "URL replaced successfully"
    except Exception as e:
        return False, None, str(e)

# ================================================================
# FRIDA HOOK
# ================================================================
def generate_frida_hook(func: str) -> str:
    return f'''// VTX DEX - Frida Hook for {func}
Java.perform(function() {{
    console.log("[*] Hooking {func}...");
    var classes = [
        "com.example.app.MainActivity",
        "com.example.app.Config",
        "com.example.app.FlagManager"
    ];
    for (var i = 0; i < classes.length; i++) {{
        try {{
            var target = Java.use(classes[i]);
            if (target && target.{func}) {{
                target.{func}.implementation = function() {{
                    console.log("[*] {func} called");
                    var result = this.{func}.apply(this, arguments);
                    console.log("[*] Return: " + result);
                    return result;
                }};
                console.log("[+] Hooked {func}");
            }}
        }} catch(e) {{}}
    }}
}});'''

# ================================================================
# JSON URL ANALYSIS
# ================================================================
def analyze_json_from_url(url: str) -> Tuple[bool, str, dict, dict]:
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        json_data = response.json()
        
        flattened = {}
        
        def flatten(obj, parent=''):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    new_key = f"{parent}.{k}" if parent else k
                    if isinstance(v, dict):
                        flatten(v, new_key)
                    else:
                        flattened[new_key] = str(v)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    flatten(item, f"{parent}[{i}]")
        
        flatten(json_data)
        
        report = []
        report.append("=" * 60)
        report.append("VTX DEX — JSON URL ANALYSIS REPORT")
        report.append("=" * 60)
        report.append(f"URL: {url}")
        report.append(f"Date: {fmt_ist(now_ist())}")
        report.append("")
        
        report.append("━" * 60)
        report.append("📌 EXTRACTED SETTINGS")
        report.append("━" * 60)
        for key, value in flattened.items():
            report.append(f"  • {key} = {value}")
        report.append("")
        
        report.append("━" * 60)
        report.append("📦 FULL JSON")
        report.append("━" * 60)
        report.append(json.dumps(json_data, indent=2))
        report.append("")
        
        report.append("=" * 60)
        report.append("END OF REPORT")
        report.append("=" * 60)
        
        return True, '\n'.join(report), flattened, json_data
    except Exception as e:
        return False, str(e), {}, {}

# ================================================================
# BOT APPLICATION
# ================================================================
app = Application.builder().token(TOKEN).build()

WAITING_SO = 1
WAITING_REPACK_OLD = 2
WAITING_REPACK_NEW = 3

# ================================================================
# COMMAND HANDLERS
# ================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "unknown"
    
    user = get_user(user_id)
    if not user:
        create_user(user_id, username)
        user = get_user(user_id)
    
    keyboard = [
        [InlineKeyboardButton("🔑 Redeem Key", callback_data="redeem")],
        [InlineKeyboardButton("📊 Dashboard", url="https://mn-rohan.web.app")],
        [InlineKeyboardButton("📖 Help", callback_data="help")],
        [InlineKeyboardButton("💳 Buy", callback_data="buy")]
    ]
    
    has_key = user[2] and user[2] != 'inactive'
    key_type = user[2] if has_key else "None"
    expiry = user[5]
    left = days_left(expiry)
    
    msg = f"""
╔══════════════════════════════════════╗
║          🗡️ VTX DEX BOT             ║
║     Professional Reverse Engineering ║
║     Developer: {DEV_NAME}             ║
╚══════════════════════════════════════╝

👤 User: @{username}
🔑 Key Type: {key_type}
📅 Login: {fmt_ist(now_ist())}
⏳ Expires: {expiry[:10] if expiry else 'None'}
📊 Days Left: {left}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 COMMANDS:

/start      - Show menu
/redeem     - Activate key
/mykey      - Check key
/dump       - Dump + Radar 2 scan
/repack     - Replace URL in .so
/frida      - Generate Frida hook
/jsonurl    - Analyze JSON from URL
/help       - All commands
/buy        - Pricing info

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 Need help? Contact: {DEV_NAME}
"""
    await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
    log_action(user_id, "START")
    update_user_activity(user_id)

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    if not args:
        await update.message.reply_text("❌ Usage: /redeem <KEY>")
        return
    success, msg = redeem_key(user_id, args[0].upper())
    await update.message.reply_text(msg)

async def mykey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Not registered")
        return
    
    msg = f"""
🔑 KEY INFORMATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 Type: {user[2]}
🔑 Key: {user[3] or 'None'}
📅 Login: {user[4][:10] if user[4] else 'N/A'}
⏳ Expires: {user[5][:10] if user[5] else 'N/A'}
📊 Days Left: {days_left(user[5])}
📱 Devices: {user[8] if user[8] else 1}
🔄 Used: {user[7] if user[7] else 0} times
⛔ Banned: {'Yes' if user[6] else 'No'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    await update.message.reply_text(msg)

async def dump(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    await update.message.reply_text("📤 Upload .so file for dump + Radar 2 scan")
    context.user_data['action'] = 'dump'
    return WAITING_SO

async def repack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    await update.message.reply_text(
        "📤 Upload .so file for URL replacement + repack\n\n"
        "I will show you all URLs, then you enter OLD URL and NEW URL."
    )
    context.user_data['action'] = 'repack'
    return WAITING_SO

async def frida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ Usage: /frida <function_name>")
        return
    
    script = generate_frida_hook(args[0])
    await update.message.reply_document(
        document=script.encode(),
        filename=f"hook_{args[0]}.js",
        caption=f"🔫 Frida Hook for '{args[0]}'"
    )
    log_action(user_id, "FRIDA", args[0])

async def jsonurl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ Usage: /jsonurl <JSON_URL>")
        return
    
    url = args[0]
    await update.message.reply_text(f"🔍 Fetching JSON from:\n`{url}`")
    
    success, result, flattened, json_data = analyze_json_from_url(url)
    
    if success:
        report_path = os.path.join(JSON_DIR, f"json_report_{user_id}_{int(time.time())}.txt")
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(result)
        
        await update.message.reply_document(
            document=open(report_path, 'rb'),
            filename=f"json_analysis_{int(time.time())}.txt",
            caption=f"✅ JSON Analysis Complete!\n📊 Extracted: {len(flattened)} settings"
        )
        os.remove(report_path)
        log_action(user_id, "JSONURL", url)
    else:
        await update.message.reply_text(f"❌ Error: {result}")

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💳 PLANS\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Member — $10 (30 Days)\n"
        "Pro — $25 (60 Days)\n"
        "VIP — $50 (90 Days)\n"
        "Lifetime — $100 (Forever)\n\n"
        "Contact: {DEV_NAME}"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = f"""
📖 VTX DEX COMMANDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

/start      - Show menu
/redeem     - Activate key
/mykey      - Check key
/dump       - Dump + Radar 2 scan
/repack     - Replace URL in .so
/frida      - Generate Frida hook
/jsonurl    - Analyze JSON from URL
/help       - All commands
/buy        - Pricing info

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👤 Developer: {DEV_NAME}
"""
    await update.message.reply_text(msg)

# ================================================================
# FILE HANDLERS
# ================================================================

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    doc = update.message.document
    if not doc:
        return
    
    processing_msg = await update.message.reply_text("⏳ Processing file...")
    
    file_obj = await context.bot.get_file(doc.file_id)
    file_path = os.path.join(TEMP_DIR, f"{user_id}_{doc.file_name}")
    await file_obj.download_to_drive(file_path)
    
    action = context.user_data.get('action', '')
    
    if action == 'dump':
        await process_dump(update, context, file_path, processing_msg)
    elif action == 'repack':
        await process_repack(update, context, file_path, processing_msg)
    else:
        await processing_msg.edit_text("❌ Use /dump or /repack first")
        os.remove(file_path)

# ================================================================
# PROCESS FUNCTIONS
# ================================================================

async def process_dump(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: str, processing_msg):
    user_id = update.effective_user.id
    
    await processing_msg.edit_text("📄 Generating dump...")
    
    try:
        dump_text, urls, json_structures = generate_dump_with_radar(file_path)
        
        dump_path = os.path.join(DUMP_DIR, f"dump_{int(time.time())}.txt")
        with open(dump_path, 'w', encoding='utf-8') as f:
            f.write(dump_text)
        
        await update.message.reply_document(
            document=open(dump_path, 'rb'),
            filename=f"dump_radar_{int(time.time())}.txt",
            caption=f"✅ Dump complete!\n📡 URLs: {len(urls)}"
        )
        
        os.remove(file_path)
        os.remove(dump_path)
        await processing_msg.delete()
        
    except Exception as e:
        await processing_msg.edit_text(f"❌ Error: {str(e)}")

# ================================================================
# REPACK — SIMPLE & DIRECT
# ================================================================

async def process_repack(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: str, processing_msg):
    user_id = update.effective_user.id
    
    await processing_msg.edit_text("🔍 Scanning URLs...")
    
    try:
        with open(file_path, 'rb') as f:
            data = f.read()
        text_data = data.decode('utf-8', errors='ignore')
        
        clean_pattern = r'https?://[a-zA-Z0-9\-\.]+(?:\.[a-zA-Z]{2,})+(?:/[a-zA-Z0-9\-\._~:/?#\[\]@!$&\'()*+,;=]*)?'
        urls = list(set(re.findall(clean_pattern, text_data)))
        urls = [u for u in urls if len(u) > 10 and ' ' not in u]
        
        if not urls:
            await processing_msg.edit_text("❌ No HTTPS URLs found")
            os.remove(file_path)
            return
        
        url_list = "\n".join([f"{i+1}. {url}" for i, url in enumerate(urls)])
        
        await processing_msg.delete()
        
        await update.message.reply_text(
            f"📡 Found {len(urls)} URLs\n\n"
            f"{url_list}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 Enter the OLD URL to replace:\n"
            f"(Paste exact URL from the list)"
        )
        
        context.user_data['repack_so'] = file_path
        context.user_data['repack_urls'] = urls
        context.user_data['repack_step'] = 'old_url'
        return WAITING_REPACK_OLD
        
    except Exception as e:
        await processing_msg.edit_text(f"❌ Error: {str(e)}")

# ================================================================
# REPACK CONVERSATION — DIRECT REPLACE (NO COMPARE)
# ================================================================

async def handle_repack_old_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    old_url = update.message.text.strip()
    
    if old_url.lower() == '/cancel':
        await update.message.reply_text("❌ Cancelled")
        context.user_data['repack_so'] = None
        context.user_data['repack_step'] = None
        return
    
    await update.message.reply_text(
        f"🔧 OLD URL: {old_url}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 Enter the NEW URL:"
    )
    
    context.user_data['repack_old_url'] = old_url
    context.user_data['repack_step'] = 'new_url'
    return WAITING_REPACK_NEW

async def handle_repack_new_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    new_url = update.message.text.strip()
    
    old_url = context.user_data.get('repack_old_url')
    so_path = context.user_data.get('repack_so')
    
    if not old_url or not so_path:
        await update.message.reply_text("❌ Error. Start /repack again")
        context.user_data['repack_step'] = None
        return
    
    await update.message.reply_text("🔄 Repacking...")
    
    try:
        success, output_path, msg = repack_so(so_path, old_url, new_url)
        
        if success:
            await update.message.reply_document(
                document=open(output_path, 'rb'),
                filename=f"repacked_{os.path.basename(so_path)}",
                caption=f"✅ Repacked!\nOld: {old_url}\nNew: {new_url}"
            )
            os.remove(output_path)
        else:
            await update.message.reply_text(f"❌ {msg}")
        
        os.remove(so_path)
        context.user_data['repack_so'] = None
        context.user_data['repack_step'] = None
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

# ================================================================
# ADMIN COMMANDS
# ================================================================

async def genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only")
        return
    
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("Usage: /genkey <type> <days> <devices>")
        return
    
    key_type, expiry_days, max_devices = args[0], int(args[1]), int(args[2])
    key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
    
    c.execute(
        "INSERT INTO keys (key, type, expiry_days, max_devices, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (key, key_type, expiry_days, max_devices, ADMIN_ID, now_ist().isoformat())
    )
    conn.commit()
    
    await update.message.reply_text(f"✅ Key: {key}\nType: {key_type}\nDays: {expiry_days}")

async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    c.execute("SELECT user_id, username, key_type, expiry_date, is_banned FROM users LIMIT 20")
    users = c.fetchall()
    if not users:
        await update.message.reply_text("No users")
        return
    
    text = "👥 USERS\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for u in users:
        status = "🚫" if u[4] else "✅"
        text += f"{status} {u[0]} | @{u[1]} | {u[2]}\n"
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

# ================================================================
# CALLBACK
# ================================================================

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "redeem":
        await query.message.reply_text("🔑 /redeem <KEY>")
    elif query.data == "help":
        await help_cmd(update, context)
    elif query.data == "buy":
        await buy(update, context)

# ================================================================
# REGISTER
# ================================================================

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("redeem", redeem))
app.add_handler(CommandHandler("mykey", mykey))
app.add_handler(CommandHandler("dump", dump))
app.add_handler(CommandHandler("repack", repack))
app.add_handler(CommandHandler("frida", frida))
app.add_handler(CommandHandler("jsonurl", jsonurl))
app.add_handler(CommandHandler("buy", buy))
app.add_handler(CommandHandler("help", help_cmd))

app.add_handler(CommandHandler("genkey", genkey))
app.add_handler(CommandHandler("users", users))
app.add_handler(CommandHandler("ban", ban))
app.add_handler(CommandHandler("unban", unban))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_repack_old_url))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_repack_new_url))
app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
app.add_handler(CallbackQueryHandler(callback))

# ================================================================
# MAIN
# ================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("🗡️ VTX DEX — ULTIMATE REVERSE ENGINEERING BOT")
    print("=" * 60)
    print(f"🔥 Developer: {DEV_NAME}")
    print("✅ Bot is ONLINE!")
    print("=" * 60)
    
    app.run_polling()
