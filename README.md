# Design Team Task Management Bot

A Telegram bot that replaces chaotic chat communication with a structured workflow for design teams. SMM managers create tasks, designers execute them, and the Head of Design reviews and approves.

## Features

- **SMM Manager**: Create tasks with description, deadline, and brief; view created tasks; cancel open tasks
- **Designer**: View and take open tasks; upload results for review; track assigned tasks
- **Head of Design**: Review submitted work; approve or request revisions with comments
- **Notifications**: All team members receive real-time updates on task status changes

## Setup

### 1. Create a bot

1. Open [@BotFather](https://t.me/BotFather) in Telegram
2. Send `/newbot` and follow the prompts
3. Copy the bot token

### 2. Install dependencies

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 3. Configure

```bash
cp config.example.py config.py
```

Edit `config.py`:
- Set `BOT_TOKEN` to your bot token
- Set `ADMIN_USER_ID` to your Telegram user ID (get it from [@userinfobot](https://t.me/userinfobot))

### 4. Run

```bash
.venv/bin/python bot.py
```

### 5. Assign roles

Start a chat with your bot and send `/start`. Then, as admin, assign roles:

```
/setrole <telegram_user_id> smm_manager
/setrole <telegram_user_id> designer
/setrole <telegram_user_id> head_of_design
```

Get user IDs from [@userinfobot](https://t.me/userinfobot).

## Adding the bot to your team chat

1. Add the bot to your design team group as a member
2. Team members should **start a private chat** with the bot (`/start`) to receive notifications and use commands
3. Notifications are sent privately; tasks are managed via direct bot conversation

## Workflow

1. **SMM** sends `/newtask` → enters description → deadline (DD.MM.YYYY HH:MM) → brief (link or file)
2. **Designers** get notified → `/opentasks` → click "Take" on a task
3. **Designer** completes work → `/done` or "Submit result" → uploads image/link/document
4. **Head of Design** gets notified → `/review` → Approve or Request revision with comment
5. If revision: **Designer** re-uploads via `/done`
6. If approved: **SMM** and **Designer** get notified

## Commands

| Command | Role | Description |
|---------|------|-------------|
| `/start` | All | Register and see your role |
| `/help` | All | List available commands |
| `/mytasks` | All | View your tasks |
| `/newtask` | SMM Manager | Create a new task |
| `/edittask <id>` | SMM Manager | Edit task details (only if not taken) |
| `/canceltask <id>` | SMM Manager | Cancel a task (only if not taken) |
| `/opentasks` | Designer | View and take open tasks |
| `/done [id]` | Designer | Submit result for review |
| `/review` | Head of Design | View and process tasks on review |
| `/setrole <user_id> <role>` | Admin | Assign role to user |

## Data

Tasks and users are stored in `design_tasks.db` (SQLite). Backup this file to preserve data.

## License

MIT
