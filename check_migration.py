import sqlite3

conn = sqlite3.connect('design_tasks.db')
c = conn.cursor()

print("=== ПРОВЕРКА МИГРАЦИИ ===")

c.execute("SELECT DISTINCT status FROM tasks")
statuses = [row[0] for row in c.fetchall()]
print(f"Уникальные статусы в tasks: {statuses}")

c.execute("SELECT DISTINCT role FROM users")
roles = [row[0] for row in c.fetchall()]
print(f"Уникальные роли в users: {roles}")

conn.close()