import os
import json
import logging
import asyncio
import sqlite3
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import signal
import sys
import time

# ========== سيرفر HTTP للـ Health Check ==========
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'Bot Factory is running!')
    
    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    print(f"✅ Health server running on port {port}")
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

# ========== إعدادات ==========
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MASTER_OWNER_ID = 1170411845
MASTER_BOT_TOKEN = "8909739497:AAHmL5nLCKm6OKkRsjJDIoNQoC_VP9uN5TM"
DEVELOPER_USERNAME = "@SSSTlF"

# ========== قاعدة البيانات ==========
class BotFactoryDB:
    def __init__(self, db_path="bot_factory.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._create_tables()
    
    def _create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS bots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_token TEXT UNIQUE NOT NULL,
                bot_name TEXT NOT NULL,
                bot_username TEXT,
                owner_id INTEGER NOT NULL,
                owner_username TEXT,
                developer_username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                total_users INTEGER DEFAULT 0,
                config TEXT
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS pending_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                bot_token TEXT NOT NULL,
                bot_name TEXT NOT NULL,
                bot_username TEXT NOT NULL,
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending'
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS master_developers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS global_banned (
                user_id INTEGER PRIMARY KEY,
                reason TEXT,
                banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_token TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                first_use TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_use TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(bot_token, user_id)
            )
        ''')
        
        self.cursor.execute('''
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
        
        self.conn.commit()
        self.add_master_developer(MASTER_OWNER_ID, "SSSTlF")
    
    def add_master_developer(self, user_id, username):
        try:
            self.cursor.execute(
                "INSERT OR REPLACE INTO master_developers (user_id, username) VALUES (?, ?)",
                (user_id, username)
            )
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding master developer: {e}")
            return False
    
    def is_master_developer(self, user_id):
        self.cursor.execute("SELECT 1 FROM master_developers WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone() is not None
    
    def add_pending_request(self, user_id, username, bot_token, bot_name, bot_username):
        try:
            self.cursor.execute('''
                INSERT INTO pending_requests (user_id, username, bot_token, bot_name, bot_username)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, username, bot_token, bot_name, bot_username))
            self.conn.commit()
            return self.cursor.lastrowid
        except Exception as e:
            logger.error(f"Error adding pending request: {e}")
            return None
    
    def get_pending_request(self, request_id):
        self.cursor.execute("SELECT * FROM pending_requests WHERE id = ?", (request_id,))
        row = self.cursor.fetchone()
        if row:
            columns = [desc[0] for desc in self.cursor.description]
            return dict(zip(columns, row))
        return None
    
    def update_request_status(self, request_id, status):
        self.cursor.execute("UPDATE pending_requests SET status = ? WHERE id = ?", (status, request_id))
        self.conn.commit()
    
    def get_pending_requests(self):
        self.cursor.execute("SELECT * FROM pending_requests WHERE status = 'pending' ORDER BY requested_at DESC")
        rows = self.cursor.fetchall()
        columns = [desc[0] for desc in self.cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    
    def add_bot(self, bot_token, bot_name, bot_username, owner_id, owner_username, developer_username, config=None):
        try:
            self.cursor.execute(
                '''INSERT INTO bots 
                   (bot_token, bot_name, bot_username, owner_id, owner_username, developer_username, config)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (bot_token, bot_name, bot_username, owner_id, owner_username, developer_username, json.dumps(config) if config else None)
            )
            self.conn.commit()
            return self.cursor.lastrowid
        except Exception as e:
            logger.error(f"Error adding bot: {e}")
            return None
    
    def get_bot(self, bot_token):
        self.cursor.execute("SELECT * FROM bots WHERE bot_token = ?", (bot_token,))
        row = self.cursor.fetchone()
        if row:
            columns = [desc[0] for desc in self.cursor.description]
            return dict(zip(columns, row))
        return None
    
    def get_bots_by_owner(self, owner_id):
        self.cursor.execute("SELECT * FROM bots WHERE owner_id = ?", (owner_id,))
        rows = self.cursor.fetchall()
        columns = [desc[0] for desc in self.cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    
    def update_bot_active(self, bot_token, is_active):
        self.cursor.execute("UPDATE bots SET is_active = ? WHERE bot_token = ?", (is_active, bot_token))
        self.conn.commit()
    
    def delete_bot(self, bot_token):
        self.cursor.execute("DELETE FROM bots WHERE bot_token = ?", (bot_token,))
        self.conn.commit()
    
    def get_all_bots(self):
        self.cursor.execute("SELECT * FROM bots")
        rows = self.cursor.fetchall()
        columns = [desc[0] for desc in self.cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    
    def add_user(self, bot_token, user_id, username, first_name, last_name=None):
        try:
            self.cursor.execute('''
                INSERT OR REPLACE INTO bot_users 
                (bot_token, user_id, username, first_name, last_name, last_use)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (bot_token, user_id, username, first_name, last_name))
            self.conn.commit()
            
            self.cursor.execute(
                "UPDATE bots SET total_users = (SELECT COUNT(*) FROM bot_users WHERE bot_token = ?) WHERE bot_token = ?",
                (bot_token, bot_token)
            )
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            return False
    
    def get_user_count(self, bot_token):
        self.cursor.execute("SELECT COUNT(*) FROM bot_users WHERE bot_token = ?", (bot_token,))
        return self.cursor.fetchone()[0]
    
    def get_users(self, bot_token, limit=50):
        self.cursor.execute("SELECT user_id, first_name, username, last_use FROM bot_users WHERE bot_token = ? LIMIT ?", (bot_token, limit))
        return self.cursor.fetchall()
    
    def save_reply(self, bot_token, user_id, name, username, message, time):
        try:
            self.cursor.execute('''
                INSERT OR REPLACE INTO bot_replies (bot_token, user_id, name, username, message, time)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (bot_token, user_id, name, username, message, time))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error saving reply: {e}")
            return False
    
    def get_replies(self, bot_token, limit=50):
        self.cursor.execute("SELECT user_id, name, username, message, time FROM bot_replies WHERE bot_token = ? ORDER BY id DESC LIMIT ?", (bot_token, limit))
        rows = self.cursor.fetchall()
        return [{"user_id": r[0], "name": r[1], "username": r[2], "message": r[3], "time": r[4]} for r in rows]
    
    def close(self):
        self.conn.close()

db = BotFactoryDB()

# ========== قاموس البوتات النشطة ==========
active_bots = {}
bot_threads = {}
bot_apps = {}

# ========== تشغيل البوت الفرعي ==========
def run_sub_bot_sync(bot_token, owner_id, developer_username):
    """تشغيل البوت الفرعي في thread منفصل"""
    try:
        logger.info(f"🚀 Starting sub bot: {bot_token[:10]}...")
        
        # إنشاء حلقة asyncio جديدة
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # تشغيل البوت
        loop.run_until_complete(start_sub_bot_async(bot_token, owner_id, developer_username))
        
    except Exception as e:
        logger.error(f"❌ Sub bot error: {e}")
        import traceback
        traceback.print_exc()

async def start_sub_bot_async(bot_token, owner_id, developer_username):
    """تشغيل البوت الفرعي بشكل غير متزامن"""
    try:
        # إنشاء التطبيق
        app = Application.builder().token(bot_token).build()
        
        # إضافة المعالجات
        await setup_bot_handlers(app, bot_token, owner_id, developer_username)
        
        # بدء البوت
        await app.initialize()
        await app.start()
        
        # حذف أي webhook موجود واستخدام polling
        await app.bot.delete_webhook()
        await app.updater.start_polling(drop_pending_updates=True)
        
        # تخزين التطبيق
        bot_apps[bot_token] = app
        
        logger.info(f"✅ Sub bot {bot_token[:10]}... started successfully!")
        
        # الحفاظ على التشغيل
        while True:
            await asyncio.sleep(10)
            
    except Exception as e:
        logger.error(f"❌ Sub bot error: {e}")
        import traceback
        traceback.print_exc()

async def setup_bot_handlers(app, bot_token, owner_id, developer_username):
    """إعداد معالجات البوت الفرعي"""
    
    # ملفات البيانات
    DATA_FILE = f"bot_data_{bot_token[:10]}.json"
    REPLIES_FILE = f"replies_data_{bot_token[:10]}.json"
    
    def load_data():
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"users": [], "banned_users": [], "bot_active": True, "total_users": 0}
    
    def save_data(data):
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    
    def load_replies():
        if os.path.exists(REPLIES_FILE):
            with open(REPLIES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def save_replies(replies):
        with open(REPLIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(replies, f, ensure_ascii=False, indent=4)
    
    # إنشاء الملفات
    if not os.path.exists(DATA_FILE):
        save_data({"users": [], "banned_users": [], "bot_active": True, "total_users": 0})
    if not os.path.exists(REPLIES_FILE):
        save_replies({})
    
    # ===== دوال البوت =====
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            user_id = update.message.from_user.id
            user_name = update.message.from_user.first_name
            username = update.message.from_user.username
            
            data = load_data()
            
            if str(user_id) in data["banned_users"] and user_id != owner_id and user_id != MASTER_OWNER_ID:
                await update.message.reply_text("🚫 **أنت محظور من استخدام هذا البوت.**\nللتواصل: @SSSTlF", parse_mode="Markdown")
                return
            
            if str(user_id) not in data["users"]:
                data["users"].append(str(user_id))
                data["total_users"] = len(data["users"])
                save_data(data)
                
                try:
                    await context.bot.send_message(
                        chat_id=owner_id,
                        text=f"🆕 **مستخدم جديد!**\n\n👤 {user_name}\n🆔 @{username if username else 'لا يوجد'}\n🔢 `{user_id}`\n📊 الإجمالي: {data['total_users']}",
                        parse_mode="Markdown"
                    )
                except:
                    pass
            
            keyboard = [
                [
                    InlineKeyboardButton("📩 رسالة", callback_data="send_message"),
                    InlineKeyboardButton("🖼️ صورة", callback_data="send_photo"),
                ],
                [
                    InlineKeyboardButton("🎥 فيديو", callback_data="send_video"),
                    InlineKeyboardButton("🎵 صوت", callback_data="send_audio"),
                ],
                [
                    InlineKeyboardButton("📎 ملف", callback_data="send_document"),
                    InlineKeyboardButton("🏷️ ملصق", callback_data="send_sticker"),
                ],
            ]
            
            if user_id == owner_id or user_id == MASTER_OWNER_ID:
                keyboard.append([InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="admin_panel")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"📩 **بوت التواصل مع المطور**\n\n"
                f"👨‍💻 **المطور:** {developer_username}\n"
                f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                f"📌 **اختر ما تريد إرساله:**\n"
                f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                f"🔧 المبرمج: @SSSTlF",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error in start: {e}")
    
    async def panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.message.from_user.id
        if user_id != owner_id and user_id != MASTER_OWNER_ID:
            await update.message.reply_text("🚫 **هذا الأمر مخصص للمطور فقط.**", parse_mode="Markdown")
            return
        
        data = load_data()
        keyboard = [
            [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
            [InlineKeyboardButton("⏸️ تعطيل البوت", callback_data="admin_disable")] if data["bot_active"] else [InlineKeyboardButton("▶️ تفعيل البوت", callback_data="admin_enable")],
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
    
    async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            query = update.callback_query
            await query.answer()
            
            data = load_data()
            user_id = query.from_user.id
            
            if str(user_id) in data["banned_users"] and user_id != owner_id and user_id != MASTER_OWNER_ID:
                await query.edit_message_text("🚫 **أنت محظور.**", parse_mode="Markdown")
                return
            
            if not data["bot_active"] and user_id != owner_id and user_id != MASTER_OWNER_ID:
                await query.edit_message_text("⏸️ **البوت معطل.**", parse_mode="Markdown")
                return
            
            data_callback = query.data
    
            # ردود المطور
            if data_callback.startswith("reply_custom_"):
                target_id = int(data_callback.split('_')[2])
                context.user_data['replying_to_custom'] = target_id
                context.user_data['waiting_for'] = 'custom_reply'
                await query.edit_message_text(
                    f"✏️ **أرسل رسالتك المخصصة للرد**\n👤 للمستخدم: `{target_id}`\n\nلإلغاء: /cancel",
                    parse_mode="Markdown"
                )
                return
    
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
    
            # عرض جميع الرسائل
            elif data_callback == "show_all_messages":
                if user_id != owner_id and user_id != MASTER_OWNER_ID:
                    return
                
                replies = load_replies()
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
    
            # أزرار الإرسال
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
                    [
                        InlineKeyboardButton("📩 رسالة", callback_data="send_message"),
                        InlineKeyboardButton("🖼️ صورة", callback_data="send_photo"),
                    ],
                    [
                        InlineKeyboardButton("🎥 فيديو", callback_data="send_video"),
                        InlineKeyboardButton("🎵 صوت", callback_data="send_audio"),
                    ],
                    [
                        InlineKeyboardButton("📎 ملف", callback_data="send_document"),
                        InlineKeyboardButton("🏷️ ملصق", callback_data="send_sticker"),
                    ],
                ]
                if user_id == owner_id or user_id == MASTER_OWNER_ID:
                    keyboard.append([InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="admin_panel")])
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"📩 **بوت التواصل مع المطور**\n\n👨‍💻 **المطور:** {developer_username}\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n📌 **اختر ما تريد إرساله:**\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n🔧 المبرمج: @SSSTlF",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            
            # لوحة تحكم المطور
            elif data_callback == "admin_panel" and (user_id == owner_id or user_id == MASTER_OWNER_ID):
                keyboard = [
                    [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
                    [InlineKeyboardButton("⏸️ تعطيل البوت", callback_data="admin_disable")] if data["bot_active"] else [InlineKeyboardButton("▶️ تفعيل البوت", callback_data="admin_enable")],
                    [InlineKeyboardButton("🚫 حظر مستخدم", callback_data="admin_ban")],
                    [InlineKeyboardButton("✅ الغاء حظر", callback_data="admin_unban")],
                    [InlineKeyboardButton("📋 المحظورين", callback_data="admin_banned_list")],
                    [InlineKeyboardButton("📩 جميع الرسائل", callback_data="show_all_messages")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                status = "🟢 مفعل" if data["bot_active"] else "🔴 معطل"
                await query.edit_message_text(
                    f"⚙️ **لوحة التحكم**\n\n👨‍💻 المطور: {developer_username}\n📊 المستخدمين: {data['total_users']}\n🚫 المحظورين: {len(data['banned_users'])}\n📌 الحالة: {status}",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            
            elif data_callback == "admin_stats" and (user_id == owner_id or user_id == MASTER_OWNER_ID):
                keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    f"📊 **الإحصائيات**\n\n👥 المستخدمين: {data['total_users']}\n🚫 المحظورين: {len(data['banned_users'])}\n📌 الحالة: {'🟢 مفعل' if data['bot_active'] else '🔴 معطل'}\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            
            elif data_callback == "admin_disable" and (user_id == owner_id or user_id == MASTER_OWNER_ID):
                data["bot_active"] = False
                save_data(data)
                await query.edit_message_text("⏸️ **تم تعطيل البوت!**", parse_mode="Markdown")
            
            elif data_callback == "admin_enable" and (user_id == owner_id or user_id == MASTER_OWNER_ID):
                data["bot_active"] = True
                save_data(data)
                await query.edit_message_text("▶️ **تم تفعيل البوت!**", parse_mode="Markdown")
            
            elif data_callback == "admin_ban" and (user_id == owner_id or user_id == MASTER_OWNER_ID):
                context.user_data['waiting_for'] = 'ban_user'
                await query.edit_message_text("🚫 **حظر مستخدم**\n\nأرسل الآيدي:\nمثال: `123456789`\nلإلغاء: /cancel", parse_mode="Markdown")
            
            elif data_callback == "admin_unban" and (user_id == owner_id or user_id == MASTER_OWNER_ID):
                context.user_data['waiting_for'] = 'unban_user'
                await query.edit_message_text("✅ **الغاء حظر**\n\nأرسل الآيدي:\nمثال: `123456789`\nلإلغاء: /cancel", parse_mode="Markdown")
            
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
        except Exception as e:
            logger.error(f"Error in button_handler: {e}")
    
    # ===== معالج الرد المخصص =====
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
                    text=f"📩 **رد من المطور {developer_username}**\n\n{user_message}",
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
            await update.message.reply_text("❌ حدث خطأ.", parse_mode="Markdown")
    
    # ===== معالج الرسائل =====
    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            user_id = update.message.from_user.id
            user_name = update.message.from_user.first_name
            username = update.message.from_user.username
            user_message = update.message.text
            
            if user_id == owner_id or user_id == MASTER_OWNER_ID:
                if context.user_data.get('waiting_for') == 'custom_reply':
                    await handle_custom_reply(update, context)
                    return
            
            if user_message and user_message.lower() == "/cancel":
                context.user_data.clear()
                await update.message.reply_text("❌ **تم الإلغاء.**", parse_mode="Markdown")
                return
            
            data = load_data()
            
            if str(user_id) in data["banned_users"] and user_id != owner_id and user_id != MASTER_OWNER_ID:
                await update.message.reply_text("🚫 **أنت محظور.**", parse_mode="Markdown")
                return
            
            if not data["bot_active"] and user_id != owner_id and user_id != MASTER_OWNER_ID:
                await update.message.reply_text("⏸️ **البوت معطل.**", parse_mode="Markdown")
                return
    
            # أوامر المطور
            if user_id == owner_id or user_id == MASTER_OWNER_ID:
                if context.user_data.get('waiting_for') == 'ban_user':
                    try:
                        target_id = int(user_message.strip())
                        if str(target_id) not in data["banned_users"]:
                            data["banned_users"].append(str(target_id))
                            save_data(data)
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
                            save_data(data)
                            await update.message.reply_text(f"✅ **تم الغاء حظر `{target_id}`**", parse_mode="Markdown")
                        else:
                            await update.message.reply_text("⚠️ **غير محظور.**", parse_mode="Markdown")
                        context.user_data['waiting_for'] = None
                    except ValueError:
                        await update.message.reply_text("❌ **أرسل أرقام فقط.**", parse_mode="Markdown")
                    return
            
            # إرسال رسالة للمطور
            if context.user_data.get('waiting_for') == 'message_to_dev':
                try:
                    replies = load_replies()
                    replies[str(user_id)] = {
                        "name": user_name,
                        "username": username,
                        "message": user_message,
                        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        "user_id": user_id
                    }
                    save_replies(replies)
                    
                    keyboard = [
                        [
                            InlineKeyboardButton("✏️ رد برسالة مخصصة", callback_data=f"reply_custom_{user_id}"),
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
                        text=f"📩 **رسالة جديدة**\n\n👤 {user_name}\n🆔 @{username if username else 'لا يوجد'}\n🔢 `{user_id}`\n\n📝 {user_message}\n\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
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
            logger.error(f"Error in handle_message: {e}")
    
    # ===== معالجات الوسائط =====
    async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            user_id = update.message.from_user.id
            user_name = update.message.from_user.first_name
            username = update.message.from_user.username
            photo_file = update.message.photo[-1]
            caption = update.message.caption or "بدون تعليق"
            
            data = load_data()
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
                        caption=f"🖼️ **صورة جديدة**\n\n👤 {user_name}\n🆔 @{username if username else 'لا يوجد'}\n🔢 `{user_id}`\n📝 {caption}\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    
                    keyboard = [
                        [
                            InlineKeyboardButton("✏️ رد برسالة مخصصة", callback_data=f"reply_custom_{user_id}"),
                            InlineKeyboardButton("🖼️ رد بصورة", callback_data=f"reply_photo_{user_id}"),
                        ],
                        [
                            InlineKeyboardButton("🎥 رد بفيديو", callback_data=f"reply_video_{user_id}"),
                            InlineKeyboardButton("🎵 رد بصوت", callback_data=f"reply_audio_{user_id}"),
                        ],
                        [
                            InlineKeyboardButton("🏷️ رد بملصق", callback_data=f"reply_sticker_{user_id}"),
                            InlineKeyboardButton("📎 رد بملف", callback_data=f"reply_document_{user_id}"),
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
            
            data = load_data()
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
                        caption=f"🎥 **فيديو جديد**\n\n👤 {user_name}\n🆔 @{username if username else 'لا يوجد'}\n🔢 `{user_id}`\n📝 {caption}\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    
                    keyboard = [
                        [
                            InlineKeyboardButton("✏️ رد برسالة مخصصة", callback_data=f"reply_custom_{user_id}"),
                            InlineKeyboardButton("🖼️ رد بصورة", callback_data=f"reply_photo_{user_id}"),
                        ],
                        [
                            InlineKeyboardButton("🎥 رد بفيديو", callback_data=f"reply_video_{user_id}"),
                            InlineKeyboardButton("🎵 رد بصوت", callback_data=f"reply_audio_{user_id}"),
                        ],
                        [
                            InlineKeyboardButton("🏷️ رد بملصق", callback_data=f"reply_sticker_{user_id}"),
                            InlineKeyboardButton("📎 رد بملف", callback_data=f"reply_document_{user_id}"),
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
            
            data = load_data()
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
                        caption=f"🎵 **ملف صوتي جديد**\n\n👤 {user_name}\n🆔 @{username if username else 'لا يوجد'}\n🔢 `{user_id}`\n📝 {caption}\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    
                    keyboard = [
                        [
                            InlineKeyboardButton("✏️ رد برسالة مخصصة", callback_data=f"reply_custom_{user_id}"),
                            InlineKeyboardButton("🖼️ رد بصورة", callback_data=f"reply_photo_{user_id}"),
                        ],
                        [
                            InlineKeyboardButton("🎥 رد بفيديو", callback_data=f"reply_video_{user_id}"),
                            InlineKeyboardButton("🎵 رد بصوت", callback_data=f"reply_audio_{user_id}"),
                        ],
                        [
                            InlineKeyboardButton("🏷️ رد بملصق", callback_data=f"reply_sticker_{user_id}"),
                            InlineKeyboardButton("📎 رد بملف", callback_data=f"reply_document_{user_id}"),
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
            
            data = load_data()
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
                        text=f"🏷️ **ملصق جديد**\n\n👤 {user_name}\n🆔 @{username if username else 'لا يوجد'}\n🔢 `{user_id}`\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    
                    keyboard = [
                        [
                            InlineKeyboardButton("✏️ رد برسالة مخصصة", callback_data=f"reply_custom_{user_id}"),
                            InlineKeyboardButton("🖼️ رد بصورة", callback_data=f"reply_photo_{user_id}"),
                        ],
                        [
                            InlineKeyboardButton("🎥 رد بفيديو", callback_data=f"reply_video_{user_id}"),
                            InlineKeyboardButton("🎵 رد بصوت", callback_data=f"reply_audio_{user_id}"),
                        ],
                        [
                            InlineKeyboardButton("🏷️ رد بملصق", callback_data=f"reply_sticker_{user_id}"),
                            InlineKeyboardButton("📎 رد بملف", callback_data=f"reply_document_{user_id}"),
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
            
            data = load_data()
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
                        caption=f"📎 **ملف جديد**\n\n👤 {user_name}\n🆔 @{username if username else 'لا يوجد'}\n🔢 `{user_id}`\n📝 {caption}\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    
                    keyboard = [
                        [
                            InlineKeyboardButton("✏️ رد برسالة مخصصة", callback_data=f"reply_custom_{user_id}"),
                            InlineKeyboardButton("🖼️ رد بصورة", callback_data=f"reply_photo_{user_id}"),
                        ],
                        [
                            InlineKeyboardButton("🎥 رد بفيديو", callback_data=f"reply_video_{user_id}"),
                            InlineKeyboardButton("🎵 رد بصوت", callback_data=f"reply_audio_{user_id}"),
                        ],
                        [
                            InlineKeyboardButton("🏷️ رد بملصق", callback_data=f"reply_sticker_{user_id}"),
                            InlineKeyboardButton("📎 رد بملف", callback_data=f"reply_document_{user_id}"),
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
    
    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            f"📖 **المساعدة**\n\n/start - القائمة الرئيسية\n/help - هذه المساعدة\n/dev - المطور\n/panel - لوحة التحكم\n/cancel - إلغاء العملية",
            parse_mode="Markdown"
        )
    
    async def dev_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            f"👨‍💻 **المطور**\n\nالبوت من تصميم:\n✨ @SSSTlF ✨\n\n📌 للتواصل: @SSSTlF",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    
    async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data.clear()
        await update.message.reply_text("❌ **تم الإلغاء.**", parse_mode="Markdown")
    
    # إضافة المعالجات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("dev", dev_command))
    app.add_handler(CommandHandler("panel", panel_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

# ========== بدء البوت الفرعي ==========
def start_sub_bot(bot_token, owner_id, developer_username):
    """بدء بوت فرعي في thread منفصل"""
    try:
        if bot_token in active_bots and active_bots[bot_token]:
            return False, "البوت يعمل بالفعل"
        
        # تشغيل في thread جديد
        thread = threading.Thread(
            target=run_sub_bot_sync,
            args=(bot_token, owner_id, developer_username),
            daemon=True
        )
        thread.start()
        
        # انتظار قليلاً للتأكد من بدء التشغيل
        time.sleep(1)
        
        active_bots[bot_token] = True
        bot_threads[bot_token] = thread
        
        logger.info(f"✅ Bot {bot_token[:10]}... started in background")
        return True, "تم تشغيل البوت ✅"
        
    except Exception as e:
        logger.error(f"Error starting sub bot: {e}")
        return False, f"خطأ: {str(e)}"

# ========== البوت الرئيسي ==========
class MasterBot:
    def __init__(self, token):
        self.token = token
        self.app = None
    
    async def start(self):
        self.app = Application.builder().token(self.token).build()
        await self._setup_handlers()
        await self.app.initialize()
        await self.app.start()
        await self.app.bot.delete_webhook()
        await self.app.updater.start_polling(drop_pending_updates=True)
        logger.info("✅ Master bot started!")
        return self.app
    
    async def _setup_handlers(self):
        async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.message.from_user
            user_id = user.id
            
            db.add_master_developer(user_id, user.username)
            
            keyboard = [
                [InlineKeyboardButton("🤖 طلب بوت جديد", callback_data="request_bot")],
            ]
            
            if user_id == MASTER_OWNER_ID:
                keyboard.extend([
                    [InlineKeyboardButton("📋 الطلبات المعلقة", callback_data="pending_requests")],
                    [InlineKeyboardButton("📊 إحصائيات المصنع", callback_data="factory_stats")],
                    [InlineKeyboardButton("⚙️ إدارة البوتات", callback_data="manage_bots")],
                ])
            
            keyboard.append([InlineKeyboardButton("ℹ️ عن المصنع", callback_data="about")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "🏭 **مصنع بوتات التواصل**\n\n"
                "📌 اطلب بوت التواصل الخاص بك\n"
                "⚠️ سيرسل طلبك للموافقة\n"
                "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                f"👤 {user.first_name}\n"
                f"🔧 المبرمج: @SSSTlF",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        
        async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            query = update.callback_query
            await query.answer()
            
            user_id = query.from_user.id
            data = query.data
            
            if data == "about":
                await query.edit_message_text(
                    "🏭 **مصنع بوتات التواصل**\n\n"
                    "👨‍💻 المطور: @SSSTlF\n"
                    "🆔 ID: 1170411845\n"
                    "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    "🔧 جميع الحقوق محفوظة © 2026\n"
                    "المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                return
            
            if data == "request_bot":
                context.user_data['waiting_for'] = 'bot_token'
                await query.edit_message_text(
                    "🤖 **طلب بوت جديد**\n\n"
                    "📌 **الخطوة 1:** أرسل توكن البوت\n"
                    "مثال: `1234567890:ABCdef...`\n\n"
                    "⚠️ من @BotFather\n"
                    "🔄 /cancel للإلغاء\n"
                    "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    "🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                return
            
            if user_id != MASTER_OWNER_ID:
                await query.edit_message_text("🚫 غير مصرح لك.", parse_mode="Markdown")
                return
            
            if data == "pending_requests":
                pending = db.get_pending_requests()
                if not pending:
                    await query.edit_message_text(
                        "📭 **لا توجد طلبات معلقة**\n\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                    return
                
                text = "📋 **الطلبات المعلقة**\n\n"
                for req in pending:
                    text += f"📌 طلب #{req['id']}\n"
                    text += f"👤 من: @{req['username'] or 'unknown'}\n"
                    text += f"🆔 ID: `{req['user_id']}`\n"
                    text += f"🤖 البوت: {req['bot_name']}\n"
                    text += f"🆔 @{req['bot_username']}\n"
                    text += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                
                keyboard = []
                for req in pending:
                    keyboard.append([
                        InlineKeyboardButton(f"✅ قبول {req['bot_name']}", callback_data=f"approve_{req['id']}"),
                        InlineKeyboardButton(f"❌ رفض", callback_data=f"reject_{req['id']}")
                    ])
                keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")])
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    text + f"\n🔧 المبرمج: @SSSTlF",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
                return
            
            elif data.startswith("approve_"):
                request_id = int(data.replace("approve_", ""))
                req = db.get_pending_request(request_id)
                if not req:
                    await query.edit_message_text("❌ الطلب غير موجود.", parse_mode="Markdown")
                    return
                
                bot_id = db.add_bot(
                    bot_token=req['bot_token'],
                    bot_name=req['bot_name'],
                    bot_username=req['bot_username'],
                    owner_id=req['user_id'],
                    owner_username=req['username'],
                    developer_username=f"@{req['username'] or 'unknown'}"
                )
                
                if bot_id:
                    success, msg = start_sub_bot(req['bot_token'], req['user_id'], f"@{req['username'] or 'unknown'}")
                    db.update_request_status(request_id, 'approved')
                    
                    try:
                        await context.bot.send_message(
                            chat_id=req['user_id'],
                            text=f"✅ **تم قبول طلبك!**\n\n"
                                 f"🤖 بوتك جاهز الآن:\n"
                                 f"@{req['bot_username']}\n\n"
                                 f"📌 استخدم /start للبدء\n\n"
                                 f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                                 f"🔧 المبرمج: @SSSTlF",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
                    
                    await query.edit_message_text(
                        f"✅ **تم قبول الطلب**\n\n"
                        f"🤖 تم تشغيل بوت {req['bot_name']}\n"
                        f"👤 المالك: @{req['username'] or 'unknown'}\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                return
            
            elif data.startswith("reject_"):
                request_id = int(data.replace("reject_", ""))
                req = db.get_pending_request(request_id)
                if req:
                    db.update_request_status(request_id, 'rejected')
                    try:
                        await context.bot.send_message(
                            chat_id=req['user_id'],
                            text=f"❌ **للأسف تم رفض طلبك**\n\n"
                                 f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                                 f"🔧 المبرمج: @SSSTlF",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
                
                await query.edit_message_text(
                    f"❌ **تم رفض الطلب**\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                return
            
            elif data == "factory_stats":
                bots = db.get_all_bots()
                total_bots = len(bots)
                total_users = sum(b.get('total_users', 0) for b in bots)
                active = db.cursor.execute("SELECT COUNT(*) FROM bots WHERE is_active = 1").fetchone()[0]
                pending = len(db.get_pending_requests())
                
                keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"📊 **إحصائيات المصنع**\n\n"
                    f"🤖 إجمالي البوتات: {total_bots}\n"
                    f"🟢 البوتات النشطة: {active}\n"
                    f"👥 إجمالي المستخدمين: {total_users}\n"
                    f"📋 الطلبات المعلقة: {pending}\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
                return
            
            elif data == "manage_bots":
                bots = db.get_all_bots()
                if not bots:
                    await query.edit_message_text(
                        "📭 **لا توجد بوتات**\n\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                    return
                
                text = "🤖 **قائمة البوتات**\n\n"
                for b in bots[:10]:
                    status = "🟢" if b['is_active'] else "🔴"
                    text += f"{status} {b['bot_name']}\n"
                    text += f"🆔 @{b['bot_username']}\n"
                    text += f"👤 {b['owner_username']}\n"
                    text += f"👥 {b['total_users']} مستخدم\n"
                    text += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                
                keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    text + f"\n🔧 المبرمج: @SSSTlF",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
                return
            
            elif data == "back_to_main":
                keyboard = [
                    [InlineKeyboardButton("🤖 طلب بوت جديد", callback_data="request_bot")],
                ]
                if user_id == MASTER_OWNER_ID:
                    keyboard.extend([
                        [InlineKeyboardButton("📋 الطلبات المعلقة", callback_data="pending_requests")],
                        [InlineKeyboardButton("📊 إحصائيات المصنع", callback_data="factory_stats")],
                        [InlineKeyboardButton("⚙️ إدارة البوتات", callback_data="manage_bots")],
                    ])
                keyboard.append([InlineKeyboardButton("ℹ️ عن المصنع", callback_data="about")])
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    "🏭 **مصنع بوتات التواصل**\n\n"
                    "📌 اطلب بوت التواصل الخاص بك\n"
                    "⚠️ سيرسل طلبك للموافقة\n"
                    "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
                return
        
        async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.message.from_user
            user_id = user.id
            
            waiting_for = context.user_data.get('waiting_for')
            
            if waiting_for == 'bot_token':
                bot_token = update.message.text.strip()
                
                if not re.match(r'^\d+:[A-Za-z0-9_-]+$', bot_token):
                    await update.message.reply_text(
                        "❌ **تنسيق توكن غير صحيح**\n\n"
                        "📌 يجب أن يكون على الشكل:\n"
                        "`1234567890:ABCdef...`\n\n"
                        "🔄 أرسل التوكن مجدداً أو /cancel للإلغاء\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                    return
                
                try:
                    temp_app = Application.builder().token(bot_token).build()
                    await temp_app.initialize()
                    bot_info = await temp_app.bot.get_me()
                    await temp_app.shutdown()
                    
                    if db.get_bot(bot_token):
                        await update.message.reply_text(
                            "❌ **هذا البوت مسجل مسبقاً**\n\n"
                            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                            f"🔧 المبرمج: @SSSTlF",
                            parse_mode="Markdown"
                        )
                        return
                    
                    context.user_data['bot_token'] = bot_token
                    context.user_data['bot_info'] = {'name': bot_info.full_name, 'username': bot_info.username}
                    context.user_data['waiting_for'] = 'bot_name'
                    
                    await update.message.reply_text(
                        f"✅ **تم التحقق من البوت**\n\n"
                        f"🤖 الاسم: {bot_info.full_name}\n"
                        f"🆔 @{bot_info.username}\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"📌 **الخطوة 2:** أرسل الاسم الذي تريد عرضه للمستخدمين\n"
                        f"(الاسم الذي سيظهر في رسائل البوت)\n\n"
                        f"🔄 /cancel للإلغاء\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                    
                except Exception as e:
                    await update.message.reply_text(
                        f"❌ **خطأ في التوكن**\n\n"
                        f"السبب: {str(e)}\n\n"
                        f"🔄 أرسل توكن صحيح أو /cancel للإلغاء\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                return
            
            elif waiting_for == 'bot_name':
                bot_name = update.message.text.strip()
                bot_token = context.user_data.get('bot_token')
                bot_info = context.user_data.get('bot_info', {})
                
                if not bot_token or not bot_info:
                    await update.message.reply_text(
                        "❌ **حدث خطأ، حاول مجدداً**\n\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                    return
                
                request_id = db.add_pending_request(
                    user_id=user_id,
                    username=user.username,
                    bot_token=bot_token,
                    bot_name=bot_name,
                    bot_username=bot_info.get('username', 'unknown')
                )
                
                if request_id:
                    await update.message.reply_text(
                        f"✅ **تم إرسال طلبك بنجاح!**\n\n"
                        f"🤖 البوت: {bot_name}\n"
                        f"🆔 @{bot_info.get('username', 'unknown')}\n"
                        f"📌 سيتم مراجعة طلبك من قبل المطور\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                    
                    await context.bot.send_message(
                        chat_id=MASTER_OWNER_ID,
                        text=f"📋 **طلب بوت جديد**\n\n"
                             f"👤 من: @{user.username or 'unknown'}\n"
                             f"🆔 ID: `{user_id}`\n"
                             f"🤖 البوت: {bot_name}\n"
                             f"🆔 @{bot_info.get('username', 'unknown')}\n"
                             f"🔗 توكن: `{bot_token}`\n\n"
                             f"📌 استخدم /start لإدارة الطلبات\n"
                             f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                             f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                else:
                    await update.message.reply_text(
                        "❌ **حدث خطأ أثناء حفظ الطلب**\n\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                
                context.user_data.clear()
                return
            
            elif update.message.text and update.message.text.lower() == "/cancel":
                context.user_data.clear()
                await update.message.reply_text(
                    "❌ **تم الإلغاء**\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                return
        
        self.app.add_handler(CommandHandler("start", start_command))
        self.app.add_handler(CommandHandler("cancel", lambda u, c: u.message.reply_text("❌ تم الإلغاء\n\n🔧 المبرمج: @SSSTlF", parse_mode="Markdown")))
        self.app.add_handler(CallbackQueryHandler(button_handler))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

# ========== التشغيل ==========
async def main():
    master = MasterBot(MASTER_BOT_TOKEN)
    await master.start()
    
    # تشغيل البوتات المخزنة
    bots = db.get_all_bots()
    for bot in bots:
        if bot['is_active']:
            start_sub_bot(bot['bot_token'], bot['owner_id'], bot['developer_username'])
    
    while True:
        await asyncio.sleep(60)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
