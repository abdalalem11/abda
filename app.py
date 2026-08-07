import os
import json
import logging
import asyncio
import threading
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import secrets

# ========== إعدادات ==========
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MASTER_OWNER_ID = 1170411845
MASTER_BOT_TOKEN = "8909739497:AAHmL5nLCKm6OKkRsjJDIoNQoC_VP9uN5TM"

flask_app = Flask(__name__)
flask_app.secret_key = secrets.token_hex(32)

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
        self.cursor.execute("SELECT * FROM bots ORDER BY id DESC")
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
        
        async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user = update.message.from_user
            user_id = user.id
            
            cursor = self.db.conn.cursor()
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

# ========== واجهة ويب احترافية ==========
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🏭 مصنع بوتات التواصل</title>
    <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap" rel="stylesheet">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Cairo', Tahoma, sans-serif;
            background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
            min-height: 100vh;
            color: #fff;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        
        /* Header */
        .header {
            text-align: center;
            padding: 40px 0 30px;
            position: relative;
        }
        
        .header .logo {
            font-size: 80px;
            display: block;
            animation: float 3s ease-in-out infinite;
        }
        
        @keyframes float {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-15px); }
        }
        
        .header h1 {
            font-size: 3.5em;
            font-weight: 800;
            background: linear-gradient(135deg, #667eea, #764ba2, #f093fb);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin: 10px 0;
        }
        
        .header .subtitle {
            font-size: 1.2em;
            opacity: 0.7;
            margin-top: 5px;
        }
        
        .status-badge {
            display: inline-block;
            background: rgba(74, 222, 128, 0.15);
            color: #4ade80;
            padding: 8px 30px;
            border-radius: 50px;
            border: 1px solid rgba(74, 222, 128, 0.3);
            font-weight: 600;
            margin: 15px 0;
        }
        
        /* Stats Cards */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }
        
        .stat-card {
            background: rgba(255,255,255,0.05);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 25px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.05);
            transition: all 0.3s;
        }
        
        .stat-card:hover {
            transform: translateY(-5px);
            background: rgba(255,255,255,0.08);
        }
        
        .stat-card .number {
            font-size: 2.5em;
            font-weight: 800;
            background: linear-gradient(135deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .stat-card .label {
            opacity: 0.6;
            font-size: 0.9em;
            margin-top: 5px;
        }
        
        /* Main Content */
        .main-grid {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 30px;
            margin: 30px 0;
        }
        
        @media (max-width: 768px) {
            .main-grid {
                grid-template-columns: 1fr;
            }
        }
        
        /* Form */
        .card {
            background: rgba(255,255,255,0.05);
            backdrop-filter: blur(10px);
            border-radius: 25px;
            padding: 30px;
            border: 1px solid rgba(255,255,255,0.05);
        }
        
        .card-title {
            font-size: 1.5em;
            font-weight: 700;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            opacity: 0.8;
        }
        
        .form-group input,
        .form-group textarea {
            width: 100%;
            padding: 14px 18px;
            background: rgba(255,255,255,0.08);
            border: 2px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            color: #fff;
            font-size: 1em;
            font-family: 'Cairo', sans-serif;
            transition: all 0.3s;
            direction: ltr;
        }
        
        .form-group input:focus,
        .form-group textarea:focus {
            outline: none;
            border-color: #667eea;
            background: rgba(255,255,255,0.12);
        }
        
        .form-group input::placeholder,
        .form-group textarea::placeholder {
            color: rgba(255,255,255,0.4);
        }
        
        .btn {
            padding: 14px 35px;
            border: none;
            border-radius: 12px;
            font-size: 1.05em;
            font-weight: 700;
            font-family: 'Cairo', sans-serif;
            cursor: pointer;
            transition: all 0.3s;
            display: inline-flex;
            align-items: center;
            gap: 10px;
        }
        
        .btn-primary {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: #fff;
            width: 100%;
        }
        
        .btn-primary:hover {
            transform: scale(1.02);
            box-shadow: 0 10px 40px rgba(102, 126, 234, 0.4);
        }
        
        .btn-success {
            background: linear-gradient(135deg, #4ade80, #22d3ee);
            color: #000;
        }
        
        .btn-danger {
            background: linear-gradient(135deg, #f87171, #ef4444);
            color: #fff;
        }
        
        .btn-warning {
            background: linear-gradient(135deg, #fbbf24, #f59e0b);
            color: #000;
        }
        
        .btn-small {
            padding: 8px 16px;
            font-size: 0.85em;
        }
        
        /* Bots List */
        .bot-item {
            background: rgba(255,255,255,0.03);
            border-radius: 15px;
            padding: 18px 20px;
            margin-bottom: 12px;
            border: 1px solid rgba(255,255,255,0.05);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
            transition: all 0.3s;
        }
        
        .bot-item:hover {
            background: rgba(255,255,255,0.06);
        }
        
        .bot-info {
            display: flex;
            flex-direction: column;
            gap: 3px;
        }
        
        .bot-name {
            font-weight: 700;
            font-size: 1.1em;
        }
        
        .bot-username {
            opacity: 0.6;
            font-size: 0.9em;
        }
        
        .bot-status {
            font-size: 0.85em;
            padding: 3px 12px;
            border-radius: 20px;
        }
        
        .status-active {
            background: rgba(74, 222, 128, 0.2);
            color: #4ade80;
        }
        
        .status-inactive {
            background: rgba(248, 113, 113, 0.2);
            color: #f87171;
        }
        
        .bot-actions {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }
        
        /* Toast */
        .toast {
            position: fixed;
            bottom: 30px;
            right: 30px;
            padding: 18px 30px;
            border-radius: 15px;
            font-weight: 600;
            transform: translateY(100px);
            opacity: 0;
            transition: all 0.5s;
            z-index: 999;
        }
        
        .toast.show {
            transform: translateY(0);
            opacity: 1;
        }
        
        .toast-success {
            background: linear-gradient(135deg, #4ade80, #22d3ee);
            color: #000;
        }
        
        .toast-error {
            background: linear-gradient(135deg, #f87171, #ef4444);
            color: #fff;
        }
        
        /* Loading */
        .loading {
            display: none;
            text-align: center;
            padding: 20px;
        }
        
        .loading.active {
            display: block;
        }
        
        .spinner {
            display: inline-block;
            width: 40px;
            height: 40px;
            border: 4px solid rgba(255,255,255,0.1);
            border-top: 4px solid #667eea;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        /* Footer */
        .footer {
            text-align: center;
            padding: 30px 0;
            opacity: 0.5;
            font-size: 0.9em;
            border-top: 1px solid rgba(255,255,255,0.05);
            margin-top: 30px;
        }
        
        .footer .highlight {
            color: #a78bfa;
        }
        
        /* Responsive */
        @media (max-width: 600px) {
            .header h1 { font-size: 2.2em; }
            .header .logo { font-size: 60px; }
            .bot-item { flex-direction: column; align-items: stretch; }
            .bot-actions { justify-content: center; }
            .card { padding: 20px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <span class="logo">🏭</span>
            <h1>مصنع بوتات التواصل</h1>
            <p class="subtitle">أنشئ بوت التواصل الخاص بك خلال ثواني</p>
            <div class="status-badge">🟢 النظام يعمل</div>
        </div>
        
        <!-- Stats -->
        <div class="stats-grid" id="stats">
            <div class="stat-card">
                <div class="number" id="totalBots">0</div>
                <div class="label">🤖 إجمالي البوتات</div>
            </div>
            <div class="stat-card">
                <div class="number" id="activeBots">0</div>
                <div class="label">🟢 بوتات نشطة</div>
            </div>
            <div class="stat-card">
                <div class="number" id="inactiveBots">0</div>
                <div class="label">🔴 بوتات متوقفة</div>
            </div>
        </div>
        
        <!-- Main -->
        <div class="main-grid">
            <!-- Create Bot Form -->
            <div class="card">
                <div class="card-title">🤖 صنع بوت جديد</div>
                <form id="createBotForm" onsubmit="createBot(event)">
                    <div class="form-group">
                        <label>🔑 توكن البوت (من @BotFather)</label>
                        <input type="text" id="botToken" placeholder="1234567890:ABCdefGHIjklMNOpqrsTUVwxyz" required>
                    </div>
                    <div class="form-group">
                        <label>📝 اسم البوت</label>
                        <input type="text" id="botName" placeholder="بوت التواصل الرسمي" required>
                    </div>
                    <div class="form-group">
                        <label>🆔 يوزر البوت (بدون @)</label>
                        <input type="text" id="botUsername" placeholder="MySupportBot" required>
                    </div>
                    <button type="submit" class="btn btn-primary">🚀 صنع البوت الآن</button>
                </form>
                <div class="loading" id="loading">
                    <div class="spinner"></div>
                    <p style="margin-top:15px;">جاري صنع البوت...</p>
                </div>
            </div>
            
            <!-- Bots List -->
            <div class="card">
                <div class="card-title">📋 البوتات الخاصة بك</div>
                <div id="botsList">
                    <p style="opacity:0.5; text-align:center; padding:20px;">قم بصنع بوتك الأول الآن 🚀</p>
                </div>
            </div>
        </div>
        
        <!-- Footer -->
        <div class="footer">
            👨‍💻 المطور الرئيسي: <span class="highlight">@SSSTlF</span> &nbsp;|&nbsp; 🆔 <span class="highlight">1170411845</span>
        </div>
    </div>
    
    <!-- Toast -->
    <div class="toast" id="toast"></div>
    
    <script>
        // ========== Load Bots ==========
        async function loadBots() {
            try {
                const res = await fetch('/api/bots');
                const data = await res.json();
                
                if (data.success) {
                    updateStats(data.bots);
                    renderBots(data.bots);
                }
            } catch (e) {
                console.error('Error loading bots:', e);
            }
        }
        
        function updateStats(bots) {
            const total = bots.length;
            const active = bots.filter(b => b.is_active).length;
            const inactive = total - active;
            
            document.getElementById('totalBots').textContent = total;
            document.getElementById('activeBots').textContent = active;
            document.getElementById('inactiveBots').textContent = inactive;
        }
        
        function renderBots(bots) {
            const container = document.getElementById('botsList');
            
            if (!bots || bots.length === 0) {
                container.innerHTML = '<p style="opacity:0.5; text-align:center; padding:20px;">قم بصنع بوتك الأول الآن 🚀</p>';
                return;
            }
            
            container.innerHTML = bots.map(bot => `
                <div class="bot-item">
                    <div class="bot-info">
                        <div class="bot-name">${bot.bot_name}</div>
                        <div class="bot-username">@${bot.bot_username}</div>
                        <div>
                            <span class="bot-status ${bot.is_active ? 'status-active' : 'status-inactive'}">
                                ${bot.is_active ? '🟢 مفعل' : '🔴 معطل'}
                            </span>
                        </div>
                    </div>
                    <div class="bot-actions">
                        ${bot.is_active ? 
                            `<button class="btn btn-warning btn-small" onclick="toggleBot('${bot.bot_token}', false)">⏸️ إيقاف</button>` :
                            `<button class="btn btn-success btn-small" onclick="toggleBot('${bot.bot_token}', true)">▶️ تشغيل</button>`
                        }
                        <button class="btn btn-danger btn-small" onclick="deleteBot('${bot.bot_token}')">🗑️</button>
                    </div>
                </div>
            `).join('');
        }
        
        // ========== Create Bot ==========
        async function createBot(e) {
            e.preventDefault();
            
            const token = document.getElementById('botToken').value.trim();
            const name = document.getElementById('botName').value.trim();
            const username = document.getElementById('botUsername').value.trim().replace('@', '');
            
            if (!token || !name || !username) {
                showToast('❌ يرجى ملء جميع الحقول', 'error');
                return;
            }
            
            if (!token.includes(':') || token.length < 20) {
                showToast('❌ توكن غير صحيح', 'error');
                return;
            }
            
            document.getElementById('loading').classList.add('active');
            document.querySelector('#createBotForm button').disabled = true;
            
            try {
                const res = await fetch('/api/create_bot', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        bot_token: token,
                        bot_name: name,
                        bot_username: username
                    })
                });
                
                const data = await res.json();
                
                if (data.success) {
                    showToast('✅ تم صنع البوت بنجاح!', 'success');
                    loadBots();
                    document.getElementById('createBotForm').reset();
                } else {
                    showToast('❌ ' + data.message, 'error');
                }
            } catch (e) {
                showToast('❌ حدث خطأ', 'error');
            }
            
            document.getElementById('loading').classList.remove('active');
            document.querySelector('#createBotForm button').disabled = false;
        }
        
        // ========== Toggle Bot ==========
        async function toggleBot(token, active) {
            try {
                const res = await fetch('/api/toggle_bot', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ bot_token: token, active: active })
                });
                
                const data = await res.json();
                if (data.success) {
                    showToast(data.message, 'success');
                    loadBots();
                } else {
                    showToast('❌ ' + data.message, 'error');
                }
            } catch (e) {
                showToast('❌ حدث خطأ', 'error');
            }
        }
        
        // ========== Delete Bot ==========
        async function deleteBot(token) {
            if (!confirm('⚠️ هل أنت متأكد من حذف هذا البوت؟')) return;
            
            try {
                const res = await fetch('/api/delete_bot', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ bot_token: token })
                });
                
                const data = await res.json();
                if (data.success) {
                    showToast('🗑️ تم حذف البوت', 'success');
                    loadBots();
                } else {
                    showToast('❌ ' + data.message, 'error');
                }
            } catch (e) {
                showToast('❌ حدث خطأ', 'error');
            }
        }
        
        // ========== Toast ==========
        function showToast(message, type = 'success') {
            const toast = document.getElementById('toast');
            toast.textContent = message;
            toast.className = 'toast toast-' + type + ' show';
            
            setTimeout(() => {
                toast.classList.remove('show');
            }, 3000);
        }
        
        // ========== Load on Start ==========
        loadBots();
        
        // Auto refresh every 10 seconds
        setInterval(loadBots, 10000);
    </script>
</body>
</html>
'''

# ========== Routes ==========
@flask_app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@flask_app.route('/api/bots')
def api_bots():
    try:
        bots = db.get_all_bots()
        return jsonify({
            "success": True,
            "count": len(bots),
            "bots": bots
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@flask_app.route('/api/create_bot', methods=['POST'])
def api_create_bot():
    try:
        data = request.json
        bot_token = data.get('bot_token')
        bot_name = data.get('bot_name')
        bot_username = data.get('bot_username')
        
        if not all([bot_token, bot_name, bot_username]):
            return jsonify({"success": False, "message": "جميع الحقول مطلوبة"})
        
        if db.get_bot(bot_token):
            return jsonify({"success": False, "message": "هذا البوت مستخدم بالفعل"})
        
        bot_id = db.add_bot(
            bot_token=bot_token,
            bot_name=bot_name,
            bot_username=bot_username,
            owner_id=MASTER_OWNER_ID,
            owner_username="SSSTlF",
            developer_username="@SSSTlF",
            config={"created_by": "web_interface", "version": "2.0"}
        )
        
        if bot_id:
            success, message = bot_manager.start_bot_process(bot_token)
            return jsonify({
                "success": True,
                "message": "تم صنع البوت بنجاح",
                "bot_id": bot_id,
                "running": success
            })
        else:
            return jsonify({"success": False, "message": "فشل في إنشاء البوت"})
            
    except Exception as e:
        logger.error(f"Error creating bot: {e}")
        return jsonify({"success": False, "message": str(e)})

@flask_app.route('/api/toggle_bot', methods=['POST'])
def api_toggle_bot():
    try:
        data = request.json
        bot_token = data.get('bot_token')
        active = data.get('active')
        
        if active:
            success, message = bot_manager.start_bot_process(bot_token)
        else:
            success, message = bot_manager.stop_bot(bot_token)
        
        return jsonify({"success": success, "message": message})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@flask_app.route('/api/delete_bot', methods=['POST'])
def api_delete_bot():
    try:
        data = request.json
        bot_token = data.get('bot_token')
        
        bot_manager.stop_bot(bot_token)
        db.delete_bot(bot_token)
        
        return jsonify({"success": True, "message": "تم حذف البوت"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@flask_app.route('/health')
def health():
    return jsonify({
        "status": "ok",
        "version": "2.0",
        "master_id": MASTER_OWNER_ID
    })

# ========== Master Bot (Telegram) ==========
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
        logger.info("Master bot started")
        return self.app
    
    async def _setup_handlers(self):
        async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            keyboard = [
                [InlineKeyboardButton("🌐 افتح الويب", url="https://your-app.onrender.com")],
                [InlineKeyboardButton("📋 بوتاتي", callback_data="my_bots")],
                [InlineKeyboardButton("ℹ️ عن المصنع", callback_data="about")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "🏭 **مصنع بوتات التواصل v2.0**\n\n"
                "🔹 اصنع بوتك من خلال الويب\n"
                "🔹 إدارة متقدمة وتحكم كامل\n\n"
                "🌐 **افتح الويب للبدء**",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        
        async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            query = update.callback_query
            await query.answer()
            
            if query.data == "about":
                await query.edit_message_text(
                    "🏭 **مصنع بوتات التواصل v2.0**\n\n"
                    "👨‍💻 المطور: @SSSTlF\n"
                    "🆔 ID: 1170411845\n"
                    "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                    "🌐 افتح الويب لصنع بوتك",
                    parse_mode="Markdown"
                )
            elif query.data == "my_bots":
                bots = db.get_bots_by_owner(MASTER_OWNER_ID)
                if not bots:
                    await query.edit_message_text("📭 لا توجد بوتات", parse_mode="Markdown")
                    return
                text = "📋 **بوتاتي**\n\n"
                for bot in bots:
                    text += f"🤖 {bot['bot_name']}\n"
                    text += f"🆔 @{bot['bot_username']}\n"
                    text += f"📌 {'🟢 مفعل' if bot['is_active'] else '🔴 معطل'}\n⎯\n"
                await query.edit_message_text(text, parse_mode="Markdown")
        
        self.app.add_handler(CommandHandler("start", start))
        self.app.add_handler(CallbackQueryHandler(button_handler))

# ========== Main ==========
def main():
    # Start Master Bot
    master = MasterBot(MASTER_BOT_TOKEN)
    
    def run_master():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(master.start())
        loop.run_forever()
    
    thread = threading.Thread(target=run_master, daemon=True)
    thread.start()
    
    # Start Flask
    port = int(os.environ.get('PORT', 8080))
    print(f"🚀 Server running on port {port}")
    print(f"🌐 Open: http://localhost:{port}")
    flask_app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == "__main__":
    main()
