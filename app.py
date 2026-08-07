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

# ========== نظام إدارة البوتات ==========
class BotManager:
    def __init__(self, db):
        self.db = db
        self.active_bots = {}
        self.bot_instances = {}
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
    
    def create_bot_code(self, bot_token, bot_name, owner_id, developer_username):
        """إنشاء كود البوت الكامل مع جميع الأوامر"""
        return f'''from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import os
import logging
import json
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# ========== سيرفر HTTP ==========
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'Bot is running!')
    
    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

# ========== إعداد التسجيل ==========
logging.basicConfig(level=logging.INFO)

# ========== التوكن ==========
BOT_TOKEN = "{bot_token}"

# ========== إعدادات المطور ==========
DEVELOPER_USERNAME = "{developer_username}"
DEVELOPER_ID = {owner_id}

# ========== ملفات البيانات ==========
DATA_FILE = "bot_data.json"
REPLIES_FILE = "replies_data.json"

# ========== تحميل/حفظ البيانات ==========
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {{"users": [], "banned_users": [], "bot_active": True, "total_users": 0}}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_replies():
    if os.path.exists(REPLIES_FILE):
        with open(REPLIES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {{}}

def save_replies(replies):
    with open(REPLIES_FILE, 'w', encoding='utf-8') as f:
        json.dump(replies, f, ensure_ascii=False, indent=4)

# ========== دوال البوت ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        user_name = update.message.from_user.first_name
        username = update.message.from_user.username
        
        data = load_data()
        
        if str(user_id) in data["banned_users"]:
            await update.message.reply_text("🚫 **أنت محظور من استخدام هذا البوت.**\nللتواصل: {developer_username}", parse_mode="Markdown")
            return
        
        if str(user_id) not in data["users"]:
            data["users"].append(str(user_id))
            data["total_users"] = len(data["users"])
            save_data(data)
            
            try:
                await context.bot.send_message(
                    chat_id=DEVELOPER_ID,
                    text=f"🆕 **مستخدم جديد!**\\n\\n👤 {{user_name}}\\n🆔 @{{username if username else 'لا يوجد'}}\\n🔢 `{{user_id}}`\\n📊 الإجمالي: {{data['total_users']}}",
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
        
        if user_id == DEVELOPER_ID:
            keyboard.append([InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="admin_panel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"📩 **بوت التواصل مع المطور**\\n\\n"
            f"👨‍💻 **المطور:** {developer_username}\\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\\n"
            f"📌 **اختر ما تريد إرساله:**\\n"
            f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\\n",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Error in start: {{e}}")

async def panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != DEVELOPER_ID:
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
        f"⚙️ **لوحة التحكم**\\n\\n"
        f"👨‍💻 المطور: {developer_username}\\n"
        f"📊 المستخدمين: {{data['total_users']}}\\n"
        f"🚫 المحظورين: {{len(data['banned_users'])}}\\n"
        f"📌 الحالة: {{status}}",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        
        data = load_data()
        user_id = query.from_user.id
        
        if str(user_id) in data["banned_users"] and user_id != DEVELOPER_ID:
            await query.edit_message_text("🚫 **أنت محظور.**", parse_mode="Markdown")
            return
        
        if not data["bot_active"] and user_id != DEVELOPER_ID:
            await query.edit_message_text("⏸️ **البوت معطل.**", parse_mode="Markdown")
            return
        
        data_callback = query.data

        # ========== رد برسالة مخصصة ==========
        if data_callback.startswith("reply_custom_"):
            target_id = int(data_callback.split('_')[2])
            context.user_data['replying_to_custom'] = target_id
            context.user_data['waiting_for'] = 'custom_reply'
            await query.edit_message_text(
                f"✏️ **أرسل رسالتك المخصصة للرد**\\n👤 للمستخدم: `{{target_id}}`\\n\\nلإلغاء: /cancel",
                parse_mode="Markdown"
            )
            return

        # ========== ردود المطور ==========
        elif data_callback.startswith("reply_photo_"):
            target_id = int(data_callback.split('_')[2])
            context.user_data['replying_to_photo'] = target_id
            context.user_data['waiting_for'] = 'reply_photo'
            await query.edit_message_text(f"🖼️ **أرسل الصورة التي تريد الرد بها**\\n👤 للمستخدم: `{{target_id}}`\\nلإلغاء: /cancel", parse_mode="Markdown")
            return

        elif data_callback.startswith("reply_video_"):
            target_id = int(data_callback.split('_')[2])
            context.user_data['replying_to_video'] = target_id
            context.user_data['waiting_for'] = 'reply_video'
            await query.edit_message_text(f"🎥 **أرسل الفيديو الذي تريد الرد به**\\n👤 للمستخدم: `{{target_id}}`\\nلإلغاء: /cancel", parse_mode="Markdown")
            return

        elif data_callback.startswith("reply_audio_"):
            target_id = int(data_callback.split('_')[2])
            context.user_data['replying_to_audio'] = target_id
            context.user_data['waiting_for'] = 'reply_audio'
            await query.edit_message_text(f"🎵 **أرسل الصوت الذي تريد الرد به**\\n👤 للمستخدم: `{{target_id}}`\\nلإلغاء: /cancel", parse_mode="Markdown")
            return

        elif data_callback.startswith("reply_sticker_"):
            target_id = int(data_callback.split('_')[2])
            context.user_data['replying_to_sticker'] = target_id
            context.user_data['waiting_for'] = 'reply_sticker'
            await query.edit_message_text(f"🏷️ **أرسل الملصق الذي تريد الرد به**\\n👤 للمستخدم: `{{target_id}}`\\nلإلغاء: /cancel", parse_mode="Markdown")
            return

        elif data_callback.startswith("reply_document_"):
            target_id = int(data_callback.split('_')[2])
            context.user_data['replying_to_document'] = target_id
            context.user_data['waiting_for'] = 'reply_document'
            await query.edit_message_text(f"📎 **أرسل الملف الذي تريد الرد به**\\n👤 للمستخدم: `{{target_id}}`\\nلإلغاء: /cancel", parse_mode="Markdown")
            return

        # ========== عرض جميع الرسائل ==========
        elif data_callback == "show_all_messages":
            if user_id != DEVELOPER_ID:
                return
            
            replies = load_replies()
            if not replies:
                await query.edit_message_text("📭 **لا توجد رسائل.**", parse_mode="Markdown")
                return
            
            message_list = []
            for uid, msg_data in list(replies.items())[-10:]:
                message_list.append(
                    f"━━━━━━━━━━━━━━━━━━━\\n"
                    f"👤 {{msg_data['name']}}\\n"
                    f"🆔 `{{uid}}`\\n"
                    f"📝 {{msg_data['message'][:50]}}...\\n"
                    f"⏰ {{msg_data['time']}}"
                )
            
            messages_text = "\\n".join(message_list)
            keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"📋 **آخر الرسائل ({{len(replies)}})**\\n\\n{{messages_text}}",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            return

        # ========== أزرار الإرسال ==========
        elif data_callback == "send_message":
            context.user_data['waiting_for'] = 'message_to_dev'
            await query.edit_message_text("📝 **أرسل رسالتك الآن**\\nللمطور {developer_username}\\n⚠️ المحتوى المخالف = حظر فوري", parse_mode="Markdown")
        
        elif data_callback == "send_photo":
            context.user_data['waiting_for'] = 'photo_to_dev'
            await query.edit_message_text("🖼️ **أرسل الصورة الآن**\\nللمطور {developer_username}", parse_mode="Markdown")
        
        elif data_callback == "send_video":
            context.user_data['waiting_for'] = 'video_to_dev'
            await query.edit_message_text("🎥 **أرسل الفيديو الآن**\\nللمطور {developer_username}", parse_mode="Markdown")
        
        elif data_callback == "send_audio":
            context.user_data['waiting_for'] = 'audio_to_dev'
            await query.edit_message_text("🎵 **أرسل الصوت الآن**\\nللمطور {developer_username}", parse_mode="Markdown")
        
        elif data_callback == "send_document":
            context.user_data['waiting_for'] = 'document_to_dev'
            await query.edit_message_text("📎 **أرسل الملف الآن**\\nللمطور {developer_username}", parse_mode="Markdown")
        
        elif data_callback == "send_sticker":
            context.user_data['waiting_for'] = 'sticker_to_dev'
            await query.edit_message_text("🏷️ **أرسل الملصق الآن**\\nللمطور {developer_username}", parse_mode="Markdown")

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
            if user_id == DEVELOPER_ID:
                keyboard.append([InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="admin_panel")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"📩 **بوت التواصل مع المطور**\\n\\n👨‍💻 **المطور:** {developer_username}\\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\\n📌 **اختر ما تريد إرساله:**\\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        
        # ========== لوحة تحكم المطور ==========
        elif data_callback == "admin_panel" and user_id == DEVELOPER_ID:
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
                f"⚙️ **لوحة التحكم**\\n\\n👨‍💻 المطور: {developer_username}\\n📊 المستخدمين: {{data['total_users']}}\\n🚫 المحظورين: {{len(data['banned_users'])}}\\n📌 الحالة: {{status}}",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        
        elif data_callback == "admin_stats" and user_id == DEVELOPER_ID:
            keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"📊 **الإحصائيات**\\n\\n👥 المستخدمين: {{data['total_users']}}\\n🚫 المحظورين: {{len(data['banned_users'])}}\\n📌 الحالة: {{'🟢 مفعل' if data['bot_active'] else '🔴 معطل'}}\\n📅 {{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}}",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        
        elif data_callback == "admin_disable" and user_id == DEVELOPER_ID:
            data["bot_active"] = False
            save_data(data)
            await query.edit_message_text("⏸️ **تم تعطيل البوت!**", parse_mode="Markdown")
        
        elif data_callback == "admin_enable" and user_id == DEVELOPER_ID:
            data["bot_active"] = True
            save_data(data)
            await query.edit_message_text("▶️ **تم تفعيل البوت!**", parse_mode="Markdown")
        
        elif data_callback == "admin_ban" and user_id == DEVELOPER_ID:
            context.user_data['waiting_for'] = 'ban_user'
            await query.edit_message_text("🚫 **حظر مستخدم**\\n\\nأرسل الآيدي:\\nمثال: `123456789`\\nلإلغاء: /cancel", parse_mode="Markdown")
        
        elif data_callback == "admin_unban" and user_id == DEVELOPER_ID:
            context.user_data['waiting_for'] = 'unban_user'
            await query.edit_message_text("✅ **الغاء حظر**\\n\\nأرسل الآيدي:\\nمثال: `123456789`\\nلإلغاء: /cancel", parse_mode="Markdown")
        
        elif data_callback == "admin_banned_list" and user_id == DEVELOPER_ID:
            keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if data["banned_users"]:
                banned_list = "\\n".join([f"🚫 `{{uid}}`" for uid in data["banned_users"]])
                await query.edit_message_text(
                    f"📋 **المحظورين**\\n\\n{{banned_list}}\\n\\nالعدد: {{len(data['banned_users'])}}",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text("✅ **لا يوجد محظورين.**", reply_markup=reply_markup, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error in button_handler: {{e}}")

# ========== معالج الرد المخصص ==========

async def handle_custom_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الرد المخصص من المطور"""
    try:
        user_id = update.message.from_user.id
        user_message = update.message.text
        
        # التأكد أن المستخدم هو المطور
        if user_id != DEVELOPER_ID:
            return
        
        # التأكد أننا في وضع الرد المخصص
        if context.user_data.get('waiting_for') != 'custom_reply':
            return
        
        target_id = context.user_data.get('replying_to_custom')
        if not target_id:
            await update.message.reply_text("❌ لا يوجد مستخدم مستهدف.", parse_mode="Markdown")
            context.user_data.clear()
            return
        
        # إرسال الرسالة للمستخدم
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"📩 **رد من المطور {developer_username}**\\n\\n{{user_message}}",
                parse_mode="Markdown"
            )
            
            await update.message.reply_text(
                f"✅ **تم الإرسال!**\\n👤 `{{target_id}}`\\n📝 {{user_message}}",
                parse_mode="Markdown"
            )
        except Exception as e:
            await update.message.reply_text(
                f"❌ **خطأ:** لم يتمكن البوت من إرسال الرد.",
                parse_mode="Markdown"
            )
        
        # تنظيف البيانات
        context.user_data.clear()
        
    except Exception as e:
        logging.error(f"Error in handle_custom_reply: {{e}}")
        await update.message.reply_text("❌ حدث خطأ.", parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        user_name = update.message.from_user.first_name
        username = update.message.from_user.username
        user_message = update.message.text
        
        # ========== معالج الرد المخصص (يتم تشغيله قبل أي شيء) ==========
        if user_id == DEVELOPER_ID and context.user_data.get('waiting_for') == 'custom_reply':
            await handle_custom_reply(update, context)
            return
        
        if user_message and user_message.lower() == "/cancel":
            context.user_data.clear()
            await update.message.reply_text("❌ **تم الإلغاء.**", parse_mode="Markdown")
            return
        
        data = load_data()
        
        if str(user_id) in data["banned_users"] and user_id != DEVELOPER_ID:
            await update.message.reply_text("🚫 **أنت محظور.**", parse_mode="Markdown")
            return
        
        if not data["bot_active"] and user_id != DEVELOPER_ID:
            await update.message.reply_text("⏸️ **البوت معطل.**", parse_mode="Markdown")
            return

        # ========== أوامر المطور ==========
        if user_id == DEVELOPER_ID:
            if context.user_data.get('waiting_for') == 'ban_user':
                try:
                    target_id = int(user_message.strip())
                    if str(target_id) not in data["banned_users"]:
                        data["banned_users"].append(str(target_id))
                        save_data(data)
                        await update.message.reply_text(f"✅ **تم حظر `{{target_id}}`**", parse_mode="Markdown")
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
                        await update.message.reply_text(f"✅ **تم الغاء حظر `{{target_id}}`**", parse_mode="Markdown")
                    else:
                        await update.message.reply_text("⚠️ **غير محظور.**", parse_mode="Markdown")
                    context.user_data['waiting_for'] = None
                except ValueError:
                    await update.message.reply_text("❌ **أرسل أرقام فقط.**", parse_mode="Markdown")
                return
        
        # ========== إرسال رسالة للمطور ==========
        if context.user_data.get('waiting_for') == 'message_to_dev':
            try:
                replies = load_replies()
                replies[str(user_id)] = {{
                    "name": user_name,
                    "username": username,
                    "message": user_message,
                    "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "user_id": user_id
                }}
                save_replies(replies)
                
                keyboard = [
                    [
                        InlineKeyboardButton("✏️ رد برسالة مخصصة", callback_data=f"reply_custom_{{user_id}}"),
                    ],
                    [
                        InlineKeyboardButton("🖼️ رد بصورة", callback_data=f"reply_photo_{{user_id}}"),
                        InlineKeyboardButton("🎥 رد بفيديو", callback_data=f"reply_video_{{user_id}}"),
                    ],
                    [
                        InlineKeyboardButton("🎵 رد بصوت", callback_data=f"reply_audio_{{user_id}}"),
                        InlineKeyboardButton("🏷️ رد بملصق", callback_data=f"reply_sticker_{{user_id}}"),
                    ],
                    [
                        InlineKeyboardButton("📎 رد بملف", callback_data=f"reply_document_{{user_id}}"),
                        InlineKeyboardButton("📋 جميع الرسائل", callback_data="show_all_messages"),
                    ],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await context.bot.send_message(
                    chat_id=DEVELOPER_ID,
                    text=f"📩 **رسالة جديدة**\\n\\n👤 {{user_name}}\\n🆔 @{{username if username else 'لا يوجد'}}\\n🔢 `{{user_id}}`\\n\\n📝 {{user_message}}\\n\\n⏰ {{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}}",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
                
                await update.message.reply_text("✅ **تم الإرسال!**\\n\\n📨 سيتم الرد عليك قريباً.", parse_mode="Markdown")
                context.user_data['waiting_for'] = None
                
            except Exception as e:
                await update.message.reply_text("❌ حدث خطأ.", parse_mode="Markdown")
                logging.error(f"Error: {{e}}")
            return
        
        await update.message.reply_text("📩 استخدم /start للتواصل.", parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error in handle_message: {{e}}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        user_name = update.message.from_user.first_name
        username = update.message.from_user.username
        photo_file = update.message.photo[-1]
        caption = update.message.caption or "بدون تعليق"
        
        data = load_data()
        if str(user_id) in data["banned_users"] and user_id != DEVELOPER_ID:
            await update.message.reply_text("🚫 محظور.", parse_mode="Markdown")
            return

        if user_id == DEVELOPER_ID and context.user_data.get('waiting_for') == 'reply_photo':
            target_id = context.user_data.get('replying_to_photo')
            if target_id:
                try:
                    await context.bot.send_photo(chat_id=target_id, photo=photo_file.file_id)
                    await update.message.reply_text(f"✅ **تم الرد بالصورة** 👤 `{{target_id}}`", parse_mode="Markdown")
                except Exception as e:
                    await update.message.reply_text("❌ فشل الإرسال.", parse_mode="Markdown")
                context.user_data.clear()
            return

        if context.user_data.get('waiting_for') == 'photo_to_dev':
            try:
                await context.bot.send_photo(
                    chat_id=DEVELOPER_ID,
                    photo=photo_file.file_id,
                    caption=f"🖼️ **صورة جديدة**\\n\\n👤 {{user_name}}\\n🆔 @{{username if username else 'لا يوجد'}}\\n🔢 `{{user_id}}`\\n📝 {{caption}}\\n⏰ {{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}}"
                )
                
                keyboard = [
                    [
                        InlineKeyboardButton("✏️ رد برسالة مخصصة", callback_data=f"reply_custom_{{user_id}}"),
                        InlineKeyboardButton("🖼️ رد بصورة", callback_data=f"reply_photo_{{user_id}}"),
                    ],
                    [
                        InlineKeyboardButton("🎥 رد بفيديو", callback_data=f"reply_video_{{user_id}}"),
                        InlineKeyboardButton("🎵 رد بصوت", callback_data=f"reply_audio_{{user_id}}"),
                    ],
                    [
                        InlineKeyboardButton("🏷️ رد بملصق", callback_data=f"reply_sticker_{{user_id}}"),
                        InlineKeyboardButton("📎 رد بملف", callback_data=f"reply_document_{{user_id}}"),
                    ],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")],
                ]
                await context.bot.send_message(
                    chat_id=DEVELOPER_ID,
                    text=f"📌 للرد على هذه الصورة:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                await update.message.reply_text("✅ **تم الإرسال!**", parse_mode="Markdown")
                context.user_data['waiting_for'] = None
            except Exception as e:
                await update.message.reply_text("❌ حدث خطأ.", parse_mode="Markdown")
                logging.error(f"Error: {{e}}")
            return
        
        await update.message.reply_text("📸 استخدم /start للإرسال.", parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error in handle_photo: {{e}}")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        user_name = update.message.from_user.first_name
        username = update.message.from_user.username
        video_file = update.message.video
        caption = update.message.caption or "بدون تعليق"
        
        data = load_data()
        if str(user_id) in data["banned_users"] and user_id != DEVELOPER_ID:
            await update.message.reply_text("🚫 محظور.", parse_mode="Markdown")
            return

        if user_id == DEVELOPER_ID and context.user_data.get('waiting_for') == 'reply_video':
            target_id = context.user_data.get('replying_to_video')
            if target_id:
                try:
                    await context.bot.send_video(chat_id=target_id, video=video_file.file_id)
                    await update.message.reply_text(f"✅ **تم الرد بالفيديو** 👤 `{{target_id}}`", parse_mode="Markdown")
                except Exception as e:
                    await update.message.reply_text("❌ فشل الإرسال.", parse_mode="Markdown")
                context.user_data.clear()
            return

        if context.user_data.get('waiting_for') == 'video_to_dev':
            try:
                await context.bot.send_video(
                    chat_id=DEVELOPER_ID,
                    video=video_file.file_id,
                    caption=f"🎥 **فيديو جديد**\\n\\n👤 {{user_name}}\\n🆔 @{{username if username else 'لا يوجد'}}\\n🔢 `{{user_id}}`\\n📝 {{caption}}\\n⏰ {{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}}"
                )
                
                keyboard = [
                    [
                        InlineKeyboardButton("✏️ رد برسالة مخصصة", callback_data=f"reply_custom_{{user_id}}"),
                        InlineKeyboardButton("🖼️ رد بصورة", callback_data=f"reply_photo_{{user_id}}"),
                    ],
                    [
                        InlineKeyboardButton("🎥 رد بفيديو", callback_data=f"reply_video_{{user_id}}"),
                        InlineKeyboardButton("🎵 رد بصوت", callback_data=f"reply_audio_{{user_id}}"),
                    ],
                    [
                        InlineKeyboardButton("🏷️ رد بملصق", callback_data=f"reply_sticker_{{user_id}}"),
                        InlineKeyboardButton("📎 رد بملف", callback_data=f"reply_document_{{user_id}}"),
                    ],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")],
                ]
                await context.bot.send_message(
                    chat_id=DEVELOPER_ID,
                    text=f"📌 للرد على هذا الفيديو:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                await update.message.reply_text("✅ **تم الإرسال!**", parse_mode="Markdown")
                context.user_data['waiting_for'] = None
            except Exception as e:
                await update.message.reply_text("❌ حدث خطأ.", parse_mode="Markdown")
                logging.error(f"Error: {{e}}")
            return
        
        await update.message.reply_text("🎥 استخدم /start للإرسال.", parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error in handle_video: {{e}}")

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        user_name = update.message.from_user.first_name
        username = update.message.from_user.username
        audio_file = update.message.audio
        caption = update.message.caption or "بدون تعليق"
        
        data = load_data()
        if str(user_id) in data["banned_users"] and user_id != DEVELOPER_ID:
            await update.message.reply_text("🚫 محظور.", parse_mode="Markdown")
            return

        if user_id == DEVELOPER_ID and context.user_data.get('waiting_for') == 'reply_audio':
            target_id = context.user_data.get('replying_to_audio')
            if target_id:
                try:
                    await context.bot.send_audio(chat_id=target_id, audio=audio_file.file_id)
                    await update.message.reply_text(f"✅ **تم الرد بالصوت** 👤 `{{target_id}}`", parse_mode="Markdown")
                except Exception as e:
                    await update.message.reply_text("❌ فشل الإرسال.", parse_mode="Markdown")
                context.user_data.clear()
            return

        if context.user_data.get('waiting_for') == 'audio_to_dev':
            try:
                await context.bot.send_audio(
                    chat_id=DEVELOPER_ID,
                    audio=audio_file.file_id,
                    caption=f"🎵 **ملف صوتي جديد**\\n\\n👤 {{user_name}}\\n🆔 @{{username if username else 'لا يوجد'}}\\n🔢 `{{user_id}}`\\n📝 {{caption}}\\n⏰ {{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}}"
                )
                
                keyboard = [
                    [
                        InlineKeyboardButton("✏️ رد برسالة مخصصة", callback_data=f"reply_custom_{{user_id}}"),
                        InlineKeyboardButton("🖼️ رد بصورة", callback_data=f"reply_photo_{{user_id}}"),
                    ],
                    [
                        InlineKeyboardButton("🎥 رد بفيديو", callback_data=f"reply_video_{{user_id}}"),
                        InlineKeyboardButton("🎵 رد بصوت", callback_data=f"reply_audio_{{user_id}}"),
                    ],
                    [
                        InlineKeyboardButton("🏷️ رد بملصق", callback_data=f"reply_sticker_{{user_id}}"),
                        InlineKeyboardButton("📎 رد بملف", callback_data=f"reply_document_{{user_id}}"),
                    ],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")],
                ]
                await context.bot.send_message(
                    chat_id=DEVELOPER_ID,
                    text=f"📌 للرد على هذا الصوت:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                await update.message.reply_text("✅ **تم الإرسال!**", parse_mode="Markdown")
                context.user_data['waiting_for'] = None
            except Exception as e:
                await update.message.reply_text("❌ حدث خطأ.", parse_mode="Markdown")
                logging.error(f"Error: {{e}}")
            return
        
        await update.message.reply_text("🎵 استخدم /start للإرسال.", parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error in handle_audio: {{e}}")

async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        user_name = update.message.from_user.first_name
        username = update.message.from_user.username
        sticker_file = update.message.sticker
        
        data = load_data()
        if str(user_id) in data["banned_users"] and user_id != DEVELOPER_ID:
            await update.message.reply_text("🚫 محظور.", parse_mode="Markdown")
            return

        if user_id == DEVELOPER_ID and context.user_data.get('waiting_for') == 'reply_sticker':
            target_id = context.user_data.get('replying_to_sticker')
            if target_id:
                try:
                    await context.bot.send_sticker(chat_id=target_id, sticker=sticker_file.file_id)
                    await update.message.reply_text(f"✅ **تم الرد بالملصق** 👤 `{{target_id}}`", parse_mode="Markdown")
                except Exception as e:
                    await update.message.reply_text("❌ فشل الإرسال.", parse_mode="Markdown")
                context.user_data.clear()
            return

        if context.user_data.get('waiting_for') == 'sticker_to_dev':
            try:
                await context.bot.send_sticker(
                    chat_id=DEVELOPER_ID,
                    sticker=sticker_file.file_id
                )
                
                await context.bot.send_message(
                    chat_id=DEVELOPER_ID,
                    text=f"🏷️ **ملصق جديد**\\n\\n👤 {{user_name}}\\n🆔 @{{username if username else 'لا يوجد'}}\\n🔢 `{{user_id}}`\\n⏰ {{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}}"
                )
                
                keyboard = [
                    [
                        InlineKeyboardButton("✏️ رد برسالة مخصصة", callback_data=f"reply_custom_{{user_id}}"),
                        InlineKeyboardButton("🖼️ رد بصورة", callback_data=f"reply_photo_{{user_id}}"),
                    ],
                    [
                        InlineKeyboardButton("🎥 رد بفيديو", callback_data=f"reply_video_{{user_id}}"),
                        InlineKeyboardButton("🎵 رد بصوت", callback_data=f"reply_audio_{{user_id}}"),
                    ],
                    [
                        InlineKeyboardButton("🏷️ رد بملصق", callback_data=f"reply_sticker_{{user_id}}"),
                        InlineKeyboardButton("📎 رد بملف", callback_data=f"reply_document_{{user_id}}"),
                    ],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")],
                ]
                await context.bot.send_message(
                    chat_id=DEVELOPER_ID,
                    text=f"📌 للرد على هذا الملصق:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                await update.message.reply_text("✅ **تم الإرسال!**", parse_mode="Markdown")
                context.user_data['waiting_for'] = None
            except Exception as e:
                await update.message.reply_text("❌ حدث خطأ.", parse_mode="Markdown")
                logging.error(f"Error: {{e}}")
            return
        
        await update.message.reply_text("🏷️ استخدم /start للإرسال.", parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error in handle_sticker: {{e}}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        user_name = update.message.from_user.first_name
        username = update.message.from_user.username
        document_file = update.message.document
        caption = update.message.caption or "بدون تعليق"
        
        data = load_data()
        if str(user_id) in data["banned_users"] and user_id != DEVELOPER_ID:
            await update.message.reply_text("🚫 محظور.", parse_mode="Markdown")
            return

        if user_id == DEVELOPER_ID and context.user_data.get('waiting_for') == 'reply_document':
            target_id = context.user_data.get('replying_to_document')
            if target_id:
                try:
                    await context.bot.send_document(chat_id=target_id, document=document_file.file_id)
                    await update.message.reply_text(f"✅ **تم الرد بالملف** 👤 `{{target_id}}`", parse_mode="Markdown")
                except Exception as e:
                    await update.message.reply_text("❌ فشل الإرسال.", parse_mode="Markdown")
                context.user_data.clear()
            return

        if context.user_data.get('waiting_for') == 'document_to_dev':
            try:
                await context.bot.send_document(
                    chat_id=DEVELOPER_ID,
                    document=document_file.file_id,
                    caption=f"📎 **ملف جديد**\\n\\n👤 {{user_name}}\\n🆔 @{{username if username else 'لا يوجد'}}\\n🔢 `{{user_id}}`\\n📝 {{caption}}\\n⏰ {{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}}"
                )
                
                keyboard = [
                    [
                        InlineKeyboardButton("✏️ رد برسالة مخصصة", callback_data=f"reply_custom_{{user_id}}"),
                        InlineKeyboardButton("🖼️ رد بصورة", callback_data=f"reply_photo_{{user_id}}"),
                    ],
                    [
                        InlineKeyboardButton("🎥 رد بفيديو", callback_data=f"reply_video_{{user_id}}"),
                        InlineKeyboardButton("🎵 رد بصوت", callback_data=f"reply_audio_{{user_id}}"),
                    ],
                    [
                        InlineKeyboardButton("🏷️ رد بملصق", callback_data=f"reply_sticker_{{user_id}}"),
                        InlineKeyboardButton("📎 رد بملف", callback_data=f"reply_document_{{user_id}}"),
                    ],
                    [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")],
                ]
                await context.bot.send_message(
                    chat_id=DEVELOPER_ID,
                    text=f"📌 للرد على هذا الملف:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                
                await update.message.reply_text("✅ **تم الإرسال!**", parse_mode="Markdown")
                context.user_data['waiting_for'] = None
            except Exception as e:
                await update.message.reply_text("❌ حدث خطأ.", parse_mode="Markdown")
                logging.error(f"Error: {{e}}")
            return
        
        await update.message.reply_text("📎 استخدم /start للإرسال.", parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error in handle_document: {{e}}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📖 **المساعدة**\\n\\n/start - القائمة الرئيسية\\n/help - هذه المساعدة\\n/dev - المطور\\n/panel - لوحة التحكم\\n/cancel - إلغاء العملية",
        parse_mode="Markdown"
    )

async def dev_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👨‍💻 **المطور**\\n\\nالبوت من تصميم:\\n✨ {developer_username} ✨\\n\\n📌 للتواصل: {developer_username}",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ **تم الإلغاء.**", parse_mode="Markdown")

# ========== التشغيل الرئيسي ==========

def main():
    print("🚀 تشغيل بوت التواصل الذكي...")
    print(f"👨‍💻 المطور: {developer_username}")
    
    if not os.path.exists(DATA_FILE):
        save_data({{"users": [], "banned_users": [], "bot_active": True, "total_users": 0}})
    
    if not os.path.exists(REPLIES_FILE):
        save_replies({{}})
    
    app = Application.builder().token(BOT_TOKEN).build()
    
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
    
    print("✅ البوت يعمل الآن...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
'''
    
    def start_bot_process(self, bot_token):
        try:
            bot_data = self.db.get_bot(bot_token)
            if not bot_data:
                return False, "البوت غير موجود"
            
            if not bot_data['is_active']:
                return False, "البوت معطل"
            
            # إنشاء كود البوت
            bot_code = self.create_bot_code(
                bot_token,
                bot_data['bot_name'],
                bot_data['owner_id'],
                bot_data['developer_username']
            )
            
            # حفظ الكود في ملف
            bot_file = f"bot_{bot_token.replace(':', '_')}.py"
            with open(bot_file, 'w', encoding='utf-8') as f:
                f.write(bot_code)
            
            # إنشاء التطبيق
            app = Application.builder().token(bot_token).build()
            self._setup_bot_handlers(app, bot_data)
            
            # تشغيل في thread منفصل
            def run_bot():
                try:
                    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
                except Exception as e:
                    logger.error(f"Bot {bot_token} error: {e}")
            
            thread = threading.Thread(target=run_bot, daemon=True)
            thread.start()
            
            self.bot_instances[bot_token] = app
            self.active_bots[bot_token] = {"app": app, "thread": thread}
            
            logger.info(f"✅ Bot {bot_token} started successfully")
            return True, "تم تشغيل البوت بنجاح ✅"
            
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            return False, f"خطأ: {str(e)}"
    
    def stop_bot(self, bot_token):
        try:
            if bot_token in self.active_bots:
                app = self.bot_instances.get(bot_token)
                if app:
                    try:
                        asyncio.run_coroutine_threadsafe(app.stop(), self.loop)
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
        bot_name = bot_data['bot_name']
        
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
