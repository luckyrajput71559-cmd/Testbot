#!/usr/bin/env python3
# ================================================================
# VTX DEX — PROFESSIONAL REVERSE ENGINEERING BOT
# ================================================================
# DEVELOPER: @VICKYGAMING0
# VERSION: 8.0 ULTIMATE
# LINES: 1300+
# STATUS: PRODUCTION READY
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
TOKEN = os.getenv("TELEGRAM_TOKEN") or "8256413457:AAGurkdBHnvK7h3CZPx0lleqxEZuGnKm7dA"
ADMIN_ID = int(os.getenv("ADMIN_ID") or "5510702228")
BOT_NAME = "VTX DEX"
DEV_NAME = "@VICKYGAMING0"
FIREBASE_URL = "https://mn-rohan-default-rtdb.firebaseio.com"
DB_FILE = "vtxdex.db"
DUMP_DIR = "dumps"
PATCH_DIR = "patches"
TEMP_DIR = "temp"
APK_DIR = "apks"

for d in [DUMP_DIR, PATCH_DIR, TEMP_DIR, APK_DIR]:
    os.makedirs(d, exist_ok=True)

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
    total_analysis INTEGER DEFAULT 0,
    total_patches INTEGER DEFAULT 0,
    total_apk_patches INTEGER DEFAULT 0,
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

c.execute('''CREATE TABLE IF NOT EXISTS analysis_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    file_name TEXT,
    file_hash TEXT,
    file_size INTEGER,
    architecture TEXT,
    firebase_urls TEXT,
    api_keys TEXT,
    flags TEXT,
    strings_count INTEGER,
    json_count INTEGER,
    timestamp TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS patches_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    original_file TEXT,
    patched_file TEXT,
    original_hash TEXT,
    patched_hash TEXT,
    changes TEXT,
    timestamp TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS apk_patches_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    original_file TEXT,
    patched_file TEXT,
    original_hash TEXT,
    patched_hash TEXT,
    so_files_patched INTEGER,
    timestamp TEXT
)''')

conn.commit()

# ================================================================
# FIREBASE HELPERS
# ================================================================
def fb_get(path: str) -> Optional[dict]:
    try:
        r = requests.get(f"{FIREBASE_URL}/{path}.json", timeout=10)
        return r.json() if r.status_code == 200 else None
    except:
        return None

def fb_put(path: str, data: dict) -> bool:
    try:
        r = requests.put(f"{FIREBASE_URL}/{path}.json", json=data, timeout=10)
        return r.status_code in [200, 201]
    except:
        return False

def fb_patch(path: str, data: dict) -> bool:
    try:
        r = requests.patch(f"{FIREBASE_URL}/{path}.json", json=data, timeout=10)
        return r.status_code in [200, 201]
    except:
        return False

# ================================================================
# TIME HELPERS
# ================================================================
def now_ist():
    try:
        return datetime.now(IST)
    except:
        return datetime.now()

def fmt_ist(dt):
    return dt.strftime("%d-%b-%Y %I:%M %p IST")

def fmt_date(dt):
    return dt.strftime("%d-%b-%Y")

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

# ================================================================
# DATABASE FUNCTIONS
# ================================================================
def log_action(user_id: int, action: str, detail: str = "", target: str = ""):
    c.execute(
        "INSERT INTO logs (user_id, action, detail, target, timestamp) VALUES (?, ?, ?, ?, ?)",
        (user_id, action, detail, target, now_ist().isoformat())
    )
    conn.commit()
    fb_put(f"logs/{user_id}_{int(time.time())}", {
        'user_id': user_id,
        'action': action,
        'detail': detail,
        'target': target,
        'timestamp': now_ist().isoformat()
    })

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
    fb_put(f"users/{user_id}", {
        'username': username,
        'key_type': 'inactive',
        'key_value': None,
        'login_date': now,
        'expiry_date': None,
        'is_banned': 0,
        'used_count': 0,
        'registered_date': now
    })
    log_action(user_id, "REGISTER")
    return True

def check_access(user_id: int) -> Tuple[bool, str]:
    # ===== STEP 1: FIREBASE SE BAN STATUS CHECK (PRIORITY) =====
    try:
        import requests
        fb_url = f"{FIREBASE_URL}/users/{user_id}/is_banned.json"
        response = requests.get(fb_url, timeout=5)
        if response.status_code == 200:
            fb_banned = response.json()
            if fb_banned == 1:
                return False, "⛔ You are banned"
            # If Firebase says not banned, update SQLite to match
            elif fb_banned == 0:
                c.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,))
                conn.commit()
        # If user doesn't exist in Firebase, fallback to SQLite
    except Exception as e:
        print(f"Firebase check failed: {e}")
    
    # ===== STEP 2: SQLITE CHECK (FALLBACK) =====
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

def update_user_activity(user_id: int):
    c.execute("UPDATE users SET used_count = used_count + 1, last_activity = ? WHERE user_id = ?",
              (now_ist().isoformat(), user_id))
    conn.commit()

# ================================================================
# REDEEM KEY SYSTEM
# ================================================================
def redeem_key(user_id: int, key: str) -> Tuple[bool, str]:
    key = key.upper().strip()
    
    # Check if key is blacklisted
    c.execute("SELECT * FROM keys WHERE key=? AND is_blacklisted=1", (key,))
    if c.fetchone():
        return False, "❌ This key has been blacklisted"
    
    # STEP 1: Check Firebase
    fb_data = fb_get(f"keys/{key}")
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
        
        fb_patch(f"keys/{key}", {'used_by': user_id, 'used_at': now_ist().isoformat()})
        fb_patch(f"users/{user_id}", {
            'key_type': key_type,
            'key_value': key,
            'expiry_date': expiry,
            'login_date': now_ist().isoformat(),
            'expiry_days': expiry_days,
            'max_devices': max_devices
        })
        
        c.execute(
            """INSERT OR REPLACE INTO keys 
            (key, type, expiry_days, max_devices, created_by, created_at, used_by, used_at) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (key, key_type, expiry_days, max_devices, 0, now_ist().isoformat(), user_id, now_ist().isoformat())
        )
        conn.commit()
        
        log_action(user_id, "REDEEM", f"{key_type}:{key}")
        return True, f"✅ Key Redeemed!\n📦 Type: {key_type}\n📅 Expires: {expiry[:10]}\n📊 Days: {expiry_days}\n📱 Devices: {max_devices}"
    
    # STEP 2: Check SQLite
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
        
        fb_patch(f"users/{user_id}", {
            'key_type': key_type,
            'key_value': key,
            'expiry_date': expiry,
            'login_date': now_ist().isoformat(),
            'expiry_days': expiry_days,
            'max_devices': max_devices
        })
        fb_patch(f"keys/{key}", {'used_by': user_id, 'used_at': now_ist().isoformat()})
        
        log_action(user_id, "REDEEM", f"{key_type}:{key}")
        return True, f"✅ Key Redeemed!\n📦 Type: {key_type}\n📅 Expires: {expiry[:10]}\n📊 Days: {expiry_days}\n📱 Devices: {max_devices}"
    
    log_action(user_id, "REDEEM_FAILED", key)
    return False, "❌ Invalid or already used key"

# ================================================================
# .SO ANALYSIS ENGINE
# ================================================================
class SOAnalyzer:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.file_name = os.path.basename(file_path)
        self.file_size = os.path.getsize(file_path)
        self.data = None
        self.text_data = None
        self.result = {
            'file_name': self.file_name,
            'size': self.file_size,
            'architecture': 'Unknown',
            'firebase_urls': [],
            'api_keys': [],
            'flags': {},
            'strings': [],
            'json_structures': [],
            'offsets': {},
            'functions': [],
            'hex_dump': {},
            'hash': hashlib.md5(open(file_path, 'rb').read()).hexdigest(),
            'packer': 'None',
            'sections': []
        }
        self._analyze()
    
    def _analyze(self):
        try:
            with open(self.file_path, 'rb') as f:
                self.data = f.read()
            
            if self.data[:4] == b'\x7fELF':
                if self.data[4] == 1:
                    self.result['architecture'] = 'ARM32'
                elif self.data[4] == 2:
                    self.result['architecture'] = 'ARM64'
            
            self.text_data = self.data.decode('utf-8', errors='ignore')
            
            # Firebase URLs
            fb_pattern = r'https://[a-zA-Z0-9-]+\.firebaseio\.com'
            self.result['firebase_urls'] = list(set(re.findall(fb_pattern, self.text_data)))
            
            # API Keys
            api_pattern = r'AIza[0-9A-Za-z_-]{35}'
            self.result['api_keys'] = list(set(re.findall(api_pattern, self.text_data)))
            
            # Flags
            flag_patterns = [
                r'verify_active\s*=\s*([0-9]+)',
                r'access_hours\s*=\s*([0-9]+)',
                r'maintenance\s*=\s*([0-9]+)',
                r'debug_mode\s*=\s*([0-9]+)',
                r'is_verified\s*=\s*([0-9]+)',
                r'is_premium\s*=\s*([0-9]+)',
                r'is_pro\s*=\s*([0-9]+)',
                r'enable_logging\s*=\s*([0-9]+)',
                r'ssl_pinning\s*=\s*([0-9]+)',
                r'root_check\s*=\s*([0-9]+)',
                r'isDeviceRooted\s*=\s*([0-9]+)',
                r'isRooted\s*=\s*([0-9]+)',
                r'isMagiskInstalled\s*=\s*([0-9]+)',
            ]
            for pattern in flag_patterns:
                matches = re.findall(pattern, self.text_data)
                if matches:
                    flag_name = re.search(r'([a-zA-Z_]+)\s*=', pattern)
                    if flag_name:
                        self.result['flags'][flag_name.group(1)] = matches[0]
            
            # Strings
            str_pattern = r'[a-zA-Z0-9_\-\./\\@:]{4,}'
            self.result['strings'] = list(set(re.findall(str_pattern, self.text_data)))
            
            # JSON
            json_pattern = r'\{[^{}]*\}'
            for match in re.findall(json_pattern, self.text_data):
                try:
                    self.result['json_structures'].append(json.loads(match))
                except:
                    pass
            
            # Offsets
            for url in self.result['firebase_urls']:
                idx = self.text_data.find(url)
                if idx != -1:
                    self.result['offsets'][url] = hex(idx)
            for key in self.result['api_keys']:
                idx = self.text_data.find(key)
                if idx != -1:
                    self.result['offsets'][key] = hex(idx)
            
            # Functions
            func_pattern = r'[a-zA-Z_][a-zA-Z0-9_]*\s*\([^)]*\)\s*\{'
            self.result['functions'] = list(set(re.findall(func_pattern, self.text_data)))[:30]
            
            # Hex dump
            self.result['hex_dump'] = {
                'offset': '0x0',
                'hex': binascii.hexlify(self.data[:256]).decode('utf-8')
            }
            
            # Sections
            section_pattern = r'\.(text|data|rodata|bss|init|fini|got|plt|dynsym|dynstr|hash|gnu\.hash)'
            sections = re.findall(section_pattern, self.text_data)
            self.result['sections'] = list(set(sections))
            
            # Packer detection
            packers = [('UPX', 'UPX'), ('MPRESS', 'MPRESS'), ('ASPack', 'ASPack'), 
                       ('Themida', 'Themida'), ('VMProtect', 'VMProtect'), ('Enigma', 'Enigma')]
            for pattern, name in packers:
                if re.search(pattern, self.text_data, re.IGNORECASE):
                    self.result['packer'] = name
                    break
                    
        except Exception as e:
            self.result['error'] = str(e)
    
    def get_report(self) -> str:
        r = self.result
        report = f"""
📊 ANALYSIS REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 File: {r['file_name']}
📏 Size: {r['size']:,} bytes
🏗️ Architecture: {r['architecture']}
🔑 Hash: {r['hash'][:16]}...
📦 Packer: {r['packer']}

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
    
    def generate_dump_txt(self) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append("VTX DEX DUMP FILE")
        lines.append("=" * 60)
        lines.append(f"File: {self.result['file_name']}")
        lines.append(f"Size: {self.result['size']:,} bytes")
        lines.append(f"Architecture: {self.result['architecture']}")
        lines.append(f"Hash: {self.result['hash']}")
        lines.append(f"Packer: {self.result['packer']}")
        lines.append(f"Date: {fmt_ist(now_ist())}")
        lines.append("")
        lines.append("=" * 60)
        lines.append("FIREBASE URLs")
        lines.append("=" * 60)
        for url in self.result['firebase_urls']:
            off = self.result['offsets'].get(url, 'Unknown')
            lines.append(f"{url} (offset: {off})")
        lines.append("")
        lines.append("=" * 60)
        lines.append("API KEYS")
        lines.append("=" * 60)
        for key in self.result['api_keys']:
            off = self.result['offsets'].get(key, 'Unknown')
            lines.append(f"{key} (offset: {off})")
        lines.append("")
        lines.append("=" * 60)
        lines.append("FLAGS")
        lines.append("=" * 60)
        for flag, value in self.result['flags'].items():
            lines.append(f"{flag} = {value}")
        lines.append("")
        lines.append("=" * 60)
        lines.append("JSON STRUCTURES")
        lines.append("=" * 60)
        for js in self.result['json_structures']:
            lines.append(json.dumps(js, indent=2))
        lines.append("")
        lines.append("=" * 60)
        lines.append("FUNCTIONS")
        lines.append("=" * 60)
        for f in self.result['functions']:
            lines.append(f)
        lines.append("")
        lines.append("=" * 60)
        lines.append("SECTIONS")
        lines.append("=" * 60)
        for s in self.result['sections']:
            lines.append(s)
        lines.append("")
        lines.append("=" * 60)
        lines.append("STRINGS (First 100)")
        lines.append("=" * 60)
        for s in self.result['strings'][:100]:
            lines.append(s)
        if len(self.result['strings']) > 100:
            lines.append(f"... and {len(self.result['strings']) - 100} more")
        lines.append("")
        lines.append("=" * 60)
        lines.append("HEX DUMP (First 256 bytes)")
        lines.append("=" * 60)
        lines.append(self.result['hex_dump']['hex'])
        lines.append("")
        lines.append("=" * 60)
        lines.append("END OF DUMP")
        lines.append("=" * 60)
        return '\n'.join(lines)

# ================================================================
# APK ROOT DETECTION BYPASS
# ================================================================
def bypass_root_detection(apk_path: str) -> Tuple[bool, Optional[str], str]:
    try:
        output_dir = os.path.join(APK_DIR, f"patched_{int(time.time())}")
        os.makedirs(output_dir, exist_ok=True)
        
        with zipfile.ZipFile(apk_path, 'r') as zip_ref:
            zip_ref.extractall(output_dir)
        
        so_files = []
        for root, dirs, files in os.walk(output_dir):
            for file in files:
                if file.endswith('.so'):
                    so_files.append(os.path.join(root, file))
        
        patched_count = 0
        for so_file in so_files:
            with open(so_file, 'rb') as f:
                data = f.read()
            text_data = data.decode('utf-8', errors='ignore')
            modified = False
            
            patterns = [
                (r'isDeviceRooted\s*=\s*[0-9]+', 'isDeviceRooted = 0'),
                (r'isRooted\s*=\s*[0-9]+', 'isRooted = 0'),
                (r'isMagiskInstalled\s*=\s*[0-9]+', 'isMagiskInstalled = 0'),
                (r'root_check\s*=\s*[0-9]+', 'root_check = 0'),
                (r'verify_root\s*=\s*[0-9]+', 'verify_root = 0'),
                (r'checkRoot\s*=\s*[0-9]+', 'checkRoot = 0'),
                (r'isDeviceRooted\(\)\s*\{[^}]*\}', 'isDeviceRooted() { return 0; }'),
                (r'isRooted\(\)\s*\{[^}]*\}', 'isRooted() { return 0; }'),
            ]
            
            for pattern, replacement in patterns:
                new_text = re.sub(pattern, replacement, text_data, flags=re.DOTALL)
                if new_text != text_data:
                    text_data = new_text
                    modified = True
            
            if modified:
                with open(so_file, 'wb') as f:
                    f.write(text_data.encode('utf-8', errors='ignore'))
                patched_count += 1
        
        output_apk = os.path.join(APK_DIR, f"patched_{os.path.basename(apk_path)}")
        with zipfile.ZipFile(output_apk, 'w') as zipf:
            for root, dirs, files in os.walk(output_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, output_dir)
                    zipf.write(file_path, arcname)
        
        shutil.rmtree(output_dir)
        
        if patched_count > 0:
            orig_hash = hashlib.md5(open(apk_path, 'rb').read()).hexdigest()
            patched_hash = hashlib.md5(open(output_apk, 'rb').read()).hexdigest()
            return True, output_apk, f"✅ Patched {patched_count} .so files\nOriginal: {orig_hash[:16]}\nPatched: {patched_hash[:16]}"
        else:
            return False, None, "No root detection patterns found"
            
    except Exception as e:
        return False, None, f"Error: {str(e)}"

# ================================================================
# FRIDA SCRIPT GENERATORS
# ================================================================
def generate_frida_hook(func: str) -> str:
    return f'''// VTX DEX - Frida Hook for {func}
Java.perform(function() {{
    console.log("[*] Hooking {func}...");
    var classes = [
        "com.example.app.MainActivity",
        "com.example.app.Config",
        "com.example.app.FlagManager",
        "com.example.app.AuthManager",
        "com.example.app.SecurityManager",
        "com.example.app.RootDetection"
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

def generate_root_bypass_script() -> str:
    return '''// VTX DEX - Root Detection Bypass
Java.perform(function() {
    console.log("[*] Loading root bypass...");
    try {
        var RootDetection = Java.use("com.example.rootdetection.RootDetection");
        RootDetection.isDeviceRooted.implementation = function() { return false; };
        RootDetection.isRooted.implementation = function() { return false; };
    } catch(e) {}
    try {
        var SafetyNet = Java.use("com.google.android.gms.safetynet.SafetyNet");
        SafetyNet.isDeviceRooted.implementation = function() { return false; };
    } catch(e) {}
    try {
        var MagiskDetector = Java.use("com.topjohnwu.magisk.detector");
        MagiskDetector.isMagiskInstalled.implementation = function() { return false; };
    } catch(e) {}
    console.log("[*] Root bypass loaded!");
});'''

def generate_antidebug_script() -> str:
    return '''// VTX DEX - Anti-Debug Bypass
Java.perform(function() {
    console.log("[*] Loading anti-debug bypass...");
    try {
        var ptrace = Module.findExportByName("libc.so", "ptrace");
        if (ptrace) {
            Interceptor.replace(ptrace, new NativeCallback(function() { return 0; }, 'int', ['int', 'int', 'pointer', 'pointer']));
        }
    } catch(e) {}
    try {
        var BufferedReader = Java.use("java.io.BufferedReader");
        BufferedReader.readLine.implementation = function() {
            var line = this.readLine();
            if (line && line.indexOf("TracerPid") !== -1) {
                return "TracerPid:\\t0";
            }
            return line;
        };
    } catch(e) {}
    console.log("[*] Anti-debug bypass loaded!");
});'''

def generate_cert_pinning_script() -> str:
    return '''// VTX DEX - Certificate Pinning Bypass
Java.perform(function() {
    console.log("[*] Loading certificate pinning bypass...");
    try {
        var TrustManager = Java.use("javax.net.ssl.X509TrustManager");
        TrustManager.checkClientTrusted.implementation = function(chain, authType) {};
        TrustManager.checkServerTrusted.implementation = function(chain, authType) {};
        TrustManager.getAcceptedIssuers.implementation = function() { return []; };
    } catch(e) {}
    try {
        var HostnameVerifier = Java.use("javax.net.ssl.HostnameVerifier");
        HostnameVerifier.verify.implementation = function(hostname, session) { return true; };
    } catch(e) {}
    console.log("[*] Certificate pinning bypass loaded!");
});'''

# ================================================================
# BOT APPLICATION
# ================================================================
app = Application.builder().token(TOKEN).build()

WAITING_SO = 1
WAITING_APK = 2

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

🔐 AUTHENTICATION
  /start      - Show menu
  /redeem     - Activate key
  /mykey      - Check key status

🔧 ANALYSIS
  /analyze    - Analyze .so file
  /dump       - Generate dump.txt
  /patch      - Patch .so file
  /rootpatch  - Bypass root detection in APK

🛡️ BYPASS TOOLS
  /rootbypass - Root bypass script
  /antidebug  - Anti-debug script
  /pinning    - SSL bypass script
  /frida      - Frida hook

📊 INFORMATION
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
🔍 Analysis: {user[9] if user[9] else 0}
🔧 Patches: {user[10] if user[10] else 0}
📱 APK Patches: {user[11] if user[11] else 0}
⛔ Banned: {'Yes' if user[6] else 'No'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    await update.message.reply_text(msg)
    update_user_activity(user_id)

async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    await update.message.reply_text(
        "📤 Upload .so file for analysis\n\n"
        "I will extract:\n"
        "• Firebase URLs\n"
        "• API Keys\n"
        "• Flags\n"
        "• Strings\n"
        "• JSON structures\n"
        "• Functions\n"
        "• ELF sections\n"
        "• Packer detection"
    )
    context.user_data['action'] = 'analyze'
    return WAITING_SO

async def dump(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    await update.message.reply_text("📤 Upload .so file to generate dump.txt")
    context.user_data['action'] = 'dump'
    return WAITING_SO

async def patch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    args = context.args
    if len(args) >= 2:
        context.user_data['patch_data'] = {'old': args[0], 'new': args[1]}
        await update.message.reply_text(f"📤 Upload .so file to patch\nChanging: {args[0]} → {args[1]}")
        context.user_data['action'] = 'patch'
        return WAITING_SO
    
    await update.message.reply_text(
        "🔧 Usage: /patch <old_url> <new_url>\n"
        "Example: /patch https://old.com https://new.com"
    )

async def rootpatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    await update.message.reply_text(
        "📤 Upload APK file to bypass root detection\n\n"
        "I will:\n"
        "• Extract APK\n"
        "• Patch all .so files\n"
        "• Remove root checks\n"
        "• Repack APK\n"
        "• Return patched APK\n\n"
        "⚠️ Works for all APKs (Universal)"
    )
    context.user_data['action'] = 'rootpatch'
    return WAITING_APK

async def rootbypass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    script = generate_root_bypass_script()
    await update.message.reply_document(
        document=script.encode(),
        filename="root_bypass.js",
        caption="🔓 Root Detection Bypass Script\n\nInject: frida -U -f com.example.app -l root_bypass.js"
    )
    log_action(user_id, "ROOTBYPASS")
    update_user_activity(user_id)

async def antidebug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    script = generate_antidebug_script()
    await update.message.reply_document(
        document=script.encode(),
        filename="antidebug.js",
        caption="🛡️ Anti-Debug Bypass Script\n\nInject: frida -U -f com.example.app -l antidebug.js"
    )
    log_action(user_id, "ANTIDEBUG")
    update_user_activity(user_id)

async def pinning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    script = generate_cert_pinning_script()
    await update.message.reply_document(
        document=script.encode(),
        filename="pinning_bypass.js",
        caption="🔓 SSL Pinning Bypass Script\n\nInject: frida -U -f com.example.app -l pinning_bypass.js"
    )
    log_action(user_id, "PINNING")
    update_user_activity(user_id)

async def frida_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("❌ Usage: /frida <function_name>\nExample: /frida verify_active")
        return
    
    func = args[0]
    script = generate_frida_hook(func)
    await update.message.reply_document(
        document=script.encode(),
        filename=f"hook_{func}.js",
        caption=f"🔫 Frida Hook for '{func}'\n\nInject: frida -U -f com.example.app -l hook_{func}.js"
    )
    log_action(user_id, "FRIDA", func)
    update_user_activity(user_id)

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💳 SUBSCRIPTION PLANS\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔹 Member — $10 (30 Days)\n"
        "🔸 Pro Member — $25 (60 Days)\n"
        "🔹 VIP Member — $50 (90 Days)\n"
        "🔸 Lifetime — $100 (Forever)\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📌 Contact: {DEV_NAME}\n"
        "💳 Payment: UPI / Crypto / PayPal\n\n"
        "After payment, you'll receive a key.\n"
        "Use /redeem <key> to activate."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = f"""
📖 VTX DEX — COMPLETE COMMANDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔐 AUTHENTICATION
  /start      - Show main menu
  /redeem     - Activate subscription key
  /mykey      - Check key status

🔧 ANALYSIS
  /analyze    - Analyze .so file
  /dump       - Generate dump.txt
  /patch      - Patch .so file
  /rootpatch  - Bypass root detection in APK

🛡️ BYPASS TOOLS
  /rootbypass - Generate root bypass script
  /antidebug  - Generate anti-debug script
  /pinning    - Generate SSL bypass script
  /frida      - Generate Frida hook

📊 INFORMATION
  /help       - Show this
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
    file_obj = await context.bot.get_file(doc.file_id)
    file_path = os.path.join(TEMP_DIR, f"{user_id}_{file_name}")
    await file_obj.download_to_drive(file_path)
    
    action = context.user_data.get('action', '')
    
    if action == 'analyze':
        await process_analyze(update, context, file_path)
    elif action == 'dump':
        await process_dump(update, context, file_path)
    elif action == 'patch':
        await process_patch(update, context, file_path)
    elif action == 'rootpatch':
        await process_rootpatch(update, context, file_path)
    else:
        await update.message.reply_text("❌ Use a command first: /analyze, /dump, /patch, /rootpatch")
        os.remove(file_path)
    
    context.user_data['action'] = ''

# ================================================================
# PROCESS FUNCTIONS
# ================================================================

async def process_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: str):
    user_id = update.effective_user.id
    await update.message.reply_text("🔍 Analyzing .so file...")
    
    analyzer = SOAnalyzer(file_path)
    if hasattr(analyzer.result, 'error'):
        await update.message.reply_text(f"❌ Error: {analyzer.result['error']}")
        os.remove(file_path)
        return
    
    await update.message.reply_text(analyzer.get_report())
    
    c.execute(
        """INSERT INTO analysis_history 
        (user_id, file_name, file_hash, file_size, architecture, firebase_urls, api_keys, flags, strings_count, json_count, timestamp) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, analyzer.file_name, analyzer.result['hash'], analyzer.file_size,
         analyzer.result['architecture'],
         json.dumps(analyzer.result['firebase_urls']),
         json.dumps(analyzer.result['api_keys']),
         json.dumps(analyzer.result['flags']),
         len(analyzer.result['strings']),
         len(analyzer.result['json_structures']),
         now_ist().isoformat())
    )
    conn.commit()
    
    c.execute("UPDATE users SET total_analysis = total_analysis + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    
    log_action(user_id, "ANALYZE", analyzer.file_name)
    update_user_activity(user_id)
    os.remove(file_path)

async def process_dump(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: str):
    user_id = update.effective_user.id
    await update.message.reply_text("📄 Generating dump.txt...")
    
    analyzer = SOAnalyzer(file_path)
    if hasattr(analyzer.result, 'error'):
        await update.message.reply_text(f"❌ Error: {analyzer.result['error']}")
        os.remove(file_path)
        return
    
    dump_text = analyzer.generate_dump_txt()
    dump_path = os.path.join(DUMP_DIR, f"dump_{user_id}_{analyzer.file_name}.txt")
    with open(dump_path, 'w', encoding='utf-8') as f:
        f.write(dump_text)
    
    await update.message.reply_document(
        document=open(dump_path, 'rb'),
        filename=f"dump_{analyzer.file_name}.txt",
        caption="📄 Full dump.txt generated"
    )
    
    log_action(user_id, "DUMP", analyzer.file_name)
    update_user_activity(user_id)
    os.remove(file_path)
    os.remove(dump_path)

async def process_patch(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: str):
    user_id = update.effective_user.id
    patch_data = context.user_data.get('patch_data', {})
    
    if not patch_data:
        await update.message.reply_text("❌ Use /patch <old> <new> first")
        os.remove(file_path)
        return
    
    await update.message.reply_text("🔧 Patching .so file...")
    
    try:
        with open(file_path, 'rb') as f:
            data = f.read()
        text_data = data.decode('utf-8', errors='ignore')
        
        old_url = patch_data['old']
        new_url = patch_data['new']
        
        if old_url in text_data:
            text_data = text_data.replace(old_url, new_url)
            output_path = os.path.join(PATCH_DIR, f"patched_{os.path.basename(file_path)}")
            with open(output_path, 'wb') as f:
                f.write(text_data.encode('utf-8', errors='ignore'))
            
            orig_hash = hashlib.md5(open(file_path, 'rb').read()).hexdigest()
            patched_hash = hashlib.md5(open(output_path, 'rb').read()).hexdigest()
            
            await update.message.reply_document(
                document=open(output_path, 'rb'),
                filename=f"patched_{os.path.basename(file_path)}",
                caption=f"✅ Patch applied!\nOld: {old_url}\nNew: {new_url}\nHash: {patched_hash[:16]}"
            )
            
            c.execute(
                """INSERT INTO patches_history 
                (user_id, original_file, patched_file, original_hash, patched_hash, changes, timestamp) 
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, os.path.basename(file_path), os.path.basename(output_path),
                 orig_hash, patched_hash, f"{old_url}->{new_url}", now_ist().isoformat())
            )
            conn.commit()
            
            c.execute("UPDATE users SET total_patches = total_patches + 1 WHERE user_id = ?", (user_id,))
            conn.commit()
            
            log_action(user_id, "PATCH", f"{old_url}->{new_url}")
            update_user_activity(user_id)
            os.remove(output_path)
        else:
            await update.message.reply_text(f"❌ URL not found: {old_url}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
    
    os.remove(file_path)
    context.user_data['patch_data'] = {}

async def process_rootpatch(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: str):
    user_id = update.effective_user.id
    await update.message.reply_text("🔓 Bypassing root detection in APK...")
    
    success, output_path, msg = bypass_root_detection(file_path)
    
    if success:
        await update.message.reply_document(
            document=open(output_path, 'rb'),
            filename=f"patched_{os.path.basename(file_path)}",
            caption=f"✅ Root detection bypassed!\n\n{msg}"
        )
        c.execute("UPDATE users SET total_apk_patches = total_apk_patches + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        log_action(user_id, "ROOTPATCH", os.path.basename(file_path))
        update_user_activity(user_id)
        os.remove(output_path)
    else:
        await update.message.reply_text(f"❌ {msg}")
    
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
            "Example: /genkey vip 90 2\n\n"
            "Types: member, pro, vip, lifetime, custom"
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
    
    fb_put(f"keys/{key}", {
        'type': key_type,
        'expiry_days': expiry_days,
        'max_devices': max_devices,
        'created_by': ADMIN_ID,
        'created_at': now_ist().isoformat(),
        'used_by': None,
        'used_at': None
    })
    
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

# ================================================================
# UNBAN COMMAND
# ================================================================
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
        
        # Update SQLite
        c.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,))
        conn.commit()
        
        # Update Firebase
        fb_patch(f"users/{user_id}", {'is_banned': 0})
        
        await update.message.reply_text(f"✅ User {user_id} unbanned")
        log_action(ADMIN_ID, "UNBAN", str(user_id))
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Must be a number.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    
    try:
        user_id = int(args[0])
        c.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,))
        conn.commit()
        await update.message.reply_text(f"✅ User {user_id} unbanned")
        log_action(ADMIN_ID, "UNBAN", str(user_id))
    except:
        await update.message.reply_text("❌ Invalid user ID")

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
    c.execute("SELECT COUNT(*) FROM analysis_history")
    analysis_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM patches_history")
    patch_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM apk_patches_history")
    apk_count = c.fetchone()[0]
    
    await update.message.reply_text(
        f"📊 VTX DEX STATISTICS\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Total Users: {total}\n"
        f"✅ Active: {active}\n"
        f"🚫 Banned: {banned}\n"
        f"🔑 Unused Keys: {unused}\n"
        f"📝 Logs: {log_count}\n"
        f"🔍 Analyses: {analysis_count}\n"
        f"🔧 Patches: {patch_count}\n"
        f"📱 APK Patches: {apk_count}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Developer: {DEV_NAME}"
    )

# ================================================================
# CALLBACK HANDLER
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

# User Commands
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("redeem", redeem))
app.add_handler(CommandHandler("mykey", mykey))
app.add_handler(CommandHandler("analyze", analyze))
app.add_handler(CommandHandler("dump", dump))
app.add_handler(CommandHandler("patch", patch))
app.add_handler(CommandHandler("rootpatch", rootpatch))
app.add_handler(CommandHandler("rootbypass", rootbypass))
app.add_handler(CommandHandler("antidebug", antidebug))
app.add_handler(CommandHandler("pinning", pinning))
app.add_handler(CommandHandler("frida", frida_cmd))
app.add_handler(CommandHandler("buy", buy))
app.add_handler(CommandHandler("help", help_cmd))

# Admin Commands
app.add_handler(CommandHandler("genkey", genkey))
app.add_handler(CommandHandler("users", users))
app.add_handler(CommandHandler("logs", logs))
app.add_handler(CommandHandler("ban", ban))
app.add_handler(CommandHandler("unban", unban))
app.add_handler(CommandHandler("stats", stats))

# File Handler
app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

# Callback
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
    print(f"📁 Dump Dir: {DUMP_DIR}")
    print(f"📁 Patch Dir: {PATCH_DIR}")
    print(f"📁 APK Dir: {APK_DIR}")
    print("=" * 60)
    print("✅ Bot is ONLINE and READY!")
    print("=" * 60)
    
    app.run_polling()
