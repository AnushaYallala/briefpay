import sqlite3
from pathlib import Path

db_path = Path(__file__).resolve().parents[1] / "briefpay_dev.db"
if not db_path.exists():
    print("Database does not exist.")
    raise SystemExit(0)

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# Disable foreign keys temporarily during truncate
cursor.execute("PRAGMA foreign_keys = OFF;")
tables = [
    r[0] for r in cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version';"
    ).fetchall()
]

for table in tables:
    cursor.execute(f"DELETE FROM {table};")
    print(f"Cleared table: {table}")

conn.commit()
cursor.execute("PRAGMA foreign_keys = ON;")
cursor.execute("VACUUM;")
conn.close()

print(f"Successfully cleared {len(tables)} tables in {db_path.name}. Database is clean and ready.")
