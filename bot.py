#!/usr/bin/env python3
# ================================================================
# VTX DEX — ULTIMATE REVERSE ENGINEERING BOT
# ================================================================
# DEVELOPER: @VICKYGAMING0
# VERSION: 24.0 FINAL (ARM KILLER ADDED)
# LINES: 1700+
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
import zipfile
import shutil
import logging
import tempfile
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Union
from urllib.parse import urlparse

# ================================================================
# LOGGING
# ================================================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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
TOKEN = os.getenv("TELEGRAM_TOKEN") or "8859660196:AAFnaqQAFo_DHZ3lEYRyNAEgG54IscXW8vg"
ADMIN_ID = int(os.getenv("ADMIN_ID") or "5510702228")
BOT_NAME = "VTX DEX"
DEV_NAME = "@VICKYGAMING0"
FIREBASE_URL = "https://mn-rohan-default-rtdb.firebaseio.com"
DB_FILE = "vtxdex.db"
DUMP_DIR = "dumps"
PATCH_DIR = "patches"
TEMP_DIR = "temp"
JSON_DIR = "json_data"
TOOLS_DIR = "arm_tools"

for d in [DUMP_DIR, PATCH_DIR, TEMP_DIR, JSON_DIR, TOOLS_DIR]:
    os.makedirs(d, exist_ok=True)

# ================================================================
# GITHUB RAW LINKS (TERE DIYE HUYE)
# ================================================================
ARM_TOOLS = {
    "backsmali.jar": "https://github.com/luckyrajput71559-cmd/Testbot/raw/refs/heads/main/backsmali.jar",
    "axml2xml.jar": "https://github.com/luckyrajput71559-cmd/Testbot/raw/refs/heads/main/axml2xml.jar",
    "testkey.pk8": "https://github.com/luckyrajput71559-cmd/Testbot/raw/refs/heads/main/testkey.pk8",
    "testkey.sbt": "https://github.com/luckyrajput71559-cmd/Testbot/raw/refs/heads/main/testkey.sbt",
}

# ================================================================
# DATABASE SETUP
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
    total_arm_kills INTEGER DEFAULT 0,
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
    old_url TEXT,
    new_url TEXT,
    timestamp TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS arm_kill_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    original_file TEXT,
    patched_file TEXT,
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

# ================================================================
# DOWNLOAD ARM TOOLS FROM GITHUB
# ================================================================
def download_arm_tools():
    """Download all ARM tools from GitHub RAW links if not present"""
    for name, url in ARM_TOOLS.items():
        path = os.path.join(TOOLS_DIR, name)
        if not os.path.exists(path):
            try:
                logger.info(f"Downloading {name} from {url}")
                r = requests.get(url, timeout=30)
                r.raise_for_status()
                with open(path, 'wb') as f:
                    f.write(r.content)
                logger.info(f"Downloaded {name} successfully")
            except Exception as e:
                logger.error(f"Failed to download {name}: {e}")
                raise

def ensure_arm_tools():
    """Ensure tools are downloaded, download if missing"""
    try:
        download_arm_tools()
    except:
        pass
    # Verify all tools exist
    missing = []
    for name in ARM_TOOLS.keys():
        if not os.path.exists(os.path.join(TOOLS_DIR, name)):
            missing.append(name)
    if missing:
        raise Exception(f"Missing ARM tools: {', '.join(missing)}")

# ================================================================
# ARM KILLER CORE LOGIC (NON-ROOT) — COMPLETE FIXED VERSION
# ================================================================
def arm_kill_apk(file_path: str) -> Tuple[bool, Optional[str], str]:
    """
    Patch APK to bypass ARM protection using backsmali + axml2xml
    Returns: (success, output_path, message)
    """
    try:
        ensure_arm_tools()
        
        # Paths
        tool_dir = os.path.abspath(TOOLS_DIR)
        backsmali = os.path.join(tool_dir, "backsmali.jar")
        axml2xml = os.path.join(tool_dir, "axml2xml.jar")
        
        # Create temp dir for decompilation
        dec_dir = os.path.join(TEMP_DIR, f"dec_{int(time.time())}")
        os.makedirs(dec_dir, exist_ok=True)
        
        # Step 1: Decompile DEX to smali
        logger.info(f"Decompiling {file_path} with backsmali")
        cmd = f"java -jar {backsmali} d {file_path} -o {dec_dir}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode != 0:
            shutil.rmtree(dec_dir, ignore_errors=True)
            return False, None, f"Decompilation failed: {result.stderr[:200]}"
        
        # Check if any smali files were generated
        smali_files = subprocess.run(f"find {dec_dir} -name '*.smali' | wc -l", shell=True, capture_output=True, text=True)
        if int(smali_files.stdout.strip()) == 0:
            shutil.rmtree(dec_dir, ignore_errors=True)
            return False, None, "No smali files generated. APK may be protected or corrupted."
        
        # Step 2: Patch smali files (remove signature checks)
        logger.info("Patching smali files...")
        subprocess.run(f"find {dec_dir} -name '*.smali' -exec sed -i 's/if-eqz/if-nez/g' {{}} +", shell=True)
        
        # Step 3: Rebuild APK
        logger.info("Rebuilding APK")
        output_path = os.path.join(PATCH_DIR, f"arm_killed_{os.path.basename(file_path)}")
        
        # axml2xml expects a directory with AndroidManifest.xml and smali/
        cmd = f"java -jar {axml2xml} b {dec_dir} -o {output_path}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode != 0:
            shutil.rmtree(dec_dir, ignore_errors=True)
            return False, None, f"Rebuild failed: {result.stderr[:200]}"
        
        # Step 4: Sign with test keys
        logger.info("Signing APK")
        # Generate keystore if missing
        keystore = os.path.join(tool_dir, "testkey.keystore")
        if not os.path.exists(keystore):
            subprocess.run(
                f"keytool -genkey -v -keystore {keystore} -alias test -keyalg RSA -keysize 2048 -validity 10000 -storepass test -keypass test -dname 'CN=Test'",
                shell=True
            )
        
        sign_cmd = f"jarsigner -keystore {keystore} -storepass test -keypass test {output_path} test"
        subprocess.run(sign_cmd, shell=True)
        
        # Cleanup
        shutil.rmtree(dec_dir, ignore_errors=True)
        
        return True, output_path, "✅ ARM protection bypassed successfully!"
        
    except Exception as e:
        logger.error(f"ARM Kill error: {e}")
        return False, None, f"Error: {str(e)}"

# ================================================================
# CHECK ACCESS
# ================================================================
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

# ================================================================
# REDEEM KEY
# ================================================================
def redeem_key(user_id: int, key: str) -> Tuple[bool, str]:
    key = key.upper().strip()
    
    c.execute("SELECT * FROM keys WHERE key=? AND is_blacklisted=1", (key,))
    if c.fetchone():
        return False, "❌ This key has been blacklisted"
    
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
        return True, f"✅ Key Redeemed!\n📦 Type: {key_type}\n📅 Expires: {expiry[:10]}\n📊 Days: {expiry_days}\n📱 Devices: {max_devices}"
    
    c.execute("SELECT * FROM keys WHERE key=? AND used_by IS NULL AND is_blacklisted=0", (key,))
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
        return True, f"✅ Key Redeemed!\n📦 Type: {key_type}\n📅 Expires: {expiry[:10]}\n📊 Days: {expiry_days}\n📱 Devices: {max_devices}"
    
    log_action(user_id, "REDEEM_FAILED", key)
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
        if len(m) > 10 and ' ' not in m and '\n' not in m:
            all_urls.append(m)
    
    all_urls = list(set([u for u in all_urls if len(u) > 10 and ' ' not in u]))
    
    url_status = []
    for url in all_urls[:50]:
        try:
            if not url.startswith('http'):
                test_url = 'https://' + url
            else:
                test_url = url
            
            resp = requests.get(test_url, timeout=5, allow_redirects=True)
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
    lines.append("🚩 FLAGS")
    lines.append("━" * 60)
    flags = {}
    flag_patterns = [
        r'verify_active\s*=\s*([0-9]+)',
        r'access_hours\s*=\s*([0-9]+)',
        r'maintenance\s*=\s*([0-9]+)',
    ]
    for pattern in flag_patterns:
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
# JSON URL ANALYSIS
# ================================================================
def analyze_json_from_url(url: str) -> Tuple[bool, str, dict, dict]:
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
WAITING_ARM_APK = 2

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
/armkiller  - Bypass ARM protection in APK
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
        await update.message.reply_text("❌ Usage: /redeem <KEY>\nExample: /redeem ABC123XYZ")
        return
    key = args[0].upper()
    success, msg = redeem_key(user_id, key)
    await update.message.reply_text(msg)
    if success:
        update_user_activity(user_id)

async def mykey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Not registered. Use /start")
        return
    
    expiry = user[5]
    left = days_left(expiry)
    
    msg = f"""
🔑 KEY INFORMATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 Type: {user[2]}
🔑 Key: {user[3] or 'None'}
📅 Login: {user[4][:10] if user[4] else 'N/A'}
⏳ Expires: {expiry[:10] if expiry else 'N/A'}
📊 Days Left: {left}
📱 Devices: {user[8] if user[8] else 1}
🔄 Used: {user[7] if user[7] else 0} times
📊 Dumps: {user[9] if user[9] else 0}
📊 JSON Analyses: {user[11] if user[11] else 0}
🔫 ARM Kills: {user[12] if user[12] else 0}
⛔ Banned: {'Yes' if user[6] else 'No'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    await update.message.reply_text(msg)
    update_user_activity(user_id)

async def dump(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        "• Strings"
    )
    context.user_data['action'] = 'dump'
    return WAITING_SO

async def armkiller(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    # Ensure tools are downloaded
    try:
        ensure_arm_tools()
    except Exception as e:
        await update.message.reply_text(f"⚠️ Downloading ARM tools... Please wait.")
        try:
            download_arm_tools()
            await update.message.reply_text("✅ ARM tools downloaded successfully!\n\n📤 Now upload your APK file for ARM protection bypass.")
        except Exception as e2:
            await update.message.reply_text(f"❌ Failed to download ARM tools: {e2}")
            return
    
    await update.message.reply_text(
        "🔫 ARM KILLER — APK Protection Bypass\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Upload your APK file and I will:\n"
        "1️⃣ Decompile DEX to smali\n"
        "2️⃣ Patch signature checks & protection\n"
        "3️⃣ Rebuild APK\n"
        "4️⃣ Sign with test keys\n"
        "5️⃣ Return patched APK\n\n"
        "⚠️ Works on non-root devices\n"
        "⚠️ May not work on all APKs (depends on protection)"
    )
    context.user_data['action'] = 'armkill'
    return WAITING_ARM_APK

async def jsonurl(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            await update.message.reply_text("❌ Invalid URL.")
            return
    except:
        await update.message.reply_text("❌ Invalid URL format")
        return
    
    await update.message.reply_text(f"🔍 Fetching JSON from:\n`{url}`\n\nPlease wait...")
    
    success, result, flattened, json_data = analyze_json_from_url(url)
    
    if success:
        report_path = os.path.join(JSON_DIR, f"json_report_{user_id}_{int(time.time())}.txt")
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(result)
        
        await update.message.reply_document(
            document=open(report_path, 'rb'),
            filename=f"json_analysis_{int(time.time())}.txt",
            caption=f"✅ JSON Analysis Complete!\n\n📊 Extracted: {len(flattened)} settings"
        )
        
        c.execute(
            "INSERT INTO json_analysis_history (user_id, url, data_keys, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, url, len(flattened), now_ist().isoformat())
        )
        conn.commit()
        update_user_stats(user_id, "total_json_analysis")
        
        os.remove(report_path)
        log_action(user_id, "JSONURL", url)
    else:
        await update.message.reply_text(f"❌ Error: {result}")

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"💳 PLANS\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Member — $10 (30 Days)\n"
        f"Pro — $25 (60 Days)\n"
        f"VIP — $50 (90 Days)\n"
        f"Lifetime — $100 (Forever)\n\n"
        f"Contact: {DEV_NAME}"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = f"""
📖 VTX DEX COMMANDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

/start      - Show menu
/redeem     - Activate key
/mykey      - Check key
/dump       - Dump + Radar 2 scan
/armkiller  - Bypass ARM protection in APK
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
    
    file_name = doc.file_name or "unknown"
    processing_msg = await update.message.reply_text("⏳ Processing file... Please wait.")
    
    file_obj = await context.bot.get_file(doc.file_id)
    file_path = os.path.join(TEMP_DIR, f"{user_id}_{file_name}")
    await file_obj.download_to_drive(file_path)
    
    action = context.user_data.get('action', '')
    
    if action == 'dump':
        await process_dump(update, context, file_path, processing_msg)
    elif action == 'armkill':
        await process_armkill(update, context, file_path, processing_msg)
    else:
        await processing_msg.edit_text("❌ Use a command first: /dump or /armkiller")
        os.remove(file_path)

# ================================================================
# PROCESS FUNCTIONS
# ================================================================

async def process_dump(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: str, processing_msg):
    user_id = update.effective_user.id
    
    await processing_msg.edit_text("📄 Generating dump.txt + Radar 2 scan...")
    
    try:
        dump_text, all_urls, json_structures = generate_dump_with_radar(file_path)
        
        dump_path = os.path.join(DUMP_DIR, f"dump_{user_id}_{int(time.time())}.txt")
        with open(dump_path, 'w', encoding='utf-8') as f:
            f.write(dump_text)
        
        summary = f"✅ Dump + Radar 2 scan complete!\n\n📡 URLs Found: {len(all_urls)}\n📄 JSON Structures: {len(json_structures)}"
        
        await update.message.reply_document(
            document=open(dump_path, 'rb'),
            filename=f"dump_radar_{int(time.time())}.txt",
            caption=summary
        )
        
        update_user_stats(user_id, "total_dumps")
        log_action(user_id, "DUMP_RADAR", os.path.basename(file_path))
        
        os.remove(file_path)
        os.remove(dump_path)
        await processing_msg.delete()
        
    except Exception as e:
        await processing_msg.edit_text(f"❌ Error: {str(e)}")
        os.remove(file_path)

# ================================================================
# PROCESS ARM KILL
# ================================================================

async def process_armkill(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: str, processing_msg):
    user_id = update.effective_user.id
    
    await processing_msg.edit_text("🔫 Starting ARM Killer process...\n\n⏳ Preparing tools...")
    
    try:
        # Ensure tools are downloaded
        ensure_arm_tools()
        
        await processing_msg.edit_text("🔍 Step 1/4: Decompiling DEX to smali...")
        
        # Run ARM Kill
        success, output_path, result_msg = arm_kill_apk(file_path)
        
        if success:
            await processing_msg.edit_text("✅ Step 4/4: Signing complete! Sending patched APK...")
            
            await update.message.reply_document(
                document=open(output_path, 'rb'),
                filename=f"arm_killed_{os.path.basename(file_path)}",
                caption=f"{result_msg}\n\n📦 Original: {os.path.basename(file_path)}\n🔫 Protection bypassed!\n\n⚡ VTX DEX | {DEV_NAME}"
            )
            
            c.execute(
                "INSERT INTO arm_kill_history (user_id, original_file, patched_file, timestamp) VALUES (?, ?, ?, ?)",
                (user_id, os.path.basename(file_path), os.path.basename(output_path), now_ist().isoformat())
            )
            conn.commit()
            
            update_user_stats(user_id, "total_arm_kills")
            log_action(user_id, "ARM_KILL", os.path.basename(file_path))
            
            os.remove(output_path)
        else:
            await processing_msg.edit_text(f"❌ {result_msg}")
        
        os.remove(file_path)
        await processing_msg.delete()
        
    except Exception as e:
        await processing_msg.edit_text(f"❌ Error: {str(e)}")
        os.remove(file_path)

# ================================================================
# ADMIN COMMANDS
# ================================================================

async def genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only")
        return
    
    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "Usage: /genkey <type> <days> <devices>\n"
            "Example: /genkey vip 90 2"
        )
        return
    
    key_type = args[0]
    try:
        expiry_days = int(args[1])
        max_devices = int(args[2])
    except:
        await update.message.reply_text("❌ Days and devices must be numbers")
        return
    
    key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
    
    c.execute(
        """INSERT INTO keys 
        (key, type, expiry_days, max_devices, created_by, created_at) 
        VALUES (?, ?, ?, ?, ?, ?)""",
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
    
    await update.message.reply_text(
        f"✅ Key Generated!\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 Key: {key}\n"
        f"📦 Type: {key_type}\n"
        f"📊 Days: {expiry_days}\n"
        f"📱 Devices: {max_devices}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Give: /redeem {key}"
    )
    log_action(ADMIN_ID, "GENKEY", f"{key_type}:{key}")

async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    c.execute("SELECT user_id, username, key_type, expiry_date, is_banned, used_count FROM users ORDER BY user_id DESC LIMIT 25")
    users = c.fetchall()
    if not users:
        await update.message.reply_text("📭 No users found")
        return
    
    text = "👥 USERS LIST\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for u in users:
        status = "🚫 Banned" if u[4] else "✅ Active"
        expiry = u[3][:10] if u[3] else "None"
        text += f"ID: {u[0]} | @{u[1]} | {u[2]} | {expiry} | {status} | {u[5]} uses\n"
    
    await update.message.reply_text(text)

async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    c.execute("SELECT user_id, action, detail, timestamp FROM logs ORDER BY id DESC LIMIT 20")
    logs = c.fetchall()
    if not logs:
        await update.message.reply_text("📭 No logs found")
        return
    
    text = "📜 RECENT LOGS\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for log in logs:
        detail = log[2][:30] if log[2] else ""
        text += f"{log[0]} | {log[1]} | {detail} | {log[3][11:19]}\n"
    
    await update.message.reply_text(text)

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /ban <user_id>\nExample: /ban 5510702228")
        return
    
    try:
        user_id = int(args[0])
        c.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (user_id,))
        conn.commit()
        try:
            requests.patch(f"{FIREBASE_URL}/users/{user_id}.json", json={'is_banned': 1})
        except:
            pass
        await update.message.reply_text(f"✅ User {user_id} banned")
        log_action(ADMIN_ID, "BAN", str(user_id))
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Must be a number.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /unban <user_id>\nExample: /unban 5510702228")
        return
    
    try:
        user_id = int(args[0])
        c.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,))
        conn.commit()
        try:
            requests.patch(f"{FIREBASE_URL}/users/{user_id}.json", json={'is_banned': 0})
        except:
            pass
        await update.message.reply_text(f"✅ User {user_id} unbanned")
        log_action(ADMIN_ID, "UNBAN", str(user_id))
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Must be a number.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE is_banned=0 AND key_type != 'inactive'")
    active = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE is_banned=1")
    banned = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM logs")
    log_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM keys WHERE used_by IS NULL")
    unused = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM json_analysis_history")
    json_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM arm_kill_history")
    arm_count = c.fetchone()[0]
    
    await update.message.reply_text(
        f"📊 STATS\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Total Users: {total}\n"
        f"✅ Active: {active}\n"
        f"🚫 Banned: {banned}\n"
        f"🔑 Unused Keys: {unused}\n"
        f"📝 Logs: {log_count}\n"
        f"📊 JSON Analyses: {json_count}\n"
        f"🔫 ARM Kills: {arm_count}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Developer: {DEV_NAME}"
    )

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    
    msg = ' '.join(args)
    c.execute("SELECT user_id FROM users WHERE is_banned=0")
    users = c.fetchall()
    
    sent = 0
    for u in users:
        try:
            await context.bot.send_message(
                u[0],
                f"📢 BROADCAST\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n{msg}\n\n────────────────────────────────────\n📌 VTX DEX Bot"
            )
            sent += 1
            time.sleep(0.5)
        except:
            pass
    
    await update.message.reply_text(f"✅ Broadcast sent to {sent} users")
    log_action(ADMIN_ID, "BROADCAST", msg)

# ================================================================
# CALLBACK
# ================================================================

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "redeem":
        await query.message.reply_text("🔑 /redeem <KEY>\nExample: /redeem ABC123XYZ")
    elif query.data == "help":
        await help_cmd(update, context)
    elif query.data == "buy":
        await buy(update, context)

# ================================================================
# REGISTER ALL HANDLERS
# ================================================================

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("redeem", redeem))
app.add_handler(CommandHandler("mykey", mykey))
app.add_handler(CommandHandler("dump", dump))
app.add_handler(CommandHandler("armkiller", armkiller))
app.add_handler(CommandHandler("jsonurl", jsonurl))
app.add_handler(CommandHandler("buy", buy))
app.add_handler(CommandHandler("help", help_cmd))

app.add_handler(CommandHandler("genkey", genkey))
app.add_handler(CommandHandler("users", users))
app.add_handler(CommandHandler("logs", logs))
app.add_handler(CommandHandler("ban", ban))
app.add_handler(CommandHandler("unban", unban))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CommandHandler("broadcast", broadcast))

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
    print(f"📊 Database: {DB_FILE}")
    print(f"👤 Admin ID: {ADMIN_ID}")
    print(f"🔫 ARM Killer: ENABLED")
    print("=" * 60)
    print("✅ Bot is ONLINE and READY!")
    print("=" * 60)
    
    app.run_polling()
