"""
Quick check: can we reach the DB and create tables?
Run from Backend/:

  python test_db.py
"""

from db import DATABASE_URL, init_db, engine
from sqlalchemy import text


def main():
    host = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL
    print(f"Connecting to: {host}")

    init_db()

    with engine.connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar()
        tables = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' "
                "ORDER BY table_name"
            )
        ).scalars().all()

    print("OK")
    print(f"Postgres: {version.split(',')[0]}")
    print(f"Tables: {', '.join(tables) or '(none)'}")


if __name__ == "__main__":
    main()
