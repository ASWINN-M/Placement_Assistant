import json
import os

from dotenv import load_dotenv
from groq import Groq


load_dotenv()

client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)


def extract_placement_info(subject, body):

    prompt = f"""
Extract placement information from the following college placement email.

You must understand the context of dates and times.

For example, if the email says:
"Students must report by 9:30 AM"
and
"test starts at 10:00 AM"

then:
reporting_time = "09:30 AM"
test_time = "10:00 AM"

Do not confuse reporting time with test start time.

Registration / drive emails often look like:
- Test: 11.09.2026
- Interviews: 16.09.2026
- Last date for Registration: 03-09-2026 5pm
- Eligible Branches: B.Tech CSE/IT related branches, B.Tech ECE/EEE

For those:
- test_date = the Test date
- interview_date = the Interviews date
- application_deadline = registration last date with time
- eligible_branches = list of branches mentioned (e.g. ["CSE", "IT", "ECE", "EEE"]
  or ["CSE/IT related"]). NEVER leave this empty if the email lists branches.
  Do NOT put Mechanical / Civil / etc. unless the email explicitly includes them.
- eligible_degrees = list like ["B.Tech"] or ["M.Tech", "MBA"] when mentioned
- open_to_all_branches = true ONLY if email clearly says all branches / open to all.
  If only CSE/IT/ECE are listed, open_to_all_branches must be false.
- test_time / reporting_time may be null if no clock time is given

Date and time rules:
- Prefer dates as YYYY-MM-DD when possible (still accept DD.MM.YYYY style).
- If only one event time is mentioned (e.g. a PPT at 5:15 PM),
  put it in test_time. Also put the same value in reporting_time
  only if the email says students must report by that time.
- For Pre-Placement Talk / PPT / webinar, the scheduled time is
  test_time (or reporting_time if that is all that is given).
- application_deadline should keep both date and time when present,
  e.g. "03-09-2026 5:00 PM".
- application_link must be the full URL when available.
- Job location goes in venue.
- If a field is not present, return null (or [] for lists, false for open_to_all_branches).

Subject:
{subject}

Email:
{body}
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-20b",

        messages=[
            {
                "role": "system",
                "content": (
                    "You are an assistant that extracts structured "
                    "information from college placement emails."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],

        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "placement_information",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "company": {
                            "type": ["string", "null"]
                        },
                        "role": {
                            "type": ["string", "null"]
                        },
                        "event_type": {
                            "type": ["string", "null"]
                        },
                        "test_date": {
                            "type": ["string", "null"]
                        },
                        "interview_date": {
                            "type": ["string", "null"]
                        },
                        "reporting_time": {
                            "type": ["string", "null"]
                        },
                        "test_time": {
                            "type": ["string", "null"]
                        },
                        "venue": {
                            "type": ["string", "null"]
                        },
                        "application_deadline": {
                            "type": ["string", "null"]
                        },
                        "application_link": {
                            "type": ["string", "null"]
                        },
                        "eligible_branches": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "eligible_degrees": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "open_to_all_branches": {
                            "type": "boolean"
                        }
                    },
                    "required": [
                        "company",
                        "role",
                        "event_type",
                        "test_date",
                        "interview_date",
                        "reporting_time",
                        "test_time",
                        "venue",
                        "application_deadline",
                        "application_link",
                        "eligible_branches",
                        "eligible_degrees",
                        "open_to_all_branches"
                    ],
                    "additionalProperties": False
                }
            }
        }
    )

    content = response.choices[0].message.content

    return json.loads(content)
