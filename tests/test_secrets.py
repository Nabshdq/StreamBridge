"""Tests for secret storage (no real Credential Manager is touched)."""

import pytest
from keyring.errors import PasswordDeleteError

from streambridge.core import secrets
from streambridge.core.secrets import KeyringStore, MemoryStore, load_json, save_json


class FakeKeyring:
    """Stands in for the keyring module functions."""

    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, key: str) -> str | None:
        return self.values.get((service, key))

    def set_password(self, service: str, key: str, value: str) -> None:
        self.values[(service, key)] = value

    def delete_password(self, service: str, key: str) -> None:
        if (service, key) not in self.values:
            raise PasswordDeleteError("not found")
        del self.values[(service, key)]


@pytest.fixture
def fake_keyring(monkeypatch: pytest.MonkeyPatch) -> FakeKeyring:
    """Replace the keyring functions used by KeyringStore."""
    fake = FakeKeyring()
    monkeypatch.setattr(secrets.keyring, "get_password", fake.get_password)
    monkeypatch.setattr(secrets.keyring, "set_password", fake.set_password)
    monkeypatch.setattr(secrets.keyring, "delete_password", fake.delete_password)
    return fake


def test_keyring_store_uses_streambridge_service(fake_keyring: FakeKeyring) -> None:
    """Secrets are saved under the StreamBridge service name."""
    store = KeyringStore()
    store.set("twitch.broadcaster", "abc")
    assert fake_keyring.values == {("StreamBridge", "twitch.broadcaster"): "abc"}
    assert store.get("twitch.broadcaster") == "abc"


def test_keyring_store_delete_missing_is_fine(fake_keyring: FakeKeyring) -> None:
    """Deleting something that is not there does not raise."""
    KeyringStore().delete("never-saved")


def test_keyring_store_delete(fake_keyring: FakeKeyring) -> None:
    """Deleted secrets are gone."""
    store = KeyringStore()
    store.set("k", "v")
    store.delete("k")
    assert store.get("k") is None


def test_json_round_trip() -> None:
    """A dict saved as JSON comes back equal."""
    store = MemoryStore()
    save_json(store, "k", {"access_token": "a", "scopes": ["user:write:chat"]})
    assert load_json(store, "k") == {"access_token": "a", "scopes": ["user:write:chat"]}


@pytest.mark.parametrize("stored", [None, "", "{not json", "[1, 2]"])
def test_load_json_missing_or_broken(stored: str | None) -> None:
    """Missing, broken or non-object values load as None."""
    store = MemoryStore()
    if stored is not None:
        store.set("k", stored)
    assert load_json(store, "k") is None
