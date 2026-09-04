from sqlalchemy import func, select, text

from db import Student, engine, get_db_session


def ensure_student_columns():
    """Add branch/degree columns if the DB was created before they existed."""
    statements = [
        "ALTER TABLE students ADD COLUMN IF NOT EXISTS branch VARCHAR(120)",
        "ALTER TABLE students ADD COLUMN IF NOT EXISTS degree VARCHAR(64)",
        "ALTER TABLE pending_signups ADD COLUMN IF NOT EXISTS branch VARCHAR(120)",
        "ALTER TABLE pending_signups ADD COLUMN IF NOT EXISTS degree VARCHAR(64)",
    ]

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def get_verified_students():
    session = get_db_session()

    try:
        rows = session.scalars(
            select(Student).order_by(Student.name)
        ).all()

        return [
            {
                "name": row.name,
                "neo_id": row.neo_id,
                "reg_no": row.reg_no,
                "college_email": row.college_email,
                "branch": getattr(row, "branch", None),
                "degree": getattr(row, "degree", None),
            }
            for row in rows
        ]

    finally:
        session.close()


def get_student_by_neo_id(neo_id: str):
    session = get_db_session()

    try:
        return session.scalar(
            select(Student).where(
                func.lower(Student.neo_id) == neo_id.strip().lower()
            )
        )
    finally:
        session.close()


def student_exists(neo_id=None, reg_no=None, college_email=None):
    session = get_db_session()

    try:
        if neo_id:
            found = session.scalar(
                select(Student).where(
                    func.lower(Student.neo_id) == neo_id.strip().lower()
                )
            )
            if found:
                return "neo_id"

        if reg_no:
            found = session.scalar(
                select(Student).where(
                    func.lower(Student.reg_no) == reg_no.strip().lower()
                )
            )
            if found:
                return "reg_no"

        if college_email:
            found = session.scalar(
                select(Student).where(
                    func.lower(Student.college_email)
                    == college_email.strip().lower()
                )
            )
            if found:
                return "college_email"

        return None

    finally:
        session.close()
