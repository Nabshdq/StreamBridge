"""Tests for creating the YouTube destination from the user's settings."""

from streambridge.auth.google_oauth import YouTubeAuthError
from streambridge.core.config import AppConfig
from streambridge.core.engine import ConnectionStatus, RelayEngine
from streambridge.core.paths import HOME_OVERRIDE_ENV, quota_file
from streambridge.core.quota import QuotaTracker, shared_quota
from streambridge.core.secrets import YOUTUBE_TOKEN_KEY, MemoryStore
from streambridge.destinations.youtube import YouTubeDestination, youtube_factory
from tests.test_engine import (
    FAST,
    ListSource,
    RecordingDestination,
    RecordingListener,
    ev,
    setup_for,
    wait_until,
)


def set_up(tmp_path, monkeypatch, secret: bool = True, token: bool = True) -> MemoryStore:
    """Point the app folder at ``tmp_path`` and create the files the factory looks for."""
    monkeypatch.setenv(HOME_OVERRIDE_ENV, str(tmp_path))
    store = MemoryStore()
    if secret:
        (tmp_path / "client_secret.json").write_text("{}", encoding="utf-8")
    if token:
        store.set(YOUTUBE_TOKEN_KEY, "{}")
    return store


def test_not_set_up_without_client_secret(tmp_path, monkeypatch) -> None:
    store = set_up(tmp_path, monkeypatch, secret=False)
    assert youtube_factory(AppConfig(), store) is None


def test_not_set_up_without_login(tmp_path, monkeypatch) -> None:
    store = set_up(tmp_path, monkeypatch, token=False)
    assert youtube_factory(AppConfig(), store) is None


def test_set_up_creates_destination_with_live_url(tmp_path, monkeypatch) -> None:
    store = set_up(tmp_path, monkeypatch)
    config = AppConfig()
    config.youtube.live_url = "https://youtu.be/abc"
    destination = youtube_factory(config, store)
    assert isinstance(destination, YouTubeDestination)
    assert destination._live_url == "https://youtu.be/abc"


def test_every_destination_shares_one_quota_counter(tmp_path, monkeypatch) -> None:
    """Stop and Start build a new destination, but the day's count must carry on."""
    store = set_up(tmp_path, monkeypatch)
    first = youtube_factory(AppConfig(), store)
    second = youtube_factory(AppConfig(), store)
    assert first is not None
    assert second is not None
    assert first.quota is second.quota
    assert first.quota is shared_quota(quota_file())
    assert isinstance(first.quota, QuotaTracker)


def test_failed_youtube_start_leaves_the_other_destination_running(tmp_path) -> None:
    def no_login():
        raise YouTubeAuthError("Not logged in to YouTube yet.")

    quota = QuotaTracker(tmp_path / "q.json")
    youtube = YouTubeDestination(MemoryStore(), quota, service_factory=no_login)
    other = RecordingDestination(name="other")
    listener = RecordingListener()
    engine = RelayEngine(
        ListSource([ev("chat", text="halo")]),
        [setup_for(youtube), setup_for(other)],
        FAST,
        listener,
    )
    engine.start()
    wait_until(lambda: len(other.sent) == 1)
    engine.stop()
    assert ("youtube", ConnectionStatus.ERROR) in listener.statuses
