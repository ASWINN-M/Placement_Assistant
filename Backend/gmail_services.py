import os
import base64
import json
import pandas as pd

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from llm_extractor import extract_placement_info
from calendar_service import (
    authenticate_calendar,
    create_calendar_event
)
from students_repo import get_verified_students, ensure_student_columns
from eligibility import filter_students_by_eligibility
from processed_repo import (
    ensure_processed_table,
    get_processed_neo_ids,
    mark_students_processed,
    message_fully_handled,
)


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send"
]

CDC_EMAIL = "students.cdc2027@vitap.ac.in"

STUDENT_ID = "I5Y4H3N6"


def authenticate_gmail():
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file(
            "token.json",
            SCOPES
        )

        granted = set(creds.scopes or [])
        required = set(SCOPES)

        # Old tokens may only have gmail.readonly
        if not required.issubset(granted):
            print(
                "Gmail token is missing send permission. "
                "Re-authorizing..."
            )
            creds = None

    if not creds or not creds.valid:

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json",
                SCOPES
            )

            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    service = build(
        "gmail",
        "v1",
        credentials=creds
    )

    return service


def get_cdc_emails(service, max_results=20):
    results = service.users().messages().list(
        userId="me",
        q=f"from:{CDC_EMAIL}",
        maxResults=max_results
    ).execute()

    return results.get("messages", [])


def get_email(service, message_id):
    return service.users().messages().get(
        userId="me",
        id=message_id,
        format="full"
    ).execute()


def get_email_headers(message):
    headers = message["payload"].get("headers", [])

    result = {}

    for header in headers:

        name = header["name"].lower()

        if name in ["subject", "from", "date"]:
            result[name] = header["value"]

    return result


def decode_body(data):
    return base64.urlsafe_b64decode(
        data
    ).decode(
        "utf-8",
        errors="ignore"
    )


def extract_email_body(payload):
    body_data = (
        payload.get("body", {})
        .get("data")
    )

    if body_data:
        return decode_body(body_data)

    parts = payload.get("parts", [])

    for part in parts:

        mime_type = part.get(
            "mimeType",
            ""
        )

        if mime_type == "text/plain":

            data = (
                part.get("body", {})
                .get("data")
            )

            if data:
                return decode_body(data)

        if part.get("parts"):

            body = extract_email_body(part)

            if body:
                return body

    return ""


def find_attachments(payload):
    attachments = []

    def scan_parts(parts):

        for part in parts:

            filename = part.get(
                "filename",
                ""
            )

            if filename:

                attachments.append({
                    "filename": filename,
                    "mime_type": part.get(
                        "mimeType"
                    ),
                    "attachment_id": (
                        part.get("body", {})
                        .get("attachmentId")
                    )
                })

            if part.get("parts"):
                scan_parts(part["parts"])

    scan_parts(
        payload.get("parts", [])
    )

    return attachments


def download_attachment(
    service,
    message_id,
    attachment_id,
    filename
):
    attachment = (
        service.users()
        .messages()
        .attachments()
        .get(
            userId="me",
            messageId=message_id,
            id=attachment_id
        )
        .execute()
    )

    file_data = base64.urlsafe_b64decode(
        attachment["data"]
    )

    os.makedirs(
        "attachments",
        exist_ok=True
    )

    filepath = os.path.join(
        "attachments",
        filename
    )

    with open(filepath, "wb") as file:
        file.write(file_data)

    return filepath


def find_registered_in_excel(filepath, students):
    df = pd.read_excel(filepath)
    sheet_values = set()

    for column in df.columns:
        sheet_values.update(
            df[column]
            .astype(str)
            .str.strip()
            .str.lower()
            .tolist()
        )

    matched = []

    for student in students:
        neo_id = str(student["neo_id"]).strip().lower()
        reg_no = str(student.get("reg_no") or "").strip().lower()

        if neo_id in sheet_values or (reg_no and reg_no in sheet_values):
            matched.append(student)

    return matched


def students_mentioned_in_text(text, students):
    haystack = (text or "").lower()
    matched = []

    for student in students:
        neo_id = str(student["neo_id"]).strip().lower()
        reg_no = str(student.get("reg_no") or "").strip().lower()

        if neo_id and neo_id in haystack:
            matched.append(student)
            continue

        if reg_no and len(reg_no) >= 6 and reg_no in haystack:
            matched.append(student)

    return matched


def resolve_invite_candidates(excel_filepaths, subject, body, students):
    """
    Shortlist Excel / IDs in mail → only students whose Neo ID or reg no appears.
    Open registration (no IDs) → all verified students (branch filter applied later).
    """
    if not students:
        print("\ni No registered students in DB yet.")
        return []

    if excel_filepaths:
        matched = []
        seen = set()

        for filepath in excel_filepaths:
            for student in find_registered_in_excel(filepath, students):
                key = student["neo_id"].lower()
                if key in seen:
                    continue
                seen.add(key)
                matched.append(student)

        print(
            f"\nNeo ID / reg no on Excel shortlist: "
            f"{len(matched)}/{len(students)}"
        )

        for student in matched:
            print(
                f"  - {student['neo_id']} / {student.get('reg_no')} "
                f"<{student['college_email']}>"
            )

        return matched

    mentioned = students_mentioned_in_text(
        f"{subject}\n{body}",
        students
    )

    if mentioned:
        print(
            f"\nNeo ID / reg no found in email body: "
            f"{len(mentioned)}/{len(students)}"
        )
        for student in mentioned:
            print(
                f"  - {student['neo_id']} / {student.get('reg_no')}"
            )
        return mentioned

    print(
        "\nNo Neo ID / reg no in this email "
        "(open registration / drive). "
        "Will filter by branch next."
    )
    return list(students)


def check_student_shortlisted(
    filepath,
    student_id
):
    df = pd.read_excel(filepath)

    student_id = str(
        student_id
    ).strip().lower()

    for column in df.columns:

        values = (
            df[column]
            .astype(str)
            .str.strip()
            .str.lower()
        )

        if student_id in values.values:
            return True, column

    return False, None


def is_placement_email(
    subject,
    body
):
    keywords = [
        "placement",
        "recruitment",
        "hiring",
        "drive",
        "campus",
        "career",
        "registration",
        "apply",
        "shortlist",
        "assessment",
        "test"
    ]

    text = (
        subject + " " + body
    ).lower()

    return any(
        keyword in text
        for keyword in keywords
    )


def process_email(
    gmail_service,
    calendar_service,
    message,
    students,
    focus_neo_ids=None,
):
    message_id = message["id"]

    headers = get_email_headers(message)
    subject = headers.get("subject", "No Subject")
    sender = headers.get("from", "Unknown Sender")
    date = headers.get("date", "Unknown Date")
    body = extract_email_body(message["payload"])
    attachments = find_attachments(message["payload"])

    print("\n" + "=" * 60)
    print("PROCESSING CDC EMAIL")
    print("=" * 60)
    print(f"\nFrom    : {sender}")
    print(f"Subject : {subject}")
    print(f"Date    : {date}")

    student_neo_ids = [student["neo_id"] for student in students]

    if not is_placement_email(subject, body):
        print("\n✗ Not a placement-related email.")
        mark_students_processed(message_id, student_neo_ids)
        return True

    print("\n✓ Placement-related email detected.")

    excel_attachments = []
    for attachment in attachments:
        filename = attachment["filename"].lower()
        mime_type = attachment["mime_type"] or ""
        if filename.endswith((".xlsx", ".xls")):
            excel_attachments.append(attachment)
        elif mime_type.startswith("image/"):
            print(f"✓ Ignoring image: {attachment['filename']}")
        else:
            print(f"✓ Ignoring attachment: {attachment['filename']}")

    excel_filepaths = []
    if excel_attachments:
        print("\nExcel shortlist attachment detected.")
        for attachment in excel_attachments:
            print(f"\nAttachment: {attachment['filename']}")
            attachment_id = attachment["attachment_id"]
            if not attachment_id:
                print("✗ Attachment ID not found.")
                continue
            filepath = download_attachment(
                gmail_service,
                message_id,
                attachment_id,
                attachment["filename"],
            )
            print(f"✓ Downloaded: {filepath}")
            excel_filepaths.append(filepath)
    else:
        print("\nNo Excel shortlist attachment.")
        print("Processing as normal placement email...")

    print("\nSending email to Groq...")
    try:
        placement = extract_placement_info(subject, body)
    except Exception as error:
        print(f"\n✗ Groq extraction failed: {error}")
        return False

    print("\n" + "-" * 60)
    print("PLACEMENT INFORMATION")
    print("-" * 60)
    print(f"Company              : {placement.get('company')}")
    print(f"Role                 : {placement.get('role')}")
    print(f"Event Type           : {placement.get('event_type')}")
    print(f"Test Date            : {placement.get('test_date')}")
    print(f"Interview Date       : {placement.get('interview_date')}")
    print(f"Reporting Time       : {placement.get('reporting_time')}")
    print(f"Test Time            : {placement.get('test_time')}")
    print(f"Venue                : {placement.get('venue')}")
    print(f"Application Deadline : {placement.get('application_deadline')}")
    print(f"Application Link     : {placement.get('application_link')}")
    print(f"Eligible Degrees     : {placement.get('eligible_degrees')}")
    print(f"Eligible Branches    : {placement.get('eligible_branches')}")
    print(f"Open to all branches : {placement.get('open_to_all_branches')}")

    candidates = resolve_invite_candidates(
        excel_filepaths, subject, body, students
    )

    if excel_filepaths and not candidates:
        print("\nNo registered Neo ID / reg no on the shortlist.")
        print("Ignoring this email for calendar.")
        mark_students_processed(message_id, student_neo_ids)
        return True

    invite_targets, skipped_branch = filter_students_by_eligibility(
        candidates, placement
    )

    if skipped_branch:
        print("\nSkipped (branch/degree not eligible):")
        for student in skipped_branch:
            print(
                f"  - {student['neo_id']} "
                f"[{student.get('degree')} {student.get('branch')}]"
            )

    invite_targets = [
        student for student in invite_targets if student.get("branch")
    ]

    already_done = get_processed_neo_ids(message_id)
    if focus_neo_ids:
        focus = {str(neo_id).upper() for neo_id in focus_neo_ids}
        invite_targets = [
            student for student in invite_targets
            if str(student["neo_id"]).upper() in focus
        ]

    pending_invites = [
        student for student in invite_targets
        if str(student["neo_id"]).upper() not in already_done
    ]

    if not pending_invites:
        print("\nNo new eligible students to invite for this email.")
        mark_students_processed(message_id, student_neo_ids)
        return True

    print("\nEligible students for calendar invite (new):")
    for student in pending_invites:
        print(
            f"  - {student['neo_id']} "
            f"[{student.get('degree')} {student.get('branch')}] "
            f"<{student['college_email']}>"
        )

    print("\nAdding event to Google Calendar...")
    try:
        calendar_result = create_calendar_event(
            calendar_service,
            placement,
            attendee_emails=[
                student["college_email"]
                for student in pending_invites
                if student.get("college_email")
            ],
        )
    except Exception as error:
        print(f"\n✗ Calendar event creation failed: {error}")
        return False

    if calendar_result is None:
        print("\n✗ Calendar step failed. Will retry for these students later.")
        return False

    mark_students_processed(message_id, student_neo_ids)
    return True


def run_worker(focus_neo_ids=None, max_results=40):
    """Process recent CDC mails. Optionally only invite focus_neo_ids."""
    ensure_processed_table()

    print("Connecting to Gmail...")
    gmail_service = authenticate_gmail()
    print("✓ Gmail connected successfully.")

    print("\nConnecting to Google Calendar...")
    calendar_service = authenticate_calendar()
    print("✓ Google Calendar connected successfully.")

    try:
        ensure_student_columns()
        students = get_verified_students()
    except Exception as error:
        print(f"\ni Could not read student DB: {error}")
        students = []

    if focus_neo_ids:
        focus = {str(neo_id).upper() for neo_id in focus_neo_ids}
        students = [
            student for student in students
            if str(student["neo_id"]).upper() in focus
        ]
        joined = ", ".join(sorted(focus))
        print(f"\nInstant backfill for: {joined}")

    if not students:
        print("\nNo matching registered students.")
        return

    print(f"\nSearching emails from: {CDC_EMAIL}")
    messages = get_cdc_emails(gmail_service, max_results=max_results)
    if not messages:
        print("\nNo CDC emails found.")
        return

    student_neo_ids = [student["neo_id"] for student in students]
    to_process = []
    for message_info in messages:
        message_id = message_info["id"]
        if message_fully_handled(message_id, student_neo_ids):
            continue
        to_process.append(message_info)

    print(f"\nFound {len(messages)} CDC emails.")
    print(f"Emails needing work for these students: {len(to_process)}")

    if not to_process:
        print("\nNothing new to process for these students.")
        return

    for message_info in to_process:
        message = get_email(gmail_service, message_info["id"])
        process_email(
            gmail_service,
            calendar_service,
            message,
            students,
            focus_neo_ids=focus_neo_ids,
        )

    print("\n" + "=" * 60)
    print("Processing completed.")
    print("=" * 60)


def main():
    run_worker()


if __name__ == "__main__":
    main()
