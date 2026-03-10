"""
Design Team Task Management Telegram Bot
"""

import logging
import re
from datetime import datetime
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

from database import Database, Task, TaskStatus, UserRole

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
DESCRIPTION, DEADLINE, BRIEF = range(3)  # newtask
EDIT_TASK_ID, EDIT_FIELD = range(10, 12)  # edittask

# Load config — env vars first (for Render/cloud), then config.py
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))

if not BOT_TOKEN:
    try:
        from config import BOT_TOKEN as _t, ADMIN_USER_ID as _a
        BOT_TOKEN = _t
        ADMIN_USER_ID = _a
    except ImportError:
        BOT_TOKEN = "YOUR_BOT_TOKEN"
        logger.warning("Set BOT_TOKEN env var or create config.py")

db = Database()


# ============== Helper functions ==============

def format_task(task: Task, include_result: bool = False) -> str:
    deadline_str = task.deadline.strftime("%d.%m.%Y %H:%M") if hasattr(task.deadline, "strftime") else str(task.deadline)
    text = (
        f"📋 *Задача #{task.id}*\n"
        f"*{task.title}*\n\n"
        f"{task.description}\n\n"
        f"📎 Описания: {task.brief_link}\n"
        f"⏰ Дедлайн: {deadline_str}\n"
        f"📊 Статус: {task.status.value}\n"
    )
    if task.assignee_id and task.status != TaskStatus.NEW:
        assignee = db.get_user_by_id(task.assignee_id)
        assignee_name = assignee.full_name if assignee else "Unknown"
        text += f"👤 Исполнитель: {assignee_name}\n"
    if include_result and task.result_link:
        ft, _ = parse_result_file(task.result_link)
        res_label = "Прикреплено изображение" if ft == "photo" else "Прикреплён документ" if ft == "document" else task.result_link
        text += f"\n🎨 Результат: {res_label}\n"
    if task.revision_comment:
        text += f"\n💬 Комментарий: {task.revision_comment}\n"
    return text


def format_task_short(task: Task) -> str:
    deadline_str = task.deadline.strftime("%d.%m.%Y %H:%M") if hasattr(task.deadline, "strftime") else str(task.deadline)
    return f"#{task.id} — {task.title} | {task.status.value} | {deadline_str}"


async def notify_users(context: ContextTypes.DEFAULT_TYPE, telegram_ids: list[int], message: str) -> None:
    """Send private notification to users."""
    for uid in telegram_ids:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=message,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.warning(f"Не могу отправить сообщение пользователю {uid}: {e}")


def parse_result_file(result_link: Optional[str]) -> tuple[str | None, str | None]:
    """Parse result_link: returns (type, file_id) for PHOTO:/DOC: or legacy format, else (None, None)."""
    if not result_link or ":" not in result_link:
        return None, None
    prefix, _, rest = result_link.partition(":")
    if prefix == "PHOTO" and rest:
        return "photo", rest.strip()
    if prefix == "DOC" and rest:
        return "document", rest.strip()
    if "file_id:" in result_link.lower():
        fid = result_link.split("file_id:", 1)[-1].strip().split()[0].rstrip("…")
        if fid and len(fid) > 15:
            return "photo", fid
    return None, None


# ============== Role checks ==============

def require_role(*roles: UserRole):
    def decorator(func):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user = update.effective_user
            if not user:
                return
            role = db.get_user_role(user.id)
            if role not in roles:
                await update.message.reply_text(
                    "❌ Куда собрался, только крутые ребята так могут "
                )
                return
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator


def require_role_callback(*roles: UserRole):
    def decorator(func):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user = update.callback_query.from_user
            if not user:
                return
            role = db.get_user_role(user.id)
            if role not in roles:
                await update.callback_query.answer("❌ Куда собрался, только крутые ребята так могут", show_alert=True)
                return
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator


# ============== Start & Help ==============

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    db.ensure_user(user.id, user.username, user.full_name or "Неизвестный пользователь")
    role = db.get_user_role(user.id)
    role_text = role.value.replace("_", " ").title() if role else "Не назначено"
    await update.message.reply_text(
        f"👋 Привет мой юный друг, {user.first_name}!\n\n"
        f"На этой тусовке ты *{role_text}*\n\n"
        "Используй /help чтобы посмотреть доступные функции",
        parse_mode="Markdown"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    role = db.get_user_role(update.effective_user.id) if update.effective_user else None
    text = "📖 *Что я умею:*\n\n"
    text += "/start — Начни меня\n"
    text += "/help — Это помощь если забыл\n"
    text += "/mytasks — Можешь посмотреть свои задачки\n"
    text += "/opentasks — Можешь посмотреть новые задачки (их еще не взяли)\n"
    if role == UserRole.SMM_MANAGER:
        text += "\n*Глашатай (СММ):*\n"
        text += "/newtask — Создать задачку\n"
        text += "/edittask — Редактировать задачку (если её ещё не взяли)\n"
        text += "/mytasks — Все созданные задачи\n"
        text += "/canceltask — Отменить задачку (если её ещё не взяли)\n"
    elif role == UserRole.DESIGNER:
        text += "\n*Рисовальшик (Дезигнер):*\n"
        text += "/opentasks — Взять задачку (кнопка ниже)\n"
        text += "/done — Сдать задачку на проверку\n"
    elif role == UserRole.HEAD_OF_DESIGN:
        text += "\n*Самый главный:*\n"
        text += "/newtask — Создать задачку\n"
        text += "/opentasks — Взять задачку (как дизайнер)\n"
        text += "/done — Сдать задачку на проверку\n"
        text += "/review — Задачки на согласование\n"
    if update.effective_user and update.effective_user.id == ADMIN_USER_ID:
        text += "\n*Админ:*\n"
        text += "/users — Список пользователей (username — роль)\n"
        text += "/setrole — Назначить роль\n"
    await update.message.reply_text(text, parse_mode="Markdown")


# ============== New Task (SMM) — Conversation ==============

async def newtask_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    role = db.get_user_role(update.effective_user.id)
    if role not in (UserRole.SMM_MANAGER, UserRole.HEAD_OF_DESIGN):
        await update.message.reply_text("❌ Только СММ и глава дизайна могут создавать задачи")
        return ConversationHandler.END
    await update.message.reply_text(
        "📝 *Сделать задачу*\n\n"
        "Отправить задачу *заголовок и описание* (одним сообщением):",
        parse_mode="Markdown"
    )
    return DESCRIPTION


async def newtask_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["task_description"] = update.message.text
    await update.message.reply_text(
        "⏰ Установить *дедлайн* в формате:\n"
        "`ДД.ММ.ГГГГ ЧЧ:ММ`\n\n"
        "Например: 15.03.2025 18:00",
        parse_mode="Markdown"
    )
    return DEADLINE


async def newtask_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    match = re.match(r"(\d{2})\.(\d{2})\.(\d{4})\s+(\d{1,2}):(\d{2})", text)
    if not match:
        await update.message.reply_text(
            "❌ Неправильный формат. Используй ДД.ММ.ГГГГ ЧЧ:ММ\n"
            "Например: 15.03.2025 18:00"
        )
        return DEADLINE
    d, m, y, h, mi = map(int, match.groups())
    try:
        deadline = datetime(y, m, d, h, mi)
        if deadline <= datetime.now():
            await update.message.reply_text("❌ Я знаю что в дизайне дедлайн это вчера, но все же...")
            return DEADLINE
    except ValueError:
        await update.message.reply_text("❌ Нет такой даты")
        return DEADLINE
    context.user_data["task_deadline"] = deadline
    await update.message.reply_text(
        "📎 Отправь *ТЗ* — ссылка/изобрадение или текст:",
        parse_mode="Markdown"
    )
    return BRIEF


async def newtask_brief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    brief = update.message.text or ""
    if update.message.photo:
        # Use file_id if photo sent
        brief = f"[Photo] file_id: {update.message.photo[-1].file_id}"
    elif update.message.document:
        brief = f"[Document] {update.message.document.file_name or 'file'}"
    if not brief.strip():
        brief = "Без четкого ТЗ (результат сами знаете)"
    desc = context.user_data.get("task_description", "")
    deadline = context.user_data.get("task_deadline")
    if not desc or not deadline:
        await update.message.reply_text("❌ Время вышло. Начни снова введя /newtask")
        return ConversationHandler.END
    user = update.effective_user
    creator_db_id = db.ensure_user(user.id, user.username, user.full_name or "Неизвестный пользователь")
    task_id = db.create_task(
        title=desc[:50] + ("..." if len(desc) > 50 else ""),
        description=desc,
        deadline=deadline,
        brief_link=brief[:500],
        creator_id=creator_db_id
    )
    task = db.get_task(task_id)
    context.user_data.clear()
    await update.message.reply_text(
        f"✅ Задача #{task_id} создана!\n\n{format_task(task)}",
        parse_mode="Markdown"
    )
    # Notify designers and head
    users = db.get_all_designers_and_head()
    telegram_ids = [u.telegram_id for u in users]
    deadline_str = deadline.strftime("%d.%m.%Y %H:%M")
    msg = (
        f"🆕 *Опа новая задача #{task_id}*\n\n"
        f"{desc[:200]}...\n\n"
        f"⏰ Дедлайн: {deadline_str}\n\n"
        "Используй /opentasks чтобы взять ее себе"
    )
    await notify_users(context, telegram_ids, msg)
    return ConversationHandler.END


async def newtask_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Задачи не будет...")
    return ConversationHandler.END


# ============== Open tasks (Designers) ==============

async def cmd_opentasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    tasks = db.get_open_tasks()
    if not tasks:
        await update.message.reply_text("📭 Пока новых задач нет")
        return
    text = "📋 *Открыть задачи* (по дедлайну):\n\n"
    keyboard = []
    for t in tasks:
        text += f"{format_task_short(t)}\n"
        keyboard.append([InlineKeyboardButton(f"Взять #{t.id}", callback_data=f"take_{t.id}")])
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def callback_take_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    role = db.get_user_role(query.from_user.id)
    if role not in (UserRole.DESIGNER, UserRole.HEAD_OF_DESIGN):
        await query.edit_message_text("❌ Только дизайнеры и руководитель дизайна могут брать задачи")
        return
    task_id = int(query.data.split("_")[1])
    task = db.get_task(task_id)
    if not task:
        await query.edit_message_text("Нет такой задачи")
        return
    if task.status != TaskStatus.NEW:
        await query.edit_message_text(f"Задачу #{task_id} уже взяли 😭")
        return
    user = db.get_user_by_telegram_id(query.from_user.id)
    if not user:
        db.ensure_user(query.from_user.id, query.from_user.username, query.from_user.full_name or "Неизвестный пользователь")
        user = db.get_user_by_telegram_id(query.from_user.id)
    db.assign_task(task_id, user.id)
    task = db.get_task(task_id)
    await query.edit_message_text(
        f"✅ Ты взял себе задачу #{task_id}!\n\n{format_task(task)}\n\n"
        "Когда закончищь, напиши /done или кликни ниже",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Отправить свой шедевр", callback_data=f"submit_{task_id}")
        ]])
    )
    # Notify SMM and Head
    creator_tg = db.get_creator_telegram_id(task.creator_id)
    heads = db.get_users_by_role(UserRole.HEAD_OF_DESIGN)
    smms = db.get_users_by_role(UserRole.SMM_MANAGER)
    to_notify = [creator_tg] if creator_tg else []
    to_notify += [h.telegram_id for h in heads]
    to_notify += [s.telegram_id for s in smms if creator_tg != s.telegram_id]
    to_notify = list(set(to_notify))
    msg = f"📌 Задача #{task_id} сделана *{query.from_user.full_name}*"
    await notify_users(context, to_notify, msg)


# ============== Submit result (Designer) ==============

async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    role = db.get_user_role(update.effective_user.id)
    if role not in (UserRole.DESIGNER, UserRole.HEAD_OF_DESIGN):
        await update.message.reply_text("❌ Только дизайнеры и руководитель дизайна могут сдавать задачи")
        return
    args = context.args
    if not args:
        u = db.get_user_by_telegram_id(update.effective_user.id)
        if not u:
            await update.message.reply_text("Начни используя /start сначала.")
            return
        tasks = db.get_tasks(assignee_id=u.id)
        in_progress = [t for t in tasks if t.status in (TaskStatus.IN_PROGRESS, TaskStatus.REVISION)]
        if not in_progress:
            await update.message.reply_text(
                "Нет задач для отправки. Посмотри: /done <task_id>\n"
                "Например: /done 42"
            )
            return
        keyboard = [[InlineKeyboardButton(f"Сдать #{t.id}", callback_data=f"submit_{t.id}")] for t in in_progress]
        await update.message.reply_text(
            "Выбери, что хочешь отправить:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    try:
        task_id = int(args[0])
    except ValueError:
        await update.message.reply_text("Usage: /done 42")
        return
    context.user_data["awaiting_result_task"] = task_id
    await update.message.reply_text(
        f"📎 Прикрепи *результат* задачи #{task_id} — изображение, документ или ссылку:",
        parse_mode="Markdown"
    )


async def receive_result_or_revision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle result upload (designer) or revision comment (head) - only when in that flow."""
    task_id = context.user_data.get("awaiting_result_task")
    if task_id:
        await _process_result(update, context, task_id)
        return
    task_id = context.user_data.get("revision_task_id")
    if task_id:
        await _process_revision_comment(update, context, task_id)
        return


async def _process_result(update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: int) -> None:
    result = update.message.text or ""
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        result = f"PHOTO:{file_id}"
    elif update.message.document:
        file_id = update.message.document.file_id
        result = f"DOC:{file_id}"
    if not result.strip():
        await update.message.reply_text("Я ж попросил: изображение, документ или ссылку")
        return
    context.user_data.pop("awaiting_result_task", None)
    task = db.get_task(task_id)
    if not task:
        await update.message.reply_text("Нет такой задачи")
        return
    user = db.get_user_by_telegram_id(update.effective_user.id)
    if not user or task.assignee_id != user.id:
        await update.message.reply_text("Это не твоя задача")
        return
    if task.status not in (TaskStatus.IN_PROGRESS, TaskStatus.REVISION):
        await update.message.reply_text("Задача не в процессе и не на рассмотрении.")
        return
    db.submit_for_review(task_id, result[:600])
    task = db.get_task(task_id)
    await update.message.reply_text(
        f"✅ Задача #{task_id} отправлена на согласование!\n\n{format_task(task)}",
        parse_mode="Markdown"
    )
    # Notify Head
    heads = db.get_users_by_role(UserRole.HEAD_OF_DESIGN)
    msg = f"🔍 *Задача #{task_id}* готова к проверке.\nИспользуй /review чтобы посмотреть."
    for h in heads:
        try:
            await context.bot.send_message(chat_id=h.telegram_id, text=msg, parse_mode="Markdown")
            file_type, file_id = parse_result_file(result)
            if file_type == "photo" and file_id:
                await context.bot.send_photo(chat_id=h.telegram_id, photo=file_id, caption=f"Задача #{task_id}")
            elif file_type == "document" and file_id:
                await context.bot.send_document(chat_id=h.telegram_id, document=file_id, caption=f"Задача #{task_id}")
        except Exception as e:
            logger.warning(f"Не удалось уведомить Head {h.telegram_id}: {e}")


async def _process_revision_comment(update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: int) -> None:
    comment = update.message.text or ""
    if not comment.strip():
        await update.message.reply_text("Что скажете, мой госоподин?")
        return
    context.user_data.pop("revision_task_id", None)
    task = db.get_task(task_id)
    if not task or task.status != TaskStatus.ON_REVIEW:
        await update.message.reply_text("Задача не найдена или уже отсмотрена")
        return
    db.request_revision(task_id, comment[:500])
    task = db.get_task(task_id)
    await update.message.reply_text(
        f"🔄 Правки направлены для задачи #{task_id}.\n\n{format_task(task)}",
        parse_mode="Markdown"
    )
    assignee_tg = db.get_assignee_telegram_id(task.assignee_id) if task.assignee_id else None
    if assignee_tg:
        msg = (
            f"🔄 *Задача #{task_id}* — опа есть правочки\n\n"
            f"Правки: {comment}"
        )
        await notify_users(context, [assignee_tg], msg)


async def callback_submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split("_")[1])
    context.user_data["awaiting_result_task"] = task_id
    await query.edit_message_text(
        f"📎 Прикрепи результат задачи #{task_id} — изображение, документ или ссылку:"
    )


# ============== Review (Head of Design) ==============

async def cmd_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    role = db.get_user_role(update.effective_user.id)
    if role != UserRole.HEAD_OF_DESIGN:
        await update.message.reply_text("❌ Только глава дизайна может вносить правки")
        return
    tasks = db.get_tasks(status=TaskStatus.ON_REVIEW)
    if not tasks:
        await update.message.reply_text("📭 Нет задач на согласовании")
        return
    for t in tasks:
        file_type, file_id = parse_result_file(t.result_link)
        if file_type == "photo" and file_id:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=file_id,
                caption=format_task(t, include_result=False) + "\n\n🎨 Результат — выше",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Все супер!", callback_data=f"approve_{t.id}"),
                    InlineKeyboardButton("🔄 Правки", callback_data=f"revision_{t.id}")
                ]])
            )
        elif file_type == "document" and file_id:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=file_id,
                caption=format_task(t, include_result=False) + "\n\n🎨 Результат — выше",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Все супер!", callback_data=f"approve_{t.id}"),
                    InlineKeyboardButton("🔄 Правки", callback_data=f"revision_{t.id}")
                ]])
            )
        else:
            await update.message.reply_text(
                format_task(t, include_result=True),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Все супер!", callback_data=f"approve_{t.id}"),
                    InlineKeyboardButton("🔄 Правки", callback_data=f"revision_{t.id}")
                ]])
            )


async def callback_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    role = db.get_user_role(query.from_user.id)
    if role != UserRole.HEAD_OF_DESIGN:
        await query.edit_message_text("❌ Нет доступа")
        return
    task_id = int(query.data.split("_")[1])
    task = db.get_task(task_id)
    if not task or task.status != TaskStatus.ON_REVIEW:
        await query.edit_message_text("Задача не найдена или уже отсмотрена")
        return
    result_link = task.result_link
    db.approve_task(task_id)
    task = db.get_task(task_id)
    try:
        await query.edit_message_caption(caption=f"✅ Задача #{task_id} согласована!")
    except Exception:
        try:
            await query.edit_message_text(f"✅ Задача #{task_id} согласована!")
        except Exception:
            pass
    # Отправить файл SMM и уведомить дизайнера
    creator_tg = db.get_creator_telegram_id(task.creator_id)
    assignee_tg = db.get_assignee_telegram_id(task.assignee_id) if task.assignee_id else None
    file_type, file_id = parse_result_file(result_link)
    if creator_tg and file_type and file_id:
        try:
            if file_type == "photo":
                await context.bot.send_photo(
                    chat_id=creator_tg,
                    photo=file_id,
                    caption=f"✅ Согласованный макет по задаче #{task_id}\n\n{task.title}"
                )
            elif file_type == "document":
                await context.bot.send_document(
                    chat_id=creator_tg,
                    document=file_id,
                    caption=f"✅ Согласованный макет по задаче #{task_id}\n\n{task.title}"
                )
        except Exception as e:
            logger.warning(f"Не удалось отправить файл SMM: {e}")
    msg = f"✅ *Задача #{task_id}* согласована и отправлена SMM!"
    await notify_users(context, [t for t in [creator_tg, assignee_tg] if t], msg)


async def callback_revision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    role = db.get_user_role(query.from_user.id)
    if role != UserRole.HEAD_OF_DESIGN:
        await query.edit_message_text("❌ Нет доступа")
        return
    task_id = int(query.data.split("_")[1])
    context.user_data["revision_task_id"] = task_id
    await query.edit_message_text(
        f"💬 Оставь свои *правки* к задаче #{task_id}:",
        parse_mode="Markdown"
    )


# ============== My tasks ==============

async def cmd_mytasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    u = db.get_user_by_telegram_id(user.id)
    if not u:
        db.ensure_user(user.id, user.username, user.full_name or "Неизвестный пользователь")
        u = db.get_user_by_telegram_id(user.id)
    role = db.get_user_role(user.id)
    status_filter = None
    _status_map = {"новые": TaskStatus.NEW, "в процессе": TaskStatus.IN_PROGRESS, "в процессе": TaskStatus.IN_PROGRESS,
                   "на проверке": TaskStatus.ON_REVIEW, "отправлена на проверку": TaskStatus.ON_REVIEW, "проверка": TaskStatus.REVISION,
                   "сделано": TaskStatus.DONE, "отклонена": TaskStatus.CANCELLED}
    if context.args:
        key = context.args[0].lower().replace(" ", "_").replace("-", "_")
        status_filter = _status_map.get(key)
    if role == UserRole.SMM_MANAGER:
        tasks = db.get_tasks(status=status_filter)
    elif role == UserRole.DESIGNER:
        tasks = db.get_tasks(assignee_id=u.id, status=status_filter)
    elif role == UserRole.HEAD_OF_DESIGN:
        tasks = db.get_tasks(status=status_filter)
    else:
        await update.message.reply_text("Чтобы изменить свою роль, свяжись с главным")
        return
    if not tasks:
        await update.message.reply_text("📭 Задач нет (невозможно)")
        return
    text = "📋 *Твои задачи:*\n\n"
    for t in tasks:
        text += format_task_short(t) + "\n"
        if (role == UserRole.DESIGNER or (role == UserRole.HEAD_OF_DESIGN and t.assignee_id == u.id)) and t.status in (TaskStatus.IN_PROGRESS, TaskStatus.REVISION):
            text += f"   /done {t.id}\n"
    text += "\n_Filter: /mytasks новые | в процессе | отправлено на проверку | проверка | сделано_"
    await update.message.reply_text(text, parse_mode="Markdown")


# ============== Edit task (SMM) ==============

async def edittask_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    role = db.get_user_role(update.effective_user.id)
    if role != UserRole.SMM_MANAGER:
        await update.message.reply_text("❌ Только СММ может редактировать задачу")
        return ConversationHandler.END
    args = context.args
    if not args:
        await update.message.reply_text(
            "Используй: /edittask <task_id>\n"
            "Пример: /edittask 42"
        )
        return ConversationHandler.END
    try:
        task_id = int(args[0])
    except ValueError:
        await update.message.reply_text("Неверный номер задачи")
        return ConversationHandler.END
    task = db.get_task(task_id)
    if not task:
        await update.message.reply_text("Задача не найдена")
        return ConversationHandler.END
    if task.status != TaskStatus.NEW:
        await update.message.reply_text("Можно редактировать только те задачи, которые не взяли")
        return ConversationHandler.END
    u = db.get_user_by_telegram_id(update.effective_user.id)
    if task.creator_id != u.id:
        await update.message.reply_text("Вы можете редактировать только собственные задачи")
        return ConversationHandler.END
    context.user_data["edittask_id"] = task_id
    await update.message.reply_text(
        f"Редактирование #{task_id}. Отправь одно из этого:\n\n"
        "`заголовок Новый заголовок`\n"
        "`описание Новое описание`\n"
        "`дедлайн ДД.ММ.ГГГГ ЧЧ:ММ`\n"
        "`ТЗ Новая ссылка или текст`\n\n"
        "Или введи /cancel для отмены.",
        parse_mode="Markdown"
    )
    return EDIT_FIELD


async def edittask_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task_id = context.user_data.get("edittask_id")
    if not task_id:
        return ConversationHandler.END
    text = update.message.text.strip()
    if not text or " " not in text:
        await update.message.reply_text(
            "Отправь: что поменять и на что поменять\nНапример: дедлайн 20.03.2025 18:00"
        )
        return EDIT_FIELD
    field, value = text.split(" ", 1)
    field = field.lower()
    task = db.get_task(task_id)
    if not task or task.status != TaskStatus.NEW:
        context.user_data.pop("edittask_id", None)
        await update.message.reply_text("Задачу больше нельзя менять.")
        return ConversationHandler.END
    if field == "заголовок":
        db.update_task_details(task_id, title=value[:100])
        await update.message.reply_text(f"✅ Заголовок обновлен.")
    elif field == "описание":
        db.update_task_details(task_id, description=value)
        await update.message.reply_text("✅ Описание обновлено.")
    elif field == "дедлайн":
        match = re.match(r"(\d{2})\.(\d{2})\.(\d{4})\s+(\d{1,2}):(\d{2})", value)
        if match:
            d, m, y, h, mi = map(int, match.groups())
            try:
                deadline = datetime(y, m, d, h, mi)
                db.update_task_details(task_id, deadline=deadline)
                await update.message.reply_text("✅ Дедлайн обновлен.")
            except ValueError:
                await update.message.reply_text("Неверная дата")
        else:
            await update.message.reply_text("Используй формат: ДД.ММ.ГГГГ ЧЧ:ММ")
    elif field == "ТЗ":
        db.update_task_details(task_id, brief_link=value[:500])
        await update.message.reply_text("✅ ТЗ обновлено")
    else:
        await update.message.reply_text("Непонятно что указано. Используй: заголовок, описание, дедлайн, ТЗ")
        return EDIT_FIELD
    await update.message.reply_text("Укажи, что еще нужно обновить или напиши /cancel для завершения")
    return EDIT_FIELD


async def edittask_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("edittask_id", None)
    await update.message.reply_text("Редактирование закончено")
    return ConversationHandler.END


# ============== Cancel task (SMM) ==============

async def cmd_canceltask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    role = db.get_user_role(update.effective_user.id)
    if role != UserRole.SMM_MANAGER:
        await update.message.reply_text("❌ Только СММ может отменять задачи")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Используй: /canceltask <task_id>\nНапример: /canceltask 42")
        return
    try:
        task_id = int(args[0])
    except ValueError:
        await update.message.reply_text("Используй: /canceltask 42")
        return
    task = db.get_task(task_id)
    if not task:
        await update.message.reply_text("Задача не найдена")
        return
    u = db.get_user_by_telegram_id(update.effective_user.id)
    if task.creator_id != u.id:
        await update.message.reply_text("Можно отменять только свои задачи")
        return
    if db.cancel_task(task_id):
        await update.message.reply_text(f"✅ Задача #{task_id} отменена.")
    else:
        await update.message.reply_text("❌ Можно отменять только те задачи, которые отменены")


# ============== Deadline notifications (Job) ==============

async def check_deadlines(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Проверяет дедлайны и шлёт уведомления за 3ч и в момент дедлайна."""
    now = datetime.now()
    tasks = db.get_tasks_for_deadline_check()
    for task in tasks:
        if not task.assignee_id:
            continue
        assignee_tg = db.get_assignee_telegram_id(task.assignee_id)
        if not assignee_tg:
            continue
        deadline = task.deadline
        if isinstance(deadline, str):
            try:
                deadline = datetime.fromisoformat(deadline)
            except (ValueError, TypeError):
                continue
        delta = deadline - now
        delta_sec = delta.total_seconds()
        # За 3 часа (окно 3ч — 2ч45м, проверка каждые 10 мин)
        if 10800 >= delta_sec > 9900 and not db.deadline_notification_sent(task.id, "3h_before"):
            try:
                await context.bot.send_message(
                    chat_id=assignee_tg,
                    text=f"⏰ *Напоминание:* до дедлайна задачи #{task.id} (*{task.title}*) осталось ~3 часа!\n"
                         f"Дедлайн: {deadline.strftime('%d.%m.%Y %H:%M')}",
                    parse_mode="Markdown"
                )
                db.mark_deadline_notification_sent(task.id, "3h_before")
            except Exception as e:
                logger.warning(f"Deadline 3h notify failed task {task.id}: {e}")
        # В момент дедлайна (от 2 мин до дедлайна до 10 мин после)
        elif -600 <= delta_sec <= 120 and not db.deadline_notification_sent(task.id, "deadline"):
            try:
                await context.bot.send_message(
                    chat_id=assignee_tg,
                    text=f"🔔 *Дедлайн!* Задача #{task.id} (*{task.title}*) — время вышло.\n"
                         f"Дедлайн был: {deadline.strftime('%d.%m.%Y %H:%M')}",
                    parse_mode="Markdown"
                )
                db.mark_deadline_notification_sent(task.id, "deadline")
            except Exception as e:
                logger.warning(f"Deadline at-time notify failed task {task.id}: {e}")


# ============== Set role (Admin) ==============

async def cmd_setrole(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Только админ")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Используй: /setrole <user_id> <role>\n"
            "Роли: CMM, Дизайнер, Глава дизайна\n"
            "Пример: /setrole 123456789 designer"
        )
        return
    _role_map = {"smm": UserRole.SMM_MANAGER, "cmm": UserRole.SMM_MANAGER, "смм": UserRole.SMM_MANAGER,
                 "designer": UserRole.DESIGNER, "дизайнер": UserRole.DESIGNER,
                 "head": UserRole.HEAD_OF_DESIGN, "глава": UserRole.HEAD_OF_DESIGN}
    try:
        telegram_id = int(args[0])
        role_str = args[1].lower().strip()
        role = _role_map.get(role_str) or UserRole(role_str)
    except (ValueError, KeyError):
        await update.message.reply_text("Роли: smm/cmm, designer, head/глава")
        return
    db.ensure_user(telegram_id, None, "Unknown")
    db.set_user_role(telegram_id, role)
    await update.message.reply_text(f"✅ Role {role.value} assigned to user {telegram_id}.")


async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ: список пользователей в формате username — role."""
    if update.effective_user and update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Только админ")
        return
    users = db.get_all_users()
    if not users:
        await update.message.reply_text("Пользователей пока нет.")
        return
    lines = []
    for u in users:
        username = f"@{u.username}" if u.username else str(u.telegram_id)
        role = u.role.value if u.role else "—"
        lines.append(f"{username} — {role}")
    await update.message.reply_text("👥 *Пользователи:*\n\n" + "\n".join(lines), parse_mode="Markdown")


# ============== Main ==============

def main() -> None:
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(False)  # Required for ConversationHandler
        .build()
    )

    # Conversation for new task
    newtask_conv = ConversationHandler(
        entry_points=[CommandHandler("newtask", newtask_start)],
        states={
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, newtask_description)],
            DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, newtask_deadline)],
            BRIEF: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, newtask_brief),
                MessageHandler(filters.PHOTO, newtask_brief),
                MessageHandler(filters.Document.ALL, newtask_brief),
            ],
        },
        fallbacks=[CommandHandler("cancel", newtask_cancel)],
    )
    application.add_handler(newtask_conv)

    # Conversation for edit task
    edittask_conv = ConversationHandler(
        entry_points=[CommandHandler("edittask", edittask_start)],
        states={
            EDIT_FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, edittask_field)],
        },
        fallbacks=[CommandHandler("cancel", edittask_cancel)],
    )
    application.add_handler(edittask_conv)

    # Result submission (designer) and revision comment (head) — only when in flow
    application.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND,
        receive_result_or_revision
    ))

    # Commands
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("opentasks", cmd_opentasks))
    application.add_handler(CommandHandler("done", cmd_done))
    application.add_handler(CommandHandler("review", cmd_review))
    application.add_handler(CommandHandler("mytasks", cmd_mytasks))
    application.add_handler(CommandHandler("canceltask", cmd_canceltask))
    application.add_handler(CommandHandler("setrole", cmd_setrole))
    application.add_handler(CommandHandler("users", cmd_users))

    # Дедлайны: проверка каждые 10 минут (требует python-telegram-bot[job-queue])
    if application.job_queue:
        application.job_queue.run_repeating(check_deadlines, interval=600, first=60)
    else:
        logger.warning("JobQueue не доступен. Установите: pip install 'python-telegram-bot[job-queue]'")

    # Callbacks
    application.add_handler(CallbackQueryHandler(callback_take_task, pattern=r"^take_\d+$"))
    application.add_handler(CallbackQueryHandler(callback_submit, pattern=r"^submit_\d+$"))
    application.add_handler(CallbackQueryHandler(callback_approve, pattern=r"^approve_\d+$"))
    application.add_handler(CallbackQueryHandler(callback_revision, pattern=r"^revision_\d+$"))

    # Webhook mode для Render (Web Service, бесплатный тариф)
    port = os.environ.get("PORT")
    webhook_base = os.environ.get("WEBHOOK_URL", "").rstrip("/")

    if port and webhook_base and BOT_TOKEN != "YOUR_BOT_TOKEN":
        import asyncio
        import signal
        from aiohttp import web

        webhook_url = f"{webhook_base}/webhook"

        async def handle_health(_: web.Request) -> web.Response:
            return web.Response(text="OK", status=200)

        async def handle_webhook(request: web.Request) -> web.Response:
            try:
                data = await request.json()
                update = Update.de_json(data, application.bot)
                if update:
                    await application.update_queue.put(update)
            except Exception as e:
                logger.exception("Webhook error: %s", e)
            return web.Response(status=200)

        async def run_webhook_server() -> None:
            await application.initialize()
            await application.bot.set_webhook(webhook_url, allowed_updates=Update.ALL_TYPES)
            await application.start()

            app = web.Application()
            app.router.add_get("/", handle_health)
            app.router.add_post("/webhook", handle_webhook)

            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", int(port))
            await site.start()
            logger.info("Webhook server started: %s", webhook_url)

            stop = asyncio.Event()
            try:
                loop = asyncio.get_running_loop()
                for sig in (signal.SIGTERM, signal.SIGINT):
                    loop.add_signal_handler(sig, stop.set)
            except (NotImplementedError, OSError):
                pass
            await stop.wait()
            await site.stop()
            await runner.cleanup()
            await application.stop()
            await application.shutdown()

        asyncio.run(run_webhook_server())
    else:
        # Локально: polling
        logger.info("Starting polling mode")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
