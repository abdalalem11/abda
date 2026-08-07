import os
import json
import logging
import asyncio
import threading
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ========== إعدادات ==========
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MASTER_OWNER_ID = 1170411845
MASTER_BOT_TOKEN = "8909739497:AAHmL5nLCKm6OKkRsjJDIoNQoC_VP9uN5TM"

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
    
    def close(self):
        self.conn.close()

db = BotFactoryDB()

# ========== نظام إدارة البوتات ==========
class BotManager:
    def __init__(self, db):
        self.db = db
        self.active_bots = {}
        self.bot_instances = {}
    
    def start_bot_process(self, bot_token):
        try:
            bot_data = self.db.get_bot(bot_token)
            if not bot_data:
                return False, "البوت غير موجود"
            
            if not bot_data['is_active']:
                return False, "البوت معطل"
            
            app = Application.builder().token(bot_token).build()
            self._setup_bot_handlers(app, bot_data)
            
            def run_bot():
                try:
                    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
                except Exception as e:
                    logger.error(f"Bot {bot_token} error: {e}")
            
            thread = threading.Thread(target=run_bot, daemon=True)
            thread.start()
            
            self.bot_instances[bot_token] = app
            self.active_bots[bot_token] = {"app": app, "thread": thread}
            
            return True, "تم تشغيل البوت بنجاح"
            
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            return False, str(e)
    
    def stop_bot(self, bot_token):
        try:
            if bot_token in self.active_bots:
                app = self.bot_instances.get(bot_token)
                if app:
                    asyncio.create_task(app.stop())
                del self.active_bots[bot_token]
                if bot_token in self.bot_instances:
                    del self.bot_instances[bot_token]
                self.db.update_bot_active(bot_token, False)
                return True, "تم إيقاف البوت"
            return False, "البوت غير قيد التشغيل"
        except Exception as e:
            return False, str(e)
    
    def _setup_bot_handlers(self, app, bot_data):
        owner_id = bot_data['owner_id']
        developer_username = bot_data['developer_username']
        bot_name = bot_data['bot_name']
        
        async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.message.from_user
            user_id = user.id
            
            cursor = db.conn.cursor()
            cursor.execute("SELECT 1 FROM global_banned WHERE user_id = ?", (user_id,))
            if cursor.fetchone() and user_id != owner_id and user_id != MASTER_OWNER_ID:
                await update.message.reply_text("🚫 **أنت محظور من استخدام هذا البوت.**", parse_mode="Markdown")
                return
            
            keyboard = [
                [InlineKeyboardButton("📩 رسالة", callback_data="send_message")],
                [InlineKeyboardButton("🖼️ صورة", callback_data="send_photo")],
                [InlineKeyboardButton("🎥 فيديو", callback_data="send_video")],
                [InlineKeyboardButton("🎵 صوت", callback_data="send_audio")],
                [InlineKeyboardButton("📎 ملف", callback_data="send_document")],
                [InlineKeyboardButton("🏷️ ملصق", callback_data="send_sticker")],
            ]
            
            if user_id == owner_id or user_id == MASTER_OWNER_ID:
                keyboard.append([InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="admin_panel")])
            
            reply_markup = InlineKeyboardMarkup([keyboard[i:i+2] for i in range(0, len(keyboard), 2)])
            
            await update.message.reply_text(
                f"📩 **بوت التواصل مع المطور**\n\n"
                f"👨‍💻 **المطور:** {developer_username}\n"
                f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                f"📌 **اختر ما تريد إرساله:**",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        
        async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            query = update.callback_query
            await query.answer()
            
            user_id = query.from_user.id
            data_callback = query.data
            
            cursor = db.conn.cursor()
            cursor.execute("SELECT 1 FROM global_banned WHERE user_id = ?", (user_id,))
            if cursor.fetchone() and user_id != owner_id and user_id != MASTER_OWNER_ID:
                await query.edit_message_text("🚫 **أنت محظور.**", parse_mode="Markdown")
                return
            
            if data_callback == "send_message":
                context.user_data['waiting_for'] = 'message_to_dev'
                await query.edit_message_text(
                    f"📝 **أرسل رسالتك الآن**\nللمطور {developer_username}\n⚠️ المحتوى المخالف = حظر فوري",
                    parse_mode="Markdown"
                )
            elif data_callback == "send_photo":
                context.user_data['waiting_for'] = 'photo_to_dev'
                await query.edit_message_text(f"🖼️ **أرسل الصورة الآن**\nللمطور {developer_username}", parse_mode="Markdown")
            elif data_callback == "send_video":
                context.user_data['waiting_for'] = 'video_to_dev'
                await query.edit_message_text(f"🎥 **أرسل الفيديو الآن**\nللمطور {developer_username}", parse_mode="Markdown")
            elif data_callback == "send_audio":
                context.user_data['waiting_for'] = 'audio_to_dev'
                await query.edit_message_text(f"🎵 **أرسل الصوت الآن**\nللمطور {developer_username}", parse_mode="Markdown")
            elif data_callback == "send_document":
                context.user_data['waiting_for'] = 'document_to_dev'
                await query.edit_message_text(f"📎 **أرسل الملف الآن**\nللمطور {developer_username}", parse_mode="Markdown")
            elif data_callback == "send_sticker":
                context.user_data['waiting_for'] = 'sticker_to_dev'
                await query.edit_message_text(f"🏷️ **أرسل الملصق الآن**\nللمطور {developer_username}", parse_mode="Markdown")
            elif data_callback == "admin_panel" and (user_id == owner_id or user_id == MASTER_OWNER_ID):
                keyboard = [
                    [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
                    [InlineKeyboardButton("🚫 حظر مستخدم", callback_data="admin_ban")],
                    [InlineKeyboardButton("✅ الغاء حظر", callback_data="admin_unban")],
                    [InlineKeyboardButton("📋 المحظورين", callback_data="admin_banned_list")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    f"⚙️ **لوحة التحكم**\n\n"
                    f"👨‍💻 المطور: {developer_username}\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            elif data_callback == "admin_stats" and (user_id == owner_id or user_id == MASTER_OWNER_ID):
                keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    f"📊 **الإحصائيات**\n\n"
                    f"👤 البوت: {bot_name}\n"
                    f"📅 تم الإنشاء: {bot_data['created_at']}\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"📌 الحالة: 🟢 مفعل",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            elif data_callback == "back_to_start":
                keyboard = [
                    [InlineKeyboardButton("📩 رسالة", callback_data="send_message")],
                    [InlineKeyboardButton("🖼️ صورة", callback_data="send_photo")],
                    [InlineKeyboardButton("🎥 فيديو", callback_data="send_video")],
                    [InlineKeyboardButton("🎵 صوت", callback_data="send_audio")],
                    [InlineKeyboardButton("📎 ملف", callback_data="send_document")],
                    [InlineKeyboardButton("🏷️ ملصق", callback_data="send_sticker")],
                ]
                if user_id == owner_id or user_id == MASTER_OWNER_ID:
                    keyboard.append([InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="admin_panel")])
                reply_markup = InlineKeyboardMarkup([keyboard[i:i+2] for i in range(0, len(keyboard), 2)])
                await query.edit_message_text(
                    f"📩 **بوت التواصل مع المطور**\n\n"
                    f"👨‍💻 **المطور:** {developer_username}\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    f"📌 **اختر ما تريد إرساله:**",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
        
        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.message.from_user
            user_id = user.id
            user_name = user.first_name
            username = user.username
            user_message = update.message.text
            
            cursor = db.conn.cursor()
            cursor.execute("SELECT 1 FROM global_banned WHERE user_id = ?", (user_id,))
            if cursor.fetchone() and user_id != owner_id and user_id != MASTER_OWNER_ID:
                await update.message.reply_text("🚫 **أنت محظور.**", parse_mode="Markdown")
                return
            
            if context.user_data.get('waiting_for') == 'message_to_dev':
                try:
                    await context.bot.send_message(
                        chat_id=owner_id,
                        text=f"📩 **رسالة جديدة**\n\n"
                             f"👤 {user_name}\n"
                             f"🆔 @{username if username else 'لا يوجد'}\n"
                             f"🔢 `{user_id}`\n\n"
                             f"📝 {user_message}\n\n"
                             f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    await update.message.reply_text("✅ **تم الإرسال!**\n\n📨 سيتم الرد عليك قريباً.", parse_mode="Markdown")
                    context.user_data['waiting_for'] = None
                except Exception as e:
                    await update.message.reply_text("❌ حدث خطأ.", parse_mode="Markdown")
                    logger.error(f"Error: {e}")
                return
            await update.message.reply_text("📩 استخدم /start للتواصل.", parse_mode="Markdown")
        
        async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.message.from_user
            user_id = user.id
            user_name = user.first_name
            username = user.username
            
            cursor = db.conn.cursor()
            cursor.execute("SELECT 1 FROM global_banned WHERE user_id = ?", (user_id,))
            if cursor.fetchone() and user_id != owner_id and user_id != MASTER_OWNER_ID:
                await update.message.reply_text("🚫 **أنت محظور.**", parse_mode="Markdown")
                return
            
            if context.user_data.get('waiting_for') == 'photo_to_dev':
                try:
                    photo = update.message.photo[-1]
                    caption = update.message.caption or "بدون تعليق"
                    await context.bot.send_photo(
                        chat_id=owner_id,
                        photo=photo.file_id,
                        caption=f"🖼️ **صورة جديدة**\n\n"
                                f"👤 {user_name}\n"
                                f"🆔 @{username if username else 'لا يوجد'}\n"
                                f"🔢 `{user_id}`\n"
                                f"📝 {caption}\n"
                                f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    await update.message.reply_text("✅ **تم الإرسال!**", parse_mode="Markdown")
                    context.user_data['waiting_for'] = None
                except Exception as e:
                    await update.message.reply_text("❌ حدث خطأ.", parse_mode="Markdown")
                    logger.error(f"Error: {e}")
                return
            await update.message.reply_text("📸 استخدم /start للإرسال.", parse_mode="Markdown")
        
        async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.message.from_user
            user_id = user.id
            user_name = user.first_name
            username = user.username
            
            cursor = db.conn.cursor()
            cursor.execute("SELECT 1 FROM global_banned WHERE user_id = ?", (user_id,))
            if cursor.fetchone() and user_id != owner_id and user_id != MASTER_OWNER_ID:
                await update.message.reply_text("🚫 **أنت محظور.**", parse_mode="Markdown")
                return
            
            if context.user_data.get('waiting_for') == 'video_to_dev':
                try:
                    video = update.message.video
                    caption = update.message.caption or "بدون تعليق"
                    await context.bot.send_video(
                        chat_id=owner_id,
                        video=video.file_id,
                        caption=f"🎥 **فيديو جديد**\n\n"
                                f"👤 {user_name}\n"
                                f"🆔 @{username if username else 'لا يوجد'}\n"
                                f"🔢 `{user_id}`\n"
                                f"📝 {caption}\n"
                                f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    await update.message.reply_text("✅ **تم الإرسال!**", parse_mode="Markdown")
                    context.user_data['waiting_for'] = None
                except Exception as e:
                    await update.message.reply_text("❌ حدث خطأ.", parse_mode="Markdown")
                    logger.error(f"Error: {e}")
                return
            await update.message.reply_text("🎥 استخدم /start للإرسال.", parse_mode="Markdown")
        
        async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.message.from_user
            user_id = user.id
            user_name = user.first_name
            username = user.username
            
            cursor = db.conn.cursor()
            cursor.execute("SELECT 1 FROM global_banned WHERE user_id = ?", (user_id,))
            if cursor.fetchone() and user_id != owner_id and user_id != MASTER_OWNER_ID:
                await update.message.reply_text("🚫 **أنت محظور.**", parse_mode="Markdown")
                return
            
            if context.user_data.get('waiting_for') == 'audio_to_dev':
                try:
                    audio = update.message.audio
                    caption = update.message.caption or "بدون تعليق"
                    await context.bot.send_audio(
                        chat_id=owner_id,
                        audio=audio.file_id,
                        caption=f"🎵 **ملف صوتي جديد**\n\n"
                                f"👤 {user_name}\n"
                                f"🆔 @{username if username else 'لا يوجد'}\n"
                                f"🔢 `{user_id}`\n"
                                f"📝 {caption}\n"
                                f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    await update.message.reply_text("✅ **تم الإرسال!**", parse_mode="Markdown")
                    context.user_data['waiting_for'] = None
                except Exception as e:
                    await update.message.reply_text("❌ حدث خطأ.", parse_mode="Markdown")
                    logger.error(f"Error: {e}")
                return
            await update.message.reply_text("🎵 استخدم /start للإرسال.", parse_mode="Markdown")
        
        async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.message.from_user
            user_id = user.id
            user_name = user.first_name
            username = user.username
            
            cursor = db.conn.cursor()
            cursor.execute("SELECT 1 FROM global_banned WHERE user_id = ?", (user_id,))
            if cursor.fetchone() and user_id != owner_id and user_id != MASTER_OWNER_ID:
                await update.message.reply_text("🚫 **أنت محظور.**", parse_mode="Markdown")
                return
            
            if context.user_data.get('waiting_for') == 'document_to_dev':
                try:
                    document = update.message.document
                    caption = update.message.caption or "بدون تعليق"
                    await context.bot.send_document(
                        chat_id=owner_id,
                        document=document.file_id,
                        caption=f"📎 **ملف جديد**\n\n"
                                f"👤 {user_name}\n"
                                f"🆔 @{username if username else 'لا يوجد'}\n"
                                f"🔢 `{user_id}`\n"
                                f"📝 {caption}\n"
                                f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    await update.message.reply_text("✅ **تم الإرسال!**", parse_mode="Markdown")
                    context.user_data['waiting_for'] = None
                except Exception as e:
                    await update.message.reply_text("❌ حدث خطأ.", parse_mode="Markdown")
                    logger.error(f"Error: {e}")
                return
            await update.message.reply_text("📎 استخدم /start للإرسال.", parse_mode="Markdown")
        
        async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.message.from_user
            user_id = user.id
            user_name = user.first_name
            username = user.username
            
            cursor = db.conn.cursor()
            cursor.execute("SELECT 1 FROM global_banned WHERE user_id = ?", (user_id,))
            if cursor.fetchone() and user_id != owner_id and user_id != MASTER_OWNER_ID:
                await update.message.reply_text("🚫 **أنت محظور.**", parse_mode="Markdown")
                return
            
            if context.user_data.get('waiting_for') == 'sticker_to_dev':
                try:
                    sticker = update.message.sticker
                    await context.bot.send_sticker(chat_id=owner_id, sticker=sticker.file_id)
                    await context.bot.send_message(
                        chat_id=owner_id,
                        text=f"🏷️ **ملصق جديد**\n\n"
                             f"👤 {user_name}\n"
                             f"🆔 @{username if username else 'لا يوجد'}\n"
                             f"🔢 `{user_id}`\n"
                             f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    await update.message.reply_text("✅ **تم الإرسال!**", parse_mode="Markdown")
                    context.user_data['waiting_for'] = None
                except Exception as e:
                    await update.message.reply_text("❌ حدث خطأ.", parse_mode="Markdown")
                    logger.error(f"Error: {e}")
                return
            await update.message.reply_text("🏷️ استخدم /start للإرسال.", parse_mode="Markdown")
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(button_handler))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        app.add_handler(MessageHandler(filters.VIDEO, handle_video))
        app.add_handler(MessageHandler(filters.AUDIO, handle_audio))
        app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))

bot_manager = BotManager(db)

# ========== البوت الرئيسي (المصنع) ==========
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
        logger.info("✅ Master bot started successfully!")
        return self.app
    
    async def _setup_handlers(self):
        async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.message.from_user
            user_id = user.id
            
            db.add_master_developer(user_id, user.username)
            
            keyboard = []
            
            if db.is_master_developer(user_id):
                keyboard.extend([
                    [InlineKeyboardButton("🤖 صنع بوت جديد", callback_data="create_bot")],
                    [InlineKeyboardButton("📋 بوتاتي", callback_data="my_bots")],
                    [InlineKeyboardButton("⚙️ إدارة البوتات", callback_data="manage_bots")],
                    [InlineKeyboardButton("🚫 حظر شامل", callback_data="global_ban")],
                    [InlineKeyboardButton("✅ الغاء حظر شامل", callback_data="global_unban")],
                    [InlineKeyboardButton("📊 إحصائيات المصنع", callback_data="factory_stats")],
                ])
            
            keyboard.append([InlineKeyboardButton("ℹ️ عن المصنع", callback_data="about")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "🏭 **مصنع بوتات التواصل v2.0**\n\n"
                "📌 **أنشئ بوت التواصل الخاص بك**\n"
                "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                "🔹 صنع بوت احترافي خلال ثواني\n"
                "🔹 إدارة متقدمة وتحكم كامل\n"
                "🔹 نظام حماية وأمان متكامل\n"
                "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                f"👤 {user.first_name}",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        
        async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            query = update.callback_query
            await query.answer()
            
            user_id = query.from_user.id
            data_callback = query.data
            
            if data_callback == "about":
                await query.edit_message_text(
                    "🏭 **مصنع بوتات التواصل v2.0**\n\n"
                    "📌 **مميزات المصنع:**\n"
                    "• صنع بوتات تواصل متعددة\n"
                    "• نظام إدارة متقدم\n"
                    "• حماية ضد الهجمات\n"
                    "• تحديثات مستمرة\n"
                    "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    "👨‍💻 **للمطور الرئيسي:** @SSSTlF\n"
                    "🆔 **ID:** 1170411845",
                    parse_mode="Markdown"
                )
                return
            
            if not db.is_master_developer(user_id):
                await query.edit_message_text("🚫 **غير مصرح لك.**", parse_mode="Markdown")
                return
            
            if data_callback == "create_bot":
                context.user_data['waiting_for'] = 'bot_token'
                await query.edit_message_text(
                    "🤖 **صنع بوت جديد**\n\n"
                    "📌 **الخطوة 1:** أرسل توكن البوت\n"
                    "مثال: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`\n\n"
                    "⚠️ **ملاحظات:**\n"
                    "• توكن من @BotFather\n"
                    "• سيكون البوت جاهزاً خلال ثواني\n"
                    "• لإلغاء: /cancel",
                    parse_mode="Markdown"
                )
            
            elif data_callback == "my_bots":
                bots = db.get_bots_by_owner(user_id)
                if not bots:
                    await query.edit_message_text(
                        "📭 **لا توجد بوتات**\n\n"
                        "🔄 استخدم /start ثم اختر 'صنع بوت جديد'",
                        parse_mode="Markdown"
                    )
                    return
                
                text = "📋 **بوتاتي**\n\n"
                for bot in bots:
                    text += f"🤖 **{bot['bot_name']}**\n"
                    text += f"🆔 @{bot['bot_username']}\n"
                    text += f"📌 الحالة: {'🟢 مفعل' if bot['is_active'] else '🔴 معطل'}\n"
                    text += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                
                keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
            
            elif data_callback == "manage_bots":
                bots = db.get_bots_by_owner(user_id)
                if not bots:
                    await query.edit_message_text("📭 لا توجد بوتات لإدارتها.", parse_mode="Markdown")
                    return
                
                keyboard = []
                for bot in bots:
                    status = "🔴 معطل" if not bot['is_active'] else "🟢 مفعل"
                    btn_text = f"{bot['bot_name']} - {status}"
                    callback = f"manage_bot_{bot['bot_token']}"
                    keyboard.append([InlineKeyboardButton(btn_text, callback_data=callback)])
                
                keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")])
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    "⚙️ **إدارة البوتات**\n\n"
                    "📌 اختر بوتاً لإدارته:",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            
            elif data_callback.startswith("manage_bot_"):
                bot_token = data_callback.replace("manage_bot_", "")
                bot_data = db.get_bot(bot_token)
                if not bot_data:
                    await query.edit_message_text("❌ البوت غير موجود.", parse_mode="Markdown")
                    return
                
                keyboard = [
                    [InlineKeyboardButton("▶️ تشغيل", callback_data=f"start_bot_{bot_token}")],
                    [InlineKeyboardButton("⏸️ إيقاف", callback_data=f"stop_bot_{bot_token}")],
                    [InlineKeyboardButton("🗑️ حذف", callback_data=f"delete_bot_{bot_token}")],
                    [InlineKeyboardButton("🔄 إعادة تشغيل", callback_data=f"restart_bot_{bot_token}")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="manage_bots")],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                status = "🟢 مفعل" if bot_data['is_active'] else "🔴 معطل"
                is_running = "🟢 يعمل" if bot_token in bot_manager.active_bots else "🔴 متوقف"
                
                await query.edit_message_text(
                    f"⚙️ **إدارة البوت**\n\n"
                    f"🤖 الاسم: {bot_data['bot_name']}\n"
                    f"🆔 @{bot_data['bot_username']}\n"
                    f"📌 الحالة: {status}\n"
                    f"🔄 التشغيل: {is_running}\n"
                    f"📅 تم الإنشاء: {bot_data['created_at']}\n"
                    f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            
            elif data_callback.startswith("start_bot_"):
                bot_token = data_callback.replace("start_bot_", "")
                db.update_bot_active(bot_token, True)
                success, message = bot_manager.start_bot_process(bot_token)
                await query.edit_message_text(f"{'✅' if success else '❌'} {message}", parse_mode="Markdown")
            
            elif data_callback.startswith("stop_bot_"):
                bot_token = data_callback.replace("stop_bot_", "")
                success, message = bot_manager.stop_bot(bot_token)
                await query.edit_message_text(f"{'✅' if success else '❌'} {message}", parse_mode="Markdown")
            
            elif data_callback.startswith("restart_bot_"):
                bot_token = data_callback.replace("restart_bot_", "")
                bot_manager.stop_bot(bot_token)
                db.update_bot_active(bot_token, True)
                success, message = bot_manager.start_bot_process(bot_token)
                await query.edit_message_text(f"{'✅' if success else '❌'} إعادة التشغيل: {message}", parse_mode="Markdown")
            
            elif data_callback.startswith("delete_bot_"):
                bot_token = data_callback.replace("delete_bot_", "")
                bot_manager.stop_bot(bot_token)
                db.delete_bot(bot_token)
                await query.edit_message_text("🗑️ **تم حذف البوت.**", parse_mode="Markdown")
            
            elif data_callback == "global_ban":
                context.user_data['waiting_for'] = 'global_ban'
                await query.edit_message_text(
                    "🚫 **حظر شامل**\n\n"
                    "📌 أرسل الآيدي الذي تريد حظره:\n"
                    "مثال: `123456789`\n\n"
                    "⚠️ سيتم حظر هذا المستخدم من جميع البوتات\n"
                    "🔄 /cancel للإلغاء",
                    parse_mode="Markdown"
                )
            
            elif data_callback == "global_unban":
                context.user_data['waiting_for'] = 'global_unban'
                await query.edit_message_text(
                    "✅ **الغاء الحظر الشامل**\n\n"
                    "📌 أرسل الآيدي الذي تريد الغاء حظره:\n"
                    "مثال: `123456789`\n\n"
                    "🔄 /cancel للإلغاء",
                    parse_mode="Markdown"
                )
            
            elif data_callback == "factory_stats":
                bots = db.get_all_bots()
                active_bots = len(bot_manager.active_bots)
                total_bots = len(bots)
                
                stats_text = f"📊 **إحصائيات المصنع**\n\n"
                stats_text += f"🤖 إجمالي البوتات: {total_bots}\n"
                stats_text += f"🟢 البوتات النشطة: {active_bots}\n"
                stats_text += f"🔴 البوتات المتوقفة: {total_bots - active_bots}\n"
                stats_text += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                
                if bots:
                    stats_text += "📋 **البوتات:**\n"
                    for bot in bots[-5:]:
                        status = "🟢" if bot['is_active'] else "🔴"
                        running = "🔄" if bot['bot_token'] in bot_manager.active_bots else "⏸️"
                        stats_text += f"{status} {bot['bot_name']} {running}\n"
                
                keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(stats_text, reply_markup=reply_markup, parse_mode="Markdown")
            
            elif data_callback == "back_to_main":
                keyboard = []
                if db.is_master_developer(user_id):
                    keyboard.extend([
                        [InlineKeyboardButton("🤖 صنع بوت جديد", callback_data="create_bot")],
                        [InlineKeyboardButton("📋 بوتاتي", callback_data="my_bots")],
                        [InlineKeyboardButton("⚙️ إدارة البوتات", callback_data="manage_bots")],
                        [InlineKeyboardButton("🚫 حظر شامل", callback_data="global_ban")],
                        [InlineKeyboardButton("✅ الغاء حظر شامل", callback_data="global_unban")],
                        [InlineKeyboardButton("📊 إحصائيات المصنع", callback_data="factory_stats")],
                    ])
                keyboard.append([InlineKeyboardButton("ℹ️ عن المصنع", callback_data="about")])
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    "🏭 **مصنع بوتات التواصل**\n\n"
                    "📌 **مرحباً بك في المصنع**\n"
                    "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    "🔹 اختر ما تريد فعله:",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
        
        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.message.from_user
            user_id = user.id
            user_message = update.message.text
            
            if user_message and user_message.lower() == "/cancel":
                context.user_data.clear()
                await update.message.reply_text("❌ **تم الإلغاء.**", parse_mode="Markdown")
                return
            
            if not db.is_master_developer(user_id):
                await update.message.reply_text("🚫 **غير مصرح لك.**", parse_mode="Markdown")
                return
            
            if context.user_data.get('waiting_for') == 'global_ban':
                try:
                    target_id = int(user_message.strip())
                    cursor = db.conn.cursor()
                    cursor.execute(
                        "INSERT OR REPLACE INTO global_banned (user_id, reason) VALUES (?, ?)",
                        (target_id, f"حظر بواسطة {user.username or user_id}")
                    )
                    db.conn.commit()
                    await update.message.reply_text(
                        f"✅ **تم حظر المستخدم** `{target_id}`\n"
                        f"📌 لن يتمكن من استخدام أي بوت في النظام",
                        parse_mode="Markdown"
                    )
                except ValueError:
                    await update.message.reply_text("❌ **أرسل أرقام فقط.**", parse_mode="Markdown")
                context.user_data.clear()
                return
            
            if context.user_data.get('waiting_for') == 'global_unban':
                try:
                    target_id = int(user_message.strip())
                    cursor = db.conn.cursor()
                    cursor.execute("DELETE FROM global_banned WHERE user_id = ?", (target_id,))
                    db.conn.commit()
                    await update.message.reply_text(
                        f"✅ **تم الغاء حظر المستخدم** `{target_id}`",
                        parse_mode="Markdown"
                    )
                except ValueError:
                    await update.message.reply_text("❌ **أرسل أرقام فقط.**", parse_mode="Markdown")
                context.user_data.clear()
                return
            
            if context.user_data.get('waiting_for') == 'bot_token':
                bot_token = user_message.strip()
                
                if not ":" in bot_token or len(bot_token) < 20:
                    await update.message.reply_text(
                        "❌ **توكن غير صحيح**\n\n"
                        "📌 يجب أن يكون على شكل:\n"
                        "`1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`\n\n"
                        "🔄 أرسل توكن صحيح أو /cancel للإلغاء",
                        parse_mode="Markdown"
                    )
                    return
                
                if db.get_bot(bot_token):
                    await update.message.reply_text(
                        "❌ **هذا البوت مستخدم بالفعل**\n\n"
                        "🔄 أرسل توكن آخر أو /cancel للإلغاء",
                        parse_mode="Markdown"
                    )
                    return
                
                context.user_data['bot_token'] = bot_token
                context.user_data['waiting_for'] = 'bot_name'
                
                await update.message.reply_text(
                    "✅ **تم التحقق من التوكن**\n\n"
                    "📌 **الخطوة 2:** أرسل اسم البوت (الاسم الذي سيظهر للمستخدمين)\n"
                    "مثال: `بوت التواصل الرسمي`\n\n"
                    "🔄 /cancel للإلغاء",
                    parse_mode="Markdown"
                )
                return
            
            elif context.user_data.get('waiting_for') == 'bot_name':
                bot_name = user_message.strip()
                context.user_data['bot_name'] = bot_name
                context.user_data['waiting_for'] = 'bot_username'
                
                await update.message.reply_text(
                    "✅ **تم حفظ الاسم**\n\n"
                    "📌 **الخطوة 3:** أرسل يوزر البوت (بدون @)\n"
                    "مثال: `MySupportBot`\n\n"
                    "🔄 /cancel للإلغاء",
                    parse_mode="Markdown"
                )
                return
            
            elif context.user_data.get('waiting_for') == 'bot_username':
                bot_username = user_message.strip().replace("@", "")
                bot_token = context.user_data.get('bot_token')
                bot_name = context.user_data.get('bot_name')
                
                if not bot_token or not bot_name:
                    await update.message.reply_text("❌ **حدث خطأ في البيانات**\n\nيرجى البدء من جديد.", parse_mode="Markdown")
                    context.user_data.clear()
                    return
                
                bot_id = db.add_bot(
                    bot_token=bot_token,
                    bot_name=bot_name,
                    bot_username=bot_username,
                    owner_id=user_id,
                    owner_username=user.username,
                    developer_username=f"@{user.username or 'unknown'}",
                    config={"created_by": "bot_factory", "version": "2.0"}
                )
                
                if bot_id:
                    success, message = bot_manager.start_bot_process(bot_token)
                    
                    await update.message.reply_text(
                        f"🤖 **تم صنع البوت بنجاح!**\n\n"
                        f"📌 الاسم: {bot_name}\n"
                        f"🆔 @{bot_username}\n"
                        f"🔑 التوكن: `{bot_token[:10]}...`\n"
                        f"📌 الحالة: {'🟢 مفعل' if success else '🔴 معطل'}\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"💡 **لإدارة البوت:** استخدم /start ثم اختر 'إدارة البوتات'\n\n"
                        f"{'✅ البوت يعمل الآن' if success else f'❌ {message}'}",
                        parse_mode="Markdown"
                    )
                else:
                    await update.message.reply_text(
                        "❌ **حدث خطأ أثناء صنع البوت**\n\n"
                        "🔄 حاول مرة أخرى أو تواصل مع المطور الرئيسي",
                        parse_mode="Markdown"
                    )
                
                context.user_data.clear()
                return
            
            await update.message.reply_text("📩 استخدم /start للبدء.", parse_mode="Markdown")
        
        self.app.add_handler(CommandHandler("start", start))
        self.app.add_handler(CommandHandler("cancel", lambda u, c: u.message.reply_text("❌ تم الإلغاء", parse_mode="Markdown")))
        self.app.add_handler(CallbackQueryHandler(button_handler))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# ========== التشغيل ==========
def main():
    print("🚀 Starting Bot Factory...")
    print(f"🤖 Master Bot Token: {MASTER_BOT_TOKEN[:10]}...")
    print(f"👨‍💻 Master Owner ID: {MASTER_OWNER_ID}")
    
    master = MasterBot(MASTER_BOT_TOKEN)
    
    async def run():
        await master.start()
        print("✅ Bot Factory is running! Send /start to @SSSTlF_bot")
        # Keep the bot running
        while True:
            await asyncio.sleep(3600)
    
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped.")

if __name__ == "__main__":
    main()
