#!/usr/bin/env python3
# ================================================================
# VTX DEX — ULTIMATE REVERSE ENGINEERING BOT
# ================================================================
# DEVELOPER: @VICKYGAMING0
# VERSION: 13.0 FINAL
# LINES: 1300+
# ================================================================

import os
import re
import json
import sqlite3
import hashlib
import random
import string
import requests
import binascii
import time
import zipfile
import shutil
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict, List, Any
from urllib.parse import urlparse

# Telegram imports
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
# CONFIGURATION
# ================================================================
TOKEN = os.getenv("TELEGRAM_TOKEN") or "8256413457:AAGurkdBHnvK7h3CZPx0lleqxEZuGnKm7dA"
ADMIN_ID = int(os.getenv("ADMIN_ID") or "5510702228")
DEV_NAME = "@VICKYGAMING0"
FIREBASE_URL = "https://mn-rohan-default-rtdb.firebaseio.com"
DB_FILE = "vtxdex.db"
DUMP_DIR = "dumps"
TEMP_DIR = "temp"
JSON_DIR = "json_data"
PATCH_DIR = "patches"

for d in [DUMP_DIR, TEMP_DIR, JSON_DIR, PATCH_DIR]:
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
    used_at TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT,
    detail TEXT,
    target TEXT,
    timestamp TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS json_analysis_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    url TEXT,
    data_keys INTEGER,
    timestamp TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS repack_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    original_file TEXT,
    patched_file TEXT,
    changes TEXT,
    timestamp TEXT
)''')

conn.commit()

# ================================================================
# HELPERS
# ================================================================
def now_ist():
    try:
        import pytz
        return datetime.now(pytz.timezone('Asia/Kolkata'))
    except:
        return datetime.now()

def fmt_ist(dt):
    return dt.strftime("%d-%b-%Y %I:%M %p IST")

def days_left(expiry_str):
    if not expiry_str:
        return "N/A"
    try:
        exp = datetime.fromisoformat(expiry_str)
        diff = (exp - now_ist()).days
        return f"{diff} days" if diff > 0 else "Expired"
    except:
        return "N/A"

def log_action(user_id, action, detail="", target=""):
    c.execute(
        "INSERT INTO logs (user_id, action, detail, target, timestamp) VALUES (?, ?, ?, ?, ?)",
        (user_id, action, detail, target, now_ist().isoformat())
    )
    conn.commit()

def get_user(user_id):
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    return c.fetchone()

def create_user(user_id, username):
    now = now_ist().isoformat()
    c.execute(
        "INSERT INTO users (user_id, username, key_type, key_value, login_date, expiry_date, last_activity, registered_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, username, 'inactive', None, now, None, now, now)
    )
    conn.commit()
    log_action(user_id, "REGISTER")
    return True

def check_access(user_id):
    try:
        fb_url = f"{FIREBASE_URL}/users/{user_id}/is_banned.json"
        response = requests.get(fb_url, timeout=5)
        if response.status_code == 200 and response.json() == 1:
            return False, "⛔ You are banned"
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
            if now_ist() > datetime.fromisoformat(user[5]):
                return False, "⏳ Key expired. Use /redeem"
        except:
            pass
    return True, "✅ Access granted"

def update_user_activity(user_id):
    c.execute("UPDATE users SET used_count = used_count + 1, last_activity = ? WHERE user_id = ?",
              (now_ist().isoformat(), user_id))
    conn.commit()

def redeem_key(user_id, key):
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
            "UPDATE users SET key_type=?, key_value=?, expiry_date=?, login_date=?, expiry_days=?, max_devices=? WHERE user_id=?",
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
            "UPDATE users SET key_type=?, key_value=?, expiry_date=?, login_date=?, expiry_days=?, max_devices=? WHERE user_id=?",
            (key_type, key, expiry, now_ist().isoformat(), expiry_days, max_devices, user_id)
        )
        c.execute("UPDATE keys SET used_by=?, used_at=? WHERE key=?", (user_id, now_ist().isoformat(), key))
        conn.commit()
        log_action(user_id, "REDEEM", f"{key_type}:{key}")
        return True, f"✅ Key Redeemed!\n📦 Type: {key_type}\n📅 Expires: {expiry[:10]}"
    
    return False, "❌ Invalid or already used key"

# ================================================================
# DUMP + RADAR 2 SCAN (FIXED — ALL URLs)
# ================================================================
def generate_dump_with_radar(file_path, user_id):
    with open(file_path, 'rb') as f:
        data = f.read()
    
    text_data = data.decode('utf-8', errors='ignore')
    
    # ===== RADAR 2: EXTRACT ALL HTTPS/HTTP URLs =====
    all_urls = []
    
    # Pattern 1: Full URLs
    url_patterns = [
        r'https?://[^\s"\'<>]+',  # http/https
        r'www\.[^\s"\'<>]+',      # www.
        r'[a-zA-Z0-9-]+\.firebaseio\.com',  # Firebase
        r'[a-zA-Z0-9-]+\.unaux\.com',       # unaux
        r'[a-zA-Z0-9-]+\.vplink\.in',       # vplink
        r'[a-zA-Z0-9-]+\.telegra\.ph',      # telegra.ph
        r'[a-zA-Z0-9-]+\.github\.io',       # github.io
        r't\.me/[a-zA-Z0-9_]+',             # t.me links
    ]
    
    for pattern in url_patterns:
        matches = re.findall(pattern, text_data)
        all_urls.extend(matches)
    
    # Pattern 2: Strings that look like URLs (obfuscated)
    obfuscated_pattern = r'[a-zA-Z0-9_\-\.]+://[a-zA-Z0-9_\-\./:?&=]+'
    matches = re.findall(obfuscated_pattern, text_data)
    all_urls.extend(matches)
    
    # Remove duplicates
    all_urls = list(set(all_urls))
    
    # ===== Generate dump =====
    lines = []
    lines.append("=" * 60)
    lines.append("VTX DEX DUMP FILE + RADAR 2 SCAN")
    lines.append("=" * 60)
    lines.append(f"File: {os.path.basename(file_path)}")
    lines.append(f"Size: {os.path.getsize(file_path):,} bytes")
    lines.append(f"Hash: {hashlib.md5(open(file_path, 'rb').read()).hexdigest()}")
    lines.append(f"Date: {fmt_ist(now_ist())}")
    lines.append("")
    
    # ===== RADAR 2 SCAN =====
    lines.append("━" * 60)
    lines.append("📡 RADAR 2 SCAN — URL STATUS")
    lines.append("━" * 60)
    lines.append("")
    
    if all_urls:
        for url in all_urls[:50]:
            # Try to resolve URL
            try:
                # Add https:// if missing
                if not url.startswith('http'):
                    test_url = 'https://' + url if not url.startswith('www.') else 'https://' + url
                else:
                    test_url = url
                
                resp = requests.get(test_url, timeout=5, allow_redirects=True)
                if resp.status_code == 200:
                    status = f"✅ {resp.status_code} OK"
                elif 300 <= resp.status_code < 400:
                    status = f"🔄 {resp.status_code} Redirect"
                else:
                    status = f"⚠️ {resp.status_code}"
                lines.append(f"  {status} → {url}")
            except:
                lines.append(f"  ❌ Failed → {url}")
        if len(all_urls) > 50:
            lines.append(f"  ... and {len(all_urls) - 50} more")
    else:
        lines.append("  No URLs found in strings")
    
    lines.append("")
    
    # ===== Firebase URLs =====
    lines.append("━" * 60)
    lines.append("📡 FIREBASE URLs")
    lines.append("━" * 60)
    fb_urls = [u for u in all_urls if 'firebase' in u]
    for url in fb_urls:
        lines.append(f"  • {url}")
    if not fb_urls:
        lines.append("  None found")
    lines.append("")
    
    # ===== API Keys =====
    lines.append("━" * 60)
    lines.append("🔑 API KEYS")
    lines.append("━" * 60)
    api_keys = list(set(re.findall(r'AIza[0-9A-Za-z_-]{35}', text_data)))
    for key in api_keys:
        lines.append(f"  • {key}")
    if not api_keys:
        lines.append("  None found")
    lines.append("")
    
    # ===== Flags =====
    lines.append("━" * 60)
    lines.append("🚩 FLAGS")
    lines.append("━" * 60)
    flags = {}
    for pattern in [r'verify_active\s*=\s*([0-9]+)', r'access_hours\s*=\s*([0-9]+)', r'maintenance\s*=\s*([0-9]+)']:
        matches = re.findall(pattern, text_data)
        if matches:
            flag_name = re.search(r'([a-zA-Z_]+)\s*=', pattern)
            if flag_name:
                flags[flag_name.group(1)] = matches[0]
    for flag, value in flags.items():
        lines.append(f"  • {flag} = {value}")
    if not flags:
        lines.append("  None found")
    lines.append("")
    
    # ===== JSON Structures =====
    lines.append("━" * 60)
    lines.append("📄 JSON STRUCTURES")
    lines.append("━" * 60)
    json_structures = []
    for match in re.findall(r'\{[^{}]*\}', text_data):
        try:
            json_structures.append(json.loads(match))
            lines.append(json.dumps(json.loads(match), indent=2))
        except:
            pass
    if not json_structures:
        lines.append("  None found")
    lines.append("")
    
    # ===== Functions =====
    lines.append("━" * 60)
    lines.append("🔧 FUNCTIONS")
    lines.append("━" * 60)
    functions = list(set(re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*\s*\([^)]*\)\s*\{', text_data)))[:10]
    for f in functions:
        lines.append(f"  • {f}")
    if not functions:
        lines.append("  None found")
    lines.append("")
    
    # ===== All Strings (first 50) =====
    lines.append("━" * 60)
    lines.append("📝 STRINGS (First 50)")
    lines.append("━" * 60)
    strings = list(set(re.findall(r'[a-zA-Z0-9_\-\./\\@:]{4,}', text_data)))[:50]
    for s in strings:
        lines.append(f"  {s}")
    lines.append("")
    
    lines.append("=" * 60)
    lines.append("END OF DUMP")
    lines.append("=" * 60)
    
    return '\n'.join(lines), all_urls, json_structures

# ================================================================
# REPACK — REPLACE ALL HTTPS URLs
# ================================================================
def repack_so_with_new_url(file_path, old_url, new_url):
    try:
        with open(file_path, 'rb') as f:
            data = f.read()
        
        text_data = data.decode('utf-8', errors='ignore')
        original_text = text_data
        
        # Replace all occurrences
        text_data = text_data.replace(old_url, new_url)
        text_data = text_data.replace(old_url.replace('https://', 'http://'), new_url.replace('https://', 'http://'))
        
        # Check if any changes were made
        if text_data == original_text:
            return False, None, "URL not found in file"
        
        # Save patched file
        output_path = os.path.join(PATCH_DIR, f"repacked_{os.path.basename(file_path)}")
        with open(output_path, 'wb') as f:
            f.write(text_data.encode('utf-8', errors='ignore'))
        
        return True, output_path, "URL replaced successfully"
    except Exception as e:
        return False, None, str(e)

# ================================================================
# JSON URL ANALYSIS — UPGRADED
# ================================================================
def analyze_json_from_url(url):
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        json_data = response.json()
        
        flattened = {}
        commands = []
        
        def flatten(obj, parent=''):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    new_key = f"{parent}.{k}" if parent else k
                    if isinstance(v, dict):
                        flatten(v, new_key)
                    else:
                        flattened[new_key] = str(v)
                        if isinstance(v, (str, int, bool)):
                            commands.append(f"/{k} {v}")
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    flatten(item, f"{parent}[{i}]")
        
        flatten(json_data)
        
        # Generate report with JSON structure for easy copy-paste
        report = []
        report.append("=" * 60)
        report.append("VTX DEX — JSON URL ANALYSIS REPORT")
        report.append("=" * 60)
        report.append(f"URL: {url}")
        report.append(f"Date: {fmt_ist(now_ist())}")
        report.append("")
        
        # Extracted settings
        report.append("━" * 60)
        report.append("📌 EXTRACTED SETTINGS")
        report.append("━" * 60)
        for key, value in flattened.items():
            report.append(f"  • {key} = {value}")
        report.append("")
        
        # Commands
        report.append("━" * 60)
        report.append("🔧 COMMANDS GENERATED")
        report.append("━" * 60)
        for cmd in commands[:20]:
            report.append(f"  {cmd}")
        report.append("")
        
        # Full JSON (ready to copy-paste)
        report.append("━" * 60)
        report.append("📦 FULL JSON (Copy this to Firebase)")
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
# FRIDA HOOK GENERATOR
# ================================================================
def generate_frida_hook(func):
    return f'''// VTX DEX - Frida Hook for {func}
Java.perform(function() {{
    console.log("[*] Hooking {func}...");
    var classes = [
        "com.example.app.MainActivity",
        "com.example.app.Config",
        "com.example.app.FlagManager",
        "com.example.app.AuthManager",
        "com.example.app.SecurityManager"
    ];
    for (var i = 0; i < classes.length; i++) {{
        try {{
            var target = Java.use(classes[i]);
            if (target && target.{func}) {{
                target.{func}.implementation = function() {{
                    console.log("[*] {func} called");
                    console.log("[*] Args: " + JSON.stringify(arguments));
                    var result = this.{func}.apply(this, arguments);
                    console.log("[*] Return: " + result);
                    return result;
                }};
                console.log("[+] Hooked {func} in " + classes[i]);
            }}
        }} catch(e) {{}}
    }}
}});'''

# ================================================================
# BOT APPLICATION
# ================================================================
app = Application.builder().token(TOKEN).build()
WAITING_SO = 1
WAITING_REPACK_URL = 2
WAITING_JSON = 3

# ================================================================
# COMMANDS
# ================================================================

async def start(update, context):
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
    
    msg = f"""
╔══════════════════════════════════════╗
║          🗡️ VTX DEX BOT             ║
║     Professional Reverse Engineering ║
║     Developer: {DEV_NAME}             ║
╚══════════════════════════════════════╝

👤 User: @{username}
🔑 Key: {key_type}
📅 Login: {fmt_ist(now_ist())}
⏳ Expires: {user[5][:10] if user[5] else 'None'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 COMMANDS:

/start      - Show menu
/redeem     - Activate key
/mykey      - Check key status
/dump       - Generate dump.txt + Radar 2 scan
/repack     - Replace URLs in .so + repack
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

async def redeem(update, context):
    user_id = update.effective_user.id
    args = context.args
    if not args:
        await update.message.reply_text("❌ Usage: /redeem <KEY>")
        return
    success, msg = redeem_key(user_id, args[0].upper())
    await update.message.reply_text(msg)

async def mykey(update, context):
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
📊 Dumps: {user[9] if user[9] else 0}
📊 Repacks: {user[10] if user[10] else 0}
📊 JSON Analyses: {user[11] if user[11] else 0}
⛔ Banned: {'Yes' if user[6] else 'No'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    await update.message.reply_text(msg)

async def dump(update, context):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    await update.message.reply_text(
        "📤 Upload .so file for dump + Radar 2 scan\n\n"
        "I will extract:\n"
        "• All HTTPS/HTTP URLs\n"
        "• Firebase URLs\n"
        "• API Keys\n"
        "• Flags\n"
        "• JSON structures\n"
        "• Functions\n"
        "• Strings"
    )
    context.user_data['action'] = 'dump'
    return WAITING_SO

async def repack(update, context):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    await update.message.reply_text(
        "📤 Upload .so file for URL replacement + repack\n\n"
        "I will:\n"
        "• Extract all HTTPS URLs\n"
        "• Ask you which URL to replace\n"
        "• Replace all occurrences\n"
        "• Repack and return patched .so"
    )
    context.user_data['action'] = 'repack'
    return WAITING_SO

async def frida(update, context):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ Usage: /frida <function_name>\nExample: /frida verify_active")
        return
    
    script = generate_frida_hook(args[0])
    await update.message.reply_document(
        document=script.encode(),
        filename=f"hook_{args[0]}.js",
        caption=f"🔫 Frida Hook for '{args[0]}'"
    )
    log_action(user_id, "FRIDA", args[0])

async def jsonurl(update, context):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Usage: /jsonurl <JSON_URL>\n"
            "Example: /jsonurl https://vplink.in/Vicky.json"
        )
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
        
        c.execute(
            "INSERT INTO json_analysis_history (user_id, url, data_keys, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, url, len(flattened), now_ist().isoformat())
        )
        conn.commit()
        c.execute("UPDATE users SET total_json_analysis = total_json_analysis + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        
        os.remove(report_path)
    else:
        await update.message.reply_text(f"❌ Error: {result}")
    
    log_action(user_id, "JSONURL", url)

async def buy(update, context):
    await update.message.reply_text(
        "💳 PLANS\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Member — $10 (30 Days)\n"
        "Pro — $25 (60 Days)\n"
        "VIP — $50 (90 Days)\n"
        "Lifetime — $100 (Forever)\n\n"
        "Contact: {DEV_NAME}"
    )

async def help_cmd(update, context):
    msg = f"""
📖 VTX DEX COMMANDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

/start      - Show menu
/redeem     - Activate key
/mykey      - Check key status
/dump       - Generate dump.txt + Radar 2 scan
/repack     - Replace URLs in .so + repack
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

async def handle_document(update, context):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    doc = update.message.document
    if not doc:
        return
    
    file_name = doc.file_name or "unknown"
    file_ext = os.path.splitext(file_name)[1].lower()
    
    file_obj = await context.bot.get_file(doc.file_id)
    file_path = os.path.join(TEMP_DIR, f"{user_id}_{file_name}")
    await file_obj.download_to_drive(file_path)
    
    action = context.user_data.get('action', '')
    
    if action == 'dump':
        await process_dump(update, context, file_path)
    elif action == 'repack':
        # Check if .so or .json
        if file_ext == '.json':
            # JSON file received for repack
            await process_repack_json(update, context, file_path)
        else:
            # .so file received
            await process_repack_so(update, context, file_path)
    else:
        await update.message.reply_text("❌ Use a command first: /dump or /repack")
        os.remove(file_path)
    
    context.user_data['action'] = ''

# ================================================================
# PROCESS FUNCTIONS
# ================================================================

async def process_dump(update, context, file_path):
    user_id = update.effective_user.id
    await update.message.reply_text("📄 Generating dump.txt + Radar 2 scan...")
    
    dump_text, all_urls, json_structures = generate_dump_with_radar(file_path, user_id)
    
    dump_path = os.path.join(DUMP_DIR, f"dump_{user_id}_{int(time.time())}.txt")
    with open(dump_path, 'w', encoding='utf-8') as f:
        f.write(dump_text)
    
    # Also send URLs summary
    url_summary = f"📡 RADAR 2: {len(all_urls)} URLs found\n"
    if all_urls:
        for url in all_urls[:10]:
            url_summary += f"  • {url}\n"
        if len(all_urls) > 10:
            url_summary += f"  ... and {len(all_urls) - 10} more"
    
    await update.message.reply_document(
        document=open(dump_path, 'rb'),
        filename=f"dump_radar_{int(time.time())}.txt",
        caption=f"✅ Dump + Radar 2 scan complete!\n📊 JSON Structures: {len(json_structures)}\n\n{url_summary}"
    )
    
    c.execute("UPDATE users SET total_dumps = total_dumps + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    log_action(user_id, "DUMP_RADAR", os.path.basename(file_path))
    os.remove(file_path)
    os.remove(dump_path)

async def process_repack_so(update, context, file_path):
    user_id = update.effective_user.id
    
    # Extract URLs from .so
    with open(file_path, 'rb') as f:
        data = f.read()
    text_data = data.decode('utf-8', errors='ignore')
    
    # Find all URLs
    url_pattern = r'https?://[^\s"\'<>]+'
    urls = list(set(re.findall(url_pattern, text_data)))
    
    if not urls:
        await update.message.reply_text("❌ No HTTPS URLs found in this .so file")
        os.remove(file_path)
        return
    
    # Show URLs and ask which to replace
    url_list = "\n".join([f"{i+1}. {url}" for i, url in enumerate(urls[:20])])
    if len(urls) > 20:
        url_list += f"\n... and {len(urls) - 20} more"
    
    await update.message.reply_text(
        f"📡 Found {len(urls)} URLs in the .so file\n\n"
        f"{url_list}\n\n"
        f"🔧 Enter the URL number to replace (or /cancel):"
    )
    
    context.user_data['repack_so'] = file_path
    context.user_data['repack_urls'] = urls
    context.user_data['repack_step'] = 'select'
    return WAITING_REPACK_URL

async def process_repack_json(update, context, file_path):
    user_id = update.effective_user.id
    so_path = context.user_data.get('repack_so')
    
    if not so_path or not os.path.exists(so_path):
        await update.message.reply_text("❌ .so file not found. Please start /repack again.")
        os.remove(file_path)
        return
    
    try:
        with open(file_path, 'r') as f:
            json_data = json.load(f)
        
        # Find old_url in JSON
        old_url = context.user_data.get('repack_old_url')
        new_url = context.user_data.get('repack_new_url')
        
        if not old_url or not new_url:
            await update.message.reply_text("❌ No URL selected. Please start /repack again.")
            os.remove(file_path)
            return
        
        # Inject JSON into .so
        with open(so_path, 'rb') as f:
            so_data = f.read()
        
        json_bytes = json.dumps(json_data).encode('utf-8')
        marker = b'VTX_DEX_JSON_START'
        end_marker = b'VTX_DEX_JSON_END'
        so_data = so_data + b'\x00\x00' + marker + json_bytes + end_marker + b'\x00\x00'
        
        # Also replace URL in .so
        text_data = so_data.decode('utf-8', errors='ignore')
        text_data = text_data.replace(old_url, new_url)
        so_data = text_data.encode('utf-8', errors='ignore')
        
        output_path = os.path.join(PATCH_DIR, f"repacked_{os.path.basename(so_path)}")
        with open(output_path, 'wb') as f:
            f.write(so_data)
        
        await update.message.reply_document(
            document=open(output_path, 'rb'),
            filename=f"repacked_{os.path.basename(so_path)}",
            caption=f"✅ Repacked successfully!\nOld URL: {old_url}\nNew URL: {new_url}"
        )
        
        c.execute("UPDATE users SET total_repacks = total_repacks + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        log_action(user_id, "REPACK", f"{old_url}->{new_url}")
        
        os.remove(output_path)
        os.remove(so_path)
        os.remove(file_path)
        context.user_data['repack_so'] = None
        context.user_data['repack_urls'] = None
        context.user_data['repack_step'] = None
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
        os.remove(file_path)

async def handle_repack_url_selection(update, context):
    user_id = update.effective_user.id
    text = update.message.text
    
    if text.lower() == '/cancel':
        await update.message.reply_text("❌ Repack cancelled")
        context.user_data['repack_so'] = None
        context.user_data['repack_urls'] = None
        context.user_data['repack_step'] = None
        return
    
    try:
        index = int(text) - 1
        urls = context.user_data.get('repack_urls', [])
        if 0 <= index < len(urls):
            old_url = urls[index]
            await update.message.reply_text(
                f"🔧 Selected: {old_url}\n\n"
                f"📝 Enter the new URL to replace it with:"
            )
            context.user_data['repack_old_url'] = old_url
            context.user_data['repack_step'] = 'new_url'
        else:
            await update.message.reply_text("❌ Invalid selection. Enter a number from the list.")
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")

async def handle_repack_new_url(update, context):
    user_id = update.effective_user.id
    new_url = update.message.text
    
    old_url = context.user_data.get('repack_old_url')
    so_path = context.user_data.get('repack_so')
    
    if not old_url or not so_path:
        await update.message.reply_text("❌ Something went wrong. Please start /repack again.")
        context.user_data['repack_step'] = None
        return
    
    context.user_data['repack_new_url'] = new_url
    
    # Ask for JSON file
    await update.message.reply_text(
        f"✅ New URL: {new_url}\n\n"
        f"📤 Now send the `.json` file to inject into the .so file.\n"
        f"(If you don't have a JSON file, send /skip)"
    )
    context.user_data['repack_step'] = 'json'

# ================================================================
# ADMIN COMMANDS
# ================================================================

async def genkey(update, context):
    if update.effective_user.id != ADMIN_ID:
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
    
    try:
        requests.put(f"{FIREBASE_URL}/keys/{key}.json", json={
            'type': key_type,
            'expiry_days': expiry_days,
            'max_devices': max_devices,
            'created_by': ADMIN_ID,
            'created_at': now_ist().isoformat()
        })
    except:
        pass
    
    await update.message.reply_text(f"✅ Key: {key}\nType: {key_type}\nDays: {expiry_days}\nDevices: {max_devices}")

async def users(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    
    c.execute("SELECT user_id, username, key_type, expiry_date, is_banned, used_count FROM users ORDER BY user_id DESC LIMIT 20")
    users = c.fetchall()
    if not users:
        await update.message.reply_text("No users")
        return
    
    text = "👥 USERS\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for u in users:
        status = "🚫" if u[4] else "✅"
        expiry = u[3][:10] if u[3] else "None"
        text += f"{status} {u[0]} | @{u[1]} | {u[2]} | {expiry} | {u[5]} uses\n"
    await update.message.reply_text(text)

async def ban(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /ban <user_id>")
        return
    user_id = int(args[0])
    c.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (user_id,))
    conn.commit()
    try:
        requests.patch(f"{FIREBASE_URL}/users/{user_id}.json", json={'is_banned': 1})
    except:
        pass
    await update.message.reply_text(f"✅ User {user_id} banned")

async def unban(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    user_id = int(args[0])
    c.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,))
    conn.commit()
    try:
        requests.patch(f"{FIREBASE_URL}/users/{user_id}.json", json={'is_banned': 0})
    except:
        pass
    await update.message.reply_text(f"✅ User {user_id} unbanned")

async def stats(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE is_banned=0 AND key_type != 'inactive'")
    active = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE is_banned=1")
    banned = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM logs")
    logs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM keys WHERE used_by IS NULL")
    unused = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM json_analysis_history")
    json_analyses = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM repack_history")
    repacks = c.fetchone()[0]
    
    await update.message.reply_text(
        f"📊 STATS\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Users: {total}\n"
        f"✅ Active: {active}\n"
        f"🚫 Banned: {banned}\n"
        f"🔑 Unused Keys: {unused}\n"
        f"📝 Logs: {logs}\n"
        f"📊 JSON Analyses: {json_analyses}\n"
        f"📦 Repacks: {repacks}"
    )

# ================================================================
# CALLBACK
# ================================================================

async def callback(update, context):
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
app.add_handler(CommandHandler("stats", stats))

# Message handlers for repack flow
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_repack_url_selection))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_repack_new_url))

app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
app.add_handler(CallbackQueryHandler(callback))

# ================================================================
# MAIN
# ================================================================

if __name__ == "__main__":
    print("=" * 50)
    print("🗡️ VTX DEX — ULTIMATE EDITION")
    print("=" * 50)
    print(f"Developer: {DEV_NAME}")
    print("✅ Bot is ONLINE!")
    print("=" * 50)
    app.run_polling()
