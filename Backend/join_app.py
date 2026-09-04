import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from db import PendingSignup, Student, init_db, is_allowed_college_email, get_db_session
from otp_mail import send_otp_email
from students_repo import ensure_student_columns


APP_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(APP_DIR, "templates", "join.html")

OTP_MINUTES = 10

ALLOWED_DEGREES = {
    "B.Tech",
    "M.Tech",
    "MBA",
    "Other",
}

ALLOWED_BRANCHES = {
    "CSE Core",
    "CSE AI/ML",
    "CSE Data Science",
    "IT",
    "ECE",
    "EEE",
    "Mechanical",
    "Civil",
    "Biotechnology",
    "Other",
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    ensure_student_columns()
    yield


app = FastAPI(title="Placement join", lifespan=lifespan)


class JoinRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    neo_id: str = Field(min_length=3, max_length=32)
    reg_no: str = Field(min_length=3, max_length=64)
    college_email: str = Field(min_length=6, max_length=255)
    degree: str = Field(min_length=2, max_length=64)
    branch: str = Field(min_length=2, max_length=120)


class VerifyRequest(BaseModel):
    pending_id: int
    otp: str = Field(min_length=6, max_length=6)


def normalize_neo_id(value: str) -> str:
    return re.sub(r"\s+", "", value).upper()


def normalize_email(value: str) -> str:
    return value.strip().lower()


def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode("utf-8")).hexdigest()


@app.get("/")
def join_page():
    return FileResponse(TEMPLATE_PATH)


@app.post("/api/join")
def join(payload: JoinRequest):
    name = " ".join(payload.name.split())
    neo_id = normalize_neo_id(payload.neo_id)
    reg_no = payload.reg_no.strip().upper()
    email = normalize_email(payload.college_email)
    degree = payload.degree.strip()
    branch = payload.branch.strip()

    if degree not in ALLOWED_DEGREES:
        raise HTTPException(status_code=400, detail="Select a valid degree.")

    if branch not in ALLOWED_BRANCHES:
        raise HTTPException(status_code=400, detail="Select a valid branch.")

    if not is_allowed_college_email(email):
        raise HTTPException(
            status_code=400,
            detail="Use your VIT-AP college email (@vitapstudent.ac.in)."
        )

    session = get_db_session()

    try:
        existing = session.scalar(
            select(Student).where(
                func.lower(Student.neo_id) == neo_id.lower()
            )
        )

        if existing and existing.college_email.lower() != email:
            raise HTTPException(
                status_code=409,
                detail="This Neo ID is already registered with another email."
            )

        email_owner = session.scalar(
            select(Student).where(
                func.lower(Student.college_email) == email
            )
        )

        if email_owner and email_owner.neo_id.lower() != neo_id.lower():
            raise HTTPException(
                status_code=409,
                detail="This college email is already registered with another Neo ID."
            )

        reg_owner = session.scalar(
            select(Student).where(
                func.lower(Student.reg_no) == reg_no.lower()
            )
        )

        if reg_owner and reg_owner.neo_id.lower() != neo_id.lower():
            raise HTTPException(
                status_code=409,
                detail="This registration number is already registered."
            )

        otp = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_MINUTES)

        session.execute(
            delete(PendingSignup).where(
                (PendingSignup.neo_id == neo_id)
                | (PendingSignup.college_email == email)
            )
        )

        pending = PendingSignup(
            name=name,
            neo_id=neo_id,
            reg_no=reg_no,
            college_email=email,
            degree=degree,
            branch=branch,
            otp_hash=hash_otp(otp),
            expires_at=expires_at,
        )
        session.add(pending)
        session.commit()
        session.refresh(pending)
        pending_id = pending.id

    finally:
        session.close()

    try:
        send_otp_email(email, otp)
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Could not send verification email: {error}"
        ) from error

    return {"pending_id": pending_id}


@app.post("/api/verify")
def verify(payload: VerifyRequest):
    otp = payload.otp.strip()

    if not otp.isdigit():
        raise HTTPException(status_code=400, detail="Enter the 6-digit code.")

    session = get_db_session()

    try:
        pending = session.get(PendingSignup, payload.pending_id)

        if not pending:
            raise HTTPException(status_code=404, detail="Verification expired. Start again.")

        now = datetime.now(timezone.utc)
        expires = pending.expires_at

        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)

        if expires < now:
            session.delete(pending)
            session.commit()
            raise HTTPException(status_code=410, detail="Code expired. Start again.")

        if pending.otp_hash != hash_otp(otp):
            raise HTTPException(status_code=400, detail="Incorrect code.")

        existing = session.scalar(
            select(Student).where(
                func.lower(Student.neo_id) == pending.neo_id.lower()
            )
        )

        if existing:
            existing.name = pending.name
            existing.reg_no = pending.reg_no
            existing.college_email = pending.college_email
            existing.degree = pending.degree
            existing.branch = pending.branch
        else:
            session.add(
                Student(
                    name=pending.name,
                    neo_id=pending.neo_id,
                    reg_no=pending.reg_no,
                    college_email=pending.college_email,
                    degree=pending.degree,
                    branch=pending.branch,
                )
            )

        session.delete(pending)
        session.commit()

        return {"ok": True}

    finally:
        session.close()
