#!/usr/bin/env python3
# ============================================
# VTX DEX — Ultimate Reverse Engineering Bot
# Developer: @VICKYGAMING0 | SOKY-DEX
# Version: 3.0 FINAL
# ============================================

import os
import sys
import re
import json
import sqlite3
import hashlib
import random
import string
import subprocess
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

# Telegram imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# For timezone
try:
    import pytz
    IST = pytz.timezone('Asia/Kolkata')
except ImportError:
    # Fallback if pytz not installed
    from datetime import timezone
    IST = timezone(timedelta(hours=5, minutes=30))

# ============================================
# CONFIGURATION
# ============================================
TOKEN = os.getenv("TELEGRAM_TOKEN") or "8256413457:AAGurkdBHnvK7h3CZPx0lleqxEZuGnKm7dA"
ADMIN_ID = 5510702228  # CHANGE TO YOUR TELEGRAM ID
BOT_NAME = "@ALLINONETOOLV1BOT"
DEV_NAME = "@VICKYGAMING0 | SOKY-DEX"
DB_FILE = "vtxdex.db"
DUMP_DIR = "dumps"
PATCH_DIR = "patches"

# Create directories
os.makedirs(DUMP_DIR, exist_ok=True)
os.makedirs(PATCH_DIR, exist_ok=True)

# ============================================
# DATABASE SETUP
# ============================================
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()

# Users table
c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    key_type TEXT DEFAULT 'member',
    key_value TEXT,
    login_date TEXT,
    expiry_date TEXT,
    is_banned INTEGER DEFAULT 0,
    used_count INTEGER DEFAULT 0,
    last_login TEXT
)''')

# Keys table
c.execute('''CREATE TABLE IF NOT EXISTS keys (
    key TEXT PRIMARY KEY,
    type TEXT,
    created_by INTEGER,
    created_at TEXT,
    used_by INTEGER,
    used_at TEXT
)''')

# Logs table
c.execute('''CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT,
    detail TEXT,
    timestamp TEXT
)''')

# Patches table
c.execute('''CREATE TABLE IF NOT EXISTS patches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    file_name TEXT,
    original_hash TEXT,
    patched_hash TEXT,
    changes TEXT,
    timestamp TEXT
)''')

# Dumps table
c.execute('''CREATE TABLE IF NOT EXISTS dumps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    file_name TEXT,
    dump_text TEXT,
    timestamp TEXT
)''')

conn.commit()

# ============================================
# TIME HELPERS (IST)
# ============================================
def get_ist_now():
    """Get current time in IST"""
    try:
        return datetime.now(IST)
    except:
        return datetime.now()

def format_ist(dt):
    """Format datetime to IST string"""
    return dt.strftime("%d-%m-%Y %H:%M IST")

def get_expiry(key_type: str) -> str:
    """Calculate expiry date based on key type"""
    days = {
        'member': 30,
        'pro': 60,
        'vip': 90,
        'lifetime': 3650
    }.get(key_type, 30)
    expiry = get_ist_now() + timedelta(days=days)
    return expiry.isoformat()

# ============================================
# DATABASE FUNCTIONS
# ============================================
def log_action(user_id: int, action: str, detail: str = ""):
    """Log user action"""
    c.execute(
        "INSERT INTO logs (user_id, action, detail, timestamp) VALUES (?, ?, ?, ?)",
        (user_id, action, detail, get_ist_now().isoformat())
    )
    conn.commit()

def get_user(user_id: int):
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    return c.fetchone()

def create_user(user_id: int, username: str):
    """Create new user with trial access (but no trial)"""
    c.execute(
        "INSERT INTO users (user_id, username, key_type, key_value, login_date, expiry_date) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, username, 'inactive', None, get_ist_now().isoformat(), None)
    )
    conn.commit()
    log_action(user_id, "REGISTER", "inactive")
    return True

def update_user_key(user_id: int, key_type: str, key_value: str):
    """Update user's key and expiry"""
    expiry = get_expiry(key_type)
    c.execute(
        "UPDATE users SET key_type=?, key_value=?, expiry_date=?, login_date=? WHERE user_id=?",
        (key_type, key_value, expiry, get_ist_now().isoformat(), user_id)
    )
    conn.commit()
    log_action(user_id, "KEY_UPDATE", f"{key_type}:{key_value}")

def check_access(user_id: int) -> Tuple[bool, str]:
    """Check if user has valid access"""
    user = get_user(user_id)
    if not user:
        return False, "❌ Not registered. Use /start"
    if user[6] == 1:
        return False, "⛔ You are banned"
    if user[2] == 'inactive' or user[2] is None:
        return False, "🔑 No active key. Please /redeem a key"
    if user[5]:
        expiry = datetime.fromisoformat(user[5])
        if get_ist_now() > expiry:
            return False, "⏳ Key expired. Please /redeem a new key"
    return True, "✅ Access granted"

def generate_key(key_type: str, admin_id: int) -> str:
    """Generate a unique key"""
    key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
    c.execute(
        "INSERT INTO keys (key, type, created_by, created_at) VALUES (?, ?, ?, ?)",
        (key, key_type, admin_id, get_ist_now().isoformat())
    )
    conn.commit()
    return key

def redeem_key(user_id: int, key: str) -> Tuple[bool, str]:
    """Redeem a key for a user"""
    c.execute("SELECT * FROM keys WHERE key=? AND used_by IS NULL", (key,))
    key_data = c.fetchone()
    if not key_data:
        return False, "❌ Invalid or already used key"
    
    key_type = key_data[1]
    expiry = get_expiry(key_type)
    
    c.execute(
        "UPDATE users SET key_type=?, key_value=?, expiry_date=?, login_date=? WHERE user_id=?",
        (key_type, key, expiry, get_ist_now().isoformat(), user_id)
    )
    c.execute(
        "UPDATE keys SET used_by=?, used_at=? WHERE key=?",
        (user_id, get_ist_now().isoformat(), key)
    )
    conn.commit()
    log_action(user_id, "REDEEM", f"{key_type}:{key}")
    return True, f"✅ Key redeemed! Type: {key_type}\nExpires: {format_ist(datetime.fromisoformat(expiry))}"

# ============================================
# .SO ANALYSIS ENGINE
# ============================================
def analyze_so_file(file_path: str) -> Dict[str, Any]:
    """Analyze .so file and extract all data"""
    result = {
        "file_name": os.path.basename(file_path),
        "size": os.path.getsize(file_path),
        "firebase_urls": [],
        "api_keys": [],
        "flags": {},
        "strings": [],
        "json_structures": [],
        "offsets": {},
        "architecture": "Unknown"
    }
    
    try:
        with open(file_path, 'rb') as f:
            data = f.read()
        
        # Detect architecture
        if data[:4] == b'\x7fELF':
            ei_class = data[4]
            if ei_class == 1:
                result["architecture"] = "ARM32"
            elif ei_class == 2:
                result["architecture"] = "ARM64"
        
        # Decode as string (ignore errors)
        text_data = data.decode('utf-8', errors='ignore')
        
        # Extract Firebase URLs
        firebase_pattern = r'https://[a-zA-Z0-9-]+\.firebaseio\.com'
        result["firebase_urls"] = list(set(re.findall(firebase_pattern, text_data)))
        
        # Extract API Keys (Google API key pattern)
        api_key_pattern = r'AIza[0-9A-Za-z_-]{35}'
        result["api_keys"] = list(set(re.findall(api_key_pattern, text_data)))
        
        # Extract flags
        flag_patterns = [
            r'verify_active\s*=\s*([0-9]+)',
            r'access_hours\s*=\s*([0-9]+)',
            r'maintenance\s*=\s*([0-9]+)',
            r'debug_mode\s*=\s*([0-9]+)',
            r'is_verified\s*=\s*([0-9]+)',
            r'is_premium\s*=\s*([0-9]+)',
            r'is_pro\s*=\s*([0-9]+)',
            r'enable_logging\s*=\s*([0-9]+)'
        ]
        for pattern in flag_patterns:
            matches = re.findall(pattern, text_data)
            if matches:
                flag_name = pattern.split('\\s*=')[0].replace(r'\s*', '').replace(r'[0-9]+', '')
                result["flags"][flag_name] = matches[0]
        
        # Extract strings (minimum length 4)
        string_pattern = r'[a-zA-Z0-9_\-\./\\@:]{4,}'
        result["strings"] = list(set(re.findall(string_pattern, text_data)))
        
        # Extract JSON structures
        json_pattern = r'\{[^{}]*\}'
        json_matches = re.findall(json_pattern, text_data)
        for jm in json_matches:
            try:
                json_data = json.loads(jm)
                result["json_structures"].append(json_data)
            except:
                pass
        
        # Find offsets for key strings
        for url in result["firebase_urls"]:
            offset = text_data.find(url)
            if offset != -1:
                result["offsets"][url] = hex(offset)
        
        for key in result["api_keys"]:
            offset = text_data.find(key)
            if offset != -1:
                result["offsets"][key] = hex(offset)
        
    except Exception as e:
        result["error"] = str(e)
    
    return result

def generate_dump_txt(analysis: Dict[str, Any], user_id: int) -> str:
    """Generate dump.txt file from analysis"""
    lines = []
    lines.append("=" * 50)
    lines.append("VTX DEX DUMP FILE")
    lines.append("=" * 50)
    lines.append(f"File: {analysis.get('file_name', 'Unknown')}")
    lines.append(f"Size: {analysis.get('size', 0)} bytes")
    lines.append(f"Architecture: {analysis.get('architecture', 'Unknown')}")
    lines.append(f"Analysis Date: {format_ist(get_ist_now())}")
    lines.append("")
    
    # Firebase URLs
    lines.append("--- FIREBASE URLs ---")
    if analysis.get("firebase_urls"):
        for url in analysis["firebase_urls"]:
            offset = analysis["offsets"].get(url, "Unknown")
            lines.append(f"{url} (offset: {offset})")
    else:
        lines.append("None found")
    lines.append("")
    
    # API Keys
    lines.append("--- API KEYS ---")
    if analysis.get("api_keys"):
        for key in analysis["api_keys"]:
            offset = analysis["offsets"].get(key, "Unknown")
            lines.append(f"{key} (offset: {offset})")
    else:
        lines.append("None found")
    lines.append("")
    
    # Flags
    lines.append("--- FLAGS ---")
    if analysis.get("flags"):
        for flag, value in analysis["flags"].items():
            lines.append(f"{flag} = {value}")
    else:
        lines.append("None found")
    lines.append("")
    
    # JSON Structures
    lines.append("--- JSON STRUCTURES ---")
    if analysis.get("json_structures"):
        for js in analysis["json_structures"]:
            lines.append(json.dumps(js, indent=2))
    else:
        lines.append("None found")
    lines.append("")
    
    # All Strings
    lines.append("--- ALL STRINGS ---")
    if analysis.get("strings"):
        for s in analysis["strings"][:100]:  # Limit to 100
            lines.append(s)
        if len(analysis["strings"]) > 100:
            lines.append(f"... and {len(analysis['strings']) - 100} more")
    else:
        lines.append("None found")
    lines.append("")
    
    lines.append("=" * 50)
    lines.append("END OF DUMP")
    lines.append("=" * 50)
    
    return '\n'.join(lines)

def patch_so_file(file_path: str, changes: Dict[str, str]) -> Tuple[bool, str, str]:
    """Patch .so file with changes"""
    try:
        with open(file_path, 'rb') as f:
            data = f.read()
        
        text_data = data.decode('utf-8', errors='ignore')
        original = text_data
        
        # Apply changes
        if 'url_patch' in changes:
            old_url = changes['url_patch']['old']
            new_url = changes['url_patch']['new']
            text_data = text_data.replace(old_url, new_url)
        
        if 'api_key_patch' in changes:
            old_key = changes['api_key_patch']['old']
            new_key = changes['api_key_patch']['new']
            text_data = text_data.replace(old_key, new_key)
        
        if 'flag_patch' in changes:
            for flag, value in changes['flag_patch'].items():
                pattern = rf'{flag}\s*=\s*[0-9]+'
                replacement = f'{flag} = {value}'
                text_data = re.sub(pattern, replacement, text_data)
        
        if 'string_patch' in changes:
            for old_str, new_str in changes['string_patch'].items():
                text_data = text_data.replace(old_str, new_str)
        
        # Write patched file
        patched_data = text_data.encode('utf-8', errors='ignore')
        patched_path = os.path.join(PATCH_DIR, f"patched_{os.path.basename(file_path)}")
        with open(patched_path, 'wb') as f:
            f.write(patched_data)
        
        return True, patched_path, "Patch applied successfully"
    
    except Exception as e:
        return False, "", f"Error: {str(e)}"

# ============================================
# ROOT DETECTION BYPASS GENERATOR
# ============================================
def generate_root_bypass_script() -> str:
    """Generate Frida script to bypass root detection"""
    return '''// VTX DEX - Root Detection Bypass
Java.perform(function() {
    console.log("[*] Loading root bypass...");
    
    // Bypass common root detection methods
    var RootDetection = Java.use("com.example.rootdetection.RootDetection");
    if (RootDetection) {
        RootDetection.isDeviceRooted.implementation = function() {
            console.log("[*] isDeviceRooted called - returning false");
            return false;
        };
        RootDetection.isRooted.implementation = function() {
            console.log("[*] isRooted called - returning false");
            return false;
        };
    }
    
    // Bypass SafetyNet
    var SafetyNet = Java.use("com.google.android.gms.safetynet.SafetyNet");
    if (SafetyNet) {
        SafetyNet.isDeviceRooted.implementation = function() {
            console.log("[*] SafetyNet.isDeviceRooted called - returning false");
            return false;
        };
    }
    
    // Bypass Magisk detection
    var MagiskDetector = Java.use("com.topjohnwu.magisk.detector");
    if (MagiskDetector) {
        MagiskDetector.isMagiskInstalled.implementation = function() {
            console.log("[*] isMagiskInstalled called - returning false");
            return false;
        };
    }
    
    console.log("[*] Root bypass loaded successfully!");
});'''

# ============================================
# ANTI-DEBUG BYPASS GENERATOR
# ============================================
def generate_antidebug_script() -> str:
    """Generate Frida script to bypass anti-debug"""
    return '''// VTX DEX - Anti-Debug Bypass
Java.perform(function() {
    console.log("[*] Loading anti-debug bypass...");
    
    // Bypass ptrace
    var ptrace = Module.findExportByName("libc.so", "ptrace");
    if (ptrace) {
        Interceptor.replace(ptrace, new NativeCallback(function(request, pid, addr, data) {
            console.log("[*] ptrace called - returning 0");
            return 0;
        }, 'int', ['int', 'int', 'pointer', 'pointer']));
    }
    
    // Bypass /proc/self/status
    var FileReader = Java.use("java.io.FileReader");
    FileReader.init.implementation = function(file) {
        var path = file.getPath();
        if (path.indexOf("/proc/self/status") !== -1) {
            console.log("[*] Blocked reading /proc/self/status");
            return null;
        }
        return this.init(file);
    };
    
    // Bypass TracerPid check
    var BufferedReader = Java.use("java.io.BufferedReader");
    BufferedReader.readLine.implementation = function() {
        var line = this.readLine();
        if (line && line.indexOf("TracerPid") !== -1) {
            console.log("[*] Modified TracerPid to 0");
            return "TracerPid:\\t0";
        }
        return line;
    };
    
    console.log("[*] Anti-debug bypass loaded!");
});'''

# ============================================
# JSON TO .SO REPACK SYSTEM
# ============================================
def json_to_so_repack(json_file_path: str, so_file_path: str) -> Tuple[bool, str, str]:
    """Inject JSON data into .so file"""
    try:
        with open(json_file_path, 'r') as f:
            json_data = json.load(f)
        
        with open(so_file_path, 'rb') as f:
            so_data = f.read()
        
        # Convert JSON to string
        json_str = json.dumps(json_data)
        json_bytes = json_str.encode('utf-8')
        
        # Find a place to inject (search for null bytes or padding)
        # Simple approach: append to end of file
        so_data = so_data + b'\x00\x00' + json_bytes + b'\x00'
        
        # Add marker to find JSON later
        marker = b'VTX_DEX_JSON_START'
        so_data = so_data + marker + json_bytes + b'VTX_DEX_JSON_END'
        
        output_path = os.path.join(PATCH_DIR, f"repacked_{os.path.basename(so_file_path)}")
        with open(output_path, 'wb') as f:
            f.write(so_data)
        
        return True, output_path, "JSON injected successfully"
    
    except Exception as e:
        return False, "", f"Error: {str(e)}"

def extract_json_from_so(so_file_path: str) -> Tuple[bool, Any, str]:
    """Extract JSON data from .so file"""
    try:
        with open(so_file_path, 'rb') as f:
            data = f.read()
        
        text_data = data.decode('utf-8', errors='ignore')
        
        # Find VTX_DEX_JSON markers
        start_marker = 'VTX_DEX_JSON_START'
        end_marker = 'VTX_DEX_JSON_END'
        
        if start_marker in text_data and end_marker in text_data:
            start = text_data.index(start_marker) + len(start_marker)
            end = text_data.index(end_marker)
            json_str = text_data[start:end]
            json_data = json.loads(json_str)
            return True, json_data, "JSON extracted successfully"
        
        # Try to find any JSON structure
        json_pattern = r'\{[^{}]*\}'
        matches = re.findall(json_pattern, text_data)
        for match in matches:
            try:
                json_data = json.loads(match)
                return True, json_data, "JSON structure found"
            except:
                pass
        
        return False, None, "No JSON data found"
    
    except Exception as e:
        return False, None, f"Error: {str(e)}"

# ============================================
# BOT COMMANDS
# ============================================
app = Application.builder().token(TOKEN).build()

# ---- START ----
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
        [InlineKeyboardButton("📄 Help", callback_data="help")]
    ]
    
    # Check if user has valid key
    has_key = user[2] and user[2] != 'inactive'
    key_type = user[2] if has_key else "None"
    expiry = user[5]
    days_left = "N/A"
    if expiry:
        try:
            exp_date = datetime.fromisoformat(expiry)
            days_left = (exp_date - get_ist_now()).days
            if days_left < 0:
                days_left = "Expired"
            else:
                days_left = f"{days_left} days"
        except:
            days_left = "N/A"
    
    status = "✅ Active" if has_key and days_left != "Expired" else "❌ Inactive"
    
    await update.message.reply_text(
        f"🗡️ **{BOT_NAME}**\n"
        f"🔥 Developer: {DEV_NAME}\n\n"
        f"👤 User: @{username}\n"
        f"🔑 Key Type: `{key_type}`\n"
        f"📅 Login Date: {format_ist(get_ist_now())}\n"
        f"⏳ Expires: `{expiry[:10] if expiry else 'None'}`\n"
        f"📊 Days Left: `{days_left}`\n"
        f"📈 Status: {status}\n"
        f"🔄 Used: `{user[7] if user[7] else 0}` times\n\n"
        f"**Commands:**\n"
        f"/start - Show this menu\n"
        f"/redeem <key> - Activate key\n"
        f"/mykey - Check key status\n"
        f"/analyze - Analyze .so file\n"
        f"/patch - Patch .so file\n"
        f"/dump - Get dump.txt of analysis\n"
        f"/json - Extract JSON from .so\n"
        f"/repack - Inject JSON into .so\n"
        f"/rootbypass - Generate root bypass script\n"
        f"/antidebug - Generate anti-debug script\n"
        f"/frida <func> - Generate Frida hook\n"
        f"/help - Show all commands",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    log_action(user_id, "START")

# ---- REDEEM ----
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

# ---- MYKEY ----
async def mykey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Not registered. Use /start")
        return
    
    expiry = user[5]
    days_left = "N/A"
    if expiry:
        try:
            exp_date = datetime.fromisoformat(expiry)
            days_left = (exp_date - get_ist_now()).days
            if days_left < 0:
                days_left = "Expired"
            else:
                days_left = f"{days_left} days"
        except:
            days_left = "N/A"
    
    await update.message.reply_text(
        f"🔑 **Your Key Info**\n\n"
        f"Type: `{user[2]}`\n"
        f"Key: `{user[3] or 'None'}`\n"
        f"Login: `{user[4][:10] if user[4] else 'N/A'}`\n"
        f"Expires: `{expiry[:10] if expiry else 'N/A'}`\n"
        f"Days Left: `{days_left}`\n"
        f"Used: `{user[7] if user[7] else 0}` times\n"
        f"Banned: `{'Yes' if user[6] else 'No'}`"
    )

# ---- ANALYZE ----
async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    await update.message.reply_text(
        "📤 Please upload the `.so` file you want to analyze.\n"
        "Send the file as a document.\n\n"
        "⚠️ Supported: .so files only"
    )
    context.user_data['action'] = 'analyze'

# ---- PATCH ----
async def patch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Usage: /patch <old_url> <new_url>\n"
            "Example: /patch https://old.firebaseio.com https://new.firebaseio.com\n\n"
            "Or send .so file and I'll help patch it."
        )
        return
    
    old_url = args[0]
    new_url = args[1]
    context.user_data['patch_data'] = {
        'type': 'url',
        'old': old_url,
        'new': new_url
    }
    await update.message.reply_text(
        f"📤 Please upload the `.so` file to patch.\n"
        f"Changing: `{old_url}` → `{new_url}`"
    )
    context.user_data['action'] = 'patch'

# ---- DUMP ----
async def dump(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    await update.message.reply_text(
        "📤 Please upload the `.so` file to generate dump.txt.\n"
        "The dump will contain all strings, URLs, API keys, and flags."
    )
    context.user_data['action'] = 'dump'

# ---- JSON ----
async def json_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    await update.message.reply_text(
        "📤 Please upload the `.so` file to extract JSON data.\n"
        "I will find and extract any JSON structures inside."
    )
    context.user_data['action'] = 'json'

# ---- REPACK ----
async def repack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    await update.message.reply_text(
        "📤 Please upload the `.so` file and a `.json` file.\n"
        "Send the .so file first, then the .json file.\n"
        "I will inject the JSON into the .so file."
    )
    context.user_data['action'] = 'repack_so'

# ---- ROOTBYPASS ----
async def rootbypass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    script = generate_root_bypass_script()
    await update.message.reply_document(
        document=script.encode(),
        file_name="root_bypass.js",
        caption="🔓 **Root Detection Bypass Script**\n\n"
                "Inject with: `frida -U -f com.example.app -l root_bypass.js`"
    )
    log_action(user_id, "ROOTBYPASS")

# ---- ANTIDEBUG ----
async def antidebug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    script = generate_antidebug_script()
    await update.message.reply_document(
        document=script.encode(),
        file_name="antidebug.js",
        caption="🛡️ **Anti-Debug Bypass Script**\n\n"
                "Inject with: `frida -U -f com.example.app -l antidebug.js`"
    )
    log_action(user_id, "ANTIDEBUG")

# ---- FRIDA ----
async def frida_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Usage: /frida <function_name>\n"
            "Example: /frida verify_active\n\n"
            "Generates Frida hook for the specified function."
        )
        return
    
    func_name = args[0]
    script = f'''// VTX DEX - Frida Hook for {func_name}
Java.perform(function() {{
    console.log("[*] Hooking {func_name}...");
    
    // Try to find the function in common classes
    var classes = [
        "com.example.app.MainActivity",
        "com.example.app.Config",
        "com.example.app.FlagManager",
        "com.example.app.AuthManager"
    ];
    
    for (var i = 0; i < classes.length; i++) {{
        try {{
            var target = Java.use(classes[i]);
            if (target && target.{func_name}) {{
                target.{func_name}.implementation = function() {{
                    console.log("[*] {func_name} called");
                    // Modify return value
                    return 1;
                }};
                console.log("[+] Hooked {func_name} in " + classes[i]);
                break;
            }}
        }} catch(e) {{
            // Class not found
        }}
    }}
}});'''
    
    await update.message.reply_document(
        document=script.encode(),
        file_name=f"hook_{func_name}.js",
        caption=f"🔫 **Frida Hook for `{func_name}`**\n\n"
                f"Inject with: `frida -U -f com.example.app -l hook_{func_name}.js`"
    )
    log_action(user_id, "FRIDA", func_name)

# ---- HELP ----
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📖 **{BOT_NAME} Commands**\n\n"
        f"🔑 **Authentication**\n"
        f"/start - Show menu\n"
        f"/redeem <key> - Activate key\n"
        f"/mykey - Check key status\n\n"
        
        f"🔧 **Analysis**\n"
        f"/analyze - Analyze .so file\n"
        f"/dump - Generate dump.txt\n"
        f"/json - Extract JSON from .so\n"
        f"/repack - Inject JSON into .so\n\n"
        
        f"🛡️ **Bypass**\n"
        f"/rootbypass - Generate root bypass\n"
        f"/antidebug - Generate anti-debug\n"
        f"/frida <func> - Generate Frida hook\n\n"
        
        f"📊 **Info**\n"
        f"/help - Show this help\n"
        f"/buy - Subscription info\n\n"
        
        f"🔥 **Developer:** {DEV_NAME}"
    )

# ---- BUY ----
async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"💳 **Subscription Plans**\n\n"
        f"🔥 **Member** — $10 (30 Days)\n"
        f"🔥 **Pro Member** — $25 (60 Days)\n"
        f"🔥 **VIP Member** — $50 (90 Days)\n"
        f"🔥 **Lifetime** — $100 (Forever)\n\n"
        f"Contact {DEV_NAME} to purchase.\n"
        f"Or use /redeem if you have a key."
    )

# ============================================
# FILE HANDLER
# ============================================
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    document = update.message.document
    if not document:
        return
    
    file_name = document.file_name or "unknown"
    file_ext = os.path.splitext(file_name)[1].lower()
    
    # Download file
    file_obj = await context.bot.get_file(document.file_id)
    file_path = os.path.join(DUMP_DIR, f"{user_id}_{file_name}")
    await file_obj.download_to_drive(file_path)
    
    action = context.user_data.get('action', '')
    
    if action == 'analyze':
        await process_analyze(update, context, file_path)
    elif action == 'patch':
        await process_patch(update, context, file_path)
    elif action == 'dump':
        await process_dump(update, context, file_path)
    elif action == 'json':
        await process_json(update, context, file_path)
    elif action == 'repack_so':
        # Check if we have a JSON file already
        if 'json_file' in context.user_data:
            json_file = context.user_data['json_file']
            await process_repack(update, context, file_path, json_file)
            del context.user_data['json_file']
        else:
            context.user_data['so_file'] = file_path
            await update.message.reply_text(
                "✅ .so file received. Now send the `.json` file to inject."
            )
    else:
        await update.message.reply_text(
            "⚠️ Use a command first:\n"
            "/analyze, /patch, /dump, /json, /repack"
        )
        os.remove(file_path)

async def process_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: str):
    user_id = update.effective_user.id
    await update.message.reply_text("🔍 Analyzing .so file... This may take a moment.")
    
    analysis = analyze_so_file(file_path)
    if "error" in analysis:
        await update.message.reply_text(f"❌ Error: {analysis['error']}")
        os.remove(file_path)
        return
    
    # Generate report
    report = f"📊 **Analysis Report**\n\n"
    report += f"📁 File: `{analysis['file_name']}`\n"
    report += f"📏 Size: {analysis['size']} bytes\n"
    report += f"🏗️ Architecture: {analysis['architecture']}\n\n"
    
    report += f"📡 **Firebase URLs:**\n"
    if analysis['firebase_urls']:
        for url in analysis['firebase_urls'][:5]:
            offset = analysis['offsets'].get(url, 'Unknown')
            report += f"• `{url}` (offset: {offset})\n"
    else:
        report += "• None found\n"
    report += "\n"
    
    report += f"🔑 **API Keys:**\n"
    if analysis['api_keys']:
        for key in analysis['api_keys'][:5]:
            offset = analysis['offsets'].get(key, 'Unknown')
            report += f"• `{key}` (offset: {offset})\n"
    else:
        report += "• None found\n"
    report += "\n"
    
    report += f"🚩 **Flags:**\n"
    if analysis['flags']:
        for flag, value in analysis['flags'].items():
            report += f"• {flag} = `{value}`\n"
    else:
        report += "• None found\n"
    report += "\n"
    
    report += f"📄 **JSON Structures:** {len(analysis['json_structures'])} found\n"
    report += f"📝 **Strings:** {len(analysis['strings'])} found\n\n"
    
    report += f"💡 Use `/dump` to get full dump.txt file."
    
    await update.message.reply_text(report)
    
    # Save dump
    dump_text = generate_dump_txt(analysis, user_id)
    dump_path = os.path.join(DUMP_DIR, f"dump_{user_id}_{analysis['file_name']}.txt")
    with open(dump_path, 'w', encoding='utf-8') as f:
        f.write(dump_text)
    
    # Send dump file
    await update.message.reply_document(
        document=open(dump_path, 'rb'),
        filename=f"dump_{analysis['file_name']}.txt",
        caption="📄 **Dump.txt generated** — contains all extracted data."
    )
    
    # Cleanup
    os.remove(file_path)
    os.remove(dump_path)
    log_action(user_id, "ANALYZE", analysis['file_name'])

async def process_patch(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: str):
    user_id = update.effective_user.id
    patch_data = context.user_data.get('patch_data', {})
    
    if not patch_data:
        await update.message.reply_text("❌ Use /patch <old_url> <new_url> first")
        os.remove(file_path)
        return
    
    await update.message.reply_text("🔧 Patching .so file...")
    
    changes = {
        'url_patch': patch_data
    }
    success, patched_path, msg = patch_so_file(file_path, changes)
    
    if success:
        await update.message.reply_document(
            document=open(patched_path, 'rb'),
            filename=f"patched_{os.path.basename(file_path)}",
            caption=f"✅ **Patch applied!**\n{msg}\n\n"
                    f"Old: `{patch_data['old']}`\n"
                    f"New: `{patch_data['new']}`"
        )
        os.remove(patched_path)
    else:
        await update.message.reply_text(f"❌ {msg}")
    
    os.remove(file_path)
    log_action(user_id, "PATCH", f"{patch_data['old']}->{patch_data['new']}")

async def process_dump(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: str):
    user_id = update.effective_user.id
    await update.message.reply_text("📄 Generating dump.txt...")
    
    analysis = analyze_so_file(file_path)
    if "error" in analysis:
        await update.message.reply_text(f"❌ Error: {analysis['error']}")
        os.remove(file_path)
        return
    
    dump_text = generate_dump_txt(analysis, user_id)
    dump_path = os.path.join(DUMP_DIR, f"dump_{user_id}_{analysis['file_name']}.txt")
    with open(dump_path, 'w', encoding='utf-8') as f:
        f.write(dump_text)
    
    await update.message.reply_document(
        document=open(dump_path, 'rb'),
        filename=f"dump_{analysis['file_name']}.txt",
        caption="📄 **Full Dump.txt** — all strings, URLs, API keys, flags, and JSON structures."
    )
    
    os.remove(file_path)
    os.remove(dump_path)
    log_action(user_id, "DUMP", analysis['file_name'])

async def process_json(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: str):
    user_id = update.effective_user.id
    await update.message.reply_text("🔍 Extracting JSON from .so...")
    
    success, json_data, msg = extract_json_from_so(file_path)
    
    if success:
        json_str = json.dumps(json_data, indent=2)
        json_path = os.path.join(DUMP_DIR, f"json_{user_id}_{os.path.basename(file_path)}.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            f.write(json_str)
        
        await update.message.reply_document(
            document=open(json_path, 'rb'),
            filename=f"extracted_{os.path.basename(file_path)}.json",
            caption=f"✅ {msg}\n\n```json\n{json_str[:500]}\n```"
        )
        os.remove(json_path)
    else:
        await update.message.reply_text(f"❌ {msg}")
    
    os.remove(file_path)
    log_action(user_id, "JSON_EXTRACT", os.path.basename(file_path))

async def process_repack(update: Update, context: ContextTypes.DEFAULT_TYPE, so_path: str, json_path: str):
    user_id = update.effective_user.id
    await update.message.reply_text("🔄 Injecting JSON into .so...")
    
    success, output_path, msg = json_to_so_repack(json_path, so_path)
    
    if success:
        await update.message.reply_document(
            document=open(output_path, 'rb'),
            filename=f"repacked_{os.path.basename(so_path)}",
            caption=f"✅ {msg}\n\n"
                    f"Original: `{os.path.basename(so_path)}`\n"
                    f"JSON file: `{os.path.basename(json_path)}`"
        )
        os.remove(output_path)
    else:
        await update.message.reply_text(f"❌ {msg}")
    
    os.remove(so_path)
    os.remove(json_path)
    log_action(user_id, "REPACK", os.path.basename(so_path))

async def handle_json_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    document = update.message.document
    if not document:
        return
    
    file_name = document.file_name or "unknown"
    file_ext = os.path.splitext(file_name)[1].lower()
    
    if file_ext != '.json':
        return
    
    # Download JSON file
    file_obj = await context.bot.get_file(document.file_id)
    json_path = os.path.join(DUMP_DIR, f"json_{user_id}_{file_name}")
    await file_obj.download_to_drive(json_path)
    
    # Check if we were waiting for JSON for repack
    if 'so_file' in context.user_data:
        so_path = context.user_data['so_file']
        await process_repack(update, context, so_path, json_path)
        del context.user_data['so_file']
    else:
        # Just save the JSON file for later
        context.user_data['json_file'] = json_path
        await update.message.reply_text(
            "✅ JSON file received. Now send the `.so` file to inject it."
        )

# ============================================
# ADMIN COMMANDS
# ============================================
async def genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only")
        return
    
    args = context.args
    if not args or args[0] not in ['member', 'pro', 'vip', 'lifetime']:
        await update.message.reply_text(
            "Usage: /genkey <member|pro|vip|lifetime>\n"
            "Example: /genkey pro"
        )
        return
    
    key_type = args[0]
    key = generate_key(key_type, ADMIN_ID)
    await update.message.reply_text(
        f"✅ Key generated:\n`{key}`\n"
        f"Type: {key_type}\n"
        f"Duration: {get_expiry(key_type)}\n\n"
        f"Give this key to user → /redeem {key}"
    )
    log_action(ADMIN_ID, "GENKEY", f"{key_type}:{key}")

async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    c.execute("SELECT user_id, username, key_type, expiry_date, is_banned FROM users ORDER BY user_id DESC LIMIT 20")
    users = c.fetchall()
    if not users:
        await update.message.reply_text("No users")
        return
    
    text = f"👥 **Users ({BOT_NAME})**\n\n"
    for u in users:
        status = "⛔" if u[4] else "✅"
        expiry = u[3][:10] if u[3] else "None"
        text += f"{status} `{u[0]}` | @{u[1]} | {u[2]} | {expiry}\n"
    await update.message.reply_text(text)

async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    c.execute("SELECT user_id, action, detail, timestamp FROM logs ORDER BY id DESC LIMIT 15")
    logs = c.fetchall()
    if not logs:
        await update.message.reply_text("No logs")
        return
    
    text = f"📜 **Recent Logs ({BOT_NAME})**\n\n"
    for log in logs:
        detail = log[2][:20] if log[2] else ""
        text += f"`{log[0]}` | {log[1]} | {detail} | {log[3][11:19]}\n"
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
    logs_total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM keys WHERE used_by IS NULL")
    unused_keys = c.fetchone()[0]
    
    await update.message.reply_text(
        f"📊 **Bot Stats**\n\n"
        f"👥 Total Users: {total}\n"
        f"✅ Active Users: {active}\n"
        f"⛔ Banned Users: {banned}\n"
        f"📝 Total Logs: {logs_total}\n"
        f"🔑 Unused Keys: {unused_keys}\n"
        f"🔥 Bot: {BOT_NAME}\n"
        f"👤 Developer: {DEV_NAME}"
    )

# ============================================
# CALLBACK HANDLER
# ============================================
async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "redeem":
        await query.message.reply_text("🔑 Send key with: /redeem <KEY>")
    elif query.data == "help":
        await help_cmd(update, context)
    elif query.data == "buy":
        await buy(update, context)

# ============================================
# REGISTER HANDLERS
# ============================================
# Commands
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("redeem", redeem))
app.add_handler(CommandHandler("mykey", mykey))
app.add_handler(CommandHandler("analyze", analyze))
app.add_handler(CommandHandler("patch", patch))
app.add_handler(CommandHandler("dump", dump))
app.add_handler(CommandHandler("json", json_cmd))
app.add_handler(CommandHandler("repack", repack))
app.add_handler(CommandHandler("rootbypass", rootbypass))
app.add_handler(CommandHandler("antidebug", antidebug))
app.add_handler(CommandHandler("frida", frida_cmd))
app.add_handler(CommandHandler("help", help_cmd))
app.add_handler(CommandHandler("buy", buy))

# Admin commands
app.add_handler(CommandHandler("genkey", genkey))
app.add_handler(CommandHandler("users", users))
app.add_handler(CommandHandler("logs", logs))
app.add_handler(CommandHandler("ban", ban))
app.add_handler(CommandHandler("unban", unban))
app.add_handler(CommandHandler("stats", stats))

# File handlers
app.add_handler(MessageHandler(filters.Document.ALL & ~filters.Document.FileExtension("json"), handle_document))
app.add_handler(MessageHandler(filters.Document.FileExtension("json"), handle_json_file))

# Callback
app.add_handler(CallbackQueryHandler(callback))

# ============================================
# MAIN
# ============================================
if __name__ == "__main__":
    print(f"🗡️ {BOT_NAME} STARTING...")
    print(f"🔥 Developer: {DEV_NAME}")
    print(f"✅ Bot is online!")
    print(f"📊 Database: {DB_FILE}")
    print("=" * 50)
    app.run_polling()
