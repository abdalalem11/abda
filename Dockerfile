FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# تشغيل البوت مباشرة (بدون gunicorn)
CMD ["python", "app.py"]
