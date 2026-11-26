import shutil
import sqlite3
from pathlib import Path

conn = sqlite3.connect("sms.db")

for table in ("registration", "student", "batch", "section", "user"):
    count = conn.execute(f"select count(*) from {table}").fetchone()[0]
    print(table, count)

conn.execute("delete from registration")
conn.execute("delete from user where username like 'rolltest-%'")
conn.commit()

shutil.rmtree(
    Path("app/static/uploads/registrations"), ignore_errors=True
)

print("after reset")

for table in ("registration", "student", "batch", "section", "user"):
    count = conn.execute(f"select count(*) from {table}").fetchone()[0]
    print(table, count)

conn.close()
