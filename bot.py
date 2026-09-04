#!/usr/bin/env python3
# ================================================================
# VTX DEX — CLEAN REVERSE ENGINEERING BOT
# ================================================================
# DEVELOPER: @VICKYGAMING0
# VERSION: 12.0 CLEAN
# LINES: 1200+
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

for d in [DUMP_DIR, TEMP_DIR, JSON_DIR]:
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
    total_analysis INTEGER DEFAULT 0,
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
    # Firebase ban check
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
    
    fb_data = requests.get(f"{FIREBASE_URL}/keys/{key}.json").json() if requests.get(f"{FIREBASE_URL}/keys/{key}.json").status_code == 200 else None
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
        requests.patch(f"{FIREBASE_URL}/keys/{key}.json", json={'used_by': user_id, 'used_at': now_ist().isoformat()})
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
# .SO ANALYZER — OPTIMISED
# ================================================================
class SOAnalyzer:
    def __init__(self, file_path):
        self.file_path = file_path
        self.file_name = os.path.basename(file_path)
        self.file_size = os.path.getsize(file_path)
        self.result = {
            'file_name': self.file_name,
            'size': self.file_size,
            'architecture': 'Unknown',
            'firebase_urls': [],
            'api_keys': [],
            'flags': {},
            'strings': [],
            'json_structures': [],
            'functions': [],
            'hash': hashlib.md5(open(file_path, 'rb').read()).hexdigest(),
            'sections': []
        }
        self._analyze()
    
    def _analyze(self):
        try:
            with open(self.file_path, 'rb') as f:
                data = f.read()
            
            # Architecture
            if data[:4] == b'\x7fELF':
                self.result['architecture'] = 'ARM64' if data[4] == 2 else 'ARM32' if data[4] == 1 else 'Unknown'
            
            text_data = data.decode('utf-8', errors='ignore')
            
            # Firebase URLs
            self.result['firebase_urls'] = list(set(re.findall(r'https://[a-zA-Z0-9-]+\.firebaseio\.com', text_data)))
            
            # API Keys
            self.result['api_keys'] = list(set(re.findall(r'AIza[0-9A-Za-z_-]{35}', text_data)))
            
            # Flags
            for pattern in [r'verify_active\s*=\s*([0-9]+)', r'access_hours\s*=\s*([0-9]+)', r'maintenance\s*=\s*([0-9]+)']:
                matches = re.findall(pattern, text_data)
                if matches:
                    flag_name = re.search(r'([a-zA-Z_]+)\s*=', pattern)
                    if flag_name:
                        self.result['flags'][flag_name.group(1)] = matches[0]
            
            # Strings (first 100)
            self.result['strings'] = list(set(re.findall(r'[a-zA-Z0-9_\-\./\\@:]{4,}', text_data)))[:100]
            
            # JSON structures
            for match in re.findall(r'\{[^{}]*\}', text_data):
                try:
                    self.result['json_structures'].append(json.loads(match))
                except:
                    pass
            
            # Functions
            self.result['functions'] = list(set(re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*\s*\([^)]*\)\s*\{', text_data)))[:10]
            
            # Sections
            sections = re.findall(r'\.(text|data|rodata|bss|init|fini|got|plt|dynsym|dynstr|hash|gnu\.hash)', text_data)
            self.result['sections'] = list(set(sections))
            
        except Exception as e:
            self.result['error'] = str(e)
    
    def get_report(self):
        r = self.result
        report = f"""
📊 ANALYSIS REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 File: {r['file_name']}
📏 Size: {r['size']:,} bytes
🏗️ Architecture: {r['architecture']}
🔑 Hash: {r['hash'][:16]}...

📡 Firebase URLs: {len(r['firebase_urls'])}
🔑 API Keys: {len(r['api_keys'])}
🚩 Flags: {len(r['flags'])}
📄 JSON Structures: {len(r['json_structures'])}
📝 Strings: {len(r['strings'])}
🔧 Functions: {len(r['functions'])}
📂 Sections: {', '.join(r['sections']) if r['sections'] else 'None'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        return report

# ================================================================
# DUMP + RADAR 2 SCAN
# ================================================================
def generate_dump_with_radar(file_path, user_id):
    analyzer = SOAnalyzer(file_path)
    
    # Generate dump text
    lines = []
    lines.append("=" * 60)
    lines.append("VTX DEX DUMP FILE + RADAR 2 SCAN")
    lines.append("=" * 60)
    lines.append(f"File: {analyzer.file_name}")
    lines.append(f"Size: {analyzer.file_size:,} bytes")
    lines.append(f"Architecture: {analyzer.result['architecture']}")
    lines.append(f"Hash: {analyzer.result['hash']}")
    lines.append(f"Date: {fmt_ist(now_ist())}")
    lines.append("")
    
    # Extract all URLs from strings
    all_urls = []
    for s in analyzer.result['strings']:
        urls = re.findall(r'https?://[^\s"\'<>]+', s)
        all_urls.extend(urls)
    
    # RADAR 2 SCAN — check each URL
    lines.append("━" * 60)
    lines.append("📡 RADAR 2 SCAN — URL STATUS")
    lines.append("━" * 60)
    lines.append("")
    
    if all_urls:
        for url in list(set(all_urls))[:20]:
            try:
                resp = requests.get(url, timeout=5, allow_redirects=True)
                status = f"✅ {resp.status_code} OK" if resp.status_code == 200 else f"⚠️ {resp.status_code}"
                lines.append(f"  {status} → {url}")
            except:
                lines.append(f"  ❌ Failed → {url}")
        if len(set(all_urls)) > 20:
            lines.append(f"  ... and {len(set(all_urls)) - 20} more")
    else:
        lines.append("  No URLs found in strings")
    
    lines.append("")
    
    # Firebase URLs
    lines.append("━" * 60)
    lines.append("📡 FIREBASE URLs")
    lines.append("━" * 60)
    for url in analyzer.result['firebase_urls']:
        lines.append(f"  • {url}")
    if not analyzer.result['firebase_urls']:
        lines.append("  None found")
    lines.append("")
    
    # API Keys
    lines.append("━" * 60)
    lines.append("🔑 API KEYS")
    lines.append("━" * 60)
    for key in analyzer.result['api_keys']:
        lines.append(f"  • {key}")
    if not analyzer.result['api_keys']:
        lines.append("  None found")
    lines.append("")
    
    # Flags
    lines.append("━" * 60)
    lines.append("🚩 FLAGS")
    lines.append("━" * 60)
    for flag, value in analyzer.result['flags'].items():
        lines.append(f"  • {flag} = {value}")
    if not analyzer.result['flags']:
        lines.append("  None found")
    lines.append("")
    
    # JSON Structures
    lines.append("━" * 60)
    lines.append("📄 JSON STRUCTURES")
    lines.append("━" * 60)
    for js in analyzer.result['json_structures']:
        lines.append(json.dumps(js, indent=2))
    if not analyzer.result['json_structures']:
        lines.append("  None found")
    lines.append("")
    
    # Functions
    lines.append("━" * 60)
    lines.append("🔧 FUNCTIONS")
    lines.append("━" * 60)
    for f in analyzer.result['functions']:
        lines.append(f"  • {f}")
    if not analyzer.result['functions']:
        lines.append("  None found")
    lines.append("")
    
    # Strings (first 50)
    lines.append("━" * 60)
    lines.append("📝 STRINGS (First 50)")
    lines.append("━" * 60)
    for s in analyzer.result['strings'][:50]:
        lines.append(f"  {s}")
    if len(analyzer.result['strings']) > 50:
        lines.append(f"  ... and {len(analyzer.result['strings']) - 50} more")
    lines.append("")
    
    lines.append("=" * 60)
    lines.append("END OF DUMP")
    lines.append("=" * 60)
    
    return '\n'.join(lines), analyzer.result['json_structures']

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
# JSON URL ANALYSIS — FIXED
# ================================================================
def analyze_json_from_url(url):
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
/analyze    - Analyze .so file
/dump       - Generate dump.txt + Radar 2 scan
/repack     - Inject JSON back into .so
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
⛔ Banned: {'Yes' if user[6] else 'No'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    await update.message.reply_text(msg)

async def analyze(update, context):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    await update.message.reply_text("📤 Upload .so file for analysis")
    context.user_data['action'] = 'analyze'
    return WAITING_SO

async def dump(update, context):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    await update.message.reply_text("📤 Upload .so file for dump + Radar 2 scan")
    context.user_data['action'] = 'dump'
    return WAITING_SO

async def repack(update, context):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    await update.message.reply_text(
        "📤 Upload .so file + .json file\n\n"
        "I will inject the JSON back into the .so file.\n"
        "Send .so file first, then .json file."
    )
    context.user_data['action'] = 'repack'
    context.user_data['repack_step'] = 'so'
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
/analyze    - Analyze .so file
/dump       - Generate dump.txt + Radar 2 scan
/repack     - Inject JSON back into .so
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
    
    if action == 'analyze':
        await process_analyze(update, context, file_path)
    elif action == 'dump':
        await process_dump(update, context, file_path)
    elif action == 'repack':
        await process_repack(update, context, file_path)
    else:
        await update.message.reply_text("❌ Use a command first")
        os.remove(file_path)
    
    context.user_data['action'] = ''

async def process_analyze(update, context, file_path):
    user_id = update.effective_user.id
    await update.message.reply_text("🔍 Analyzing .so file...")
    
    analyzer = SOAnalyzer(file_path)
    if hasattr(analyzer.result, 'error'):
        await update.message.reply_text(f"❌ Error: {analyzer.result['error']}")
        os.remove(file_path)
        return
    
    await update.message.reply_text(analyzer.get_report())
    c.execute("UPDATE users SET total_analysis = total_analysis + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    log_action(user_id, "ANALYZE", analyzer.file_name)
    os.remove(file_path)

async def process_dump(update, context, file_path):
    user_id = update.effective_user.id
    await update.message.reply_text("📄 Generating dump.txt + Radar 2 scan...")
    
    dump_text, json_structures = generate_dump_with_radar(file_path, user_id)
    
    dump_path = os.path.join(DUMP_DIR, f"dump_{user_id}_{int(time.time())}.txt")
    with open(dump_path, 'w', encoding='utf-8') as f:
        f.write(dump_text)
    
    await update.message.reply_document(
        document=open(dump_path, 'rb'),
        filename=f"dump_radar_{int(time.time())}.txt",
        caption=f"✅ Dump + Radar 2 scan complete!\n📊 JSON Structures: {len(json_structures)}"
    )
    
    log_action(user_id, "DUMP_RADAR", os.path.basename(file_path))
    os.remove(file_path)
    os.remove(dump_path)

async def process_repack(update, context, file_path):
    user_id = update.effective_user.id
    file_ext = os.path.splitext(file_path)[1].lower()
    
    if file_ext == '.so':
        context.user_data['so_file'] = file_path
        context.user_data['repack_step'] = 'json'
        await update.message.reply_text("✅ .so file received. Now send the `.json` file.")
    elif file_ext == '.json':
        so_path = context.user_data.get('so_file')
        if so_path and os.path.exists(so_path):
            await update.message.reply_text("🔄 Injecting JSON into .so...")
            
            try:
                with open(file_path, 'r') as f:
                    json_data = json.load(f)
                
                with open(so_path, 'rb') as f:
                    so_data = f.read()
                
                json_bytes = json.dumps(json_data).encode('utf-8')
                marker = b'VTX_DEX_JSON_START'
                end_marker = b'VTX_DEX_JSON_END'
                so_data = so_data + b'\x00\x00' + marker + json_bytes + end_marker + b'\x00\x00'
                
                output_path = os.path.join(TEMP_DIR, f"repacked_{os.path.basename(so_path)}")
                with open(output_path, 'wb') as f:
                    f.write(so_data)
                
                await update.message.reply_document(
                    document=open(output_path, 'rb'),
                    filename=f"repacked_{os.path.basename(so_path)}",
                    caption="✅ JSON injected successfully!"
                )
                
                os.remove(output_path)
            except Exception as e:
                await update.message.reply_text(f"❌ Error: {str(e)}")
            
            os.remove(so_path)
            os.remove(file_path)
            context.user_data['so_file'] = None
            context.user_data['repack_step'] = 'so'
        else:
            await update.message.reply_text("❌ .so file not found. Please start again.")
            os.remove(file_path)

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
    
    requests.put(f"{FIREBASE_URL}/keys/{key}.json", json={
        'type': key_type,
        'expiry_days': expiry_days,
        'max_devices': max_devices,
        'created_by': ADMIN_ID,
        'created_at': now_ist().isoformat()
    })
    
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
    requests.patch(f"{FIREBASE_URL}/users/{user_id}.json", json={'is_banned': 1})
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
    requests.patch(f"{FIREBASE_URL}/users/{user_id}.json", json={'is_banned': 0})
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
    
    await update.message.reply_text(
        f"📊 STATS\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Users: {total}\n"
        f"✅ Active: {active}\n"
        f"🚫 Banned: {banned}\n"
        f"🔑 Unused Keys: {unused}\n"
        f"📝 Logs: {logs}\n"
        f"📊 JSON Analyses: {json_analyses}"
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
app.add_handler(CommandHandler("analyze", analyze))
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

app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
app.add_handler(CallbackQueryHandler(callback))

# ================================================================
# MAIN
# ================================================================

if __name__ == "__main__":
    print("=" * 50)
    print("🗡️ VTX DEX — CLEAN VERSION")
    print("=" * 50)
    print(f"Developer: {DEV_NAME}")
    print("✅ Bot is ONLINE!")
    print("=" * 50)
    app.run_polling()
