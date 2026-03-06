# Альтернативный деплой через Docker
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py database.py ./

# Не копируем config.py — используем env vars
ENV BOT_TOKEN=""
ENV ADMIN_USER_ID="0"
ENV DATABASE_PATH="/data/design_tasks.db"

CMD ["python", "bot.py"]
