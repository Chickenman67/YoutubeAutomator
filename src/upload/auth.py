import json
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"


class AuthError(Exception):
    pass


def load_credentials(token_path: str, scopes=DEFAULT_SCOPES) -> Credentials:
    path = Path(token_path)
    if not path.is_file():
        raise AuthError(f"no stored token at {token_path}")
    info = json.loads(path.read_text(encoding="utf-8"))
    if not info.get("refresh_token"):
        raise AuthError("stored token has no refresh token")
    return Credentials.from_authorized_user_info(info, scopes=scopes)


def save_credentials(credentials, token_path: str) -> Path:
    path = Path(token_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(credentials.to_json(), encoding="utf-8")
    return path


def _client_config(client_id: str, client_secret: str) -> dict:
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": AUTH_URI,
            "token_uri": TOKEN_URI,
            "redirect_uris": ["http://localhost"],
        }
    }


def run_auth_flow(
    token_path: str, client_id: str, client_secret: str, scopes=DEFAULT_SCOPES
) -> Credentials:
    if not client_id or not client_secret:
        raise AuthError("YouTube client id/secret not configured")
    flow = InstalledAppFlow.from_client_config(
        _client_config(client_id, client_secret), scopes=scopes
    )
    credentials = flow.run_local_server(prompt="consent")
    save_credentials(credentials, token_path)
    return credentials


def get_credentials(
    token_path: str,
    client_id: str = "",
    client_secret: str = "",
    scopes=DEFAULT_SCOPES,
) -> Credentials:
    if Path(token_path).is_file():
        return load_credentials(token_path, scopes=scopes)
    return run_auth_flow(token_path, client_id, client_secret, scopes=scopes)


def build_client(credentials, builder=None):
    if builder is None:
        from googleapiclient.discovery import build as builder
    return builder("youtube", "v3", credentials=credentials)
