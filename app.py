import os
import asyncio
import logging
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from flask import Flask, request, jsonify

# ===== إعدادات =====
logging.basicConfig(level=logging.INFO)

# ===== متغيرات البوت =====
API_ID = 38532428
API_HASH = "bd13b721c96184649dbbce14de78147d"
BOT_TOKEN = "8909739497:AAHBUGLmeligI-TX3kZKlQ_8nTZK61TKVtI"
OWNER_ID = 1170411845

# ===== إعداد Flask =====
flask_app = Flask(__name__)

# ===== إعداد البوت =====
bot = Client(
    "contact_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

# ===== الروابط =====
DEVELOPER_LINK = "https://t.me/u_t_r"
SUPPORT_CHANNEL = "https://t.me/u_t_r2"

# ===== القوائم =====
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("👨‍💻 تواصل مع المطور")],
        [KeyboardButton("ℹ️ معلومات عن البوت")]
    ],
    resize_keyboard=True
)

DEV_KEYBOARD = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("👨‍💻 تواصل مع المطور", url=DEVELOPER_LINK)],
        [InlineKeyboardButton("📢 قناة الدعم", url=SUPPORT_CHANNEL)],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
    ]
)

# ===== أوامر البوت =====
@bot.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user = message.from_user
    welcome_text = f"""
✨ **مرحباً بك عزيزي {user.first_name}** ✨

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

🤖 **بوت التواصل مع المطور**

📌 **خدمات البوت:**
• 📱 التواصل المباشر مع المطور
• 💡 الحصول على الدعم الفني

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

💫 **كيفية الاستخدام:**
1️⃣ اضغط على زر "تواصل مع المطور"
2️⃣ اختر طريقة التواصل المناسبة
3️⃣ اكتب رسالتك وسيتم الرد عليك

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

⚡️ **متوفر 24/7** 
📌 **وقت الرد:** خلال 24 ساعة
"""

    await message.reply(
        welcome_text,
        reply_markup=MAIN_KEYBOARD,
        quote=True
    )

    # إشعار للمالك
    try:
        await client.send_message(
            OWNER_ID,
            f"""👤 **مستخدم جديد دخل البوت**

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

🆔 **المعرف:** `{user.id}`
📛 **الاسم:** {user.first_name} {user.last_name or ''}
👤 **اليوزر:** {f'@{user.username}' if user.username else 'لا يوجد'}
📅 **التاريخ:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        )
    except Exception as e:
        logging.error(f"خطأ في إرسال الإشعار: {e}")

@bot.on_message(filters.text & filters.private)
async def handle_messages(client, message):
    text = message.text
    user = message.from_user

    # ===== معلومات عن البوت =====
    if text == "ℹ️ معلومات عن البوت":
        info_text = """
📊 **معلومات عن البوت**

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

🤖 **الاسم:** بوت التواصل مع المطور
🐍 **لغة البرمجة:** Python (Pyrogram)
⚡️ **الحالة:** نشط 🟢

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

📌 **الوظيفة:**
• التواصل المباشر مع المطور والدعم الفني

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

📢 **قناة الدعم:** @u_t_r2
📱 **للتواصل:** @u_t_r
"""

        await message.reply(
            info_text,
            reply_markup=MAIN_KEYBOARD,
            quote=True
        )
        return

    # ===== تواصل مع المطور =====
    if text == "👨‍💻 تواصل مع المطور":
        dev_text = """
👨‍💻 **المطور**

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

📱 **طرق التواصل:**
• اضغط على زر التواصل أدناه
• ارسال رسالة مباشرة
• الرد خلال 24 ساعة

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

📢 **للانضمام لقناة الدعم:** @u_t_r2
💫 **للتواصل اضغط على الزر أدناه**
"""

        await message.reply(
            dev_text,
            reply_markup=DEV_KEYBOARD,
            quote=True
        )
        return

    # ===== إرسال رسالة المستخدم للمالك =====
    if text not in ["👨‍💻 تواصل مع المطور", "ℹ️ معلومات عن البوت"]:
        try:
            # إرسال للمالك
            await client.send_message(
                OWNER_ID,
                f"""📩 **رسالة جديدة من المستخدم**

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

👤 **من:** {user.first_name} {user.last_name or ''}
🆔 **المعرف:** `{user.id}`
👤 **اليوزر:** {f'@{user.username}' if user.username else 'لا يوجد'}

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

💬 **الرسالة:**
{text}

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

📅 **التاريخ:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
            )

            # رد للمستخدم
            await message.reply(
                f"""✅ **تم إرسال رسالتك بنجاح!**

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

📩 **سيتم الرد عليك في أقرب وقت**
⏳ **وقت الرد المتوقع:** خلال 24 ساعة

⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

📢 **قناة الدعم:** @u_t_r2
💡 **للتواصل المباشر:** @u_t_r""",
                reply_markup=MAIN_KEYBOARD,
                quote=True
            )

        except Exception as e:
            logging.error(f"خطأ في إرسال الرسالة: {e}")
            await message.reply(
                "❌ **عذراً، حدث خطأ في إرسال رسالتك**\n\n🔄 يرجى المحاولة مرة أخرى لاحقاً",
                reply_markup=MAIN_KEYBOARD,
                quote=True
            )

# ===== معالجة الأزرار =====
@bot.on_callback_query()
async def handle_callback(client, callback_query):
    if callback_query.data == "back_to_main":
        await callback_query.message.delete()
        await callback_query.message.reply(
            "✨ **تم العودة إلى القائمة الرئيسية** ✨\n\n📌 اختر الخدمة التي تريدها:",
            reply_markup=MAIN_KEYBOARD
        )
        await callback_query.answer()

# ===== تشغيل Flask مع البوت =====
@flask_app.route('/')
def index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>🤖 بوت التواصل</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                margin: 0;
                color: white;
                text-align: center;
                padding: 20px;
            }
            .container {
                background: rgba(255,255,255,0.15);
                padding: 50px;
                border-radius: 30px;
                backdrop-filter: blur(20px);
                border: 1px solid rgba(255,255,255,0.2);
                max-width: 600px;
                width: 100%;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            }
            .icon { font-size: 80px; margin-bottom: 20px; }
            h1 { 
                font-size: 2.5em; 
                margin-bottom: 15px;
                font-weight: 700;
            }
            p { 
                font-size: 1.2em; 
                opacity: 0.95;
                line-height: 1.6;
                margin-bottom: 10px;
            }
            .status { 
                color: #4ade80; 
                font-weight: bold;
                font-size: 1.1em;
                display: inline-block;
                background: rgba(74, 222, 128, 0.2);
                padding: 8px 25px;
                border-radius: 50px;
                margin: 15px 0;
            }
            hr { 
                border: 1px solid rgba(255,255,255,0.15); 
                margin: 25px 0; 
            }
            .info-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
                margin-top: 20px;
            }
            .info-item {
                background: rgba(255,255,255,0.08);
                padding: 15px;
                border-radius: 15px;
                backdrop-filter: blur(10px);
            }
            .info-item .label {
                font-size: 0.8em;
                opacity: 0.7;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            .info-item .value {
                font-size: 1.1em;
                font-weight: 600;
                margin-top: 5px;
            }
            .footer {
                margin-top: 25px;
                font-size: 0.9em;
                opacity: 0.8;
            }
            @media (max-width: 500px) {
                .container { padding: 30px 20px; }
                h1 { font-size: 1.8em; }
                .icon { font-size: 60px; }
                .info-grid { grid-template-columns: 1fr; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="icon">🤖</div>
            <h1>بوت التواصل مع المطور</h1>
            <p>✅ البوت يعمل بنجاح!</p>
            <div class="status">🟢 Online</div>
            <hr>
            <div class="info-grid">
                <div class="info-item">
                    <div class="label">📢 قناة الدعم</div>
                    <div class="value">@u_t_r2</div>
                </div>
                <div class="info-item">
                    <div class="label">📱 تواصل</div>
                    <div class="value">@u_t_r</div>
                </div>
                <div class="info-item">
                    <div class="label">⚡️ الحالة</div>
                    <div class="value" style="color: #4ade80;">نشط</div>
                </div>
            </div>
            <div class="footer">
                💡 للتواصل مع المطور اضغط على @u_t_r
            </div>
        </div>
    </body>
    </html>
    """

@flask_app.route('/health')
def health():
    return jsonify({"status": "ok", "bot": "running"})

# ===== تشغيل البوت و Flask معاً =====
async def run_bot():
    await bot.start()
    print("✅ Bot is running!")
    me = await bot.get_me()
    print(f"🤖 Bot username: @{me.username}")
    print(f"👤 Owner ID: {OWNER_ID}")
    print("📢 Support Channel: @u_t_r2")
    print("📱 Contact: @u_t_r")

async def run_flask():
    port = int(os.environ.get('PORT', 10000))
    flask_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

async def main():
    await asyncio.gather(
        run_bot(),
        run_flask()
    )

if __name__ == "__main__":
    asyncio.run(main())
