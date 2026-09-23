import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


def running_in_ci() -> bool:
    return (
        os.getenv("GITHUB_ACTIONS") == "true"
        or os.getenv("CI") == "true"
    )


def load_and_refresh_token(token_file: Path, scopes: list[str], label: str):
    """Load a saved OAuth token and refresh it if expired. Never opens a browser."""
    if not token_file.exists():
        print(f"{label}: no token file at {token_file.name}")
        return None

    try:
        credentials = Credentials.from_authorized_user_file(
            str(token_file),
            scopes,
        )
    except Exception as error:
        print(f"{label}: could not read token file: {error}")
        return None

    granted = set(credentials.scopes or [])
    required = set(scopes)
    if granted and not required.issubset(granted):
        print(
            f"{label}: token scopes {sorted(granted)} "
            f"do not include {sorted(required)}"
        )
        return None

    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
            token_file.write_text(credentials.to_json())
            print(f"{label}: refreshed expired token")
        except Exception as error:
            print(f"{label}: token refresh failed: {error}")
            return None

    if credentials.valid:
        print(f"{label}: using pre-authorized token")
        return credentials

    print(f"{label}: token is present but not valid")
    return None


def interactive_local_login(credentials_file: Path, token_file: Path, scopes: list[str]):
    """Browser OAuth for local machines only. Must never be called in CI."""
    if running_in_ci():
        raise RuntimeError(
            "Refusing interactive Google login in CI. "
            "Store a refreshable token as a GitHub secret."
        )

    if not credentials_file.exists():
        raise FileNotFoundError(f"Missing {credentials_file}")

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(
        str(credentials_file),
        scopes,
    )
    credentials = flow.run_local_server(port=0)
    token_file.write_text(credentials.to_json())
    return credentials


def get_google_credentials(
    token_file: Path,
    credentials_file: Path,
    scopes: list[str],
    label: str,
    secret_name: str,
) -> Credentials:
    """
    CI / Actions: load + refresh the secret token only.
    Local: fall back to browser login if the token is missing.
    """
    mode = "CI token-only" if running_in_ci() else "local"
    print(f"{label} auth mode: {mode}")

    credentials = load_and_refresh_token(token_file, scopes, label)
    if credentials and credentials.valid:
        return credentials

    if running_in_ci():
        raise RuntimeError(
            f"{token_file.name} is missing, invalid, or cannot be refreshed "
            f"in CI. Generate a refreshable OAuth token locally and store it "
            f"as the {secret_name} GitHub secret."
        )

    return interactive_local_login(credentials_file, token_file, scopes)
