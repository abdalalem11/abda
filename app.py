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
                status TEXT DEFAULT 'pending'  -- pending, approved, rejected
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
    
    def close(self):
        self.conn.close()

db = BotFactoryDB()

# ========== قائمة البوتات النشطة ==========
active_bots = {}
bot_tasks = {}

# ========== تشغيل بوت فرعي ==========
async def run_sub_bot_async(bot_token, owner_id, developer_username):
    """تشغيل بوت فرعي مع أزرار الرد المتقدمة"""
    try:
        logger.info(f"🚀 Starting sub bot: {bot_token[:10]}...")
        
        app = Application.builder().token(bot_token).build()
        
        async def register_user(update: Update):
            user = update.effective_user
            if user:
                try:
                    db.add_user(bot_token, user.id, user.username, user.first_name, user.last_name)
                except Exception as e:
                    logger.error(f"Error registering user: {e}")
            return user
        
        async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = await register_user(update)
            user_id = user.id
            
            cursor = db.conn.cursor()
            cursor.execute("SELECT 1 FROM global_banned WHERE user_id = ?", (user_id,))
            if cursor.fetchone() and user_id != owner_id and user_id != MASTER_OWNER_ID:
                await update.message.reply_text("🚫 **أنت محظور**", parse_mode="Markdown")
                return
            
            buttons = [
                [InlineKeyboardButton("📩 إرسال رسالة", callback_data="send_message"), InlineKeyboardButton("🖼️ إرسال صورة", callback_data="send_photo")],
                [InlineKeyboardButton("🎥 إرسال فيديو", callback_data="send_video"), InlineKeyboardButton("🎵 إرسال صوت", callback_data="send_audio")],
                [InlineKeyboardButton("📎 إرسال ملف", callback_data="send_document"), InlineKeyboardButton("📌 عن البوت", callback_data="about_bot")],
            ]
            
            if user_id == owner_id or user_id == MASTER_OWNER_ID:
                buttons.append([InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="admin_panel")])
            
            reply_markup = InlineKeyboardMarkup(buttons)
            
            await update.message.reply_text(
                f"📩 **بوت التواصل**\n\n"
                f"👨‍💻 المطور: {developer_username}\n"
                f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                f"📌 أرسل ما تريد وسيتم إيصاله للمطور\n"
                f"🔧 المبرمج: @SSSTlF",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        
        async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = await register_user(update)
            await update.message.reply_text(
                f"📖 **قائمة الأوامر**\n\n"
                f"/start - بدء البوت\n"
                f"/help - عرض هذه القائمة\n"
                f"/about - معلومات عن البوت\n"
                f"/dev - معلومات المطور\n"
                f"/stats - إحصائيات البوت (للمطور فقط)\n"
                f"/reply - الرد على مستخدم (للمطور فقط)\n"
                f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                f"📩 استخدم الأزرار لإرسال:\n"
                f"• رسالة 📩\n"
                f"• صورة 🖼️\n"
                f"• فيديو 🎥\n"
                f"• صوت 🎵\n"
                f"• ملف 📎\n"
                f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                f"🔧 المبرمج: @SSSTlF",
                parse_mode="Markdown"
            )
        
        async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = await register_user(update)
            bot_info = db.get_bot(bot_token)
            bot_name = bot_info['bot_name'] if bot_info else "بوت التواصل"
            
            await update.message.reply_text(
                f"ℹ️ **معلومات البوت**\n\n"
                f"🤖 الاسم: {bot_name}\n"
                f"🆔 @{bot_info['bot_username'] if bot_info else 'unknown'}\n"
                f"👨‍💻 المطور: {developer_username}\n"
                f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                f"🏭 تم صنعه بواسطة مصنع بوتات التواصل\n"
                f"🔧 المبرمج: @SSSTlF\n"
                f"📅 جميع الحقوق محفوظة © 2026",
                parse_mode="Markdown"
            )
        
        async def dev_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = await register_user(update)
            await update.message.reply_text(
                f"👨‍💻 **المطور**\n\n"
                f"📌 المبرمج: @SSSTlF\n"
                f"🆔 ID: {MASTER_OWNER_ID}\n"
                f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                f"🏭 مصنع بوتات التواصل\n"
                f"🔧 جميع الحقوق محفوظة © 2026",
                parse_mode="Markdown"
            )
        
        async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = await register_user(update)
            user_id = user.id
            
            if user_id != owner_id and user_id != MASTER_OWNER_ID:
                await update.message.reply_text("🚫 **هذا الأمر للمطور فقط**", parse_mode="Markdown")
                return
            
            user_count = db.get_user_count(bot_token)
            bot_info = db.get_bot(bot_token)
            
            await update.message.reply_text(
                f"📊 **إحصائيات البوت**\n\n"
                f"👥 عدد المستخدمين: {user_count}\n"
                f"🤖 اسم البوت: {bot_info['bot_name'] if bot_info else 'غير معروف'}\n"
                f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                f"🔧 المبرمج: @SSSTlF",
                parse_mode="Markdown"
            )
        
        async def reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.message.from_user
            user_id = user.id
            
            if user_id != owner_id and user_id != MASTER_OWNER_ID:
                await update.message.reply_text(
                    f"🚫 **هذا الأمر للمطور فقط**\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                return
            
            try:
                args = context.args
                if len(args) < 1:
                    await update.message.reply_text(
                        f"❌ **استخدام خاطئ**\n\n"
                        f"📌 استخدم: `/reply [معرف_المستخدم]`\n"
                        f"مثال: `/reply 123456789`\n\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                    return
                
                target_id = int(args[0])
                context.user_data['reply_target'] = target_id
                context.user_data['waiting_for'] = 'reply_choice'
                
                keyboard = [
                    [InlineKeyboardButton("📷 رد بالصورة", callback_data="reply_photo")],
                    [InlineKeyboardButton("🎵 رد بالصوت", callback_data="reply_audio")],
                    [InlineKeyboardButton("🎨 رد بالملصق", callback_data="reply_sticker")],
                    [InlineKeyboardButton("✉️ رد برسالة خاصة", callback_data="reply_message")],
                    [InlineKeyboardButton("❌ إلغاء", callback_data="reply_cancel")],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"📩 **الرد على المستخدم**\n\n"
                    f"🆔 المعرف: `{target_id}`\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"📌 اختر نوع الرد:\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
                
            except ValueError:
                await update.message.reply_text(
                    f"❌ **معرف المستخدم غير صحيح**\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
            except Exception as e:
                await update.message.reply_text(
                    f"❌ **حدث خطأ**\n\n"
                    f"الخطأ: {str(e)}\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
        
        async def reply_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            query = update.callback_query
            await query.answer()
            
            user_id = query.from_user.id
            data = query.data
            
            if user_id != owner_id and user_id != MASTER_OWNER_ID:
                await query.edit_message_text(
                    f"🚫 **غير مصرح لك**\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                return
            
            target_id = context.user_data.get('reply_target')
            if not target_id:
                await query.edit_message_text(
                    f"❌ **لا يوجد مستهدف للرد**\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                return
            
            if data == "reply_message":
                context.user_data['waiting_for'] = 'reply_text'
                await query.edit_message_text(
                    f"✉️ **إرسال رسالة خاصة**\n\n"
                    f"🆔 للمستخدم: `{target_id}`\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"📌 أرسل النص الذي تريد إرساله:\n"
                    f"🔄 /cancel للإلغاء\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
            
            elif data == "reply_photo":
                context.user_data['waiting_for'] = 'reply_photo'
                await query.edit_message_text(
                    f"📷 **إرسال صورة**\n\n"
                    f"🆔 للمستخدم: `{target_id}`\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"📌 أرسل الصورة التي تريد إرسالها:\n"
                    f"🔄 /cancel للإلغاء\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
            
            elif data == "reply_sticker":
                context.user_data['waiting_for'] = 'reply_sticker'
                await query.edit_message_text(
                    f"🎨 **إرسال ملصق**\n\n"
                    f"🆔 للمستخدم: `{target_id}`\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"📌 أرسل الملصق الذي تريد إرساله:\n"
                    f"🔄 /cancel للإلغاء\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
            
            elif data == "reply_audio":
                context.user_data['waiting_for'] = 'reply_audio'
                await query.edit_message_text(
                    f"🎵 **إرسال صوت**\n\n"
                    f"🆔 للمستخدم: `{target_id}`\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"📌 أرسل الصوت الذي تريد إرساله:\n"
                    f"🔄 /cancel للإلغاء\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
            
            elif data == "reply_cancel":
                context.user_data.clear()
                await query.edit_message_text(
                    f"❌ **تم إلغاء الرد**\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
        
        async def handle_reply_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.message.from_user
            user_id = user.id
            
            if user_id != owner_id and user_id != MASTER_OWNER_ID:
                return
            
            waiting_for = context.user_data.get('waiting_for')
            target_id = context.user_data.get('reply_target')
            
            if not target_id:
                return
            
            try:
                if waiting_for == 'reply_text':
                    await context.bot.send_message(
                        chat_id=target_id,
                        text=f"✉️ **رد من المطور**\n\n"
                             f"{update.message.text}\n\n"
                             f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                             f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                    await update.message.reply_text(
                        f"✅ **تم إرسال الرد النصي**\n\n"
                        f"🆔 للمستخدم: `{target_id}`\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                    context.user_data.clear()
                
                elif waiting_for == 'reply_photo' and update.message.photo:
                    photo = update.message.photo[-1]
                    caption = update.message.caption or "📷 رد من المطور"
                    await context.bot.send_photo(
                        chat_id=target_id,
                        photo=photo.file_id,
                        caption=f"📷 **رد من المطور**\n\n{caption}\n\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                    await update.message.reply_text(
                        f"✅ **تم إرسال الصورة**\n\n"
                        f"🆔 للمستخدم: `{target_id}`\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                    context.user_data.clear()
                
                elif waiting_for == 'reply_sticker' and update.message.sticker:
                    sticker = update.message.sticker
                    await context.bot.send_sticker(
                        chat_id=target_id,
                        sticker=sticker.file_id
                    )
                    await update.message.reply_text(
                        f"✅ **تم إرسال الملصق**\n\n"
                        f"🆔 للمستخدم: `{target_id}`\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                    context.user_data.clear()
                
                elif waiting_for == 'reply_audio' and update.message.audio:
                    audio = update.message.audio
                    caption = update.message.caption or "🎵 رد من المطور"
                    await context.bot.send_audio(
                        chat_id=target_id,
                        audio=audio.file_id,
                        caption=f"🎵 **رد من المطور**\n\n{caption}\n\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                    await update.message.reply_text(
                        f"✅ **تم إرسال الصوت**\n\n"
                        f"🆔 للمستخدم: `{target_id}`\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                    context.user_data.clear()
                
                else:
                    await update.message.reply_text(
                        f"❌ **نوع الرد غير معروف أو الوسائط غير صحيحة**\n\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                    
            except Exception as e:
                await update.message.reply_text(
                    f"❌ **فشل الإرسال**\n\n"
                    f"الخطأ: {str(e)}\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                context.user_data.clear()
        
        async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            query = update.callback_query
            await query.answer()
            user = await register_user(update)
            user_id = user.id
            data = query.data
            
            if data == "send_message":
                context.user_data['waiting_for'] = 'message'
                await query.edit_message_text(
                    "📝 **أرسل رسالتك**\n\n"
                    "📌 سيتم إيصالها للمطور فوراً\n"
                    "🔄 /cancel للإلغاء\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
            
            elif data == "send_photo":
                context.user_data['waiting_for'] = 'photo'
                await query.edit_message_text(
                    "🖼️ **أرسل الصورة**\n\n"
                    "📌 سيتم إيصالها للمطور فوراً\n"
                    "🔄 /cancel للإلغاء\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
            
            elif data == "send_video":
                context.user_data['waiting_for'] = 'video'
                await query.edit_message_text(
                    "🎥 **أرسل الفيديو**\n\n"
                    "📌 سيتم إيصاله للمطور فوراً\n"
                    "🔄 /cancel للإلغاء\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
            
            elif data == "send_audio":
                context.user_data['waiting_for'] = 'audio'
                await query.edit_message_text(
                    "🎵 **أرسل الصوت**\n\n"
                    "📌 سيتم إيصاله للمطور فوراً\n"
                    "🔄 /cancel للإلغاء\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
            
            elif data == "send_document":
                context.user_data['waiting_for'] = 'document'
                await query.edit_message_text(
                    "📎 **أرسل الملف**\n\n"
                    "📌 سيتم إيصاله للمطور فوراً\n"
                    "🔄 /cancel للإلغاء\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
            
            elif data == "about_bot":
                bot_info = db.get_bot(bot_token)
                bot_name = bot_info['bot_name'] if bot_info else "بوت التواصل"
                
                keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"ℹ️ **عن البوت**\n\n"
                    f"🤖 الاسم: {bot_name}\n"
                    f"👨‍💻 المطور: {developer_username}\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🏭 مصنع بوتات التواصل\n"
                    f"🔧 المبرمج: @SSSTlF\n"
                    f"📅 جميع الحقوق محفوظة © 2026",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            
            elif data == "admin_panel" and (user_id == owner_id or user_id == MASTER_OWNER_ID):
                keyboard = [
                    [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats"), InlineKeyboardButton("👥 المستخدمين", callback_data="admin_users")],
                    [InlineKeyboardButton("📢 إرسال جماعي", callback_data="admin_broadcast")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    f"⚙️ **لوحة التحكم**\n\n"
                    f"👨‍💻 {developer_username}\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            
            elif data == "admin_stats" and (user_id == owner_id or user_id == MASTER_OWNER_ID):
                user_count = db.get_user_count(bot_token)
                
                keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    f"📊 **إحصائيات البوت**\n\n"
                    f"👥 عدد المستخدمين: {user_count}\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            
            elif data == "admin_users" and (user_id == owner_id or user_id == MASTER_OWNER_ID):
                users = db.get_users(bot_token, 20)
                
                if not users:
                    text = "📭 **لا يوجد مستخدمين**"
                else:
                    text = "👥 **آخر المستخدمين**\n\n"
                    for u in users:
                        text += f"🆔 `{u[0]}` - {u[1]}\n"
                        if u[2]:
                            text += f"📌 @{u[2]}\n"
                        text += f"⏱️ {u[3][:16]}\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                
                keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    text + f"\n🔧 المبرمج: @SSSTlF",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            
            elif data == "admin_broadcast" and (user_id == owner_id or user_id == MASTER_OWNER_ID):
                context.user_data['waiting_for'] = 'broadcast'
                await query.edit_message_text(
                    "📢 **إرسال رسالة جماعية**\n\n"
                    "📌 أرسل الرسالة التي تريد إرسالها لجميع المستخدمين\n"
                    "⚠️ سيتم إرسالها للجميع!\n"
                    "🔄 /cancel للإلغاء\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
            
            elif data == "back_to_start":
                buttons = [
                    [InlineKeyboardButton("📩 إرسال رسالة", callback_data="send_message"), InlineKeyboardButton("🖼️ إرسال صورة", callback_data="send_photo")],
                    [InlineKeyboardButton("🎥 إرسال فيديو", callback_data="send_video"), InlineKeyboardButton("🎵 إرسال صوت", callback_data="send_audio")],
                    [InlineKeyboardButton("📎 إرسال ملف", callback_data="send_document"), InlineKeyboardButton("📌 عن البوت", callback_data="about_bot")],
                ]
                if user_id == owner_id or user_id == MASTER_OWNER_ID:
                    buttons.append([InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="admin_panel")])
                reply_markup = InlineKeyboardMarkup(buttons)
                await query.edit_message_text(
                    f"📩 **بوت التواصل**\n\n"
                    f"👨‍💻 المطور: {developer_username}\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"📌 أرسل ما تريد وسيتم إيصاله للمطور\n"
                    f"🔧 المبرمج: @SSSTlF",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
        
        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = await register_user(update)
            user_id = user.id
            waiting_for = context.user_data.get('waiting_for')
            
            if waiting_for == 'broadcast' and (user_id == owner_id or user_id == MASTER_OWNER_ID):
                users = db.get_users(bot_token, 9999)
                
                sent = 0
                failed = 0
                
                for u in users:
                    try:
                        await context.bot.send_message(
                            chat_id=u[0],
                            text=f"📢 **إعلان من المطور**\n\n{update.message.text}\n\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n🔧 المبرمج: @SSSTlF",
                            parse_mode="Markdown"
                        )
                        sent += 1
                    except:
                        failed += 1
                
                await update.message.reply_text(
                    f"✅ **تم إرسال البث**\n\n"
                    f"📨 تم الإرسال لـ: {sent} مستخدم\n"
                    f"❌ فشل: {failed}\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                context.user_data['waiting_for'] = None
                return
            
            if waiting_for == 'message':
                await context.bot.send_message(
                    chat_id=owner_id,
                    text=f"📩 **رسالة جديدة**\n\n"
                         f"👤 من: {user.first_name}\n"
                         f"🆔 ID: `{user_id}`\n"
                         f"📝 المحتوى:\n{update.message.text}\n\n"
                         f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                         f"💡 للرد: اكتب /reply {user_id}\n"
                         f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                await update.message.reply_text(
                    f"✅ **تم الإرسال بنجاح**\n\n"
                    f"📩 سيتم رد المطور عليك قريباً\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                context.user_data['waiting_for'] = None
            
            elif waiting_for == 'photo' and update.message.photo:
                photo = update.message.photo[-1]
                caption = update.message.caption or "🖼️ صورة جديدة"
                await context.bot.send_photo(
                    chat_id=owner_id,
                    photo=photo.file_id,
                    caption=f"🖼️ **صورة جديدة**\n\n"
                            f"👤 من: {user.first_name}\n"
                            f"🆔 ID: `{user_id}`\n"
                            f"📝 التعليق: {caption}\n\n"
                            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                            f"💡 للرد: اكتب /reply {user_id}\n"
                            f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                await update.message.reply_text(
                    f"✅ **تم إرسال الصورة**\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                context.user_data['waiting_for'] = None
            
            elif waiting_for == 'video' and update.message.video:
                video = update.message.video
                caption = update.message.caption or "🎥 فيديو جديد"
                await context.bot.send_video(
                    chat_id=owner_id,
                    video=video.file_id,
                    caption=f"🎥 **فيديو جديد**\n\n"
                            f"👤 من: {user.first_name}\n"
                            f"🆔 ID: `{user_id}`\n"
                            f"📝 التعليق: {caption}\n\n"
                            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                            f"💡 للرد: اكتب /reply {user_id}\n"
                            f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                await update.message.reply_text(
                    f"✅ **تم إرسال الفيديو**\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                context.user_data['waiting_for'] = None
            
            elif waiting_for == 'audio' and update.message.audio:
                audio = update.message.audio
                caption = update.message.caption or "🎵 صوت جديد"
                await context.bot.send_audio(
                    chat_id=owner_id,
                    audio=audio.file_id,
                    caption=f"🎵 **صوت جديد**\n\n"
                            f"👤 من: {user.first_name}\n"
                            f"🆔 ID: `{user_id}`\n"
                            f"📝 التعليق: {caption}\n\n"
                            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                            f"💡 للرد: اكتب /reply {user_id}\n"
                            f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                await update.message.reply_text(
                    f"✅ **تم إرسال الصوت**\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                context.user_data['waiting_for'] = None
            
            elif waiting_for == 'document' and update.message.document:
                doc = update.message.document
                caption = update.message.caption or "📎 ملف جديد"
                await context.bot.send_document(
                    chat_id=owner_id,
                    document=doc.file_id,
                    caption=f"📎 **ملف جديد**\n\n"
                            f"👤 من: {user.first_name}\n"
                            f"🆔 ID: `{user_id}`\n"
                            f"📄 الاسم: {doc.file_name}\n"
                            f"📝 التعليق: {caption}\n\n"
                            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                            f"💡 للرد: اكتب /reply {user_id}\n"
                            f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                await update.message.reply_text(
                    f"✅ **تم إرسال الملف**\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                context.user_data['waiting_for'] = None
            
            else:
                await update.message.reply_text(
                    f"❌ **أمر غير معروف**\n\n"
                    f"📌 استخدم الأزرار أو الأوامر التالية:\n"
                    f"/start - للبدء\n"
                    f"/help - للمساعدة\n"
                    f"/about - معلومات البوت\n"
                    f"/dev - معلومات المطور\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("about", about_command))
        app.add_handler(CommandHandler("dev", dev_command))
        app.add_handler(CommandHandler("stats", stats_command))
        app.add_handler(CommandHandler("reply", reply_command))
        app.add_handler(CommandHandler("cancel", lambda u, c: u.message.reply_text("❌ تم الإلغاء\n\n🔧 المبرمج: @SSSTlF", parse_mode="Markdown")))
        app.add_handler(CallbackQueryHandler(button_handler))
        app.add_handler(CallbackQueryHandler(reply_button_handler, pattern="^reply_"))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(MessageHandler(filters.PHOTO, handle_message))
        app.add_handler(MessageHandler(filters.VIDEO, handle_message))
        app.add_handler(MessageHandler(filters.AUDIO, handle_message))
        app.add_handler(MessageHandler(filters.Document.ALL, handle_message))
        app.add_handler(MessageHandler(filters.REPLY, handle_reply_send))
        
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        
        logger.info(f"✅ Sub bot {bot_token[:10]}... started successfully!")
        
        while True:
            await asyncio.sleep(10)
            
    except Exception as e:
        logger.error(f"❌ Sub bot {bot_token[:10]}... error: {e}")
        import traceback
        traceback.print_exc()
        if bot_token in active_bots:
            del active_bots[bot_token]
        if bot_token in bot_tasks:
            del bot_tasks[bot_token]

def start_sub_bot(bot_token, owner_id, developer_username):
    try:
        if bot_token in active_bots:
            return False, "البوت يعمل بالفعل"
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        def run_bot():
            try:
                asyncio.set_event_loop(loop)
                loop.run_until_complete(run_sub_bot_async(bot_token, owner_id, developer_username))
            except Exception as e:
                logger.error(f"Error in bot loop: {e}")
            finally:
                loop.close()
        
        thread = threading.Thread(target=run_bot, daemon=True)
        thread.start()
        
        active_bots[bot_token] = True
        bot_tasks[bot_token] = thread
        
        logger.info(f"✅ Bot {bot_token[:10]}... started in background")
        return True, "تم تشغيل البوت ✅"
        
    except Exception as e:
        logger.error(f"Error starting sub bot: {e}")
        return False, f"خطأ: {str(e)}"

def stop_sub_bot(bot_token):
    try:
        if bot_token in active_bots:
            del active_bots[bot_token]
        if bot_token in bot_tasks:
            del bot_tasks[bot_token]
        
        db.update_bot_active(bot_token, False)
        logger.info(f"⏸️ Bot {bot_token[:10]}... stopped")
        return True, "تم إيقاف البوت ⏸️"
    except Exception as e:
        logger.error(f"Error stopping bot: {e}")
        return False, str(e)

# ========== البوت الرئيسي (مع نظام الطلبات) ==========
class MasterBot:
    def __init__(self, token):
        self.token = token
        self.app = None
    
    async def start(self):
        self.app = Application.builder().token(self.token).build()
        await self._setup_handlers()
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        logger.info("✅ Master bot started!")
        return self.app
    
    async def _setup_handlers(self):
        async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.message.from_user
            user_id = user.id
            
            db.add_master_developer(user_id, user.username)
            
            keyboard = []
            
            # كل المستخدمين يرون زر طلب بوت جديد
            keyboard.append([InlineKeyboardButton("🤖 طلب بوت جديد", callback_data="request_bot")])
            
            # فقط المطور الرئيسي يرى الإدارة
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
            
            # ===== فقط المطور الرئيسي =====
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
                
                # إنشاء البوت
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
                    
                    # إرسال رسالة للطالب
                    try:
                        await context.bot.send_message(
                            chat_id=req['user_id'],
                            text=f"✅ **تم قبول طلبك!**\n\n"
                                 f"🤖 بوتك جاهز الآن:\n"
                                 f"@{req['bot_username']}\n\n"
                                 f"📌 استخدم /start للبدء\n"
                                 f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                                 f"🔧 المبرمج: @SSSTlF",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
                    
                    await query.edit_message_text(
                        f"✅ **تم قبول الطلب #{request_id}**\n\n"
                        f"🤖 {req['bot_name']} يعمل الآن\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                else:
                    await query.edit_message_text(
                        f"❌ فشل في إنشاء البوت\n\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                return
            
            elif data.startswith("reject_"):
                request_id = int(data.replace("reject_", ""))
                req = db.get_pending_request(request_id)
                if not req:
                    await query.edit_message_text("❌ الطلب غير موجود.", parse_mode="Markdown")
                    return
                
                db.update_request_status(request_id, 'rejected')
                
                # إرسال رسالة رفض للطالب
                try:
                    await context.bot.send_message(
                        chat_id=req['user_id'],
                        text=f"❌ **تم رفض طلبك**\n\n"
                             f"🤖 عذراً، لم يتم الموافقة على بوتك\n"
                             f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                             f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                except:
                    pass
                
                await query.edit_message_text(
                    f"❌ **تم رفض الطلب #{request_id}**\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                return
            
            elif data == "factory_stats":
                bots = db.get_all_bots()
                total = len(bots)
                active = len(active_bots)
                pending = len(db.get_pending_requests())
                
                text = f"📊 **إحصائيات المصنع**\n\n"
                text += f"🤖 إجمالي البوتات: {total}\n"
                text += f"🟢 النشطة: {active}\n"
                text += f"🔴 المتوقفة: {total - active}\n"
                text += f"📋 طلبات معلقة: {pending}\n"
                text += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                
                if bots:
                    for bot in bots[-5:]:
                        running = "🔄" if bot['bot_token'] in active_bots else "⏸️"
                        text += f"{running} {bot['bot_name']}\n"
                
                keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    text + f"\n🔧 المبرمج: @SSSTlF",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
                return
            
            elif data == "manage_bots":
                bots = db.get_all_bots()
                if not bots:
                    await query.edit_message_text(
                        f"📭 لا توجد بوتات.\n\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                    return
                
                keyboard = []
                for bot in bots:
                    status = "🟢" if bot['is_active'] else "🔴"
                    btn_text = f"{status} {bot['bot_name']}"
                    keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"manage_{bot['bot_token']}")])
                
                keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")])
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    "⚙️ **إدارة البوتات**\n\nاختر بوتاً:\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
                return
            
            elif data.startswith("manage_"):
                bot_token = data.replace("manage_", "")
                bot_data = db.get_bot(bot_token)
                if not bot_data:
                    await query.edit_message_text("❌ البوت غير موجود.", parse_mode="Markdown")
                    return
                
                is_running = bot_token in active_bots
                
                keyboard = []
                if is_running:
                    keyboard.append([InlineKeyboardButton("⏸️ إيقاف", callback_data=f"stop_{bot_token}")])
                else:
                    keyboard.append([InlineKeyboardButton("▶️ تشغيل", callback_data=f"start_{bot_token}")])
                keyboard.append([InlineKeyboardButton("🔄 إعادة تشغيل", callback_data=f"restart_{bot_token}")])
                keyboard.append([InlineKeyboardButton("🗑️ حذف", callback_data=f"delete_{bot_token}")])
                keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="manage_bots")])
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                status = "🟢 مفعل" if bot_data['is_active'] else "🔴 معطل"
                running = "🔄 يعمل" if is_running else "⏸️ متوقف"
                
                await query.edit_message_text(
                    f"⚙️ **إدارة البوت**\n\n"
                    f"🤖 {bot_data['bot_name']}\n"
                    f"🆔 @{bot_data['bot_username']}\n"
                    f"📌 {status}\n"
                    f"🔄 {running}\n"
                    f"👤 المالك: @{bot_data['owner_username'] or 'unknown'}\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
                return
            
            elif data.startswith("start_"):
                bot_token = data.replace("start_", "")
                bot_data = db.get_bot(bot_token)
                if not bot_data:
                    await query.edit_message_text("❌ البوت غير موجود", parse_mode="Markdown")
                    return
                
                db.update_bot_active(bot_token, True)
                success, msg = start_sub_bot(bot_token, bot_data['owner_id'], bot_data['developer_username'])
                await query.edit_message_text(
                    f"{'✅' if success else '❌'} {msg}\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                return
            
            elif data.startswith("stop_"):
                bot_token = data.replace("stop_", "")
                success, msg = stop_sub_bot(bot_token)
                await query.edit_message_text(
                    f"{'✅' if success else '❌'} {msg}\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                return
            
            elif data.startswith("restart_"):
                bot_token = data.replace("restart_", "")
                bot_data = db.get_bot(bot_token)
                if not bot_data:
                    await query.edit_message_text("❌ البوت غير موجود", parse_mode="Markdown")
                    return
                
                stop_sub_bot(bot_token)
                db.update_bot_active(bot_token, True)
                success, msg = start_sub_bot(bot_token, bot_data['owner_id'], bot_data['developer_username'])
                await query.edit_message_text(
                    f"{'✅' if success else '❌'} إعادة تشغيل: {msg}\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                return
            
            elif data.startswith("delete_"):
                bot_token = data.replace("delete_", "")
                stop_sub_bot(bot_token)
                db.delete_bot(bot_token)
                await query.edit_message_text(
                    f"🗑️ **تم حذف البوت**\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                return
            
            elif data == "back_to_main":
                keyboard = []
                keyboard.append([InlineKeyboardButton("🤖 طلب بوت جديد", callback_data="request_bot")])
                if user_id == MASTER_OWNER_ID:
                    keyboard.extend([
                        [InlineKeyboardButton("📋 الطلبات المعلقة", callback_data="pending_requests")],
                        [InlineKeyboardButton("📊 إحصائيات المصنع", callback_data="factory_stats")],
                        [InlineKeyboardButton("⚙️ إدارة البوتات", callback_data="manage_bots")],
                    ])
                keyboard.append([InlineKeyboardButton("ℹ️ عن المصنع", callback_data="about")])
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    "🏭 **مصنع بوتات التواصل**\n\n📌 اختر ما تريد:\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
                return
        
        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.message.from_user
            user_id = user.id
            text = update.message.text
            
            if text and text.lower() == "/cancel":
                context.user_data.clear()
                await update.message.reply_text(
                    f"❌ تم الإلغاء\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                return
            
            if context.user_data.get('waiting_for') == 'bot_token':
                bot_token = text.strip()
                
                if ":" not in bot_token or len(bot_token) < 20:
                    await update.message.reply_text(
                        f"❌ **توكن غير صحيح**\n\n"
                        f"📌 يجب أن يكون:\n"
                        f"`1234567890:ABCdef...`\n\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                    return
                
                if db.get_bot(bot_token):
                    await update.message.reply_text(
                        f"❌ **هذا البوت مستخدم بالفعل**\n\nأرسل توكن آخر:\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                    return
                
                context.user_data['bot_token'] = bot_token
                context.user_data['waiting_for'] = 'bot_name'
                await update.message.reply_text(
                    f"✅ **تم التحقق**\n\n"
                    f"📌 **الخطوة 2:** أرسل اسم البوت:\n"
                    f"مثال: `بوت التواصل`\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                return
            
            elif context.user_data.get('waiting_for') == 'bot_name':
                bot_name = text.strip()
                context.user_data['bot_name'] = bot_name
                context.user_data['waiting_for'] = 'bot_username'
                await update.message.reply_text(
                    f"✅ **تم حفظ الاسم**\n\n"
                    f"📌 **الخطوة 3:** أرسل يوزر البوت (بدون @):\n"
                    f"مثال: `MySupportBot`\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                return
            
            elif context.user_data.get('waiting_for') == 'bot_username':
                bot_username = text.strip().replace("@", "")
                bot_token = context.user_data.get('bot_token')
                bot_name = context.user_data.get('bot_name')
                
                if not bot_token or not bot_name:
                    await update.message.reply_text(
                        f"❌ خطأ في البيانات\n\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                    context.user_data.clear()
                    return
                
                # إضافة طلب جديد
                request_id = db.add_pending_request(
                    user_id=user_id,
                    username=user.username,
                    bot_token=bot_token,
                    bot_name=bot_name,
                    bot_username=bot_username
                )
                
                if request_id:
                    # إرسال اشعار للمطور الرئيسي
                    await context.bot.send_message(
                        chat_id=MASTER_OWNER_ID,
                        text=f"🔔 **طلب بوت جديد**\n\n"
                             f"👤 من: @{user.username or 'unknown'}\n"
                             f"🆔 ID: `{user_id}`\n"
                             f"🤖 البوت: {bot_name}\n"
                             f"🆔 @{bot_username}\n"
                             f"📌 رقم الطلب: #{request_id}\n"
                             f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                             f"✅ للقبول: /approve {request_id}\n"
                             f"❌ للرفض: /reject {request_id}\n"
                             f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                    
                    await update.message.reply_text(
                        f"✅ **تم إرسال طلبك بنجاح!**\n\n"
                        f"📌 رقم الطلب: #{request_id}\n"
                        f"⏳ في انتظار موافقة المطور\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                else:
                    await update.message.reply_text(
                        f"❌ فشل في إرسال الطلب\n\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                
                context.user_data.clear()
                return
        
        # أوامر الموافقة/الرفض السريعة (للمطور الرئيسي فقط)
        async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.message.from_user.id
            if user_id != MASTER_OWNER_ID:
                await update.message.reply_text("🚫 غير مصرح لك.", parse_mode="Markdown")
                return
            
            try:
                request_id = int(context.args[0])
                req = db.get_pending_request(request_id)
                if not req:
                    await update.message.reply_text("❌ الطلب غير موجود.", parse_mode="Markdown")
                    return
                
                if req['status'] != 'pending':
                    await update.message.reply_text(f"❌ الطلب {req['status']} بالفعل.", parse_mode="Markdown")
                    return
                
                # إنشاء البوت
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
                                 f"📌 استخدم /start للبدء\n"
                                 f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                                 f"🔧 المبرمج: @SSSTlF",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
                    
                    await update.message.reply_text(
                        f"✅ **تم قبول الطلب #{request_id}**\n\n"
                        f"🤖 {req['bot_name']} يعمل الآن\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                else:
                    await update.message.reply_text(
                        f"❌ فشل في إنشاء البوت\n\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
            except:
                await update.message.reply_text(
                    f"❌ استخدم: /approve [رقم_الطلب]\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
        
        async def reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.message.from_user.id
            if user_id != MASTER_OWNER_ID:
                await update.message.reply_text("🚫 غير مصرح لك.", parse_mode="Markdown")
                return
            
            try:
                request_id = int(context.args[0])
                req = db.get_pending_request(request_id)
                if not req:
                    await update.message.reply_text("❌ الطلب غير موجود.", parse_mode="Markdown")
                    return
                
                if req['status'] != 'pending':
                    await update.message.reply_text(f"❌ الطلب {req['status']} بالفعل.", parse_mode="Markdown")
                    return
                
                db.update_request_status(request_id, 'rejected')
                
                try:
                    await context.bot.send_message(
                        chat_id=req['user_id'],
                        text=f"❌ **تم رفض طلبك**\n\n"
                             f"🤖 عذراً، لم يتم الموافقة على بوتك\n"
                             f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                             f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                except:
                    pass
                
                await update.message.reply_text(
                    f"❌ **تم رفض الطلب #{request_id}**\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
            except:
                await update.message.reply_text(
                    f"❌ استخدم: /reject [رقم_الطلب]\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
        
        self.app.add_handler(CommandHandler("start", start))
        self.app.add_handler(CommandHandler("approve", approve_command))
        self.app.add_handler(CommandHandler("reject", reject_command))
        self.app.add_handler(CommandHandler("cancel", lambda u, c: u.message.reply_text("❌ تم الإلغاء\n\n🔧 المبرمج: @SSSTlF", parse_mode="Markdown")))
        self.app.add_handler(CallbackQueryHandler(button_handler))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# ========== التشغيل ==========
async def main_async():
    print("🚀 Starting Bot Factory...")
    print(f"🤖 Master Bot: {MASTER_BOT_TOKEN[:10]}...")
    print(f"👨‍💻 Owner ID: {MASTER_OWNER_ID}")
    print(f"🔧 المبرمج: {DEVELOPER_USERNAME}")
    
    master = MasterBot(MASTER_BOT_TOKEN)
    await master.start()
    
    # تشغيل البوتات الموجودة تلقائياً
    all_bots = db.get_all_bots()
    for bot in all_bots:
        if bot['is_active']:
            success, msg = start_sub_bot(bot['bot_token'], bot['owner_id'], bot['developer_username'])
            logger.info(f"Auto-start {bot['bot_name']}: {msg}")
    
    print("✅ Bot Factory is running!")
    print("📱 Open: @SSSTlF_bot")
    print(f"🔧 المبرمج: {DEVELOPER_USERNAME}")
    
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n🛑 Stopped.")
