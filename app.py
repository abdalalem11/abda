import os
import json
import logging
import asyncio
import sqlite3
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import signal
import sys
import time
import random
import gc
from asyncio import Queue, Semaphore
from concurrent.futures import ThreadPoolExecutor
import aiofiles
import aiohttp
from typing import Dict, Any, Optional

# ========== محاولة استيراد psutil مع معالجة الخطأ ==========
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    class FakePsutil:
        class virtual_memory:
            @staticmethod
            def percent():
                return 0
        class cpu_percent:
            @staticmethod
            def percent(interval=0.5):
                return 0
    psutil = FakePsutil()

# ========== إعدادات متقدمة ==========
MAX_BOTS = 30
BOT_CHECK_INTERVAL = 15
MAX_RETRIES = 5
RETRY_DELAY = 3
CACHE_SIZE = 10000
BATCH_SIZE = 10
HEARTBEAT_TIMEOUT = 90
MEMORY_THRESHOLD = 85
CPU_THRESHOLD = 75

# ========== نظام اللوغات المتقدم ==========
class AdvancedLogger:
    def __init__(self):
        self.setup_logging()
    
    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.logger = logging.getLogger('BotFactory')
        
        error_handler = logging.FileHandler('errors.log')
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'))
        self.logger.addHandler(error_handler)
        
        try:
            import colorlog
            handler = colorlog.StreamHandler()
            handler.setFormatter(colorlog.ColoredFormatter(
                '%(log_color)s%(asctime)s | %(levelname)-8s | %(message)s',
                datefmt='%H:%M:%S'
            ))
            self.logger.addHandler(handler)
        except:
            pass
    
    def info(self, msg): self.logger.info(msg)
    def error(self, msg): self.logger.error(msg)
    def warning(self, msg): self.logger.warning(msg)
    def debug(self, msg): self.logger.debug(msg)

logger = AdvancedLogger()

# ========== نظام المراقبة الذكي ==========
class PerformanceMonitor:
    def __init__(self):
        self.start_time = datetime.now()
        self.metrics = {
            'bot_starts': 0,
            'bot_stops': 0,
            'errors': 0,
            'messages_processed': 0,
            'avg_response_time': 0,
            'total_memory_usage': 0,
            'cpu_usage': 0,
            'active_bots': 0,
            'total_users': 0
        }
        self.response_times = []
        self.cache = {}
    
    async def collect_metrics(self):
        while True:
            try:
                global active_bots
                self.metrics['active_bots'] = len(active_bots) if 'active_bots' in globals() else 0
                
                try:
                    self.metrics['total_users'] = sum(b.get('total_users', 0) for b in db.get_all_bots())
                except:
                    self.metrics['total_users'] = 0
                
                if PSUTIL_AVAILABLE:
                    memory = psutil.virtual_memory()
                    self.metrics['total_memory_usage'] = memory.percent
                    self.metrics['cpu_usage'] = psutil.cpu_percent(interval=0.5)
                else:
                    self.metrics['total_memory_usage'] = 0
                    self.metrics['cpu_usage'] = 0
                
                if self.response_times:
                    self.metrics['avg_response_time'] = sum(self.response_times) / len(self.response_times)
                    if len(self.response_times) > 100:
                        self.response_times = self.response_times[-50:]
                
                if self.metrics['total_memory_usage'] > MEMORY_THRESHOLD and PSUTIL_AVAILABLE:
                    logger.warning(f"⚠️ عالية الذاكرة: {self.metrics['total_memory_usage']}%")
                    await self.cleanup_resources()
                
                if self.metrics['cpu_usage'] > CPU_THRESHOLD and PSUTIL_AVAILABLE:
                    logger.warning(f"⚠️ عالية المعالج: {self.metrics['cpu_usage']}%")
                    await self.optimize_bots()
                
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"مراقبة الأداء: {e}")
                await asyncio.sleep(10)
    
    async def cleanup_resources(self):
        gc.collect()
        if hasattr(self, 'cache') and len(self.cache) > CACHE_SIZE:
            self.cache.clear()
        if len(active_bots) > 25 and self.metrics['total_memory_usage'] > 90:
            logger.warning("⚠️ تقليل عدد البوتات لتخفيف الضغط")
    
    async def optimize_bots(self):
        try:
            for bot_token, app in bot_apps.items():
                if bot_token in active_bots and not active_bots[bot_token]:
                    await asyncio.sleep(0.1)
        except:
            pass

performance_monitor = PerformanceMonitor()

# ========== نظام الكاش المتقدم ==========
class AdvancedCache:
    def __init__(self, max_size=1000, ttl=300):
        self.cache = {}
        self.max_size = max_size
        self.ttl = ttl
        self.lock = asyncio.Lock()
    
    async def get(self, key):
        async with self.lock:
            if key in self.cache:
                value, timestamp = self.cache[key]
                if datetime.now().timestamp() - timestamp < self.ttl:
                    return value
                else:
                    del self.cache[key]
            return None
    
    async def set(self, key, value):
        async with self.lock:
            if len(self.cache) >= self.max_size:
                oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k][1])
                del self.cache[oldest_key]
            self.cache[key] = (value, datetime.now().timestamp())
    
    async def clear(self):
        async with self.lock:
            self.cache.clear()

cache = AdvancedCache()

# ========== قاعدة البيانات المتطورة ==========
class AdvancedDatabase:
    def __init__(self, db_path="bot_factory_pro.db"):
        self.db_path = db_path
        self.conn_pool = []
        self.max_connections = 5
        self.lock = asyncio.Lock()
        self._init_db()
    
    def _get_connection(self):
        if self.conn_pool:
            return self.conn_pool.pop()
        return sqlite3.connect(self.db_path, check_same_thread=False)
    
    def _return_connection(self, conn):
        if len(self.conn_pool) < self.max_connections:
            self.conn_pool.append(conn)
        else:
            conn.close()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-20000")
        cursor.execute("PRAGMA temp_store=MEMORY")
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_token TEXT UNIQUE NOT NULL,
                bot_name TEXT NOT NULL,
                bot_username TEXT,
                owner_id INTEGER NOT NULL,
                owner_username TEXT,
                developer_username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 0,
                total_users INTEGER DEFAULT 0,
                config TEXT,
                last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                start_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_bots_active ON bots(is_active)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_bots_owner ON bots(owner_id)
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS master_developers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                role TEXT DEFAULT 'developer'
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_token TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                first_use TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_use TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message_count INTEGER DEFAULT 0,
                UNIQUE(bot_token, user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_users_bot ON bot_users(bot_token)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_users_last ON bot_users(last_use)
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_token TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                name TEXT,
                username TEXT,
                message TEXT,
                time TEXT,
                UNIQUE(bot_token, user_id, message)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                bot_token TEXT,
                message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_logs_bot ON system_logs(bot_token)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_logs_time ON system_logs(created_at)
        ''')
        
        conn.commit()
        conn.close()
        
        try:
            self.add_master_developer(MASTER_OWNER_ID, "SSSTlF")
        except:
            pass
    
    def execute(self, query, params=None, commit=True):
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            if commit:
                conn.commit()
            
            result = cursor.fetchall()
            return result
        except Exception as e:
            logger.error(f"قاعدة البيانات خطأ: {e}")
            conn.rollback()
            raise
        finally:
            self._return_connection(conn)
    
    def add_master_developer(self, user_id, username):
        try:
            self.execute(
                "INSERT OR REPLACE INTO master_developers (user_id, username, role) VALUES (?, ?, ?)",
                (user_id, username, 'owner')
            )
            return True
        except Exception as e:
            logger.error(f"إضافة المطور: {e}")
            return False
    
    def add_bot(self, bot_token, bot_name, bot_username, owner_id, owner_username, developer_username):
        try:
            result = self.execute("SELECT COUNT(*) FROM bots WHERE is_active = 1")
            active_count = result[0][0] if result else 0
            
            if active_count >= MAX_BOTS:
                return None, f"الحد الأقصى ({MAX_BOTS}) بوت"
            
            self.execute(
                '''INSERT INTO bots 
                   (bot_token, bot_name, bot_username, owner_id, owner_username, developer_username, is_active, start_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (bot_token, bot_name, bot_username, owner_id, owner_username, developer_username, 1, 1)
            )
            return self.execute("SELECT last_insert_rowid()")[0][0], "تم التسجيل ✅"
        except Exception as e:
            logger.error(f"إضافة البوت: {e}")
            return None, f"خطأ: {str(e)}"
    
    def get_bot(self, bot_token):
        result = self.execute("SELECT * FROM bots WHERE bot_token = ?", (bot_token,))
        if result:
            columns = ['id', 'bot_token', 'bot_name', 'bot_username', 'owner_id', 'owner_username', 
                      'developer_username', 'created_at', 'is_active', 'total_users', 'config', 
                      'last_heartbeat', 'start_count', 'error_count']
            return dict(zip(columns, result[0]))
        return None
    
    def get_all_bots(self):
        result = self.execute("SELECT * FROM bots WHERE is_active = 1 ORDER BY created_at DESC")
        columns = ['id', 'bot_token', 'bot_name', 'bot_username', 'owner_id', 'owner_username', 
                  'developer_username', 'created_at', 'is_active', 'total_users', 'config', 
                  'last_heartbeat', 'start_count', 'error_count']
        return [dict(zip(columns, row)) for row in result]
    
    def delete_bot(self, bot_token):
        self.execute("DELETE FROM bots WHERE bot_token = ?", (bot_token,))
        self.execute("DELETE FROM bot_users WHERE bot_token = ?", (bot_token,))
        self.execute("DELETE FROM bot_replies WHERE bot_token = ?", (bot_token,))
    
    def update_heartbeat(self, bot_token):
        self.execute("UPDATE bots SET last_heartbeat = CURRENT_TIMESTAMP WHERE bot_token = ?", (bot_token,))
    
    def increment_errors(self, bot_token):
        self.execute("UPDATE bots SET error_count = error_count + 1 WHERE bot_token = ?", (bot_token,))
    
    def close(self):
        for conn in self.conn_pool:
            conn.close()

db = AdvancedDatabase()

# ========== نظام إدارة البوتات المتقدم ==========
class BotManager:
    def __init__(self):
        self.active_bots = {}
        self.bot_tasks = {}
        self.bot_apps = {}
        self.bot_queues = {}
        self.semaphore = Semaphore(MAX_BOTS)
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.lock = asyncio.Lock()
    
    async def start_bot(self, bot_token, owner_id, developer_username):
        async with self.semaphore:
            try:
                if PSUTIL_AVAILABLE:
                    memory = psutil.virtual_memory()
                    if memory.percent > 90:
                        logger.warning(f"⚠️ ذاكرة منخفضة: {memory.percent}%، تأخير بدء البوت")
                        await asyncio.sleep(5)
                
                self.bot_queues[bot_token] = Queue(maxsize=200)
                
                task = asyncio.create_task(
                    self._run_bot_async(bot_token, owner_id, developer_username)
                )
                self.bot_tasks[bot_token] = task
                self.active_bots[bot_token] = True
                
                await asyncio.sleep(2)
                
                if bot_token in self.active_bots and self.active_bots[bot_token]:
                    logger.info(f"✅ بدء البوت: {bot_token[:10]}...")
                    return True, "تم التشغيل ✅"
                else:
                    return False, "فشل بدء التشغيل"
                
            except Exception as e:
                logger.error(f"خطأ بدء البوت: {e}")
                return False, str(e)
    
    async def stop_bot(self, bot_token):
        try:
            if bot_token in self.active_bots:
                self.active_bots[bot_token] = False
            
            if bot_token in self.bot_apps:
                app = self.bot_apps[bot_token]
                try:
                    await app.updater.stop()
                except:
                    pass
                try:
                    await app.stop()
                except:
                    pass
                try:
                    await app.shutdown()
                except:
                    pass
                del self.bot_apps[bot_token]
            
            if bot_token in self.bot_tasks:
                task = self.bot_tasks[bot_token]
                if not task.done():
                    task.cancel()
                del self.bot_tasks[bot_token]
            
            if bot_token in self.bot_queues:
                del self.bot_queues[bot_token]
            
            logger.info(f"⏹️ إيقاف البوت: {bot_token[:10]}")
            return True, "تم الإيقاف ✅"
        except Exception as e:
            logger.error(f"خطأ إيقاف البوت: {e}")
            return False, str(e)
    
    async def restart_bot(self, bot_token, owner_id, developer_username):
        await self.stop_bot(bot_token)
        await asyncio.sleep(2)
        return await self.start_bot(bot_token, owner_id, developer_username)
    
    async def _run_bot_async(self, bot_token, owner_id, developer_username):
        retry_count = 0
        
        while retry_count < MAX_RETRIES:
            try:
                app = Application.builder().token(bot_token).build()
                
                await self._setup_handlers(app, bot_token, owner_id, developer_username)
                
                await app.initialize()
                await app.start()
                
                try:
                    await app.bot.delete_webhook()
                    await app.updater.start_polling(
                        drop_pending_updates=True,
                        allowed_updates=["message", "callback_query"],
                        poll_interval=1.0,
                        timeout=10
                    )
                except Exception as e:
                    logger.warning(f"Polling error for {bot_token[:10]}: {e}")
                    await asyncio.sleep(2)
                    await app.updater.start_polling(drop_pending_updates=True)
                
                self.bot_apps[bot_token] = app
                
                logger.info(f"✅ البوت جاهز: {bot_token[:10]}...")
                
                while self.active_bots.get(bot_token, False):
                    try:
                        db.update_heartbeat(bot_token)
                        await asyncio.sleep(BOT_CHECK_INTERVAL)
                    except Exception as e:
                        logger.error(f"Heartbeat error: {e}")
                        await asyncio.sleep(5)
                
                break
                
            except Exception as e:
                retry_count += 1
                logger.error(f"❌ خطأ البوت {bot_token[:10]}: {e} (محاولة {retry_count}/{MAX_RETRIES})")
                db.increment_errors(bot_token)
                
                if retry_count < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY * retry_count)
                else:
                    self.active_bots[bot_token] = False
                    logger.error(f"❌ توقف البوت: {bot_token[:10]} بعد {MAX_RETRIES} محاولات")
                    break
    
    async def _setup_handlers(self, app, bot_token, owner_id, developer_username):
        DATA_FILE = f"data/bot_{bot_token[:10]}.json"
        REPLIES_FILE = f"data/replies_{bot_token[:10]}.json"
        
        os.makedirs("data", exist_ok=True)
        
        async def load_data():
            try:
                async with aiofiles.open(DATA_FILE, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    return json.loads(content)
            except:
                return {"users": [], "banned_users": [], "bot_active": True, "total_users": 0}
        
        async def save_data(data):
            async with aiofiles.open(DATA_FILE, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, ensure_ascii=False, indent=2))
        
        async def load_replies():
            try:
                async with aiofiles.open(REPLIES_FILE, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    return json.loads(content)
            except:
                return {}
        
        async def save_replies(replies):
            async with aiofiles.open(REPLIES_FILE, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(replies, ensure_ascii=False, indent=2))
        
        if not os.path.exists(DATA_FILE):
            await save_data({"users": [], "banned_users": [], "bot_active": True, "total_users": 0})
        if not os.path.exists(REPLIES_FILE):
            await save_replies({})
        
        # ========== الأوامر الجديدة ==========
        async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            await update.message.reply_text(
                f"📖 **المساعدة**\n\n"
                f"/start - القائمة الرئيسية\n"
                f"/help - هذه المساعدة\n"
                f"/dev - المطور\n"
                f"/panel - لوحة التحكم\n"
                f"/cancel - إلغاء العملية\n\n"
                f"👨‍💻 المطور: @SSSTlF",
                parse_mode="Markdown"
            )

        async def dev_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            await update.message.reply_text(
                f"👨‍💻 **المطور**\n\n"
                f"البوت من تصميم:\n"
                f"✨ @SSSTlF ✨\n\n"
                f"📌 للتواصل: @SSSTlF",
                parse_mode="Markdown",
                disable_web_page_preview=True
            )

        async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            context.user_data.clear()
            await update.message.reply_text("❌ **تم الإلغاء.**", parse_mode="Markdown")

        async def panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.message.from_user.id
            if user_id != owner_id and user_id != MASTER_OWNER_ID:
                await update.message.reply_text("🚫 **هذا الأمر مخصص للمطور فقط.**", parse_mode="Markdown")
                return
            
            data = await load_data()
            keyboard = [
                [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
                [InlineKeyboardButton("⏸️ تعطيل البوت", callback_data="admin_disable") if data["bot_active"] 
                 else InlineKeyboardButton("▶️ تفعيل البوت", callback_data="admin_enable")],
                [InlineKeyboardButton("🚫 حظر مستخدم", callback_data="admin_ban")],
                [InlineKeyboardButton("✅ الغاء حظر", callback_data="admin_unban")],
                [InlineKeyboardButton("📋 المحظورين", callback_data="admin_banned_list")],
                [InlineKeyboardButton("📩 جميع الرسائل", callback_data="show_all_messages")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            status = "🟢 مفعل" if data["bot_active"] else "🔴 معطل"
            await update.message.reply_text(
                f"⚙️ **لوحة التحكم**\n\n"
                f"👨‍💻 المطور: {developer_username}\n"
                f"📊 المستخدمين: {data['total_users']}\n"
                f"🚫 المحظورين: {len(data['banned_users'])}\n"
                f"📌 الحالة: {status}",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )

        async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            try:
                user_id = update.message.from_user.id
                user_name = update.message.from_user.first_name
                username = update.message.from_user.username
                
                data = await load_data()
                
                if str(user_id) in data["banned_users"] and user_id != owner_id and user_id != MASTER_OWNER_ID:
                    await update.message.reply_text("🚫 **أنت محظور**\n@SSSTlF", parse_mode="Markdown")
                    return
                
                if str(user_id) not in data["users"]:
                    data["users"].append(str(user_id))
                    data["total_users"] = len(data["users"])
                    await save_data(data)
                    
                    try:
                        await context.bot.send_message(
                            chat_id=owner_id,
                            text=f"🆕 **مستخدم جديد!**\n\n👤 {user_name}\n🆔 @{username or 'لا يوجد'}\n🔢 `{user_id}`",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
                
                keyboard = [
                    [InlineKeyboardButton("📩 رسالة", callback_data="send_message"),
                     InlineKeyboardButton("🖼️ صورة", callback_data="send_photo")],
                    [InlineKeyboardButton("🎥 فيديو", callback_data="send_video"),
                     InlineKeyboardButton("🎵 صوت", callback_data="send_audio")],
                    [InlineKeyboardButton("📎 ملف", callback_data="send_document"),
                     InlineKeyboardButton("🏷️ ملصق", callback_data="send_sticker")],
                ]
                
                if user_id == owner_id or user_id == MASTER_OWNER_ID:
                    keyboard.append([InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="admin_panel")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"📩 **بوت التواصل مع المطور**\n\n"
                    f"👨‍💻 **المطور:** {developer_username}\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"📌 **اختر ما تريد إرساله**\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"⚡ بوت سريع وفعال\n"
                    f"🔧 @SSSTlF",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
                
                if hasattr(performance_monitor, 'response_times'):
                    performance_monitor.response_times.append(0.5)
                
            except Exception as e:
                logger.error(f"Start error: {e}")
        
        async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            try:
                query = update.callback_query
                await query.answer()
                
                data = await load_data()
                user_id = query.from_user.id
                
                if str(user_id) in data["banned_users"] and user_id != owner_id and user_id != MASTER_OWNER_ID:
                    await query.edit_message_text("🚫 **محظور**", parse_mode="Markdown")
                    return
                
                data_callback = query.data

                # ========== رد برسالة مخصصة ==========
                if data_callback.startswith("reply_custom_"):
                    target_id = int(data_callback.split('_')[2])
                    context.user_data['replying_to_custom'] = target_id
                    context.user_data['waiting_for'] = 'custom_reply'
                    await query.edit_message_text(
                        f"✏️ **أرسل رسالتك المخصصة للرد**\n👤 للمستخدم: `{target_id}`\n\nلإلغاء: /cancel",
                        parse_mode="Markdown"
                    )
                    return

                # ========== ردود المطور ==========
                elif data_callback.startswith("reply_photo_"):
                    target_id = int(data_callback.split('_')[2])
                    context.user_data['replying_to_photo'] = target_id
                    context.user_data['waiting_for'] = 'reply_photo'
                    await query.edit_message_text(f"🖼️ **أرسل الصورة التي تريد الرد بها**\n👤 للمستخدم: `{target_id}`\nلإلغاء: /cancel", parse_mode="Markdown")
                    return

                elif data_callback.startswith("reply_video_"):
                    target_id = int(data_callback.split('_')[2])
                    context.user_data['replying_to_video'] = target_id
                    context.user_data['waiting_for'] = 'reply_video'
                    await query.edit_message_text(f"🎥 **أرسل الفيديو الذي تريد الرد به**\n👤 للمستخدم: `{target_id}`\nلإلغاء: /cancel", parse_mode="Markdown")
                    return

                elif data_callback.startswith("reply_audio_"):
                    target_id = int(data_callback.split('_')[2])
                    context.user_data['replying_to_audio'] = target_id
                    context.user_data['waiting_for'] = 'reply_audio'
                    await query.edit_message_text(f"🎵 **أرسل الصوت الذي تريد الرد به**\n👤 للمستخدم: `{target_id}`\nلإلغاء: /cancel", parse_mode="Markdown")
                    return

                elif data_callback.startswith("reply_sticker_"):
                    target_id = int(data_callback.split('_')[2])
                    context.user_data['replying_to_sticker'] = target_id
                    context.user_data['waiting_for'] = 'reply_sticker'
                    await query.edit_message_text(f"🏷️ **أرسل الملصق الذي تريد الرد به**\n👤 للمستخدم: `{target_id}`\nلإلغاء: /cancel", parse_mode="Markdown")
                    return

                elif data_callback.startswith("reply_document_"):
                    target_id = int(data_callback.split('_')[2])
                    context.user_data['replying_to_document'] = target_id
                    context.user_data['waiting_for'] = 'reply_document'
                    await query.edit_message_text(f"📎 **أرسل الملف الذي تريد الرد به**\n👤 للمستخدم: `{target_id}`\nلإلغاء: /cancel", parse_mode="Markdown")
                    return
                
                # ========== عرض المحظورين ==========
                elif data_callback == "admin_banned_list" and (user_id == owner_id or user_id == MASTER_OWNER_ID):
                    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    if data["banned_users"]:
                        banned_list = "\n".join([f"🚫 `{uid}`" for uid in data["banned_users"]])
                        await query.edit_message_text(
                            f"📋 **المحظورين**\n\n{banned_list}\n\nالعدد: {len(data['banned_users'])}",
                            reply_markup=reply_markup,
                            parse_mode="Markdown"
                        )
                    else:
                        await query.edit_message_text("✅ **لا يوجد محظورين.**", reply_markup=reply_markup, parse_mode="Markdown")

                # ========== عرض جميع الرسائل ==========
                elif data_callback == "show_all_messages" and (user_id == owner_id or user_id == MASTER_OWNER_ID):
                    replies = await load_replies()
                    if not replies:
                        await query.edit_message_text("📭 **لا توجد رسائل.**", parse_mode="Markdown")
                        return
                    
                    message_list = []
                    for uid, msg_data in list(replies.items())[-10:]:
                        message_list.append(
                            f"━━━━━━━━━━━━━━━━━━━\n"
                            f"👤 {msg_data['name']}\n"
                            f"🆔 `{uid}`\n"
                            f"📝 {msg_data['message'][:50]}...\n"
                            f"⏰ {msg_data['time']}"
                        )
                    
                    messages_text = "\n".join(message_list)
                    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await query.edit_message_text(
                        f"📋 **آخر الرسائل ({len(replies)})**\n\n{messages_text}",
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
                    return
                
                elif data_callback == "send_message":
                    context.user_data['waiting_for'] = 'message_to_dev'
                    await query.edit_message_text("📝 **أرسل رسالتك الآن**\nللمطور @SSSTlF\n⚠️ المحتوى المخالف = حظر فوري", parse_mode="Markdown")
                
                elif data_callback == "send_photo":
                    context.user_data['waiting_for'] = 'photo_to_dev'
                    await query.edit_message_text("🖼️ **أرسل الصورة الآن**\nللمطور @SSSTlF", parse_mode="Markdown")
                
                elif data_callback == "send_video":
                    context.user_data['waiting_for'] = 'video_to_dev'
                    await query.edit_message_text("🎥 **أرسل الفيديو الآن**\nللمطور @SSSTlF", parse_mode="Markdown")
                
                elif data_callback == "send_audio":
                    context.user_data['waiting_for'] = 'audio_to_dev'
                    await query.edit_message_text("🎵 **أرسل الصوت الآن**\nللمطور @SSSTlF", parse_mode="Markdown")
                
                elif data_callback == "send_document":
                    context.user_data['waiting_for'] = 'document_to_dev'
                    await query.edit_message_text("📎 **أرسل الملف الآن**\nللمطور @SSSTlF", parse_mode="Markdown")
                
                elif data_callback == "send_sticker":
                    context.user_data['waiting_for'] = 'sticker_to_dev'
                    await query.edit_message_text("🏷️ **أرسل الملصق الآن**\nللمطور @SSSTlF", parse_mode="Markdown")

                elif data_callback == "back_to_start":
                    keyboard = [
                        [InlineKeyboardButton("📩 رسالة", callback_data="send_message"),
                         InlineKeyboardButton("🖼️ صورة", callback_data="send_photo")],
                        [InlineKeyboardButton("🎥 فيديو", callback_data="send_video"),
                         InlineKeyboardButton("🎵 صوت", callback_data="send_audio")],
                        [InlineKeyboardButton("📎 ملف", callback_data="send_document"),
                         InlineKeyboardButton("🏷️ ملصق", callback_data="send_sticker")],
                    ]
                    if user_id == owner_id or user_id == MASTER_OWNER_ID:
                        keyboard.append([InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="admin_panel")])
                    
                    await query.edit_message_text(
                        f"📩 **بوت التواصل**\n\n"
                        f"👨‍💻 {developer_username}\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"📌 **اختر ما تريد إرساله**\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"⚡ @SSSTlF",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode="Markdown"
                    )
                
                elif data_callback == "admin_panel" and (user_id == owner_id or user_id == MASTER_OWNER_ID):
                    keyboard = [
                        [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
                        [InlineKeyboardButton("⏸️ تعطيل", callback_data="admin_disable") if data["bot_active"] 
                         else InlineKeyboardButton("▶️ تفعيل", callback_data="admin_enable")],
                        [InlineKeyboardButton("🚫 حظر", callback_data="admin_ban")],
                        [InlineKeyboardButton("✅ الغاء حظر", callback_data="admin_unban")],
                        [InlineKeyboardButton("📋 المحظورين", callback_data="admin_banned_list")],
                        [InlineKeyboardButton("📩 جميع الرسائل", callback_data="show_all_messages")],
                        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")],
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    status = "🟢 مفعل" if data["bot_active"] else "🔴 معطل"
                    await query.edit_message_text(
                        f"⚙️ **لوحة التحكم**\n\n"
                        f"👨‍💻 {developer_username}\n"
                        f"👥 {data['total_users']}\n"
                        f"🚫 {len(data['banned_users'])}\n"
                        f"📌 {status}",
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
                
                elif data_callback == "admin_stats" and (user_id == owner_id or user_id == MASTER_OWNER_ID):
                    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await query.edit_message_text(
                        f"📊 **الإحصائيات**\n\n"
                        f"👥 المستخدمين: {data['total_users']}\n"
                        f"🚫 المحظورين: {len(data['banned_users'])}\n"
                        f"📌 الحالة: {'🟢 مفعل' if data['bot_active'] else '🔴 معطل'}\n"
                        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        reply_markup=reply_markup,
                        parse_mode="Markdown"
                    )
                
                elif data_callback == "admin_disable" and (user_id == owner_id or user_id == MASTER_OWNER_ID):
                    data["bot_active"] = False
                    await save_data(data)
                    await query.edit_message_text("⏸️ **تم التعطيل**", parse_mode="Markdown")
                
                elif data_callback == "admin_enable" and (user_id == owner_id or user_id == MASTER_OWNER_ID):
                    data["bot_active"] = True
                    await save_data(data)
                    await query.edit_message_text("▶️ **تم التفعيل**", parse_mode="Markdown")
                
                elif data_callback == "admin_ban" and (user_id == owner_id or user_id == MASTER_OWNER_ID):
                    context.user_data['waiting_for'] = 'ban_user'
                    await query.edit_message_text("🚫 **حظر مستخدم**\nأرسل الآيدي:", parse_mode="Markdown")
                
                elif data_callback == "admin_unban" and (user_id == owner_id or user_id == MASTER_OWNER_ID):
                    context.user_data['waiting_for'] = 'unban_user'
                    await query.edit_message_text("✅ **الغاء حظر**\nأرسل الآيدي:", parse_mode="Markdown")
                
            except Exception as e:
                logger.error(f"Button handler error: {e}")
        
        async def handle_custom_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
            try:
                user_id = update.message.from_user.id
                user_message = update.message.text
                
                if user_id != owner_id and user_id != MASTER_OWNER_ID:
                    return
                
                if context.user_data.get('waiting_for') != 'custom_reply':
                    return
                
                target_id = context.user_data.get('replying_to_custom')
                if not target_id:
                    await update.message.reply_text("❌ لا يوجد مستخدم مستهدف.", parse_mode="Markdown")
                    context.user_data.clear()
                    return
                
                try:
                    await context.bot.send_message(
                        chat_id=target_id,
                        text=f"📩 **رد من المطور @SSSTlF**\n\n{user_message}",
                        parse_mode="Markdown"
                    )
                    
                    await update.message.reply_text(
                        f"✅ **تم الإرسال!**\n👤 `{target_id}`\n📝 {user_message}",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    await update.message.reply_text(
                        f"❌ **خطأ:** لم يتمكن البوت من إرسال الرد.",
                        parse_mode="Markdown"
                    )
                
                context.user_data.clear()
                
            except Exception as e:
                logger.error(f"Error in handle_custom_reply: {e}")

        async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            try:
                user_id = update.message.from_user.id
                user_name = update.message.from_user.first_name
                username = update.message.from_user.username
                user_message = update.message.text
                
                # ========== معالج الرد المخصص ==========
                if (user_id == owner_id or user_id == MASTER_OWNER_ID) and context.user_data.get('waiting_for') == 'custom_reply':
                    await handle_custom_reply(update, context)
                    return
                
                if user_message and user_message.lower() == "/cancel":
                    context.user_data.clear()
                    await update.message.reply_text("❌ **تم الإلغاء.**", parse_mode="Markdown")
                    return
                
                data = await load_data()
                
                if str(user_id) in data["banned_users"] and user_id != owner_id and user_id != MASTER_OWNER_ID:
                    await update.message.reply_text("🚫 **محظور**", parse_mode="Markdown")
                    return
                
                if not data["bot_active"] and user_id != owner_id and user_id != MASTER_OWNER_ID:
                    await update.message.reply_text("⏸️ **البوت معطل.**", parse_mode="Markdown")
                    return

                # ========== أوامر المطور ==========
                if user_id == owner_id or user_id == MASTER_OWNER_ID:
                    if context.user_data.get('waiting_for') == 'ban_user':
                        try:
                            target_id = int(user_message.strip())
                            if str(target_id) not in data["banned_users"]:
                                data["banned_users"].append(str(target_id))
                                await save_data(data)
                                await update.message.reply_text(f"✅ **تم حظر `{target_id}`**", parse_mode="Markdown")
                            else:
                                await update.message.reply_text("⚠️ **محظور بالفعل.**", parse_mode="Markdown")
                            context.user_data['waiting_for'] = None
                        except ValueError:
                            await update.message.reply_text("❌ **أرسل أرقام فقط.**", parse_mode="Markdown")
                        return
                    
                    elif context.user_data.get('waiting_for') == 'unban_user':
                        try:
                            target_id = int(user_message.strip())
                            if str(target_id) in data["banned_users"]:
                                data["banned_users"].remove(str(target_id))
                                await save_data(data)
                                await update.message.reply_text(f"✅ **تم الغاء حظر `{target_id}`**", parse_mode="Markdown")
                            else:
                                await update.message.reply_text("⚠️ **غير محظور.**", parse_mode="Markdown")
                            context.user_data['waiting_for'] = None
                        except ValueError:
                            await update.message.reply_text("❌ **أرسل أرقام فقط.**", parse_mode="Markdown")
                        return

                # ========== إرسال رسالة للمطور ==========
                if context.user_data.get('waiting_for') == 'message_to_dev':
                    try:
                        replies = await load_replies()
                        replies[str(user_id)] = {
                            "name": user_name,
                            "username": username,
                            "message": user_message,
                            "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            "user_id": user_id
                        }
                        await save_replies(replies)
                        
                        # ========== أزرار الرد ==========
                        keyboard = [
                            [
                                InlineKeyboardButton("✏️ رد برسالة", callback_data=f"reply_custom_{user_id}"),
                            ],
                            [
                                InlineKeyboardButton("🖼️ رد بصورة", callback_data=f"reply_photo_{user_id}"),
                                InlineKeyboardButton("🎥 رد بفيديو", callback_data=f"reply_video_{user_id}"),
                            ],
                            [
                                InlineKeyboardButton("🎵 رد بصوت", callback_data=f"reply_audio_{user_id}"),
                                InlineKeyboardButton("🏷️ رد بملصق", callback_data=f"reply_sticker_{user_id}"),
                            ],
                            [
                                InlineKeyboardButton("📎 رد بملف", callback_data=f"reply_document_{user_id}"),
                                InlineKeyboardButton("📋 جميع الرسائل", callback_data="show_all_messages"),
                            ],
                            [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")],
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await context.bot.send_message(
                            chat_id=owner_id,
                            text=f"📩 **رسالة جديدة**\n\n👤 {user_name}\n🆔 @{username or 'لا يوجد'}\n🔢 `{user_id}`\n\n📝 {user_message}\n\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                            reply_markup=reply_markup,
                            parse_mode="Markdown"
                        )
                        
                        await update.message.reply_text("✅ **تم الإرسال!**\n\n📨 سيتم الرد عليك قريباً.", parse_mode="Markdown")
                        context.user_data['waiting_for'] = None
                        
                    except Exception as e:
                        await update.message.reply_text("❌ حدث خطأ.", parse_mode="Markdown")
                        logger.error(f"Error: {e}")
                    return
                
                await update.message.reply_text("📩 استخدم /start للتواصل.", parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Error in message_handler: {e}")

        async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
            try:
                user_id = update.message.from_user.id
                user_name = update.message.from_user.first_name
                username = update.message.from_user.username
                photo_file = update.message.photo[-1]
                caption = update.message.caption or "بدون تعليق"
                
                data = await load_data()
                if str(user_id) in data["banned_users"] and user_id != owner_id and user_id != MASTER_OWNER_ID:
                    await update.message.reply_text("🚫 محظور.", parse_mode="Markdown")
                    return

                if (user_id == owner_id or user_id == MASTER_OWNER_ID) and context.user_data.get('waiting_for') == 'reply_photo':
                    target_id = context.user_data.get('replying_to_photo')
                    if target_id:
                        try:
                            await context.bot.send_photo(chat_id=target_id, photo=photo_file.file_id)
                            await update.message.reply_text(f"✅ **تم الرد بالصورة** 👤 `{target_id}`", parse_mode="Markdown")
                        except Exception as e:
                            await update.message.reply_text("❌ فشل الإرسال.", parse_mode="Markdown")
                        context.user_data.clear()
                    return

                if context.user_data.get('waiting_for') == 'photo_to_dev':
                    try:
                        await context.bot.send_photo(
                            chat_id=owner_id,
                            photo=photo_file.file_id,
                            caption=f"🖼️ **صورة جديدة**\n\n👤 {user_name}\n🆔 @{username or 'لا يوجد'}\n🔢 `{user_id}`\n📝 {caption}\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                        
                        keyboard = [
                            [
                                InlineKeyboardButton("✏️ رد برسالة", callback_data=f"reply_custom_{user_id}"),
                            ],
                            [
                                InlineKeyboardButton("🖼️ رد بصورة", callback_data=f"reply_photo_{user_id}"),
                                InlineKeyboardButton("🎥 رد بفيديو", callback_data=f"reply_video_{user_id}"),
                            ],
                            [
                                InlineKeyboardButton("🎵 رد بصوت", callback_data=f"reply_audio_{user_id}"),
                                InlineKeyboardButton("🏷️ رد بملصق", callback_data=f"reply_sticker_{user_id}"),
                            ],
                            [
                                InlineKeyboardButton("📎 رد بملف", callback_data=f"reply_document_{user_id}"),
                                InlineKeyboardButton("📋 جميع الرسائل", callback_data="show_all_messages"),
                            ],
                            [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")],
                        ]
                        await context.bot.send_message(
                            chat_id=owner_id,
                            text=f"📌 للرد على هذه الصورة:",
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                        
                        await update.message.reply_text("✅ **تم الإرسال!**", parse_mode="Markdown")
                        context.user_data['waiting_for'] = None
                    except Exception as e:
                        await update.message.reply_text("❌ حدث خطأ.", parse_mode="Markdown")
                        logger.error(f"Error: {e}")
                    return
                
                await update.message.reply_text("📸 استخدم /start للإرسال.", parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Error in handle_photo: {e}")

        async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
            try:
                user_id = update.message.from_user.id
                user_name = update.message.from_user.first_name
                username = update.message.from_user.username
                video_file = update.message.video
                caption = update.message.caption or "بدون تعليق"
                
                data = await load_data()
                if str(user_id) in data["banned_users"] and user_id != owner_id and user_id != MASTER_OWNER_ID:
                    await update.message.reply_text("🚫 محظور.", parse_mode="Markdown")
                    return

                if (user_id == owner_id or user_id == MASTER_OWNER_ID) and context.user_data.get('waiting_for') == 'reply_video':
                    target_id = context.user_data.get('replying_to_video')
                    if target_id:
                        try:
                            await context.bot.send_video(chat_id=target_id, video=video_file.file_id)
                            await update.message.reply_text(f"✅ **تم الرد بالفيديو** 👤 `{target_id}`", parse_mode="Markdown")
                        except Exception as e:
                            await update.message.reply_text("❌ فشل الإرسال.", parse_mode="Markdown")
                        context.user_data.clear()
                    return

                if context.user_data.get('waiting_for') == 'video_to_dev':
                    try:
                        await context.bot.send_video(
                            chat_id=owner_id,
                            video=video_file.file_id,
                            caption=f"🎥 **فيديو جديد**\n\n👤 {user_name}\n🆔 @{username or 'لا يوجد'}\n🔢 `{user_id}`\n📝 {caption}\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                        
                        keyboard = [
                            [
                                InlineKeyboardButton("✏️ رد برسالة", callback_data=f"reply_custom_{user_id}"),
                            ],
                            [
                                InlineKeyboardButton("🖼️ رد بصورة", callback_data=f"reply_photo_{user_id}"),
                                InlineKeyboardButton("🎥 رد بفيديو", callback_data=f"reply_video_{user_id}"),
                            ],
                            [
                                InlineKeyboardButton("🎵 رد بصوت", callback_data=f"reply_audio_{user_id}"),
                                InlineKeyboardButton("🏷️ رد بملصق", callback_data=f"reply_sticker_{user_id}"),
                            ],
                            [
                                InlineKeyboardButton("📎 رد بملف", callback_data=f"reply_document_{user_id}"),
                                InlineKeyboardButton("📋 جميع الرسائل", callback_data="show_all_messages"),
                            ],
                            [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")],
                        ]
                        await context.bot.send_message(
                            chat_id=owner_id,
                            text=f"📌 للرد على هذا الفيديو:",
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                        
                        await update.message.reply_text("✅ **تم الإرسال!**", parse_mode="Markdown")
                        context.user_data['waiting_for'] = None
                    except Exception as e:
                        await update.message.reply_text("❌ حدث خطأ.", parse_mode="Markdown")
                        logger.error(f"Error: {e}")
                    return
                
                await update.message.reply_text("🎥 استخدم /start للإرسال.", parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Error in handle_video: {e}")

        async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
            try:
                user_id = update.message.from_user.id
                user_name = update.message.from_user.first_name
                username = update.message.from_user.username
                audio_file = update.message.audio
                caption = update.message.caption or "بدون تعليق"
                
                data = await load_data()
                if str(user_id) in data["banned_users"] and user_id != owner_id and user_id != MASTER_OWNER_ID:
                    await update.message.reply_text("🚫 محظور.", parse_mode="Markdown")
                    return

                if (user_id == owner_id or user_id == MASTER_OWNER_ID) and context.user_data.get('waiting_for') == 'reply_audio':
                    target_id = context.user_data.get('replying_to_audio')
                    if target_id:
                        try:
                            await context.bot.send_audio(chat_id=target_id, audio=audio_file.file_id)
                            await update.message.reply_text(f"✅ **تم الرد بالصوت** 👤 `{target_id}`", parse_mode="Markdown")
                        except Exception as e:
                            await update.message.reply_text("❌ فشل الإرسال.", parse_mode="Markdown")
                        context.user_data.clear()
                    return

                if context.user_data.get('waiting_for') == 'audio_to_dev':
                    try:
                        await context.bot.send_audio(
                            chat_id=owner_id,
                            audio=audio_file.file_id,
                            caption=f"🎵 **ملف صوتي جديد**\n\n👤 {user_name}\n🆔 @{username or 'لا يوجد'}\n🔢 `{user_id}`\n📝 {caption}\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                        
                        keyboard = [
                            [
                                InlineKeyboardButton("✏️ رد برسالة", callback_data=f"reply_custom_{user_id}"),
                            ],
                            [
                                InlineKeyboardButton("🖼️ رد بصورة", callback_data=f"reply_photo_{user_id}"),
                                InlineKeyboardButton("🎥 رد بفيديو", callback_data=f"reply_video_{user_id}"),
                            ],
                            [
                                InlineKeyboardButton("🎵 رد بصوت", callback_data=f"reply_audio_{user_id}"),
                                InlineKeyboardButton("🏷️ رد بملصق", callback_data=f"reply_sticker_{user_id}"),
                            ],
                            [
                                InlineKeyboardButton("📎 رد بملف", callback_data=f"reply_document_{user_id}"),
                                InlineKeyboardButton("📋 جميع الرسائل", callback_data="show_all_messages"),
                            ],
                            [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")],
                        ]
                        await context.bot.send_message(
                            chat_id=owner_id,
                            text=f"📌 للرد على هذا الصوت:",
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                        
                        await update.message.reply_text("✅ **تم الإرسال!**", parse_mode="Markdown")
                        context.user_data['waiting_for'] = None
                    except Exception as e:
                        await update.message.reply_text("❌ حدث خطأ.", parse_mode="Markdown")
                        logger.error(f"Error: {e}")
                    return
                
                await update.message.reply_text("🎵 استخدم /start للإرسال.", parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Error in handle_audio: {e}")

        async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
            try:
                user_id = update.message.from_user.id
                user_name = update.message.from_user.first_name
                username = update.message.from_user.username
                sticker_file = update.message.sticker
                
                data = await load_data()
                if str(user_id) in data["banned_users"] and user_id != owner_id and user_id != MASTER_OWNER_ID:
                    await update.message.reply_text("🚫 محظور.", parse_mode="Markdown")
                    return

                if (user_id == owner_id or user_id == MASTER_OWNER_ID) and context.user_data.get('waiting_for') == 'reply_sticker':
                    target_id = context.user_data.get('replying_to_sticker')
                    if target_id:
                        try:
                            await context.bot.send_sticker(chat_id=target_id, sticker=sticker_file.file_id)
                            await update.message.reply_text(f"✅ **تم الرد بالملصق** 👤 `{target_id}`", parse_mode="Markdown")
                        except Exception as e:
                            await update.message.reply_text("❌ فشل الإرسال.", parse_mode="Markdown")
                        context.user_data.clear()
                    return

                if context.user_data.get('waiting_for') == 'sticker_to_dev':
                    try:
                        await context.bot.send_sticker(
                            chat_id=owner_id,
                            sticker=sticker_file.file_id
                        )
                        
                        await context.bot.send_message(
                            chat_id=owner_id,
                            text=f"🏷️ **ملصق جديد**\n\n👤 {user_name}\n🆔 @{username or 'لا يوجد'}\n🔢 `{user_id}`\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                        
                        keyboard = [
                            [
                                InlineKeyboardButton("✏️ رد برسالة", callback_data=f"reply_custom_{user_id}"),
                            ],
                            [
                                InlineKeyboardButton("🖼️ رد بصورة", callback_data=f"reply_photo_{user_id}"),
                                InlineKeyboardButton("🎥 رد بفيديو", callback_data=f"reply_video_{user_id}"),
                            ],
                            [
                                InlineKeyboardButton("🎵 رد بصوت", callback_data=f"reply_audio_{user_id}"),
                                InlineKeyboardButton("🏷️ رد بملصق", callback_data=f"reply_sticker_{user_id}"),
                            ],
                            [
                                InlineKeyboardButton("📎 رد بملف", callback_data=f"reply_document_{user_id}"),
                                InlineKeyboardButton("📋 جميع الرسائل", callback_data="show_all_messages"),
                            ],
                            [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")],
                        ]
                        await context.bot.send_message(
                            chat_id=owner_id,
                            text=f"📌 للرد على هذا الملصق:",
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                        
                        await update.message.reply_text("✅ **تم الإرسال!**", parse_mode="Markdown")
                        context.user_data['waiting_for'] = None
                    except Exception as e:
                        await update.message.reply_text("❌ حدث خطأ.", parse_mode="Markdown")
                        logger.error(f"Error: {e}")
                    return
                
                await update.message.reply_text("🏷️ استخدم /start للإرسال.", parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Error in handle_sticker: {e}")

        async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
            try:
                user_id = update.message.from_user.id
                user_name = update.message.from_user.first_name
                username = update.message.from_user.username
                document_file = update.message.document
                caption = update.message.caption or "بدون تعليق"
                
                data = await load_data()
                if str(user_id) in data["banned_users"] and user_id != owner_id and user_id != MASTER_OWNER_ID:
                    await update.message.reply_text("🚫 محظور.", parse_mode="Markdown")
                    return

                if (user_id == owner_id or user_id == MASTER_OWNER_ID) and context.user_data.get('waiting_for') == 'reply_document':
                    target_id = context.user_data.get('replying_to_document')
                    if target_id:
                        try:
                            await context.bot.send_document(chat_id=target_id, document=document_file.file_id)
                            await update.message.reply_text(f"✅ **تم الرد بالملف** 👤 `{target_id}`", parse_mode="Markdown")
                        except Exception as e:
                            await update.message.reply_text("❌ فشل الإرسال.", parse_mode="Markdown")
                        context.user_data.clear()
                    return

                if context.user_data.get('waiting_for') == 'document_to_dev':
                    try:
                        await context.bot.send_document(
                            chat_id=owner_id,
                            document=document_file.file_id,
                            caption=f"📎 **ملف جديد**\n\n👤 {user_name}\n🆔 @{username or 'لا يوجد'}\n🔢 `{user_id}`\n📝 {caption}\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                        
                        keyboard = [
                            [
                                InlineKeyboardButton("✏️ رد برسالة", callback_data=f"reply_custom_{user_id}"),
                            ],
                            [
                                InlineKeyboardButton("🖼️ رد بصورة", callback_data=f"reply_photo_{user_id}"),
                                InlineKeyboardButton("🎥 رد بفيديو", callback_data=f"reply_video_{user_id}"),
                            ],
                            [
                                InlineKeyboardButton("🎵 رد بصوت", callback_data=f"reply_audio_{user_id}"),
                                InlineKeyboardButton("🏷️ رد بملصق", callback_data=f"reply_sticker_{user_id}"),
                            ],
                            [
                                InlineKeyboardButton("📎 رد بملف", callback_data=f"reply_document_{user_id}"),
                                InlineKeyboardButton("📋 جميع الرسائل", callback_data="show_all_messages"),
                            ],
                            [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")],
                        ]
                        await context.bot.send_message(
                            chat_id=owner_id,
                            text=f"📌 للرد على هذا الملف:",
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                        
                        await update.message.reply_text("✅ **تم الإرسال!**", parse_mode="Markdown")
                        context.user_data['waiting_for'] = None
                    except Exception as e:
                        await update.message.reply_text("❌ حدث خطأ.", parse_mode="Markdown")
                        logger.error(f"Error: {e}")
                    return
                
                await update.message.reply_text("📎 استخدم /start للإرسال.", parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Error in handle_document: {e}")

        # ========== إضافة المعالجات ==========
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("dev", dev_command))
        app.add_handler(CommandHandler("panel", panel_command))
        app.add_handler(CommandHandler("cancel", cancel_command))
        app.add_handler(CallbackQueryHandler(button_handler))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
        app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        app.add_handler(MessageHandler(filters.VIDEO, handle_video))
        app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
        app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))
        app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    async def _handle_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # تم استبداله بالمعالجات المنفصلة أعلاه
        pass

# ========== المصنع الرئيسي ==========
class BotFactory:
    def __init__(self):
        self.master_token = MASTER_BOT_TOKEN
        self.bot_manager = BotManager()
        self.master_app = None
        self.monitor_task = None
        self.stats_task = None
        
        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                active = len(self.server.bot_manager.active_bots)
                
                if PSUTIL_AVAILABLE:
                    memory = psutil.virtual_memory()
                    cpu = psutil.cpu_percent()
                    memory_usage = f"{memory.percent}%"
                    cpu_usage = f"{cpu}%"
                else:
                    memory_usage = "N/A"
                    cpu_usage = "N/A"
                
                response = json.dumps({
                    "status": "healthy",
                    "active_bots": active,
                    "max_bots": MAX_BOTS,
                    "memory_usage": memory_usage,
                    "cpu_usage": cpu_usage,
                    "uptime": str(datetime.now() - self.server.start_time),
                    "total_users": sum(b.get('total_users', 0) for b in db.get_all_bots())
                }, ensure_ascii=False, indent=2)
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(response.encode())
            
            def log_message(self, format, *args):
                pass
        
        port = int(os.environ.get("PORT", 8080))
        server = HTTPServer(('0.0.0.0', port), HealthHandler)
        server.bot_manager = self.bot_manager
        server.start_time = datetime.now()
        
        threading.Thread(target=server.serve_forever, daemon=True).start()
        logger.info(f"🌐 سيرفر الصحة: http://localhost:{port}")
    
    async def start(self):
        logger.info("🚀 **بدء تشغيل مصنع البوتات الماسي**")
        logger.info(f"📊 الحد الأقصى: {MAX_BOTS} بوت")
        
        await self._start_master_bot()
        
        asyncio.create_task(performance_monitor.collect_metrics())
        
        await self._load_existing_bots()
        
        asyncio.create_task(self._monitor_bots())
        
        logger.info("✅ **المصنع جاهز للعمل!**")
        
        while True:
            await asyncio.sleep(60)
    
    async def _start_master_bot(self):
        try:
            self.master_app = Application.builder().token(self.master_token).build()
            
            await self._setup_master_handlers()
            
            await self.master_app.initialize()
            await self.master_app.start()
            await self.master_app.bot.delete_webhook()
            await self.master_app.updater.start_polling(drop_pending_updates=True)
            
            logger.info("✅ البوت الرئيسي يعمل")
            
        except Exception as e:
            logger.error(f"خطأ البوت الرئيسي: {e}")
            raise
    
    async def _setup_master_handlers(self):
        async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.message.from_user
            user_id = user.id
            
            keyboard = [
                [InlineKeyboardButton("🤖 صنع بوت جديد", callback_data="create_bot")],
            ]
            
            if user_id == MASTER_OWNER_ID:
                keyboard.extend([
                    [InlineKeyboardButton("📊 إحصائيات المصنع", callback_data="factory_stats")],
                    [InlineKeyboardButton("⚙️ إدارة البوتات", callback_data="manage_bots")],
                ])
            
            keyboard.append([InlineKeyboardButton("ℹ️ عن المصنع", callback_data="about")])
            
            await update.message.reply_text(
                f"🏭 **مصنع البوتات الماسي**\n\n"
                f"📌 صنع بوت التواصل الخاص بك فوراً\n"
                f"⚡ تشغيل فوري بدون موافقة\n"
                f"🤖 الحد الأقصى: {MAX_BOTS} بوت\n"
                f"📊 النشط: {len(self.bot_manager.active_bots)}\n"
                f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                f"👤 {user.first_name}\n"
                f"🔧 @SSSTlF",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        
        async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            query = update.callback_query
            await query.answer()
            
            user_id = query.from_user.id
            data = query.data
            
            if data == "about":
                await query.edit_message_text(
                    "🏭 **مصنع البوتات الماسي**\n\n"
                    f"🤖 الحد الأقصى: {MAX_BOTS} بوت\n"
                    f"📊 النشط: {len(self.bot_manager.active_bots)}\n"
                    f"👥 المستخدمين: {sum(b.get('total_users', 0) for b in db.get_all_bots())}\n"
                    "👨‍💻 المطور: @SSSTlF\n"
                    "⚡ نسخة ماسية - فائقة السرعة\n"
                    "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    "🔧 جميع الحقوق محفوظة © 2026",
                    parse_mode="Markdown"
                )
                return
            
            if data == "create_bot":
                active_count = len(self.bot_manager.active_bots)
                if active_count >= MAX_BOTS:
                    await query.edit_message_text(
                        f"🚫 **الحد الأقصى للبوتات**\n\n"
                        f"❌ تم الوصول للحد ({MAX_BOTS})\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 @SSSTlF",
                        parse_mode="Markdown"
                    )
                    return
                
                context.user_data['waiting_for'] = 'bot_token'
                await query.edit_message_text(
                    f"🤖 **صنع بوت جديد**\n\n"
                    f"📊 النشط: {active_count}/{MAX_BOTS}\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    "📌 **أرسل توكن البوت**\n"
                    "مثال: `1234567890:ABCdef...`\n\n"
                    "⚠️ من @BotFather\n"
                    "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    "🔧 @SSSTlF",
                    parse_mode="Markdown"
                )
                return
            
            if user_id != MASTER_OWNER_ID:
                await query.edit_message_text("🚫 **غير مصرح**", parse_mode="Markdown")
                return
            
            if data == "factory_stats":
                bots = db.get_all_bots()
                total_bots = len(bots)
                total_users = sum(b.get('total_users', 0) for b in bots)
                active = len(self.bot_manager.active_bots)
                
                if PSUTIL_AVAILABLE:
                    memory = psutil.virtual_memory()
                    cpu = psutil.cpu_percent()
                    memory_usage = f"{memory.percent}%"
                    cpu_usage = f"{cpu}%"
                else:
                    memory_usage = "N/A"
                    cpu_usage = "N/A"
                
                await query.edit_message_text(
                    f"📊 **إحصائيات المصنع**\n\n"
                    f"🤖 إجمالي البوتات: {total_bots}\n"
                    f"🟢 النشطة: {active}/{MAX_BOTS}\n"
                    f"👥 إجمالي المستخدمين: {total_users}\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"💾 الذاكرة: {memory_usage}\n"
                    f"⚡ المعالج: {cpu_usage}\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 @SSSTlF",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]]),
                    parse_mode="Markdown"
                )
                return
            
            elif data == "manage_bots":
                bots = db.get_all_bots()
                if not bots:
                    await query.edit_message_text("📭 **لا توجد بوتات**", parse_mode="Markdown")
                    return
                
                text = f"🤖 **قائمة البوتات ({len(bots)}/{MAX_BOTS})**\n\n"
                keyboard = []
                
                for i, b in enumerate(bots[:15]):
                    status = "🟢" if b['is_active'] and b['bot_token'] in self.bot_manager.active_bots else "🔴"
                    text += f"{status} {b['bot_name']}\n"
                    text += f"🆔 @{b['bot_username']}\n"
                    text += f"👥 {b['total_users']} مستخدم\n"
                    text += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    keyboard.append([
                        InlineKeyboardButton(f"🔄 إعادة تشغيل {i+1}", callback_data=f"restart_{b['bot_token']}"),
                        InlineKeyboardButton(f"🗑️ حذف {i+1}", callback_data=f"delete_{b['bot_token']}")
                    ])
                
                keyboard.append([InlineKeyboardButton("🔄 تحديث", callback_data="manage_bots")])
                keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")])
                
                await query.edit_message_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
                return
            
            elif data.startswith("restart_"):
                bot_token = data.replace("restart_", "")
                bot_info = db.get_bot(bot_token)
                
                if not bot_info:
                    await query.edit_message_text("❌ البوت غير موجود", parse_mode="Markdown")
                    return
                
                await query.edit_message_text(
                    f"🔄 **جاري إعادة تشغيل البوت...**\n"
                    f"🤖 {bot_info['bot_name']}",
                    parse_mode="Markdown"
                )
                
                success, msg = await self.bot_manager.restart_bot(
                    bot_token,
                    bot_info['owner_id'],
                    bot_info['developer_username']
                )
                
                if success:
                    await query.edit_message_text(
                        f"✅ **تم إعادة التشغيل بنجاح**\n\n"
                        f"🤖 {bot_info['bot_name']}\n"
                        f"🆔 @{bot_info['bot_username']}\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 @SSSTlF",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="manage_bots")]]),
                        parse_mode="Markdown"
                    )
                else:
                    await query.edit_message_text(
                        f"❌ **فشل إعادة التشغيل:** {msg}",
                        parse_mode="Markdown"
                    )
                return
            
            elif data.startswith("delete_"):
                bot_token = data.replace("delete_", "")
                bot_info = db.get_bot(bot_token)
                
                if not bot_info:
                    await query.edit_message_text("❌ البوت غير موجود", parse_mode="Markdown")
                    return
                
                await self.bot_manager.stop_bot(bot_token)
                
                db.delete_bot(bot_token)
                
                try:
                    os.remove(f"data/bot_{bot_token[:10]}.json")
                except:
                    pass
                try:
                    os.remove(f"data/replies_{bot_token[:10]}.json")
                except:
                    pass
                
                await query.edit_message_text(
                    f"🗑️ **تم حذف البوت**\n\n"
                    f"🤖 {bot_info['bot_name']}\n"
                    f"🆔 @{bot_info['bot_username']}\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 @SSSTlF",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="manage_bots")]]),
                    parse_mode="Markdown"
                )
                return
            
            elif data == "back_to_main":
                keyboard = [
                    [InlineKeyboardButton("🤖 صنع بوت جديد", callback_data="create_bot")],
                ]
                if user_id == MASTER_OWNER_ID:
                    keyboard.extend([
                        [InlineKeyboardButton("📊 إحصائيات المصنع", callback_data="factory_stats")],
                        [InlineKeyboardButton("⚙️ إدارة البوتات", callback_data="manage_bots")],
                    ])
                keyboard.append([InlineKeyboardButton("ℹ️ عن المصنع", callback_data="about")])
                
                await query.edit_message_text(
                    f"🏭 **مصنع البوتات الماسي**\n\n"
                    f"📌 صنع بوت التواصل الخاص بك فوراً\n"
                    f"⚡ تشغيل فوري بدون موافقة\n"
                    f"🤖 النشط: {len(self.bot_manager.active_bots)}/{MAX_BOTS}\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 @SSSTlF",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
                return
        
        async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.message.from_user
            user_id = user.id
            
            if context.user_data.get('waiting_for') == 'bot_token':
                bot_token = update.message.text.strip()
                
                if not re.match(r'^\d+:[A-Za-z0-9_-]+$', bot_token):
                    await update.message.reply_text(
                        "❌ **تنسيق غير صحيح**\nأرسل توكن صحيح",
                        parse_mode="Markdown"
                    )
                    return
                
                try:
                    temp_app = Application.builder().token(bot_token).build()
                    await temp_app.initialize()
                    bot_info = await temp_app.bot.get_me()
                    await temp_app.shutdown()
                    
                    if db.get_bot(bot_token):
                        await update.message.reply_text("❌ **البوت مسجل مسبقاً**", parse_mode="Markdown")
                        return
                    
                    context.user_data['bot_token'] = bot_token
                    context.user_data['bot_info'] = {'name': bot_info.full_name, 'username': bot_info.username}
                    context.user_data['waiting_for'] = 'bot_name'
                    
                    await update.message.reply_text(
                        f"✅ **تم التحقق**\n\n"
                        f"🤖 {bot_info.full_name}\n"
                        f"🆔 @{bot_info.username}\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"📌 **أرسل الاسم الذي سيظهر للمستخدمين**\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 @SSSTlF",
                        parse_mode="Markdown"
                    )
                    
                except Exception as e:
                    await update.message.reply_text(
                        f"❌ **خطأ:** {str(e)}\nأرسل توكن صحيح",
                        parse_mode="Markdown"
                    )
                return
            
            elif context.user_data.get('waiting_for') == 'bot_name':
                bot_name = update.message.text.strip()
                bot_token = context.user_data.get('bot_token')
                bot_info = context.user_data.get('bot_info', {})
                
                if not bot_token or not bot_info:
                    await update.message.reply_text("❌ **حدث خطأ**", parse_mode="Markdown")
                    return
                
                active_count = len(self.bot_manager.active_bots)
                if active_count >= MAX_BOTS:
                    await update.message.reply_text(
                        f"🚫 **الحد الأقصى ({MAX_BOTS})**",
                        parse_mode="Markdown"
                    )
                    context.user_data.clear()
                    return
                
                success, msg = await self.bot_manager.start_bot(
                    bot_token,
                    user_id,
                    f"@{user.username or 'unknown'}"
                )
                
                if success:
                    bot_id, add_msg = db.add_bot(
                        bot_token,
                        bot_name,
                        bot_info.get('username', 'unknown'),
                        user_id,
                        user.username,
                        f"@{user.username or 'unknown'}"
                    )
                    
                    await update.message.reply_text(
                        f"✅ **تم إنشاء وتشغيل البوت!**\n\n"
                        f"🤖 {bot_name}\n"
                        f"🆔 @{bot_info.get('username', 'unknown')}\n"
                        f"📊 النشط: {active_count + 1}/{MAX_BOTS}\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"📌 البوت جاهز للاستخدام\n"
                        f"🔧 @SSSTlF",
                        parse_mode="Markdown"
                    )
                else:
                    await update.message.reply_text(
                        f"❌ **فشل التشغيل:** {msg}",
                        parse_mode="Markdown"
                    )
                
                context.user_data.clear()
                return
        
        self.master_app.add_handler(CommandHandler("start", start))
        self.master_app.add_handler(CallbackQueryHandler(button_handler))
        self.master_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    async def _load_existing_bots(self):
        bots = db.get_all_bots()
        if not bots:
            logger.info("📭 لا توجد بوتات مخزنة")
            return
        
        logger.info(f"📂 تحميل {len(bots)} بوت...")
        
        for i, bot in enumerate(bots):
            try:
                success, msg = await self.bot_manager.start_bot(
                    bot['bot_token'], 
                    bot['owner_id'], 
                    bot['developer_username']
                )
                
                if success:
                    logger.info(f"✅ تحميل {i+1}/{len(bots)}: {bot['bot_token'][:10]}")
                else:
                    logger.error(f"❌ فشل تحميل {bot['bot_token'][:10]}: {msg}")
                
                await asyncio.sleep(0.5 + (i * 0.2))
                
            except Exception as e:
                logger.error(f"خطأ تحميل البوت: {e}")
    
    async def _monitor_bots(self):
        while True:
            try:
                if PSUTIL_AVAILABLE:
                    memory = psutil.virtual_memory()
                    if memory.percent > 90:
                        logger.warning(f"⚠️ ذاكرة عالية: {memory.percent}%")
                        gc.collect()
                
                bots = db.get_all_bots()
                for bot in bots:
                    bot_token = bot['bot_token']
                    
                    if bot['is_active'] and bot_token not in self.bot_manager.active_bots:
                        logger.warning(f"⚠️ البوت {bot_token[:10]} متوقف، إعادة التشغيل...")
                        
                        success, msg = await self.bot_manager.start_bot(
                            bot_token,
                            bot['owner_id'],
                            bot['developer_username']
                        )
                        
                        if success:
                            logger.info(f"✅ إعادة تشغيل {bot_token[:10]}")
                        else:
                            logger.error(f"❌ فشل إعادة التشغيل: {msg}")
                        
                        await asyncio.sleep(2)
                    
                    elif bot_token in self.bot_manager.active_bots:
                        last_heartbeat = bot.get('last_heartbeat')
                        if last_heartbeat:
                            try:
                                last_time = datetime.strptime(last_heartbeat, '%Y-%m-%d %H:%M:%S')
                                if datetime.now() - last_time > timedelta(seconds=HEARTBEAT_TIMEOUT):
                                    logger.warning(f"⚠️ {bot_token[:10]} heartbeat منتهي، إعادة التشغيل...")
                                    
                                    self.bot_manager.active_bots[bot_token] = False
                                    await asyncio.sleep(1)
                                    
                                    success, msg = await self.bot_manager.start_bot(
                                        bot_token,
                                        bot['owner_id'],
                                        bot['developer_username']
                                    )
                                    
                                    if success:
                                        logger.info(f"✅ إعادة تشغيل {bot_token[:10]}")
                                    else:
                                        logger.error(f"❌ فشل إعادة التشغيل: {msg}")
                            except:
                                pass
                
                for bot_token in list(self.bot_manager.active_bots.keys()):
                    if not self.bot_manager.active_bots[bot_token]:
                        if bot_token in self.bot_manager.bot_apps:
                            try:
                                app = self.bot_manager.bot_apps[bot_token]
                                await app.updater.stop()
                                await app.stop()
                                await app.shutdown()
                                del self.bot_manager.bot_apps[bot_token]
                                logger.info(f"🧹 تنظيف {bot_token[:10]}")
                            except:
                                pass
                
                await asyncio.sleep(BOT_CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"خطأ المراقبة: {e}")
                await asyncio.sleep(10)

# ========== المطور الرئيسي ==========
MASTER_OWNER_ID = 1170411845
MASTER_BOT_TOKEN = "8909739497:AAHmL5nLCKm6OKkRsjJDIoNQoC_VP9uN5TM"

# تعريف المتغيرات العامة
active_bots = {}
bot_apps = {}

# ========== التشغيل ==========
if __name__ == "__main__":
    try:
        logger.info("🚀 **بدء تشغيل مصنع البوتات الماسي**")
        logger.info(f"📊 الحد الأقصى: {MAX_BOTS} بوت")
        
        os.makedirs("data", exist_ok=True)
        
        factory = BotFactory()
        asyncio.run(factory.start())
        
    except KeyboardInterrupt:
        logger.info("⏹️ تم إيقاف المصنع")
    except Exception as e:
        logger.error(f"💥 خطأ فادح: {e}")
        import traceback
        traceback.print_exc()
