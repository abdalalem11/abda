import os
import json
import logging
import asyncio
import threading
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from http.server import HTTPServer, BaseHTTPRequestHandler

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

# ========== نظام إدارة البوتات (مُصلَح) ==========
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
            
            # إنشاء حلقة أحداث جديدة لكل بوت
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # إنشاء التطبيق
            app = Application.builder().token(bot_token).build()
            self._setup_bot_handlers(app, bot_data)
            
            # تشغيل في thread منفصل مع الحلقة
            def run_bot():
                try:
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(app.initialize())
                    loop.run_until_complete(app.start())
                    loop.run_until_complete(app.updater.start_polling(drop_pending_updates=True))
                    loop.run_forever()
                except Exception as e:
                    logger.error(f"Bot {bot_token} error: {e}")
                finally:
                    try:
                        loop.run_until_complete(app.shutdown())
                    except:
                        pass
            
            thread = threading.Thread(target=run_bot, daemon=True)
            thread.start()
            
            self.bot_instances[bot_token] = app
            self.active_bots[bot_token] = {"app": app, "thread": thread, "loop": loop}
            
            logger.info(f"✅ Bot {bot_token} started successfully")
            return True, "تم تشغيل البوت بنجاح ✅"
            
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            return False, f"خطأ: {str(e)}"
    
    def stop_bot(self, bot_token):
        try:
            if bot_token in self.active_bots:
                app = self.bot_instances.get(bot_token)
                loop = self.active_bots[bot_token].get("loop")
                
                if app and loop:
                    try:
                        asyncio.run_coroutine_threadsafe(app.stop(), loop)
                        asyncio.run_coroutine_threadsafe(app.shutdown(), loop)
                    except:
                        pass
                
                del self.active_bots[bot_token]
                if bot_token in self.bot_instances:
                    del self.bot_instances[bot_token]
                
                self.db.update_bot_active(bot_token, False)
                logger.info(f"⏸️ Bot {bot_token} stopped")
                return True, "تم إيقاف البوت ⏸️"
            
            return False, "البوت غير قيد التشغيل"
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")
            return False, str(e)
    
    def _setup_bot_handlers(self, app, bot_data):
        owner_id = bot_data['owner_id']
        developer_username = bot_data['developer_username']
        
        async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.message.from_user
            user_id = user.id
            
            cursor = db.conn.cursor()
            cursor.execute("SELECT 1 FROM global_banned WHERE user_id = ?", (user_id,))
            if cursor.fetchone() and user_id != owner_id and user_id != MASTER_OWNER_ID:
                await update.message.reply_text("🚫 **أنت محظور**", parse_mode="Markdown")
                return
            
            keyboard = [
                [InlineKeyboardButton("📩 رسالة", callback_data="send_message")],
                [InlineKeyboardButton("🖼️ صورة", callback_data="send_photo")],
                [InlineKeyboardButton("🎥 فيديو", callback_data="send_video")],
                [InlineKeyboardButton("🎵 صوت", callback_data="send_audio")],
                [InlineKeyboardButton("📎 ملف", callback_data="send_document")],
            ]
            
            if user_id == owner_id or user_id == MASTER_OWNER_ID:
                keyboard.append([InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="admin_panel")])
            
            reply_markup = InlineKeyboardMarkup([keyboard[i:i+2] for i in range(0, len(keyboard), 2)])
            
            await update.message.reply_text(
                f"📩 **بوت التواصل**\n\n👨‍💻 المطور: {developer_username}",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        
        async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            query = update.callback_query
            await query.answer()
            user_id = query.from_user.id
            data = query.data
            
            if data == "send_message":
                context.user_data['waiting_for'] = 'message'
                await query.edit_message_text("📝 أرسل رسالتك:", parse_mode="Markdown")
            elif data == "send_photo":
                context.user_data['waiting_for'] = 'photo'
                await query.edit_message_text("🖼️ أرسل الصورة:", parse_mode="Markdown")
            elif data == "send_video":
                context.user_data['waiting_for'] = 'video'
                await query.edit_message_text("🎥 أرسل الفيديو:", parse_mode="Markdown")
            elif data == "send_audio":
                context.user_data['waiting_for'] = 'audio'
                await query.edit_message_text("🎵 أرسل الصوت:", parse_mode="Markdown")
            elif data == "send_document":
                context.user_data['waiting_for'] = 'document'
                await query.edit_message_text("📎 أرسل الملف:", parse_mode="Markdown")
            elif data == "admin_panel" and (user_id == owner_id or user_id == MASTER_OWNER_ID):
                keyboard = [
                    [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    f"⚙️ **لوحة التحكم**\n\n👨‍💻 {developer_username}",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            elif data == "back_to_start":
                keyboard = [
                    [InlineKeyboardButton("📩 رسالة", callback_data="send_message")],
                    [InlineKeyboardButton("🖼️ صورة", callback_data="send_photo")],
                    [InlineKeyboardButton("🎥 فيديو", callback_data="send_video")],
                    [InlineKeyboardButton("🎵 صوت", callback_data="send_audio")],
                    [InlineKeyboardButton("📎 ملف", callback_data="send_document")],
                ]
                if user_id == owner_id or user_id == MASTER_OWNER_ID:
                    keyboard.append([InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="admin_panel")])
                reply_markup = InlineKeyboardMarkup([keyboard[i:i+2] for i in range(0, len(keyboard), 2)])
                await query.edit_message_text(
                    f"📩 **بوت التواصل**\n\n👨‍💻 المطور: {developer_username}",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            elif data == "admin_stats" and (user_id == owner_id or user_id == MASTER_OWNER_ID):
                keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    f"📊 **إحصائيات البوت**\n\n"
                    f"👥 المستخدمين: قيد التطوير",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
        
        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.message.from_user
            user_id = user.id
            
            if context.user_data.get('waiting_for') == 'message':
                await context.bot.send_message(
                    chat_id=owner_id,
                    text=f"📩 من: {user.first_name}\n🆔 {user_id}\n\n{update.message.text}"
                )
                await update.message.reply_text("✅ تم الإرسال")
                context.user_data['waiting_for'] = None
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(button_handler))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

bot_manager = BotManager(db)

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
        await self.app.updater.start_polling()
        logger.info("✅ Master bot started!")
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
                    [InlineKeyboardButton("📊 إحصائيات المصنع", callback_data="factory_stats")],
                ])
            
            keyboard.append([InlineKeyboardButton("ℹ️ عن المصنع", callback_data="about")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "🏭 **مصنع بوتات التواصل**\n\n"
                "📌 أنشئ بوت التواصل الخاص بك خلال ثواني\n"
                "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                f"👤 {user.first_name}",
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
                    "🆔 ID: 1170411845",
                    parse_mode="Markdown"
                )
                return
            
            if not db.is_master_developer(user_id):
                await query.edit_message_text("🚫 غير مصرح لك.", parse_mode="Markdown")
                return
            
            if data == "create_bot":
                context.user_data['waiting_for'] = 'bot_token'
                await query.edit_message_text(
                    "🤖 **صنع بوت جديد**\n\n"
                    "📌 **الخطوة 1:** أرسل توكن البوت\n"
                    "مثال: `1234567890:ABCdef...`\n\n"
                    "⚠️ من @BotFather\n"
                    "🔄 /cancel للإلغاء",
                    parse_mode="Markdown"
                )
            
            elif data == "my_bots":
                bots = db.get_bots_by_owner(user_id)
                if not bots:
                    await query.edit_message_text("📭 **لا توجد بوتات**", parse_mode="Markdown")
                    return
                
                text = "📋 **بوتاتي**\n\n"
                for bot in bots:
                    status = "🟢 مفعل" if bot['is_active'] else "🔴 معطل"
                    running = "🔄 يعمل" if bot['bot_token'] in bot_manager.active_bots else "⏸️ متوقف"
                    text += f"🤖 **{bot['bot_name']}**\n"
                    text += f"🆔 @{bot['bot_username']}\n"
                    text += f"📌 {status} | {running}\n"
                    text += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                
                keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
            
            elif data == "manage_bots":
                bots = db.get_bots_by_owner(user_id)
                if not bots:
                    await query.edit_message_text("📭 لا توجد بوتات.", parse_mode="Markdown")
                    return
                
                keyboard = []
                for bot in bots:
                    status = "🟢" if bot['is_active'] else "🔴"
                    btn_text = f"{status} {bot['bot_name']}"
                    keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"manage_{bot['bot_token']}")])
                
                keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")])
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    "⚙️ **إدارة البوتات**\n\nاختر بوتاً:",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            
            elif data.startswith("manage_"):
                bot_token = data.replace("manage_", "")
                bot_data = db.get_bot(bot_token)
                if not bot_data:
                    await query.edit_message_text("❌ البوت غير موجود.", parse_mode="Markdown")
                    return
                
                is_running = bot_token in bot_manager.active_bots
                
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
                    f"🔄 {running}",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            
            elif data.startswith("start_"):
                bot_token = data.replace("start_", "")
                db.update_bot_active(bot_token, True)
                success, msg = bot_manager.start_bot_process(bot_token)
                await query.edit_message_text(f"{'✅' if success else '❌'} {msg}", parse_mode="Markdown")
            
            elif data.startswith("stop_"):
                bot_token = data.replace("stop_", "")
                success, msg = bot_manager.stop_bot(bot_token)
                await query.edit_message_text(f"{'✅' if success else '❌'} {msg}", parse_mode="Markdown")
            
            elif data.startswith("restart_"):
                bot_token = data.replace("restart_", "")
                bot_manager.stop_bot(bot_token)
                db.update_bot_active(bot_token, True)
                success, msg = bot_manager.start_bot_process(bot_token)
                await query.edit_message_text(f"{'✅' if success else '❌'} إعادة تشغيل: {msg}", parse_mode="Markdown")
            
            elif data.startswith("delete_"):
                bot_token = data.replace("delete_", "")
                bot_manager.stop_bot(bot_token)
                db.delete_bot(bot_token)
                await query.edit_message_text("🗑️ **تم حذف البوت**", parse_mode="Markdown")
            
            elif data == "factory_stats":
                bots = db.get_all_bots()
                total = len(bots)
                active = len(bot_manager.active_bots)
                
                text = f"📊 **إحصائيات المصنع**\n\n"
                text += f"🤖 إجمالي البوتات: {total}\n"
                text += f"🟢 النشطة: {active}\n"
                text += f"🔴 المتوقفة: {total - active}\n"
                text += f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                
                if bots:
                    for bot in bots[-5:]:
                        running = "🔄" if bot['bot_token'] in bot_manager.active_bots else "⏸️"
                        text += f"{running} {bot['bot_name']}\n"
                
                keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
            
            elif data == "back_to_main":
                keyboard = []
                if db.is_master_developer(user_id):
                    keyboard.extend([
                        [InlineKeyboardButton("🤖 صنع بوت جديد", callback_data="create_bot")],
                        [InlineKeyboardButton("📋 بوتاتي", callback_data="my_bots")],
                        [InlineKeyboardButton("⚙️ إدارة البوتات", callback_data="manage_bots")],
                        [InlineKeyboardButton("📊 إحصائيات المصنع", callback_data="factory_stats")],
                    ])
                keyboard.append([InlineKeyboardButton("ℹ️ عن المصنع", callback_data="about")])
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    "🏭 **مصنع بوتات التواصل**\n\n📌 اختر ما تريد:",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
        
        async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.message.from_user
            user_id = user.id
            text = update.message.text
            
            if text and text.lower() == "/cancel":
                context.user_data.clear()
                await update.message.reply_text("❌ تم الإلغاء", parse_mode="Markdown")
                return
            
            if not db.is_master_developer(user_id):
                await update.message.reply_text("🚫 غير مصرح لك.", parse_mode="Markdown")
                return
            
            # صنع بوت جديد
            if context.user_data.get('waiting_for') == 'bot_token':
                bot_token = text.strip()
                
                if ":" not in bot_token or len(bot_token) < 20:
                    await update.message.reply_text(
                        "❌ **توكن غير صحيح**\n\n"
                        "📌 يجب أن يكون:\n"
                        "`1234567890:ABCdef...`",
                        parse_mode="Markdown"
                    )
                    return
                
                if db.get_bot(bot_token):
                    await update.message.reply_text(
                        "❌ **هذا البوت مستخدم**\n\nأرسل توكن آخر:",
                        parse_mode="Markdown"
                    )
                    return
                
                context.user_data['bot_token'] = bot_token
                context.user_data['waiting_for'] = 'bot_name'
                await update.message.reply_text(
                    "✅ **تم التحقق**\n\n"
                    "📌 **الخطوة 2:** أرسل اسم البوت:\n"
                    "مثال: `بوت التواصل`",
                    parse_mode="Markdown"
                )
                return
            
            elif context.user_data.get('waiting_for') == 'bot_name':
                bot_name = text.strip()
                context.user_data['bot_name'] = bot_name
                context.user_data['waiting_for'] = 'bot_username'
                await update.message.reply_text(
                    "✅ **تم حفظ الاسم**\n\n"
                    "📌 **الخطوة 3:** أرسل يوزر البوت (بدون @):\n"
                    "مثال: `MySupportBot`",
                    parse_mode="Markdown"
                )
                return
            
            elif context.user_data.get('waiting_for') == 'bot_username':
                bot_username = text.strip().replace("@", "")
                bot_token = context.user_data.get('bot_token')
                bot_name = context.user_data.get('bot_name')
                
                if not bot_token or not bot_name:
                    await update.message.reply_text("❌ خطأ في البيانات", parse_mode="Markdown")
                    context.user_data.clear()
                    return
                
                # حفظ في قاعدة البيانات
                bot_id = db.add_bot(
                    bot_token=bot_token,
                    bot_name=bot_name,
                    bot_username=bot_username,
                    owner_id=user_id,
                    owner_username=user.username,
                    developer_username=f"@{user.username or 'unknown'}"
                )
                
                if bot_id:
                    # تشغيل البوت مباشرة
                    success, msg = bot_manager.start_bot_process(bot_token)
                    
                    await update.message.reply_text(
                        f"🤖 **تم صنع البوت بنجاح!**\n\n"
                        f"📌 الاسم: {bot_name}\n"
                        f"🆔 @{bot_username}\n"
                        f"🔑 التوكن: `{bot_token[:10]}...`\n"
                        f"📌 الحالة: {'🟢 مفعل' if success else '🔴 معطل'}\n"
                        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                        f"{'✅ البوت يعمل الآن' if success else f'❌ {msg}'}\n\n"
                        f"💡 افتح البوت: @{bot_username}",
                        parse_mode="Markdown"
                    )
                else:
                    await update.message.reply_text("❌ فشل في صنع البوت", parse_mode="Markdown")
                
                context.user_data.clear()
                return
        
        self.app.add_handler(CommandHandler("start", start))
        self.app.add_handler(CommandHandler("cancel", lambda u, c: u.message.reply_text("❌ تم الإلغاء", parse_mode="Markdown")))
        self.app.add_handler(CallbackQueryHandler(button_handler))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# ========== التشغيل ==========
def main():
    print("🚀 Starting Bot Factory...")
    print(f"🤖 Master Bot: {MASTER_BOT_TOKEN[:10]}...")
    print(f"👨‍💻 Owner ID: {MASTER_OWNER_ID}")
    
    master = MasterBot(MASTER_BOT_TOKEN)
    
    async def run():
        await master.start()
        print("✅ Bot Factory is running!")
        print("📱 Open: @SSSTlF_bot")
        while True:
            await asyncio.sleep(3600)
    
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n🛑 Stopped.")

if __name__ == "__main__":
    main()
