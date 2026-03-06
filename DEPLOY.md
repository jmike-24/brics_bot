# Деплой бота на Render (бесплатно)

## Быстрый старт

### 1. Репозиторий

Загрузи проект в GitHub (или GitLab/Bitbucket).

### 2. Создание Web Service на Render

1. [render.com](https://render.com) → **Dashboard** → **New** → **Web Service**
2. Подключи репозиторий
3. Настройки:
   - **Name:** `design-task-bot` (или любой — это будет в URL)
   - **Region:** Frankfurt или Oregon
   - **Branch:** main
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bot.py`
   - **Plan:** Free

### 3. Переменные окружения

В **Environment** добавь:

| Key | Value |
|-----|-------|
| `BOT_TOKEN` | Токен от @BotFather |
| `ADMIN_USER_ID` | Твой Telegram ID (@userinfobot) |
| `WEBHOOK_URL` | `https://твой-сервис.onrender.com` *(см. ниже)* |

**WEBHOOK_URL:** после первого деплоя Render покажет URL (например `https://design-task-bot-xyz.onrender.com`). Скопируй его **без** `/webhook` в конце и добавь в переменные. Затем **Manual Deploy** → **Deploy latest commit**.

### 4. Готово

Бот запустится. Напиши ему `/start` в Telegram.

---

## Через render.yaml (Blueprint)

1. **New** → **Blueprint**
2. Подключи репозиторий с `render.yaml`
3. Render создаст Web Service
4. В **Environment** укажи `BOT_TOKEN`, `ADMIN_USER_ID`, `WEBHOOK_URL`

---

## Бесплатный тариф — важное

- **Spin down:** сервис засыпает после ~15 мин без запросов
- **Cold start:** первое сообщение после сна обрабатывается с задержкой ~1 мин
- **750 часов/месяц** бесплатно
- **БД сбрасывается** при каждом деплое (SQLite в памяти)

Для 24/7 без задержек нужен платный план. Для тестов и небольших команд бесплатного хватает.

---

## Проверка

- В логах: `Webhook server started: https://...`
- Открой в браузере `https://твой-сервис.onrender.com` — должно быть `OK`
