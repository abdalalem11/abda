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

# ========== قاموس البوتات النشطة ==========
active_bots = {}
bot_tasks = {}
bot_apps = {}

# ========== تشغيل بوت فرعي ==========
async def run_sub_bot_async(bot_token, owner_id, developer_username):
    """تشغيل بوت فرعي مع أزرار الرد التلقائية للمطور"""
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
        
        def get_developer_display():
            return developer_username if developer_username else "المطور"
        
        # ===== أوامر البوت =====
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
                f"👨‍💻 المطور: {get_developer_display()}\n"
                f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                f"📌 أرسل ما تريد وسيتم إيصاله للمطور\n"
                f"🔧 المبرمج: @SSSTlF",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        
        async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            await register_user(update)
            await update.message.reply_text(
                f"📖 **قائمة الأوامر**\n\n"
                f"/start - بدء البوت\n"
                f"/help - عرض هذه القائمة\n"
                f"/about - معلومات عن البوت\n"
                f"/dev - معلومات المطور\n"
                f"/stats - إحصائيات البوت (للمطور فقط)\n"
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
            await register_user(update)
            bot_info = db.get_bot(bot_token)
            bot_name = bot_info['bot_name'] if bot_info else "بوت التواصل"
            
            await update.message.reply_text(
                f"ℹ️ **معلومات البوت**\n\n"
                f"🤖 الاسم: {bot_name}\n"
                f"🆔 @{bot_info['bot_username'] if bot_info else 'unknown'}\n"
                f"👨‍💻 المطور: {get_developer_display()}\n"
                f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                f"🏭 تم صنعه بواسطة مصنع بوتات التواصل\n"
                f"🔧 المبرمج: @SSSTlF\n"
                f"📅 جميع الحقوق محفوظة © 2026",
                parse_mode="Markdown"
            )
        
        async def dev_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            await register_user(update)
            await update.message.reply_text(
                f"👨‍💻 **المطور**\n\n"
                f"📌 المطور: {get_developer_display()}\n"
                f"🆔 ID: {owner_id}\n"
                f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                f"🏭 مصنع بوتات التواصل\n"
                f"🔧 المبرمج: @SSSTlF",
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
        
        # ===== دالة إرسال رسالة للمطور مع أزرار الرد =====
        async def send_to_developer(update: Update, context: ContextTypes.DEFAULT_TYPE, user, user_id, message_text=None, media_type=None, media_id=None, caption=None, file_name=None):
            """إرسال رسالة للمطور مع أزرار الرد"""
            
            text = f"📩 **رسالة جديدة**\n\n"
            text += f"👤 من: {user.first_name}\n"
            text += f"🆔 ID: `{user_id}`\n"
            
            if media_type == "photo":
                text += f"🖼️ صورة\n"
                if caption:
                    text += f"📝 التعليق: {caption}\n"
            elif media_type == "video":
                text += f"🎥 فيديو\n"
                if caption:
                    text += f"📝 التعليق: {caption}\n"
            elif media_type == "audio":
                text += f"🎵 صوت\n"
                if caption:
                    text += f"📝 التعليق: {caption}\n"
            elif media_type == "document":
                text += f"📎 ملف\n"
                text += f"📄 الاسم: {file_name or 'غير معروف'}\n"
                if caption:
                    text += f"📝 التعليق: {caption}\n"
            else:
                text += f"📝 المحتوى:\n{message_text}\n"
            
            text += f"\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            text += f"🔧 المبرمج: @SSSTlF"
            
            # أزرار الرد - جميع الأنواع
            keyboard = [
                [InlineKeyboardButton("💬 رد برسالة", callback_data=f"reply_text_{user_id}")],
                [InlineKeyboardButton("🖼️ رد بصورة", callback_data=f"reply_photo_{user_id}")],
                [InlineKeyboardButton("🎥 رد بفيديو", callback_data=f"reply_video_{user_id}")],
                [InlineKeyboardButton("🎵 رد بصوت", callback_data=f"reply_audio_{user_id}")],
                [InlineKeyboardButton("📎 رد بملف", callback_data=f"reply_document_{user_id}")],
                [InlineKeyboardButton("🎨 رد بملصق", callback_data=f"reply_sticker_{user_id}")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # إرسال للمطور
            if media_type == "photo":
                await context.bot.send_photo(
                    chat_id=owner_id,
                    photo=media_id,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            elif media_type == "video":
                await context.bot.send_video(
                    chat_id=owner_id,
                    video=media_id,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            elif media_type == "audio":
                await context.bot.send_audio(
                    chat_id=owner_id,
                    audio=media_id,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            elif media_type == "document":
                await context.bot.send_document(
                    chat_id=owner_id,
                    document=media_id,
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            else:
                await context.bot.send_message(
                    chat_id=owner_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
        
        # ===== معالج أزرار الرد التي تظهر للمطور =====
        async def reply_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            query = update.callback_query
            await query.answer()
            
            user_id = query.from_user.id
            
            if user_id != owner_id and user_id != MASTER_OWNER_ID:
                await query.edit_message_text(
                    f"🚫 **غير مصرح لك**\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                return
            
            data = query.data
            parts = data.split("_")
            action = parts[1]  # text, photo, video, audio, document, sticker
            target_user_id = int(parts[2])
            
            context.user_data['reply_target'] = target_user_id
            context.user_data['reply_action'] = action
            
            # رسائل خاصة بكل نوع
            messages = {
                "text": "💬 أرسل الرسالة التي تريد إرسالها للمستخدم.\n\n❌ للإلغاء أرسل /cancel",
                "photo": "🖼️ أرسل الصورة التي تريد إرسالها للمستخدم.\n\n❌ للإلغاء أرسل /cancel",
                "video": "🎥 أرسل الفيديو الذي تريد إرساله للمستخدم.\n\n❌ للإلغاء أرسل /cancel",
                "audio": "🎵 أرسل الملف الصوتي الذي تريد إرساله للمستخدم.\n\n❌ للإلغاء أرسل /cancel",
                "document": "📎 أرسل الملف الذي تريد إرساله للمستخدم.\n\n❌ للإلغاء أرسل /cancel",
                "sticker": "🎨 أرسل الملصق الذي تريد إرساله للمستخدم.\n\n❌ للإلغاء أرسل /cancel"
            }
            
            if action in messages:
                await query.edit_message_text(
                    f"{messages[action]}\n\n"
                    f"🆔 للمستخدم: `{target_user_id}`\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                context.user_data['waiting_for'] = f'reply_{action}'
            else:
                await query.edit_message_text("❌ نوع الرد غير معروف", parse_mode="Markdown")
        
        # ===== معالج إرسال الردود =====
        async def handle_reply_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.message.from_user
            user_id = user.id
            
            if user_id != owner_id and user_id != MASTER_OWNER_ID:
                return
            
            waiting_for = context.user_data.get('waiting_for')
            target_id = context.user_data.get('reply_target')
            
            if update.message.text and update.message.text.lower() == "/cancel":
                context.user_data.clear()
                await update.message.reply_text(
                    f"❌ تم الإلغاء\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                return
            
            if not target_id or not waiting_for:
                return
            
            try:
                if waiting_for == 'reply_text' and update.message.text:
                    await context.bot.send_message(
                        chat_id=target_id,
                        text=f"💬 **رد من المطور**\n\n{update.message.text}\n\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n🔧 المبرمج: @SSSTlF",
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
                    caption = update.message.caption or "🖼️ رد من المطور"
                    await context.bot.send_photo(
                        chat_id=target_id,
                        photo=photo.file_id,
                        caption=f"🖼️ **رد من المطور**\n\n{caption}\n\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n🔧 المبرمج: @SSSTlF",
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
                
                elif waiting_for == 'reply_video' and update.message.video:
                    video = update.message.video
                    caption = update.message.caption or "🎥 رد من المطور"
                    await context.bot.send_video(
                        chat_id=target_id,
                        video=video.file_id,
                        caption=f"🎥 **رد من المطور**\n\n{caption}\n\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                    await update.message.reply_text(
                        f"✅ **تم إرسال الفيديو**\n\n"
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
                
                elif waiting_for == 'reply_document' and update.message.document:
                    doc = update.message.document
                    caption = update.message.caption or "📎 رد من المطور"
                    await context.bot.send_document(
                        chat_id=target_id,
                        document=doc.file_id,
                        caption=f"📎 **رد من المطور**\n\n{caption}\n\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                    await update.message.reply_text(
                        f"✅ **تم إرسال الملف**\n\n"
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
                
                else:
                    await update.message.reply_text(
                        f"❌ **نوع الرد غير معروف أو الوسائط غير صحيحة**\n\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"🔧 المبرمج: @SSSTlF",
                        parse_mode="Markdown"
                    )
                    context.user_data.clear()
                    
            except Exception as e:
                await update.message.reply_text(
                    f"❌ **فشل الإرسال**\n\n"
                    f"الخطأ: {str(e)}\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                context.user_data.clear()
        
        # ===== معالج الأزرار الرئيسية =====
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
                    f"👨‍💻 المطور: {get_developer_display()}\n"
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
                    f"👨‍💻 {get_developer_display()}\n"
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
                    f"👨‍💻 المطور: {get_developer_display()}\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"📌 أرسل ما تريد وسيتم إيصاله للمطور\n"
                    f"🔧 المبرمج: @SSSTlF",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
        
        # ===== معالج الرسائل =====
        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = await register_user(update)
            user_id = user.id
            waiting_for = context.user_data.get('waiting_for')
            
            # معالجة البث الجماعي
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
            
            # ===== إرسال رسائل المستخدمين للمطور =====
            if waiting_for == 'message':
                await send_to_developer(update, context, user, user_id, message_text=update.message.text)
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
                caption = update.message.caption or ""
                await send_to_developer(update, context, user, user_id, media_type="photo", media_id=photo.file_id, caption=caption)
                await update.message.reply_text(
                    f"✅ **تم إرسال الصورة**\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                context.user_data['waiting_for'] = None
            
            elif waiting_for == 'video' and update.message.video:
                video = update.message.video
                caption = update.message.caption or ""
                await send_to_developer(update, context, user, user_id, media_type="video", media_id=video.file_id, caption=caption)
                await update.message.reply_text(
                    f"✅ **تم إرسال الفيديو**\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                context.user_data['waiting_for'] = None
            
            elif waiting_for == 'audio' and update.message.audio:
                audio = update.message.audio
                caption = update.message.caption or ""
                await send_to_developer(update, context, user, user_id, media_type="audio", media_id=audio.file_id, caption=caption)
                await update.message.reply_text(
                    f"✅ **تم إرسال الصوت**\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                context.user_data['waiting_for'] = None
            
            elif waiting_for == 'document' and update.message.document:
                doc = update.message.document
                caption = update.message.caption or ""
                await send_to_developer(update, context, user, user_id, media_type="document", media_id=doc.file_id, caption=caption, file_name=doc.file_name)
                await update.message.reply_text(
                    f"✅ **تم إرسال الملف**\n\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"🔧 المبرمج: @SSSTlF",
                    parse_mode="Markdown"
                )
                context.user_data['waiting_for'] = None
            
            elif user_id == owner_id or user_id == MASTER_OWNER_ID:
                pass
            
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
        
        # ===== إضافة المعالجات =====
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("about", about_command))
        app.add_handler(CommandHandler("dev", dev_command))
        app.add_handler(CommandHandler("stats", stats_command))
        app.add_handler(CommandHandler("cancel", lambda u, c: u.message.reply_text("❌ تم الإلغاء\n\n🔧 المبرمج: @SSSTlF", parse_mode="Markdown")))
        app.add_handler(CallbackQueryHandler(button_handler, pattern="^(send_|about_|admin_|back_)"))
        app.add_handler(CallbackQueryHandler(reply_button_handler, pattern="^reply_"))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(MessageHandler(filters.PHOTO, handle_message))
        app.add_handler(MessageHandler(filters.VIDEO, handle_message))
        app.add_handler(MessageHandler(filters.AUDIO, handle_message))
        app.add_handler(MessageHandler(filters.Document.ALL, handle_message))
        app.add_handler(MessageHandler(filters.Sticker.ALL, handle_message))
        app.add_handler(MessageHandler(filters.ALL, handle_reply_send))
        
        await app.initialize()
        await app.start()
        await app.bot.delete_webhook()
        await app.updater.start_polling(drop_pending_updates=True)
        
        bot_apps[bot_token] = app
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
        if bot_token in bot_apps:
            del bot_apps[bot_token]

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
        if bot_token in bot_apps:
            try:
                app = bot_apps[bot_token]
                if hasattr(app, 'updater') and app.updater:
                    asyncio.create_task(app.updater.stop())
            except Exception as e:
                logger.error(f"Error stopping app: {e}")
            del bot_apps[bot_token]
        
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

# ========== البوت الرئيسي ==========
class MasterBot:
    def __init__(self, token):
        self.token = token
        self.app = None
        self.running = True
    
    async def start(self):
        self.app = Application.builder().token(self.token).build()
        await self._setup_handlers()
        await self.app.initialize()
        await self.app.start()
        await self.app.bot.delete_webhook()
        
        try:
            await self.app.updater.start_polling(drop_pending_updates=True)
            logger.info("✅ Master bot started!")
        except Exception as e:
            logger.error(f"Error starting master bot: {e}")
            await asyncio.sleep(5)
            await self.app.updater.start_polling(drop_pending_updates=True)
        
        return self.app
    
    async def _setup_handlers(self):
        async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
                active_bots = db.cursor.execute("SELECT COUNT(*) FROM bots WHERE is_active = 1").fetchone()[0]
                pending = len(db.get_pending_requests())
                
                keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"📊 **إحصائيات المصنع**\n\n"
                    f"🤖 إجمالي البوتات: {total_bots}\n"
                    f"🟢 البوتات النشطة: {active_bots}\n"
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
        
        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.message.from_user
            user_id = user.id
            
            waiting_for = context.user_data.get('waiting_for')
            
            if waiting_for == 'bot_token':
                bot_token = update.message.text.strip()
                
                # تحقق من صحة التوكن
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
                
                # التحقق من البوت
                try:
                    temp_app = Application.builder().token(bot_token).build()
                    await temp_app.initialize()
                    bot_info = await temp_app.bot.get_me()
                    
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
                
                # حفظ الطلب
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
                    
                    # إشعار المطور
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
        
        self.app.add_handler(CommandHandler("start", start))
        self.app.add_handler(CommandHandler("cancel", lambda u, c: u.message.reply_text("❌ تم الإلغاء\n\n🔧 المبرمج: @SSSTlF", parse_mode="Markdown")))
        self.app.add_handler(CallbackQueryHandler(button_handler))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# ========== التشغيل ==========
async def main():
    master = MasterBot(MASTER_BOT_TOKEN)
    await master.start()
    
    # تشغيل البوتات المخزنة
    bots = db.get_all_bots()
    for bot in bots:
        if bot['is_active']:
            start_sub_bot(bot['bot_token'], bot['owner_id'], bot['developer_username'])
    
    # البقاء قيد التشغيل
    while True:
        await asyncio.sleep(60)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
