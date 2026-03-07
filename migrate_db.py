import sqlite3

def migrate_database(db_path='design_tasks.db'):
    """
    Обновляет значения статусов задач и ролей пользователей
    в соответствии с новыми русскоязычными значениями Enum.
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    print("Начинаем миграцию базы данных...")

    # 1. Миграция статусов задач
    status_mapping = {
        'New': 'новые',
        'In Progress': 'в процессе',
        'On Review': 'отправлено на проверку',
        'Revision': 'проверка',
        'Done': 'сделано',
        'Cancelled': 'отменено'  # если нужно заменить на русский, укажите здесь
    }

    for old_status, new_status in status_mapping.items():
        c.execute(
            "UPDATE tasks SET status = ? WHERE status = ?",
            (new_status, old_status)
        )
        print(f"Обновлено задач со статусом '{old_status}' → '{new_status}': {c.rowcount}")

    # 2. Миграция ролей пользователей (предполагается таблица users)
    role_mapping = {
        'smm_manager': 'СММ',
        'designer': 'Дизайнер',
        'head_of_design': 'Глава дизайна'
    }

    # Проверим, существует ли таблица users
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if c.fetchone():
        for old_role, new_role in role_mapping.items():
            c.execute(
                "UPDATE users SET role = ? WHERE role = ?",
                (new_role, old_role)
            )
            print(f"Обновлено пользователей с ролью '{old_role}' → '{new_role}': {c.rowcount}")
    else:
        print("Таблица 'users' не найдена, пропускаем миграцию ролей.")

    # Фиксируем изменения
    conn.commit()
    print("Миграция успешно завершена.")
    conn.close()

if __name__ == "__main__":
    migrate_database()