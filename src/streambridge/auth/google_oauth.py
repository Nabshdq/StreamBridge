"""Google sign-in for YouTube (installed-app flow with a loopback redirect).

Every user creates their own Google Cloud project and downloads a
``client_secret.json`` (OAuth client type "Desktop app"). We copy that file
into the app data folder, open the browser for the user to sign in, and keep
the resulting token in the Windows Credential Manager - never in a file.

Heads-up: while the Google consent screen is in "Testing", refresh tokens
expire after 7 days. The setup guide tells users to click "Publish App".
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from streambridge.core.paths import config_dir
from streambridge.core.secrets import YOUTUBE_TOKEN_KEY, SecretStore, load_json, save_json

logger = logging.getLogger(__name__)

YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
CLIENT_SECRET_NAME = "client_secret.json"


class YouTubeAuthError(Exception):
    """Signing in to Google failed or the saved login is no longer valid."""


def client_secret_path() -> Path:
    """Where the user's own ``client_secret.json`` is kept."""
    return config_dir() / CLIENT_SECRET_NAME


def import_client_secret(source: Path, target: Path | None = None) -> Path:
    """Check a downloaded ``client_secret.json`` and copy it into the app folder.

    Raises:
        YouTubeAuthError: if the file is not a "Desktop app" OAuth client.
    """
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise YouTubeAuthError(f"Cannot read {source.name}: {error}") from error
    installed = data.get("installed") if isinstance(data, dict) else None
    if not isinstance(installed, dict) or not installed.get("client_id"):
        raise YouTubeAuthError(
            "This is not a Desktop app client file. Create the OAuth client with "
            "the type 'Desktop app' and download its JSON again."
        )
    destination = target or client_secret_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return destination


def has_client_secret(path: Path | None = None) -> bool:
    """True if the user has already loaded their ``client_secret.json``."""
    return (path or client_secret_path()).is_file()


def login(store: SecretStore, secret_path: Path | None = None) -> Credentials:
    """Open the browser, let the user sign in, and save the token.

    The local redirect uses a random free port on 127.0.0.1 (Google allows any
    port for Desktop app clients).
    """
    path = secret_path or client_secret_path()
    if not path.is_file():
        raise YouTubeAuthError("Load your client_secret.json first.")
    flow = InstalledAppFlow.from_client_secrets_file(str(path), [YOUTUBE_SCOPE])
    credentials = flow.run_local_server(host="127.0.0.1", port=0, open_browser=True)
    _save(store, credentials)
    return credentials


def load_credentials(store: SecretStore) -> Credentials | None:
    """Return the saved login, refreshed if it expired. ``None`` if never logged in.

    Raises:
        YouTubeAuthError: if the saved refresh token no longer works
            (login again).
    """
    info = load_json(store, YOUTUBE_TOKEN_KEY)
    if not info:
        return None
    credentials = Credentials.from_authorized_user_info(info, [YOUTUBE_SCOPE])
    if not credentials.valid:
        if not credentials.refresh_token:
            raise YouTubeAuthError("The saved YouTube login is incomplete. Log in again.")
        try:
            credentials.refresh(Request())
        except RefreshError as error:
            raise YouTubeAuthError("YouTube login expired or was revoked. Log in again.") from error
        _save(store, credentials)
    return credentials


def logout(store: SecretStore) -> None:
    """Forget the saved YouTube login."""
    store.delete(YOUTUBE_TOKEN_KEY)


def _save(store: SecretStore, credentials: Credentials) -> None:
    """Store the login (as JSON) in the secret store, without the short-lived access token.

    Windows Credential Manager keeps a value as UTF-16, which limits it to about
    1,280 characters, and Google access tokens can be long. The refresh token is
    all that is needed: the access token is fetched again at the next start.
    """
    data: dict[str, Any] = json.loads(credentials.to_json())
    data.pop("token", None)
    data.pop("expiry", None)
    save_json(store, YOUTUBE_TOKEN_KEY, data)
