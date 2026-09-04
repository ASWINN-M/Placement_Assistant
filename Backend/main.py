import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

def authenticate_gmail():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    
    service = build(
        "gmail",
        "v1",
        credentials=creds
    )

    return service

def get_latest_email(service):
    results = service.users().messages().list(userId="me" , labelIds=["INBOX"],
        maxResults=1).execute()
    messages = results.get("messages", [])
    if not messages:
        return None
    message = service.users().messages().get(userId="me",
        id=messages[0]["id"],
        format="metadata",
        metadataHeaders=["Subject", "From"]).execute()
    return message

def main():

    print("Authenticating with Gmail...")

    service = authenticate_gmail()

    print("Successfully connected to Gmail!\n")

    email = get_latest_email(service)

    if email:

        headers = email["payload"]["headers"]

        subject = "No subject"
        sender = "Unknown sender"

        for header in headers:

            if header["name"].lower() == "subject":
                subject = header["value"]

            elif header["name"].lower() == "from":
                sender = header["value"]

        print("Latest Email")
        print("-------------------------")
        print("Sender :", sender)
        print("Subject:", subject)


if __name__ == "__main__":
    main()