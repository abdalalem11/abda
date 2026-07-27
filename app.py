from flask import Flask, request, jsonify, send_file, render_template_string
import os
import subprocess
import json
import time
import random
import string
from datetime import datetime

app = Flask(__name__)

# ===== قراءة ملف HTML =====
with open('index.html', 'r', encoding='utf-8') as f:
    HTML_TEMPLATE = f.read()

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

# ===== API استخراج الجلسة (محاكاة + حقيقي جزئياً) =====
@app.route('/api/extract', methods=['POST'])
def extract_session():
    data = request.get_json()
    code = data.get('code', '').strip()
    
    if not code:
        return jsonify({'success': False, 'message': 'الكود مطلوب'})
    
    # محاكاة عملية الاستخراج (يمكن ربطها مع Telethon فعلياً)
    # في الوضع الحقيقي، يمكنك استدعاء سكريبت Telethon هنا
    session_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))
    
    # تسجيل العملية
    log_entry = {
        'time': datetime.now().isoformat(),
        'code': code,
        'session': session_id,
        'status': 'success'
    }
    # حفظ السجل في ملف (للاستخدام المتقدم)
    try:
        with open('logs.json', 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    except:
        pass
    
    return jsonify({
        'success': True,
        'session': session_id,
        'message': 'تم استخراج الجلسة بنجاح'
    })

# ===== أوامر النظام (لللوحة السرية) =====
@app.route('/api/command', methods=['POST'])
def execute_command():
    data = request.get_json()
    cmd = data.get('cmd', '').strip()
    
    # قائمة الأوامر المسموحة (لأمان نسبي)
    allowed_commands = ['sysinfo', 'scan', 'exec', 'telegram', 'download', 'crypto']
    
    if cmd not in allowed_commands:
        return jsonify({'success': False, 'message': 'أمر غير مسموح'})
    
    # تنفيذ كل أمر
    results = {
        'sysinfo': f"🖥️ النظام: {os.name}\n🧠 المعالج: {os.cpu_count()} نواة\n💾 الذاكرة: {os.system('free -h 2>/dev/null || echo "غير متاح"')}",
        'scan': "🔍 فحص الشبكة...\n✅ المنافذ المفتوحة: 22, 80, 443, 8080\n⚠️ تم العثور على ثغرة في المنفذ 22",
        'exec': "💻 تنفيذ الأمر: whoami\n👤 المستخدم: root\n✅ تم التنفيذ بنجاح.",
        'telegram': "📡 جارٍ استهداف مجموعة تيليجرام...\n✅ تم إرسال رسائل جماعية إلى 1,234 مستخدم.",
        'download': "⬇️ تحميل الملف: payload.exe\n📦 الحجم: 2.4MB\n✅ اكتمل التحميل.",
        'crypto': f"🔐 تشفير الملفات...\n✅ تم تشفير 47 ملفًا بنجاح.\n🔑 المفتاح: {''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}"
    }
    
    return jsonify({
        'success': True,
        'result': results.get(cmd, '✅ تم التنفيذ.'),
        'command': cmd
    })

# ===== نقطة نهاية للحصول على السجل =====
@app.route('/api/logs', methods=['GET'])
def get_logs():
    try:
        with open('logs.json', 'r') as f:
            lines = f.readlines()
            logs = [json.loads(line) for line in lines[-50:]]  # آخر 50 سجل
        return jsonify({'success': True, 'logs': logs})
    except:
        return jsonify({'success': False, 'logs': []})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
