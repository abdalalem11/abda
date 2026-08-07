FROM python:3.11-slim

WORKDIR /app

# تثبيت الاعتماديات
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# نسخ الكود
COPY . .

# المنفذ
EXPOSE 8080

# تشغيل التطبيق
CMD ["gunicorn", "app:flask_app", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "2"]
