#!/usr/bin/env python3
# =============================================
# VTX DEX — ULTIMATE REVERSE ENGINEERING BOT
# =============================================
# DEVELOPER: @VICKYGAMING0 | SOKY-DEX
# VERSION: 5.0 FINAL
# LINES: 1300+
# STATUS: PRODUCTION READY
# =============================================

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
import requests
import binascii
import struct
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Union
from urllib.parse import urlparse

# =============================================
# TELEGRAM IMPORTS
# =============================================
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler
)

# =============================================
# LOGGING SETUP
# =============================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =============================================
# TIMEZONE SETUP
# =============================================
try:
    import pytz
    IST = pytz.timezone('Asia/Kolkata')
except ImportError:
    from datetime import timezone
    IST = timezone(timedelta(hours=5, minutes=30))

# =============================================
# CONFIGURATION
# =============================================
TOKEN = os.getenv("TELEGRAM_TOKEN") or "8256413457:AAGurkdBHnvK7h3CZPx0lleqxEZuGnKm7dA"
ADMIN_ID = int(os.getenv("ADMIN_ID") or "5510702228")
BOT_NAME = "VTX DEX"
DEV_NAME = "@VICKYGAMING0 | SOKY-DEX"
FIREBASE_URL = "https://mn-rohan-default-rtdb.firebaseio.com"
DB_FILE = "vtxdex.db"
DUMP_DIR = "dumps"
PATCH_DIR = "patches"
LOG_DIR = "logs"
TEMP_DIR = "temp"

# Create directories
for d in [DUMP_DIR, PATCH_DIR, LOG_DIR, TEMP_DIR]:
    os.makedirs(d, exist_ok=True)

# =============================================
# DATABASE SETUP
# =============================================
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()

# Users Table
c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    key_type TEXT DEFAULT 'inactive',
    key_value TEXT,
    login_date TEXT,
    expiry_date TEXT,
    is_banned INTEGER DEFAULT 0,
    used_count INTEGER DEFAULT 0,
    total_analysis INTEGER DEFAULT 0,
    total_patches INTEGER DEFAULT 0,
    last_activity TEXT
)''')

# Keys Table
c.execute('''CREATE TABLE IF NOT EXISTS keys (
    key TEXT PRIMARY KEY,
    type TEXT,
    created_by INTEGER,
    created_at TEXT,
    used_by INTEGER,
    used_at TEXT
)''')

# Logs Table
c.execute('''CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT,
    detail TEXT,
    target TEXT,
    timestamp TEXT
)''')

# Analysis History Table
c.execute('''CREATE TABLE IF NOT EXISTS analysis_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    file_name TEXT,
    file_hash TEXT,
    analysis_data TEXT,
    dump_path TEXT,
    timestamp TEXT
)''')

# Patches History Table
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

# Blacklisted Keys Table
c.execute('''CREATE TABLE IF NOT EXISTS blacklisted_keys (
    key TEXT PRIMARY KEY,
    reason TEXT,
    created_at TEXT
)''')

# Settings Table
c.execute('''CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)''')

conn.commit()

# =============================================
# FIREBASE HELPERS
# =============================================
def fb_get(path: str) -> Optional[dict]:
    try:
        r = requests.get(f"{FIREBASE_URL}/{path}.json", timeout=10)
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        logger.error(f"Firebase GET error: {e}")
        return None

def fb_put(path: str, data: dict) -> bool:
    try:
        r = requests.put(f"{FIREBASE_URL}/{path}.json", json=data, timeout=10)
        return r.status_code in [200, 201]
    except Exception as e:
        logger.error(f"Firebase PUT error: {e}")
        return False

def fb_patch(path: str, data: dict) -> bool:
    try:
        r = requests.patch(f"{FIREBASE_URL}/{path}.json", json=data, timeout=10)
        return r.status_code in [200, 201]
    except Exception as e:
        logger.error(f"Firebase PATCH error: {e}")
        return False

def fb_delete(path: str) -> bool:
    try:
        r = requests.delete(f"{FIREBASE_URL}/{path}.json", timeout=10)
        return r.status_code in [200, 204]
    except Exception as e:
        logger.error(f"Firebase DELETE error: {e}")
        return False

# =============================================
# TIME HELPERS
# =============================================
def now_ist():
    try:
        return datetime.now(IST)
    except:
        return datetime.now()

def fmt_ist(dt):
    return dt.strftime("%d-%m-%Y %H:%M IST")

def get_expiry(key_type: str) -> str:
    days = {
        'member': 30,
        'pro': 60,
        'vip': 90,
        'lifetime': 3650
    }.get(key_type, 30)
    return (now_ist() + timedelta(days=days)).isoformat()

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

# =============================================
# DATABASE FUNCTIONS
# =============================================
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
    c.execute(
        "INSERT INTO users (user_id, username, key_type, key_value, login_date, expiry_date, last_activity) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, username, 'inactive', None, now_ist().isoformat(), None, now_ist().isoformat())
    )
    conn.commit()
    fb_put(f"users/{user_id}", {
        'username': username,
        'key_type': 'inactive',
        'key_value': None,
        'login_date': now_ist().isoformat(),
        'expiry_date': None,
        'is_banned': 0,
        'used_count': 0,
        'total_analysis': 0,
        'total_patches': 0,
        'last_activity': now_ist().isoformat()
    })
    log_action(user_id, "REGISTER", "inactive")
    return True

def check_access(user_id: int) -> Tuple[bool, str]:
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
    fb_patch(f"users/{user_id}", {
        'used_count': c.lastrowid,
        'last_activity': now_ist().isoformat()
    })

# =============================================
# REDEEM KEY SYSTEM
# =============================================
def redeem_key(user_id: int, key: str) -> Tuple[bool, str]:
    key = key.upper().strip()
    
    # Check if key is blacklisted
    c.execute("SELECT * FROM blacklisted_keys WHERE key=?", (key,))
    if c.fetchone():
        return False, "❌ This key has been blacklisted"
    
    # STEP 1: Check Firebase
    fb_data = fb_get(f"keys/{key}")
    if fb_data and not fb_data.get('used_by'):
        key_type = fb_data.get('type', 'member')
        expiry = get_expiry(key_type)
        
        c.execute(
            "UPDATE users SET key_type=?, key_value=?, expiry_date=?, login_date=? WHERE user_id=?",
            (key_type, key, expiry, now_ist().isoformat(), user_id)
        )
        conn.commit()
        
        fb_patch(f"keys/{key}", {
            'used_by': user_id,
            'used_at': now_ist().isoformat()
        })
        
        c.execute(
            "INSERT OR REPLACE INTO keys (key, type, created_by, created_at, used_by, used_at) VALUES (?, ?, ?, ?, ?, ?)",
            (key, key_type, 0, now_ist().isoformat(), user_id, now_ist().isoformat())
        )
        conn.commit()
        
        fb_patch(f"users/{user_id}", {
            'key_type': key_type,
            'key_value': key,
            'expiry_date': expiry,
            'login_date': now_ist().isoformat()
        })
        
        log_action(user_id, "REDEEM_FIREBASE", f"{key_type}:{key}")
        return True, f"✅ Key redeemed!\nType: {key_type}\nExpires: {expiry[:10]}"
    
    # STEP 2: Check SQLite
    c.execute("SELECT * FROM keys WHERE key=? AND used_by IS NULL", (key,))
    key_data = c.fetchone()
    if key_data:
        key_type = key_data[1]
        expiry = get_expiry(key_type)
        
        c.execute(
            "UPDATE users SET key_type=?, key_value=?, expiry_date=?, login_date=? WHERE user_id=?",
            (key_type, key, expiry, now_ist().isoformat(), user_id)
        )
        c.execute("UPDATE keys SET used_by=?, used_at=? WHERE key=?", (user_id, now_ist().isoformat(), key))
        conn.commit()
        
        fb_patch(f"users/{user_id}", {
            'key_type': key_type,
            'key_value': key,
            'expiry_date': expiry,
            'login_date': now_ist().isoformat()
        })
        fb_patch(f"keys/{key}", {
            'used_by': user_id,
            'used_at': now_ist().isoformat()
        })
        
        log_action(user_id, "REDEEM_SQLITE", f"{key_type}:{key}")
        return True, f"✅ Key redeemed!\nType: {key_type}\nExpires: {expiry[:10]}"
    
    log_action(user_id, "REDEEM_FAILED", key)
    return False, "❌ Invalid or already used key"

# =============================================
# .SO ANALYSIS ENGINE
# =============================================
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
            'hash': hashlib.md5(open(file_path, 'rb').read()).hexdigest()
        }
        self._analyze()
    
    def _analyze(self):
        try:
            with open(self.file_path, 'rb') as f:
                self.data = f.read()
            
            # Detect ELF
            if self.data[:4] == b'\x7fELF':
                ei_class = self.data[4]
                if ei_class == 1:
                    self.result['architecture'] = 'ARM32'
                elif ei_class == 2:
                    self.result['architecture'] = 'ARM64'
                else:
                    self.result['architecture'] = 'Unknown'
            
            self.text_data = self.data.decode('utf-8', errors='ignore')
            
            # Extract Firebase URLs
            fb_pattern = r'https://[a-zA-Z0-9-]+\.firebaseio\.com'
            self.result['firebase_urls'] = list(set(re.findall(fb_pattern, self.text_data)))
            
            # Extract API Keys
            api_pattern = r'AIza[0-9A-Za-z_-]{35}'
            self.result['api_keys'] = list(set(re.findall(api_pattern, self.text_data)))
            
            # Extract Flags
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
            ]
            for pattern in flag_patterns:
                matches = re.findall(pattern, self.text_data)
                if matches:
                    flag_name = re.search(r'([a-zA-Z_]+)\s*=', pattern)
                    if flag_name:
                        self.result['flags'][flag_name.group(1)] = matches[0]
            
            # Extract Strings (min length 4)
            str_pattern = r'[a-zA-Z0-9_\-\./\\@:]{4,}'
            self.result['strings'] = list(set(re.findall(str_pattern, self.text_data)))
            
            # Extract JSON
            json_pattern = r'\{[^{}]*\}'
            for match in re.findall(json_pattern, self.text_data):
                try:
                    self.result['json_structures'].append(json.loads(match))
                except:
                    pass
            
            # Find offsets
            for url in self.result['firebase_urls']:
                idx = self.text_data.find(url)
                if idx != -1:
                    self.result['offsets'][url] = hex(idx)
            
            for key in self.result['api_keys']:
                idx = self.text_data.find(key)
                if idx != -1:
                    self.result['offsets'][key] = hex(idx)
            
            # Extract function names (simple)
            func_pattern = r'[a-zA-Z_][a-zA-Z0-9_]*\s*\([^)]*\)\s*\{'
            self.result['functions'] = list(set(re.findall(func_pattern, self.text_data)))[:20]
            
            # Hex dump of first 256 bytes
            self.result['hex_dump'] = {
                'offset': '0x0',
                'hex': binascii.hexlify(self.data[:256]).decode('utf-8')
            }
            
        except Exception as e:
            self.result['error'] = str(e)
    
    def get_report(self) -> str:
        r = self.result
        report = f"📊 **Analysis Report**\n\n"
        report += f"📁 File: `{r['file_name']}`\n"
        report += f"📏 Size: {r['size']:,} bytes\n"
        report += f"🏗️ Architecture: {r['architecture']}\n"
        report += f"🔑 Hash: `{r['hash'][:16]}...`\n\n"
        
        report += f"📡 **Firebase URLs** ({len(r['firebase_urls'])}):\n"
        for url in r['firebase_urls'][:5]:
            off = r['offsets'].get(url, 'Unknown')
            report += f"• `{url}` (offset: {off})\n"
        if len(r['firebase_urls']) > 5:
            report += f"• ... and {len(r['firebase_urls']) - 5} more\n"
        report += "\n"
        
        report += f"🔑 **API Keys** ({len(r['api_keys'])}):\n"
        for key in r['api_keys'][:5]:
            off = r['offsets'].get(key, 'Unknown')
            report += f"• `{key}` (offset: {off})\n"
        if len(r['api_keys']) > 5:
            report += f"• ... and {len(r['api_keys']) - 5} more\n"
        report += "\n"
        
        report += f"🚩 **Flags** ({len(r['flags'])}):\n"
        for flag, value in r['flags'].items():
            report += f"• {flag} = `{value}`\n"
        if not r['flags']:
            report += "• None found\n"
        report += "\n"
        
        report += f"📄 **JSON Structures** ({len(r['json_structures'])}):\n"
        if r['json_structures']:
            report += f"• Found {len(r['json_structures'])} JSON objects\n"
        else:
            report += "• None found\n"
        report += "\n"
        
        report += f"📝 **Strings** ({len(r['strings'])}):\n"
        report += f"• Extracted {len(r['strings'])} strings\n"
        report += f"• Sample: `{r['strings'][0] if r['strings'] else 'None'}`\n"
        report += "\n"
        
        report += f"🔧 **Functions** ({len(r['functions'])}):\n"
        if r['functions']:
            for f in r['functions'][:5]:
                report += f"• `{f[:50]}`\n"
        else:
            report += "• None found\n"
        
        return report
    
    def generate_dump_txt(self) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append(f"VTX DEX DUMP FILE")
        lines.append("=" * 60)
        lines.append(f"File: {self.result['file_name']}")
        lines.append(f"Size: {self.result['size']:,} bytes")
        lines.append(f"Architecture: {self.result['architecture']}")
        lines.append(f"Hash: {self.result['hash']}")
        lines.append(f"Analysis Date: {fmt_ist(now_ist())}")
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

# =============================================
# PATCH ENGINE
# =============================================
class SOPatcher:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.data = None
        self.text_data = None
        self.original_hash = hashlib.md5(open(file_path, 'rb').read()).hexdigest()
        self.changes = []
    
    def load(self):
        with open(self.file_path, 'rb') as f:
            self.data = f.read()
        self.text_data = self.data.decode('utf-8', errors='ignore')
        return True
    
    def patch_url(self, old_url: str, new_url: str) -> bool:
        if old_url in self.text_data:
            self.text_data = self.text_data.replace(old_url, new_url)
            self.changes.append(f"URL: {old_url} -> {new_url}")
            return True
        return False
    
    def patch_api_key(self, old_key: str, new_key: str) -> bool:
        if old_key in self.text_data:
            self.text_data = self.text_data.replace(old_key, new_key)
            self.changes.append(f"API Key: {old_key[:10]}... -> {new_key[:10]}...")
            return True
        return False
    
    def patch_flag(self, flag: str, value: str) -> bool:
        pattern = rf'{flag}\s*=\s*[0-9]+'
        replacement = f'{flag} = {value}'
        new_text = re.sub(pattern, replacement, self.text_data)
        if new_text != self.text_data:
            self.text_data = new_text
            self.changes.append(f"Flag: {flag} = {value}")
            return True
        return False
    
    def patch_string(self, old_str: str, new_str: str) -> bool:
        if old_str in self.text_data:
            self.text_data = self.text_data.replace(old_str, new_str)
            self.changes.append(f"String: {old_str[:20]} -> {new_str[:20]}")
            return True
        return False
    
    def save(self) -> Tuple[bool, str, str]:
        try:
            patched_data = self.text_data.encode('utf-8', errors='ignore')
            output_path = os.path.join(PATCH_DIR, f"patched_{os.path.basename(self.file_path)}")
            with open(output_path, 'wb') as f:
                f.write(patched_data)
            
            patched_hash = hashlib.md5(open(output_path, 'rb').read()).hexdigest()
            return True, output_path, patched_hash
        except Exception as e:
            return False, "", str(e)

# =============================================
# FRIDA SCRIPT GENERATORS
# =============================================
def generate_frida_hook(function_name: str) -> str:
    return f'''// VTX DEX - Frida Hook for {function_name}
Java.perform(function() {{
    console.log("[*] Hooking {function_name}...");
    
    var targetClasses = [
        "com.example.app.MainActivity",
        "com.example.app.Config",
        "com.example.app.FlagManager",
        "com.example.app.AuthManager",
        "com.example.app.SecurityManager",
        "com.example.app.Utils"
    ];
    
    for (var i = 0; i < targetClasses.length; i++) {{
        try {{
            var target = Java.use(targetClasses[i]);
            if (target && target.{function_name}) {{
                target.{function_name}.implementation = function() {{
                    console.log("[*] {function_name} called");
                    console.log("[*] Arguments: " + JSON.stringify(arguments));
                    
                    var result = this.{function_name}.apply(this, arguments);
                    console.log("[*] Return value: " + result);
                    
                    // Modify return value
                    return result;
                }};
                console.log("[+] Hooked {function_name} in " + targetClasses[i]);
            }}
        }} catch(e) {{
            // Class not found
        }}
    }}
    
    console.log("[*] Hook setup complete!");
}});'''

def generate_root_bypass() -> str:
    return '''// VTX DEX - Root Detection Bypass
Java.perform(function() {
    console.log("[*] Loading root bypass...");
    
    // Bypass common root checks
    try {
        var RootDetection = Java.use("com.example.rootdetection.RootDetection");
        RootDetection.isDeviceRooted.implementation = function() {
            console.log("[*] isDeviceRooted called - returning false");
            return false;
        };
        RootDetection.isRooted.implementation = function() {
            console.log("[*] isRooted called - returning false");
            return false;
        };
    } catch(e) {}
    
    try {
        var SafetyNet = Java.use("com.google.android.gms.safetynet.SafetyNet");
        SafetyNet.isDeviceRooted.implementation = function() {
            console.log("[*] SafetyNet.isDeviceRooted called - returning false");
            return false;
        };
    } catch(e) {}
    
    try {
        var MagiskDetector = Java.use("com.topjohnwu.magisk.detector");
        MagiskDetector.isMagiskInstalled.implementation = function() {
            console.log("[*] isMagiskInstalled called - returning false");
            return false;
        };
    } catch(e) {}
    
    console.log("[*] Root bypass loaded!");
});'''

def generate_antidebug_bypass() -> str:
    return '''// VTX DEX - Anti-Debug Bypass
Java.perform(function() {
    console.log("[*] Loading anti-debug bypass...");
    
    // Bypass ptrace
    try {
        var ptrace = Module.findExportByName("libc.so", "ptrace");
        if (ptrace) {
            Interceptor.replace(ptrace, new NativeCallback(function(request, pid, addr, data) {
                console.log("[*] ptrace called - returning 0");
                return 0;
            }, 'int', ['int', 'int', 'pointer', 'pointer']));
        }
    } catch(e) {}
    
    // Bypass TracerPid
    try {
        var BufferedReader = Java.use("java.io.BufferedReader");
        BufferedReader.readLine.implementation = function() {
            var line = this.readLine();
            if (line && line.indexOf("TracerPid") !== -1) {
                console.log("[*] Modified TracerPid to 0");
                return "TracerPid:\\t0";
            }
            return line;
        };
    } catch(e) {}
    
    console.log("[*] Anti-debug bypass loaded!");
});'''

def generate_cert_pinning_bypass() -> str:
    return '''// VTX DEX - Certificate Pinning Bypass
Java.perform(function() {
    console.log("[*] Loading certificate pinning bypass...");
    
    try {
        var TrustManager = Java.use("javax.net.ssl.X509TrustManager");
        TrustManager.checkClientTrusted.implementation = function(chain, authType) {
            console.log("[*] checkClientTrusted called - bypassed");
        };
        TrustManager.checkServerTrusted.implementation = function(chain, authType) {
            console.log("[*] checkServerTrusted called - bypassed");
        };
        TrustManager.getAcceptedIssuers.implementation = function() {
            return [];
        };
    } catch(e) {}
    
    try {
        var HostnameVerifier = Java.use("javax.net.ssl.HostnameVerifier");
        HostnameVerifier.verify.implementation = function(hostname, session) {
            console.log("[*] HostnameVerifier.verify called - returning true");
            return true;
        };
    } catch(e) {}
    
    console.log("[*] Certificate pinning bypass loaded!");
});'''

# =============================================
# JSON TO SO REPACK
# =============================================
def json_to_so_repack(json_path: str, so_path: str) -> Tuple[bool, str, str]:
    try:
        with open(json_path, 'r') as f:
            json_data = json.load(f)
        
        with open(so_path, 'rb') as f:
            so_data = f.read()
        
        json_str = json.dumps(json_data)
        json_bytes = json_str.encode('utf-8')
        
        # Add marker for extraction
        marker = b'VTX_DEX_JSON_START'
        end_marker = b'VTX_DEX_JSON_END'
        
        # Find a good place to inject (search for null bytes)
        so_data = so_data + b'\x00\x00' + marker + json_bytes + end_marker + b'\x00\x00'
        
        output_path = os.path.join(PATCH_DIR, f"repacked_{os.path.basename(so_path)}")
        with open(output_path, 'wb') as f:
            f.write(so_data)
        
        return True, output_path, "JSON injected successfully"
    except Exception as e:
        return False, "", str(e)

def extract_json_from_so(so_path: str) -> Tuple[bool, Any, str]:
    try:
        with open(so_path, 'rb') as f:
            data = f.read()
        
        text_data = data.decode('utf-8', errors='ignore')
        
        # Look for marker
        marker = 'VTX_DEX_JSON_START'
        end_marker = 'VTX_DEX_JSON_END'
        
        if marker in text_data and end_marker in text_data:
            start = text_data.index(marker) + len(marker)
            end = text_data.index(end_marker)
            json_str = text_data[start:end]
            return True, json.loads(json_str), "JSON extracted from marker"
        
        # Fallback: find any JSON
        json_pattern = r'\{[^{}]*\}'
        for match in re.findall(json_pattern, text_data):
            try:
                return True, json.loads(match), "JSON structure found"
            except:
                pass
        
        return False, None, "No JSON found"
    except Exception as e:
        return False, None, str(e)

# =============================================
# BOT APPLICATION
# =============================================
app = Application.builder().token(TOKEN).build()

# =============================================
# CONVERSATION STATES
# =============================================
(WAITING_SO, WAITING_JSON, WAITING_PATCH_DATA, WAITING_ANALYZE) = range(4)

# =============================================
# COMMAND HANDLERS
# =============================================

# ----- START -----
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
        [InlineKeyboardButton("📄 Help", callback_data="help")],
        [InlineKeyboardButton("💳 Buy", callback_data="buy")]
    ]
    
    has_key = user[2] and user[2] != 'inactive'
    key_type = user[2] if has_key else "None"
    expiry = user[5]
    left = days_left(expiry)
    status = "✅ Active" if has_key and left != "Expired" else "❌ Inactive"
    
    await update.message.reply_text(
        f"🗡️ **{BOT_NAME}**\n"
        f"🔥 Developer: {DEV_NAME}\n\n"
        f"👤 User: @{username}\n"
        f"🔑 Key Type: `{key_type}`\n"
        f"📅 Login: {fmt_ist(now_ist())}\n"
        f"⏳ Expires: `{expiry[:10] if expiry else 'None'}`\n"
        f"📊 Days Left: `{left}`\n"
        f"📈 Status: {status}\n"
        f"🔄 Used: `{user[7] if user[7] else 0}` times\n\n"
        f"**Commands:**\n"
        f"/start - Menu\n"
        f"/redeem <key> - Activate\n"
        f"/mykey - Check key\n"
        f"/analyze - Analyze .so\n"
        f"/patch - Patch .so\n"
        f"/dump - Get dump.txt\n"
        f"/json - Extract JSON\n"
        f"/repack - Inject JSON\n"
        f"/rootbypass - Root bypass\n"
        f"/antidebug - Anti-debug\n"
        f"/pinning - SSL bypass\n"
        f"/frida <func> - Frida hook\n"
        f"/help - Help\n"
        f"/buy - Pricing",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    log_action(user_id, "START")
    update_user_activity(user_id)

# ----- REDEEM -----
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

# ----- MYKEY -----
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
        f"Login: `{user[4][:10] if user[4] else 'N/A'}`\n"
        f"Expires: `{user[5][:10] if user[5] else 'N/A'}`\n"
        f"Days Left: `{days_left(user[5])}`\n"
        f"Used: `{user[7] if user[7] else 0}` times\n"
        f"Analysis: `{user[8] if user[8] else 0}`\n"
        f"Patches: `{user[9] if user[9] else 0}`\n"
        f"Banned: `{'Yes' if user[6] else 'No'}`"
    )
    update_user_activity(user_id)

# ----- ANALYZE -----
async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    await update.message.reply_text(
        "📤 **Upload .so file**\n\n"
        "Send the `.so` file you want to analyze.\n"
        "Supported: ARM32, ARM64, x86, x64\n\n"
        "I will extract:\n"
        "• Firebase URLs\n"
        "• API Keys\n"
        "• Flags\n"
        "• Strings\n"
        "• JSON structures\n"
        "• Functions\n"
        "• Hex dump"
    )
    context.user_data['action'] = 'analyze'
    return WAITING_SO

# ----- PATCH -----
async def patch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    args = context.args
    if len(args) >= 2:
        context.user_data['patch_data'] = {
            'type': 'url',
            'old': args[0],
            'new': args[1]
        }
        await update.message.reply_text(
            f"📤 Upload `.so` file to patch\n"
            f"Changing: `{args[0]}` → `{args[1]}`"
        )
        context.user_data['action'] = 'patch'
        return WAITING_SO
    
    await update.message.reply_text(
        "🔧 **Patch Options**\n\n"
        "Send a `.so` file and tell me what to patch:\n\n"
        "• `/patch <old_url> <new_url>` - URL patch\n"
        "• `/patch_api <old_key> <new_key>` - API key patch\n"
        "• `/patch_flag <flag> <value>` - Flag patch\n"
        "• `/patch_string <old> <new>` - String patch\n\n"
        "Example: `/patch https://old.com https://new.com`"
    )
    context.user_data['action'] = 'patch'

# ----- DUMP -----
async def dump(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    await update.message.reply_text(
        "📤 Upload `.so` file to generate dump.txt\n\n"
        "The dump will contain all extracted data:\n"
        "• URLs, API keys, flags\n"
        "• All strings\n"
        "• JSON structures\n"
        "• Hex dump\n"
        "• Function list"
    )
    context.user_data['action'] = 'dump'
    return WAITING_SO

# ----- JSON -----
async def json_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    await update.message.reply_text(
        "📤 Upload `.so` file to extract JSON structures.\n"
        "I will find and extract any JSON embedded in the file."
    )
    context.user_data['action'] = 'json'
    return WAITING_SO

# ----- REPACK -----
async def repack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    await update.message.reply_text(
        "📤 **Repack JSON into .so**\n\n"
        "Send the `.so` file and `.json` file.\n"
        "I will inject the JSON into the .so file.\n\n"
        "Send `.so` file first, then `.json` file."
    )
    context.user_data['action'] = 'repack'
    context.user_data['repack_step'] = 'so'
    return WAITING_SO

# ----- ROOTBYPASS -----
async def rootbypass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    script = generate_root_bypass()
    await update.message.reply_document(
        document=script.encode(),
        filename="root_bypass.js",
        caption="🔓 **Root Detection Bypass**\n\n"
                "Inject with: `frida -U -f com.example.app -l root_bypass.js`"
    )
    log_action(user_id, "ROOTBYPASS")
    update_user_activity(user_id)

# ----- ANTIDEBUG -----
async def antidebug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    script = generate_antidebug_bypass()
    await update.message.reply_document(
        document=script.encode(),
        filename="antidebug.js",
        caption="🛡️ **Anti-Debug Bypass**\n\n"
                "Inject with: `frida -U -f com.example.app -l antidebug.js`"
    )
    log_action(user_id, "ANTIDEBUG")
    update_user_activity(user_id)

# ----- PINNING -----
async def pinning(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    access, msg = check_access(user_id)
    if not access:
        await update.message.reply_text(f"⛔ {msg}")
        return
    
    script = generate_cert_pinning_bypass()
    await update.message.reply_document(
        document=script.encode(),
        filename="pinning_bypass.js",
        caption="🔓 **Certificate Pinning Bypass**\n\n"
                "Inject with: `frida -U -f com.example.app -l pinning_bypass.js`"
    )
    log_action(user_id, "PINNING")
    update_user_activity(user_id)

# ----- FRIDA -----
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
            "Generates a Frida hook for the specified function."
        )
        return
    
    func = args[0]
    script = generate_frida_hook(func)
    await update.message.reply_document(
        document=script.encode(),
        filename=f"hook_{func}.js",
        caption=f"🔫 **Frida Hook for `{func}`**\n\n"
                f"Inject with: `frida -U -f com.example.app -l hook_{func}.js`"
    )
    log_action(user_id, "FRIDA", func)
    update_user_activity(user_id)

# ----- BUY -----
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

# ----- HELP -----
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📖 **{BOT_NAME} Commands**\n\n"
        f"🔑 **Authentication**\n"
        f"/start - Show menu\n"
        f"/redeem <key> - Activate key\n"
        f"/mykey - Check key status\n\n"
        f"🔧 **Analysis**\n"
        f"/analyze - Analyze .so file\n"
        f"/patch - Patch .so file\n"
        f"/dump - Generate dump.txt\n"
        f"/json - Extract JSON from .so\n"
        f"/repack - Inject JSON into .so\n\n"
        f"🛡️ **Bypass Tools**\n"
        f"/rootbypass - Root detection bypass\n"
        f"/antidebug - Anti-debug bypass\n"
        f"/pinning - SSL pinning bypass\n"
        f"/frida <func> - Frida hook\n\n"
        f"📊 **Info**\n"
        f"/help - Show this\n"
        f"/buy - Pricing info\n\n"
        f"🔥 Developer: {DEV_NAME}"
    )

# =============================================
# FILE HANDLERS
# =============================================

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
    file_ext = os.path.splitext(file_name)[1].lower()
    
    # Download file
    file_obj = await context.bot.get_file(doc.file_id)
    file_path = os.path.join(TEMP_DIR, f"{user_id}_{file_name}")
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
    elif action == 'repack':
        step = context.user_data.get('repack_step', 'so')
        if step == 'so':
            context.user_data['so_file'] = file_path
            context.user_data['repack_step'] = 'json'
            await update.message.reply_text(
                "✅ .so file received.\n"
                "Now send the `.json` file to inject."
            )
        else:
            so_path = context.user_data.get('so_file')
            if so_path and os.path.exists(so_path):
                await process_repack(update, context, so_path, file_path)
                del context.user_data['so_file']
                del context.user_data['repack_step']
            else:
                await update.message.reply_text("❌ .so file not found. Please start again.")
                os.remove(file_path)
    else:
        await update.message.reply_text(
            "⚠️ Use a command first:\n"
            "/analyze, /patch, /dump, /json, /repack"
        )
        os.remove(file_path)
    
    context.user_data['action'] = ''

# =============================================
# PROCESS FUNCTIONS
# =============================================

async def process_analyze(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: str):
    user_id = update.effective_user.id
    await update.message.reply_text("🔍 Analyzing .so file... This may take a moment.")
    
    analyzer = SOAnalyzer(file_path)
    if hasattr(analyzer.result, 'error'):
        await update.message.reply_text(f"❌ Error: {analyzer.result['error']}")
        os.remove(file_path)
        return
    
    # Send report
    report = analyzer.get_report()
    await update.message.reply_text(report, parse_mode='Markdown')
    
    # Generate and send dump
    dump_text = analyzer.generate_dump_txt()
    dump_path = os.path.join(DUMP_DIR, f"dump_{user_id}_{analyzer.file_name}.txt")
    with open(dump_path, 'w', encoding='utf-8') as f:
        f.write(dump_text)
    
    await update.message.reply_document(
        document=open(dump_path, 'rb'),
        filename=f"dump_{analyzer.file_name}.txt",
        caption="📄 **Full dump.txt**"
    )
    
    # Save to history
    c.execute(
        "INSERT INTO analysis_history (user_id, file_name, file_hash, analysis_data, dump_path, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, analyzer.file_name, analyzer.result['hash'], json.dumps(analyzer.result), dump_path, now_ist().isoformat())
    )
    conn.commit()
    
    # Update user stats
    c.execute("UPDATE users SET total_analysis = total_analysis + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    
    log_action(user_id, "ANALYZE", analyzer.file_name)
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
    
    patcher = SOPatcher(file_path)
    patcher.load()
    
    if patch_data.get('type') == 'url':
        patcher.patch_url(patch_data['old'], patch_data['new'])
    elif patch_data.get('type') == 'api':
        patcher.patch_api_key(patch_data['old'], patch_data['new'])
    elif patch_data.get('type') == 'flag':
        patcher.patch_flag(patch_data['flag'], patch_data['value'])
    elif patch_data.get('type') == 'string':
        patcher.patch_string(patch_data['old'], patch_data['new'])
    
    success, output_path, patched_hash = patcher.save()
    
    if success:
        await update.message.reply_document(
            document=open(output_path, 'rb'),
            filename=f"patched_{os.path.basename(file_path)}",
            caption=f"✅ **Patch applied!**\n\n"
                    f"Original Hash: `{patcher.original_hash[:16]}`\n"
                    f"Patched Hash: `{patched_hash[:16]}`\n"
                    f"Changes:\n" + '\n'.join(f"• {c}" for c in patcher.changes)
        )
        
        # Save to history
        c.execute(
            "INSERT INTO patches_history (user_id, original_file, patched_file, original_hash, patched_hash, changes, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, os.path.basename(file_path), os.path.basename(output_path), patcher.original_hash, patched_hash, json.dumps(patcher.changes), now_ist().isoformat())
        )
        conn.commit()
        
        c.execute("UPDATE users SET total_patches = total_patches + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        
        log_action(user_id, "PATCH", str(patcher.changes))
        update_user_activity(user_id)
        
        os.remove(output_path)
    else:
        await update.message.reply_text(f"❌ Patch failed: {patched_hash}")
    
    os.remove(file_path)
    context.user_data['patch_data'] = {}

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
        caption="📄 **Complete dump.txt**"
    )
    
    log_action(user_id, "DUMP", analyzer.file_name)
    update_user_activity(user_id)
    
    os.remove(file_path)
    os.remove(dump_path)

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
            caption=f"✅ {msg}\n\n```json\n{json_str[:500]}\n```",
            parse_mode='Markdown'
        )
        os.remove(json_path)
    else:
        await update.message.reply_text(f"❌ {msg}")
    
    log_action(user_id, "JSON_EXTRACT", os.path.basename(file_path))
    update_user_activity(user_id)
    os.remove(file_path)

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
                    f"JSON: `{os.path.basename(json_path)}`"
        )
        os.remove(output_path)
    else:
        await update.message.reply_text(f"❌ {msg}")
    
    log_action(user_id, "REPACK", os.path.basename(so_path))
    update_user_activity(user_id)
    
    os.remove(so_path)
    os.remove(json_path)

# =============================================
# ADMIN COMMANDS
# =============================================

async def genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Admin only")
        return
    
    args = context.args
    if not args or args[0] not in ['member', 'pro', 'vip', 'lifetime']:
        await update.message.reply_text("Usage: /genkey <member|pro|vip|lifetime>")
        return
    
    key_type = args[0]
    key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
    
    c.execute("INSERT INTO keys (key, type, created_by, created_at) VALUES (?, ?, ?, ?)",
              (key, key_type, ADMIN_ID, now_ist().isoformat()))
    conn.commit()
    
    fb_put(f"keys/{key}", {
        'type': key_type,
        'created_by': ADMIN_ID,
        'created_at': now_ist().isoformat(),
        'used_by': None,
        'used_at': None
    })
    
    await update.message.reply_text(
        f"✅ Key generated:\n`{key}`\n"
        f"Type: {key_type}\n"
        f"Give: `/redeem {key}`"
    )
    log_action(ADMIN_ID, "GENKEY", f"{key_type}:{key}")

async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    c.execute("SELECT user_id, username, key_type, expiry_date, is_banned, used_count FROM users ORDER BY user_id DESC LIMIT 25")
    users = c.fetchall()
    if not users:
        await update.message.reply_text("No users")
        return
    
    text = f"👥 **Users ({BOT_NAME})**\n\n"
    for u in users:
        status = "⛔" if u[4] else "✅"
        expiry = u[3][:10] if u[3] else "None"
        text += f"{status} `{u[0]}` | @{u[1]} | {u[2]} | {expiry} | {u[5]} uses\n"
    await update.message.reply_text(text)

async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    c.execute("SELECT user_id, action, detail, timestamp FROM logs ORDER BY id DESC LIMIT 20")
    logs = c.fetchall()
    if not logs:
        await update.message.reply_text("No logs")
        return
    
    text = f"📜 **Recent Logs**\n\n"
    for log in logs:
        detail = log[2][:25] if log[2] else ""
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
    fb_patch(f"users/{user_id}", {'is_banned': 1})
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
    fb_patch(f"users/{user_id}", {'is_banned': 0})
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
    log_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM keys WHERE used_by IS NULL")
    unused = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM analysis_history")
    analysis_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM patches_history")
    patch_count = c.fetchone()[0]
    
    await update.message.reply_text(
        f"📊 **{BOT_NAME} Stats**\n\n"
        f"👥 Total Users: {total}\n"
        f"✅ Active: {active}\n"
        f"⛔ Banned: {banned}\n"
        f"🔑 Unused Keys: {unused}\n"
        f"📝 Logs: {log_count}\n"
        f"🔍 Analysis: {analysis_count}\n"
        f"🔧 Patches: {patch_count}\n"
        f"🔥 Developer: {DEV_NAME}"
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
            await context.bot.send_message(u[0], f"📢 **Broadcast**\n\n{msg}")
            sent += 1
            time.sleep(0.5)
        except:
            pass
    
    await update.message.reply_text(f"✅ Broadcast sent to {sent} users")
    log_action(ADMIN_ID, "BROADCAST", msg)

# =============================================
# CALLBACK HANDLER
# =============================================

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "redeem":
        await query.message.reply_text("🔑 /redeem <KEY>")
    elif query.data == "help":
        await help_cmd(update, context)
    elif query.data == "buy":
        await buy(update, context)

# =============================================
# REGISTER ALL HANDLERS
# =============================================

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
app.add_handler(CommandHandler("pinning", pinning))
app.add_handler(CommandHandler("frida", frida_cmd))
app.add_handler(CommandHandler("help", help_cmd))
app.add_handler(CommandHandler("buy", buy))

# Admin
app.add_handler(CommandHandler("genkey", genkey))
app.add_handler(CommandHandler("users", users))
app.add_handler(CommandHandler("logs", logs))
app.add_handler(CommandHandler("ban", ban))
app.add_handler(CommandHandler("unban", unban))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CommandHandler("broadcast", broadcast))

# File handlers
app.add_handler(MessageHandler(filters.Document.ALL & ~filters.Document.FileExtension("json"), handle_document))
app.add_handler(MessageHandler(filters.Document.FileExtension("json"), handle_document))

# Callback
app.add_handler(CallbackQueryHandler(callback))

# =============================================
# MAIN
# =============================================

if __name__ == "__main__":
    print("=" * 60)
    print(f"🗡️ {BOT_NAME} — ULTIMATE REVERSE ENGINEERING BOT")
    print("=" * 60)
    print(f"🔥 Developer: {DEV_NAME}")
    print(f"📡 Firebase: {FIREBASE_URL}")
    print(f"📊 Database: {DB_FILE}")
    print(f"👤 Admin ID: {ADMIN_ID}")
    print(f"📁 Dump Dir: {DUMP_DIR}")
    print(f"📁 Patch Dir: {PATCH_DIR}")
    print("=" * 60)
    print("✅ Bot is ONLINE and READY!")
    print("=" * 60)
    
    app.run_polling()
