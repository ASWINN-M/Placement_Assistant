from sqlalchemy import select

from db import (
    PlacementExtractionCache,
    StudentMessageProcessed,
    get_db_session,
    init_db,
)
from students_repo import ensure_student_columns


def ensure_processed_table():
    ensure_student_columns()
    init_db()


def get_processed_neo_ids(message_id: str) -> set[str]:
    session = get_db_session()

    try:
        rows = session.scalars(
            select(StudentMessageProcessed.neo_id).where(
                StudentMessageProcessed.message_id == message_id
            )
        ).all()
        return {str(neo_id).upper() for neo_id in rows}
    finally:
        session.close()


def mark_students_processed(message_id: str, neo_ids) -> None:
    if not neo_ids:
        return

    session = get_db_session()

    try:
        existing = {
            str(neo_id).upper()
            for neo_id in session.scalars(
                select(StudentMessageProcessed.neo_id).where(
                    StudentMessageProcessed.message_id == message_id
                )
            ).all()
        }

        for neo_id in neo_ids:
            key = str(neo_id).strip().upper()
            if not key or key in existing:
                continue

            session.add(
                StudentMessageProcessed(
                    message_id=message_id,
                    neo_id=key,
                )
            )

        session.commit()
    finally:
        session.close()


def message_fully_handled(message_id: str, student_neo_ids) -> bool:
    """True when every current student was already considered for this mail."""
    if not student_neo_ids:
        return True

    processed = get_processed_neo_ids(message_id)
    current = {str(neo_id).upper() for neo_id in student_neo_ids}
    return current <= processed


def get_cached_placement(message_id: str):
    session = get_db_session()

    try:
        row = session.get(PlacementExtractionCache, message_id)
        if not row:
            return None
        return row.placement_json
    finally:
        session.close()


def save_cached_placement(message_id: str, subject: str, placement: dict) -> None:
    session = get_db_session()

    try:
        existing = session.get(PlacementExtractionCache, message_id)
        if existing:
            existing.subject = (subject or "")[:512]
            existing.placement_json = placement
        else:
            session.add(
                PlacementExtractionCache(
                    message_id=message_id,
                    subject=(subject or "")[:512],
                    placement_json=placement,
                )
            )
        session.commit()
    finally:
        session.close()
