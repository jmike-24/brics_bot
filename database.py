"""
Database layer for design task management bot.
Uses SQLite for persistence.
"""

import os
import sqlite3
from datetime import datetime
from typing import Optional
from dataclasses import dataclass
from enum import Enum


class TaskStatus(str, Enum):
    NEW = "новые"
    IN_PROGRESS = "в процессе"
    ON_REVIEW = "отправлено на проверку"
    REVISION = "проверка"
    DONE = "сделано"
    CANCELLED = "Cancelled"


class UserRole(str, Enum):
    SMM_MANAGER = "СММ"
    DESIGNER = "Дизайнер"
    HEAD_OF_DESIGN = "Глава дизайна"


@dataclass
class Task:
    id: int
    title: str
    description: str
    deadline: datetime
    brief_link: str
    creator_id: int
    assignee_id: Optional[int]
    status: TaskStatus
    result_link: Optional[str]
    revision_comment: Optional[str]
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "deadline": self.deadline,
            "brief_link": self.brief_link,
            "creator_id": self.creator_id,
            "assignee_id": self.assignee_id,
            "status": self.status.value,
            "result_link": self.result_link,
            "revision_comment": self.revision_comment,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class User:
    id: int
    telegram_id: int
    username: Optional[str]
    full_name: str
    role: Optional[UserRole]


class Database:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.environ.get("DATABASE_PATH", "design_tasks.db")
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    full_name TEXT NOT NULL,
                    role TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    deadline TIMESTAMP NOT NULL,
                    brief_link TEXT NOT NULL,
                    creator_id INTEGER NOT NULL,
                    assignee_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'New',
                    result_link TEXT,
                    revision_comment TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (creator_id) REFERENCES users(id),
                    FOREIGN KEY (assignee_id) REFERENCES users(id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_deadline ON tasks(deadline)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)")
            conn.commit()

    def ensure_user(self, telegram_id: int, username: Optional[str], full_name: str) -> int:
        """Register or get user, returns user id."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE users SET username = ?, full_name = ? WHERE telegram_id = ?",
                    (username or "", full_name, telegram_id)
                )
                conn.commit()
                return row["id"]
            else:
                cur = conn.execute(
                    "INSERT INTO users (telegram_id, username, full_name) VALUES (?, ?, ?)",
                    (telegram_id, username or "", full_name)
                )
                conn.commit()
                return cur.lastrowid

    def set_user_role(self, telegram_id: int, role: UserRole) -> bool:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE users SET role = ? WHERE telegram_id = ?",
                (role.value, telegram_id)
            )
            conn.commit()
            return conn.total_changes > 0

    def get_user_role(self, telegram_id: int) -> Optional[UserRole]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT role FROM users WHERE telegram_id = ?", (telegram_id,)
            ).fetchone()
            if row and row["role"]:
                try:
                    return UserRole(row["role"])
                except ValueError:
                    return None
            return None

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, telegram_id, username, full_name, role FROM users WHERE id = ?",
                (user_id,)
            ).fetchone()
            if row:
                role = UserRole(row["role"]) if row["role"] else None
                return User(
                    id=row["id"],
                    telegram_id=row["telegram_id"],
                    username=row["username"],
                    full_name=row["full_name"],
                    role=role
                )
            return None

    def get_user_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, telegram_id, username, full_name, role FROM users WHERE telegram_id = ?",
                (telegram_id,)
            ).fetchone()
            if row:
                role = UserRole(row["role"]) if row["role"] else None
                return User(
                    id=row["id"],
                    telegram_id=row["telegram_id"],
                    username=row["username"],
                    full_name=row["full_name"],
                    role=role
                )
            return None

    def get_users_by_role(self, role: UserRole) -> list[User]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT id, telegram_id, username, full_name, role FROM users WHERE role = ?",
                (role.value,)
            ).fetchall()
            return [
                User(
                    id=r["id"],
                    telegram_id=r["telegram_id"],
                    username=r["username"],
                    full_name=r["full_name"],
                    role=UserRole(r["role"])
                )
                for r in rows
            ]

    def get_all_designers_and_head(self) -> list[User]:
        """Returns designers and head of design for notifications."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT id, telegram_id, username, full_name, role FROM users WHERE role IN (?, ?)",
                (UserRole.DESIGNER.value, UserRole.HEAD_OF_DESIGN.value)
            ).fetchall()
            return [
                User(
                    id=r["id"],
                    telegram_id=r["telegram_id"],
                    username=r["username"],
                    full_name=r["full_name"],
                    role=UserRole(r["role"])
                )
                for r in rows
            ]

    def create_task(
        self,
        title: str,
        description: str,
        deadline: datetime,
        brief_link: str,
        creator_id: int
    ) -> int:
        with self._get_connection() as conn:
            cur = conn.execute(
                """INSERT INTO tasks (title, description, deadline, brief_link, creator_id, status)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (title, description, deadline.isoformat(), brief_link, creator_id, TaskStatus.NEW.value)
            )
            conn.commit()
            return cur.lastrowid

    def get_task(self, task_id: int) -> Optional[Task]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row:
                return self._row_to_task(row)
            return None

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        deadline = datetime.fromisoformat(row["deadline"]) if isinstance(row["deadline"], str) else row["deadline"]
        created = datetime.fromisoformat(row["created_at"]) if isinstance(row["created_at"], str) else row["created_at"]
        updated = datetime.fromisoformat(row["updated_at"]) if isinstance(row["updated_at"], str) else row["updated_at"]
        return Task(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            deadline=deadline,
            brief_link=row["brief_link"],
            creator_id=row["creator_id"],
            assignee_id=row["assignee_id"],
            status=TaskStatus(row["status"]),
            result_link=row["result_link"],
            revision_comment=row["revision_comment"],
            created_at=created,
            updated_at=updated
        )

    def update_task_status(
        self,
        task_id: int,
        status: TaskStatus,
        assignee_id: Optional[int] = None,
        result_link: Optional[str] = None,
        revision_comment: Optional[str] = None
    ) -> bool:
        with self._get_connection() as conn:
            updates = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
            params = [status.value]
            if assignee_id is not None:
                updates.append("assignee_id = ?")
                params.append(assignee_id)
            if result_link is not None:
                updates.append("result_link = ?")
                params.append(result_link)
            if revision_comment is not None:
                updates.append("revision_comment = ?")
                params.append(revision_comment)
            params.append(task_id)
            conn.execute(
                f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?",
                params
            )
            conn.commit()
            return conn.total_changes > 0

    def get_tasks(
        self,
        status: Optional[TaskStatus] = None,
        creator_id: Optional[int] = None,
        assignee_id: Optional[int] = None,
        sort_by_deadline: bool = True
    ) -> list[Task]:
        with self._get_connection() as conn:
            query = "SELECT * FROM tasks WHERE 1=1"
            params = []
            if status:
                query += " AND status = ?"
                params.append(status.value)
            if creator_id:
                query += " AND creator_id = ?"
                params.append(creator_id)
            if assignee_id:
                query += " AND assignee_id = ?"
                params.append(assignee_id)
            query += " ORDER BY deadline ASC" if sort_by_deadline else " ORDER BY id DESC"
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_task(r) for r in rows]

    def get_open_tasks(self) -> list[Task]:
        """Tasks with status New, sorted by deadline."""
        return self.get_tasks(status=TaskStatus.NEW)

    def assign_task(self, task_id: int, assignee_id: int) -> bool:
        return self.update_task_status(
            task_id, TaskStatus.IN_PROGRESS, assignee_id=assignee_id
        )

    def submit_for_review(self, task_id: int, result_link: str) -> bool:
        return self.update_task_status(
            task_id, TaskStatus.ON_REVIEW, result_link=result_link
        )

    def approve_task(self, task_id: int) -> bool:
        return self.update_task_status(task_id, TaskStatus.DONE)

    def request_revision(self, task_id: int, comment: str) -> bool:
        return self.update_task_status(
            task_id, TaskStatus.REVISION, revision_comment=comment
        )

    def update_task_details(
        self, task_id: int, title: Optional[str] = None, description: Optional[str] = None,
        deadline: Optional[datetime] = None, brief_link: Optional[str] = None
    ) -> bool:
        """Update task details. Only for tasks with status New."""
        with self._get_connection() as conn:
            task = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not task or task["status"] != TaskStatus.NEW.value:
                return False
            updates, params = [], []
            if title is not None:
                updates.append("title = ?")
                params.append(title[:100])
            if description is not None:
                updates.append("description = ?")
                params.append(description)
            if deadline is not None:
                updates.append("deadline = ?")
                params.append(deadline.isoformat())
            if brief_link is not None:
                updates.append("brief_link = ?")
                params.append(brief_link[:500])
            if not updates:
                return True
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(task_id)
            conn.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
            return conn.total_changes > 0

    def cancel_task(self, task_id: int) -> bool:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE tasks SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = ?",
                (TaskStatus.CANCELLED.value, task_id, TaskStatus.NEW.value)
            )
            conn.commit()
            return conn.total_changes > 0

    def get_creator_telegram_id(self, creator_id: int) -> Optional[int]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT telegram_id FROM users WHERE id = ?", (creator_id,)
            ).fetchone()
            return row["telegram_id"] if row else None

    def get_assignee_telegram_id(self, assignee_id: int) -> Optional[int]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT telegram_id FROM users WHERE id = ?", (assignee_id,)
            ).fetchone()
            return row["telegram_id"] if row else None
