"""Tests for the Google sign-in helper (Google itself is mocked)."""

import json
from unittest.mock import MagicMock

import pytest
from google.auth.exceptions import RefreshError

from streambridge.auth import google_oauth
from streambridge.core.secrets import YOUTUBE_TOKEN_KEY, MemoryStore, save_json

DESKTOP = {"installed": {"client_id": "abc.apps.googleusercontent.com", "client_secret": "x"}}


def write_secret(path, data) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_import_accepts_desktop_client(tmp_path):
    source = tmp_path / "download.json"
    write_secret(source, DESKTOP)
    target = tmp_path / "app" / "client_secret.json"
    assert google_oauth.import_client_secret(source, target) == target
    assert google_oauth.has_client_secret(target)


@pytest.mark.parametrize("data", [{"web": {"client_id": "x"}}, [], {"installed": {}}])
def test_import_rejects_other_client_types(tmp_path, data):
    source = tmp_path / "download.json"
    write_secret(source, data)
    with pytest.raises(google_oauth.YouTubeAuthError):
        google_oauth.import_client_secret(source, tmp_path / "out.json")


def test_import_rejects_garbage(tmp_path):
    source = tmp_path / "download.json"
    source.write_text("nope", encoding="utf-8")
    with pytest.raises(google_oauth.YouTubeAuthError):
        google_oauth.import_client_secret(source, tmp_path / "out.json")


def test_login_needs_the_client_file(tmp_path):
    with pytest.raises(google_oauth.YouTubeAuthError):
        google_oauth.login(MemoryStore(), tmp_path / "missing.json")


def test_login_saves_token_in_the_secret_store(tmp_path, monkeypatch):
    secret = tmp_path / "client_secret.json"
    write_secret(secret, DESKTOP)
    credentials = MagicMock()
    credentials.to_json.return_value = json.dumps({"refresh_token": "r", "token": "t"})
    flow = MagicMock()
    flow.run_local_server.return_value = credentials
    monkeypatch.setattr(
        google_oauth.InstalledAppFlow, "from_client_secrets_file", lambda *a, **k: flow
    )
    store = MemoryStore()
    google_oauth.login(store, secret)
    saved = json.loads(store.get(YOUTUBE_TOKEN_KEY))
    assert saved["refresh_token"] == "r"
    assert "token" not in saved  # too long for Credential Manager; fetched again at start
    assert flow.run_local_server.call_args.kwargs["port"] == 0


def test_load_returns_none_when_never_logged_in():
    assert google_oauth.load_credentials(MemoryStore()) is None


def test_load_refreshes_and_saves_new_token(monkeypatch):
    store = MemoryStore()
    save_json(store, YOUTUBE_TOKEN_KEY, {"refresh_token": "r"})
    credentials = MagicMock(valid=False, refresh_token="r")
    credentials.to_json.return_value = json.dumps({"refresh_token": "r", "token": "new"})
    monkeypatch.setattr(
        google_oauth.Credentials, "from_authorized_user_info", lambda *a, **k: credentials
    )
    assert google_oauth.load_credentials(store) is credentials
    credentials.refresh.assert_called_once()
    assert "token" not in json.loads(store.get(YOUTUBE_TOKEN_KEY))
    assert json.loads(store.get(YOUTUBE_TOKEN_KEY))["refresh_token"] == "r"


def test_revoked_login_asks_to_log_in_again(monkeypatch):
    store = MemoryStore()
    save_json(store, YOUTUBE_TOKEN_KEY, {"refresh_token": "r"})
    credentials = MagicMock(valid=False, refresh_token="r")
    credentials.refresh.side_effect = RefreshError("invalid_grant")
    monkeypatch.setattr(
        google_oauth.Credentials, "from_authorized_user_info", lambda *a, **k: credentials
    )
    with pytest.raises(google_oauth.YouTubeAuthError):
        google_oauth.load_credentials(store)


def test_logout_forgets_token():
    store = MemoryStore()
    save_json(store, YOUTUBE_TOKEN_KEY, {"refresh_token": "r"})
    google_oauth.logout(store)
    assert store.get(YOUTUBE_TOKEN_KEY) is None
