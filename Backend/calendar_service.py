import os
import re
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/calendar"
]

TIMEZONE = "Asia/Kolkata"

CALENDAR_ID = "primary"

DATE_FORMATS = [
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%d.%m.%Y",
    "%m-%d-%Y",
    "%m/%d/%Y",
]

TIME_FORMATS = [
    "%I:%M %p",
    "%I:%M%p",
    "%I %p",
    "%I%p",
    "%H:%M",
    "%H",
]


def authenticate_calendar():
    creds = None

    if os.path.exists("calendar_token.json"):
        creds = Credentials.from_authorized_user_file(
            "calendar_token.json",
            SCOPES
        )

    if not creds or not creds.valid:

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json",
                SCOPES
            )

            creds = flow.run_local_server(port=0)

        with open("calendar_token.json", "w") as token:
            token.write(creds.to_json())

    service = build(
        "calendar",
        "v3",
        credentials=creds
    )

    return service


def _normalize_time_text(time_string):
    if not time_string:
        return None

    text = str(time_string).strip()

    # "6.30pm" / "5.15 pm" -> "6:30 pm" / "5:15 pm"
    text = re.sub(
        r"(\d{1,2})\.(\d{2})\s*(am|pm)?",
        lambda match: (
            f"{match.group(1)}:{match.group(2)}"
            + (f" {match.group(3)}" if match.group(3) else "")
        ),
        text,
        flags=re.IGNORECASE
    )

    # "5pm" -> "5 pm"
    text = re.sub(
        r"(\d{1,2})\s*(am|pm)\b",
        r"\1 \2",
        text,
        flags=re.IGNORECASE
    )

    return text.strip()


def convert_time_to_24_hour(time_string):
    text = _normalize_time_text(time_string)

    if not text:
        return None

    for time_format in TIME_FORMATS:

        try:
            parsed_time = datetime.strptime(
                text,
                time_format
            )

            return parsed_time.strftime("%H:%M")

        except ValueError:
            continue

    return None


def parse_date(date_string):
    if not date_string:
        return None

    text = str(date_string).strip()

    for date_format in DATE_FORMATS:

        try:
            return datetime.strptime(text, date_format)

        except ValueError:
            continue

    return None


def parse_deadline(deadline_string):
    """
    Parse values like:
    - 03-09-2026 5pm
    - 03.09.2026 5:00 PM
    - 2026-09-03
    Returns (date_object, time_hhmm_or_None)
    """
    if not deadline_string:
        return None, None

    text = str(deadline_string).strip()

    # Split trailing time if present
    match = re.match(
        r"^(.+?)\s+(\d{1,2}([.:]\d{2})?\s*(am|pm)?)$",
        text,
        flags=re.IGNORECASE
    )

    if match:
        date_part = match.group(1).strip()
        time_part = match.group(2).strip()
        parsed_date = parse_date(date_part)
        parsed_time = convert_time_to_24_hour(time_part)

        if parsed_date:
            return parsed_date, parsed_time

    parsed_date = parse_date(text)

    if parsed_date:
        return parsed_date, None

    return None, None


def build_description(placement):
    description_parts = []

    field_labels = [
        ("company", "Company"),
        ("role", "Role"),
        ("event_type", "Event Type"),
        ("reporting_time", "Reporting Time"),
        ("test_time", "Test Time"),
        ("interview_date", "Interview Date"),
        ("venue", "Venue"),
        ("application_deadline", "Application Deadline"),
        ("application_link", "Application Link"),
    ]

    for key, label in field_labels:
        value = placement.get(key)

        if value:
            description_parts.append(f"{label}: {value}")

    return "\n".join(description_parts)


def build_event_title(placement, suffix=None):
    title_parts = []

    company = placement.get("company")
    event_type = placement.get("event_type")
    role = placement.get("role")

    if company:
        title_parts.append(company)

    if suffix:
        title_parts.append(suffix)
    elif event_type:
        title_parts.append(event_type)

    if role and not suffix:
        title_parts.append(role)

    event_title = " - ".join(title_parts)

    return event_title or "Placement Event"


def build_reminder_overrides(reminder_minutes, methods=("popup",)):
    return [
        {"method": method, "minutes": minutes}
        for minutes in reminder_minutes
        for method in methods
    ]


def attach_attendees(event, attendee_emails):
    if attendee_emails:
        event["attendees"] = [
            {"email": email}
            for email in attendee_emails
        ]
    return event


def insert_event(service, event, attendee_emails=None):
    event = attach_attendees(event, attendee_emails)
    send_updates = "all" if attendee_emails else "none"

    return (
        service.events()
        .insert(
            calendarId=CALENDAR_ID,
            body=event,
            sendUpdates=send_updates
        )
        .execute()
    )


def insert_timed_event(
    service,
    title,
    description,
    location,
    start_object,
    duration_hours,
    reminder_minutes,
    reminder_methods=("popup",),
    attendee_emails=None
):
    end_object = start_object + timedelta(hours=duration_hours)

    event = {
        "summary": title,
        "description": description,
        "location": location or "",
        "start": {
            "dateTime": start_object.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": TIMEZONE
        },
        "end": {
            "dateTime": end_object.strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": TIMEZONE
        },
        "reminders": {
            "useDefault": False,
            "overrides": build_reminder_overrides(
                reminder_minutes,
                reminder_methods
            )
        }
    }

    return insert_event(service, event, attendee_emails)


def insert_all_day_event(
    service,
    title,
    description,
    location,
    date_object,
    reminder_minutes,
    reminder_methods=("popup",),
    attendee_emails=None
):
    day = date_object.strftime("%Y-%m-%d")
    next_day = (
        date_object + timedelta(days=1)
    ).strftime("%Y-%m-%d")

    event = {
        "summary": title,
        "description": description,
        "location": location or "",
        "start": {"date": day},
        "end": {"date": next_day},
        "reminders": {
            "useDefault": False,
            "overrides": build_reminder_overrides(
                reminder_minutes,
                reminder_methods
            )
        }
    }

    return insert_event(service, event, attendee_emails)


def create_scheduled_event(service, placement, attendee_emails=None):
    """
    Create event for test/PPT.
    Timed if test_time or reporting_time exists; otherwise all-day.
    Returns created event, "missing" if no test_date, or None on failure.
    """
    test_date = placement.get("test_date")
    test_time = placement.get("test_time")
    reporting_time = placement.get("reporting_time")
    event_time = test_time or reporting_time

    if not test_date:
        return "missing"

    parsed_date = parse_date(test_date)

    if not parsed_date:
        print(f"✗ Could not understand date: {test_date}")
        return None

    title = build_event_title(placement)
    description = build_description(placement)
    venue = placement.get("venue")

    if event_time:
        formatted_time = convert_time_to_24_hour(event_time)

        if not formatted_time:
            print(f"✗ Could not understand event time: {event_time}")
            return None

        if not test_time and reporting_time:
            print(
                "i test_time missing - "
                "using reporting_time as event start."
            )

        start_object = datetime.strptime(
            f"{parsed_date.strftime('%Y-%m-%d')}T{formatted_time}:00",
            "%Y-%m-%dT%H:%M:%S"
        )

        created_event = insert_timed_event(
            service,
            title,
            description,
            venue,
            start_object,
            duration_hours=2,
            reminder_minutes=[60, 1440],
            attendee_emails=attendee_emails
        )

        print("\n✓ Placement event created successfully!")
        print(f"Title: {title}")
        print(f"Date: {parsed_date.strftime('%Y-%m-%d')}")
        print(f"Time: {event_time}")
        print(f"Venue: {venue}")
        print(f"Event ID: {created_event['id']}")

    else:
        print(
            "i No event time given - "
            "creating all-day test event."
        )

        created_event = insert_all_day_event(
            service,
            title,
            description,
            venue,
            parsed_date,
            reminder_minutes=[60, 1440],
            attendee_emails=attendee_emails
        )

        print("\n✓ Placement event created successfully!")
        print(f"Title: {title}")
        print(f"Date: {parsed_date.strftime('%Y-%m-%d')} (all day)")
        print(f"Venue: {venue}")
        print(f"Event ID: {created_event['id']}")

    return created_event


def create_interview_event(service, placement, attendee_emails=None):
    """
    Create interview event when interview_date exists.
    Timed if test_time / reporting_time is present; otherwise all-day.
    """
    interview_date = placement.get("interview_date")

    if not interview_date:
        return "missing"

    parsed_date = parse_date(interview_date)

    if not parsed_date:
        print(
            f"✗ Could not understand interview date: "
            f"{interview_date}"
        )
        return None

    title = build_event_title(placement, suffix="Interview")
    description = build_description(placement)
    venue = placement.get("venue")
    event_time = (
        placement.get("test_time")
        or placement.get("reporting_time")
    )

    if event_time:
        formatted_time = convert_time_to_24_hour(event_time)

        if not formatted_time:
            print(f"✗ Could not understand interview time: {event_time}")
            return None

        start_object = datetime.strptime(
            f"{parsed_date.strftime('%Y-%m-%d')}T{formatted_time}:00",
            "%Y-%m-%dT%H:%M:%S"
        )

        created_event = insert_timed_event(
            service,
            title,
            description,
            venue,
            start_object,
            duration_hours=2,
            reminder_minutes=[60, 1440],
            attendee_emails=attendee_emails
        )

        print("\n✓ Interview event created successfully!")
        print(f"Title: {title}")
        print(f"Date: {parsed_date.strftime('%Y-%m-%d')}")
        print(f"Time: {event_time}")
        print(f"Event ID: {created_event['id']}")
    else:
        created_event = insert_all_day_event(
            service,
            title,
            description,
            venue,
            parsed_date,
            reminder_minutes=[60, 1440],
            attendee_emails=attendee_emails
        )

        print("\n✓ Interview event created successfully!")
        print(f"Title: {title}")
        print(f"Date: {parsed_date.strftime('%Y-%m-%d')} (all day)")
        print(f"Event ID: {created_event['id']}")

    return created_event


def create_deadline_event(service, placement, attendee_emails=None):
    """
    Create application-deadline reminder.
    Returns created event, "missing" if no deadline,
    or None on parse failure.
    """
    application_deadline = placement.get("application_deadline")

    if not application_deadline:
        return "missing"

    parsed_date, parsed_time = parse_deadline(
        application_deadline
    )

    if not parsed_date:
        print(
            f"✗ Could not understand application deadline: "
            f"{application_deadline}"
        )
        return None

    title = build_event_title(
        placement,
        suffix="Application Deadline"
    )
    description = build_description(placement)
    venue = placement.get("venue")

    if parsed_time:
        start_object = datetime.strptime(
            f"{parsed_date.strftime('%Y-%m-%d')}T{parsed_time}:00",
            "%Y-%m-%dT%H:%M:%S"
        )

        # Short timed block so the deadline is visible
        created_event = insert_timed_event(
            service,
            title,
            description,
            venue,
            start_object,
            duration_hours=1,
            reminder_minutes=[60],
            reminder_methods=("popup", "email"),
            attendee_emails=attendee_emails
        )
    else:
        created_event = insert_all_day_event(
            service,
            title,
            description,
            venue,
            parsed_date,
            reminder_minutes=[60],
            reminder_methods=("popup", "email"),
            attendee_emails=attendee_emails
        )

    print("\n✓ Deadline reminder created successfully!")
    print(f"Title: {title}")
    print(f"Deadline: {application_deadline}")
    print("Notification: 1 hour before deadline (popup + email)")
    print(f"Event ID: {created_event['id']}")

    return created_event


def create_calendar_event(service, placement, attendee_emails=None):
    """
    Create calendar entries for a placement.

    Registration emails often have:
      - application deadline
      - test date (sometimes without time)
      - interview date (sometimes without time)

    Returns:
      - list of created events on success
      - "skipped" when nothing scheduleable
      - None on failure (leave email unprocessed)
    """
    company = placement.get("company")

    if not company:
        print("✗ Company name is missing.")
        return None

    has_scheduled = bool(placement.get("test_date"))
    has_interview = bool(placement.get("interview_date"))
    has_deadline = bool(placement.get("application_deadline"))

    if not has_scheduled and not has_interview and not has_deadline:
        print(
            "\ni No scheduleable date/time or application "
            "deadline - skipping calendar."
        )
        return "skipped"

    if attendee_emails:
        print(
            f"Calendar invites: {len(attendee_emails)} registered student(s)"
        )

    created_events = []
    attempted = False
    failed = False

    creators = []

    if has_deadline:
        creators.append(create_deadline_event)

    if has_scheduled:
        creators.append(create_scheduled_event)

    if has_interview:
        creators.append(create_interview_event)

    for creator in creators:
        attempted = True
        result = creator(service, placement, attendee_emails)

        if result is None:
            failed = True
        elif result != "missing":
            created_events.append(result)

    if failed:
        return None

    if not created_events and attempted:
        print("✗ Could not create any calendar events.")
        return None

    return created_events


def test_calendar():
    service = authenticate_calendar()

    placement = {
        "company": "ExxonMobil",
        "role": None,
        "event_type": "Aptitude + Technical Test",
        "test_date": "2026-09-05",
        "reporting_time": "09:30 AM",
        "test_time": "10:00 AM",
        "venue": "PRP - 713",
        "application_deadline": None,
        "application_link": None
    }

    create_calendar_event(
        service,
        placement
    )


if __name__ == "__main__":
    test_calendar()
