import os
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from dotenv import load_dotenv
from sqlalchemy import (
    DateTime,
    String,
    create_engine,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    sessionmaker,
)


load_dotenv()


def normalize_database_url(url: str) -> str:
    """
    Accept Supabase / standard Postgres URLs and make them work with SQLAlchemy.
    - postgresql://...  -> postgresql+psycopg2://...
    - add sslmode=require for remote hosts (Supabase)
    """
    if not url:
        return url

    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]

    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    is_local = host in {"localhost", "127.0.0.1", "db"}

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))

    if not is_local and "sslmode" not in query:
        query["sslmode"] = "require"

    return urlunparse(parsed._replace(query=urlencode(query)))


DATABASE_URL = normalize_database_url(
    os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://placement:placement@127.0.0.1:5433/placement"
    )
)

ALLOWED_EMAIL_DOMAINS = (
    "vitapstudent.ac.in",
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    neo_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    reg_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    college_email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False
    )
    branch: Mapped[str | None] = mapped_column(String(120), nullable=True)
    degree: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )


class PendingSignup(Base):
    __tablename__ = "pending_signups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    neo_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reg_no: Mapped[str] = mapped_column(String(64), nullable=False)
    college_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    branch: Mapped[str | None] = mapped_column(String(120), nullable=True)
    degree: Mapped[str | None] = mapped_column(String(64), nullable=True)
    otp_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db_session():
    return SessionLocal()


def is_allowed_college_email(email: str) -> bool:
    if not email or "@" not in email:
        return False

    domain = email.rsplit("@", 1)[1].strip().lower()
    return domain in ALLOWED_EMAIL_DOMAINS
