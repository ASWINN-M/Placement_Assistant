import inspect
import os
from pathlib import Path

from google_oauth import get_google_credentials, running_in_ci


def test_ci_never_opens_browser():
    os.environ["GITHUB_ACTIONS"] = "true"
    os.environ["CI"] = "true"
    assert running_in_ci() is True

    try:
        get_google_credentials(
            Path("definitely_missing_token.json"),
            Path("credentials.json"),
            ["https://www.googleapis.com/auth/gmail.readonly"],
            "Test",
            "TEST_SECRET",
        )
    except RuntimeError as error:
        assert "CI" in str(error)
        print("OK: CI missing token raises RuntimeError")
    else:
        raise SystemExit("expected RuntimeError in CI")

    from gmail_services import authenticate_gmail, get_gmail_credentials
    from calendar_service import authenticate_calendar, get_calendar_credentials

    for name, fn in [
        ("authenticate_gmail", authenticate_gmail),
        ("get_gmail_credentials", get_gmail_credentials),
        ("authenticate_calendar", authenticate_calendar),
        ("get_calendar_credentials", get_calendar_credentials),
    ]:
        if "run_local_server" in inspect.getsource(fn):
            raise SystemExit(f"{name} still contains run_local_server")
        print(f"OK: {name} has no run_local_server")


if __name__ == "__main__":
    test_ci_never_opens_browser()
    print("ALL CI AUTH CHECKS PASSED")
