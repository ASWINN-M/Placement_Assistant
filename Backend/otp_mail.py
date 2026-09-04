import base64
from email.mime.text import MIMEText

from gmail_services import authenticate_gmail


def send_otp_email(to_email, otp_code):
    service = authenticate_gmail()

    body = (
        "Your placement alerts verification code is:\n\n"
        f"{otp_code}\n\n"
        "It expires in 10 minutes.\n"
        "If you did not request this, ignore this email."
    )

    message = MIMEText(body)
    message["to"] = to_email
    message["subject"] = "Placement alerts verification code"

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    service.users().messages().send(
        userId="me",
        body={"raw": raw}
    ).execute()
