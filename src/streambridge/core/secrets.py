"""Secret storage (login tokens, API keys).

Secrets live in the Windows Credential Manager through ``keyring``, never in
``config.json`` and never in log files. Each secret is stored under the
service name ``StreamBridge`` and a key such as ``twitch.broadcaster``.

Windows limits one stored secret to 2560 bytes; tokens are far smaller.
"""

import contextlib
import json
import logging
from typing import Any, Protocol

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

logger = logging.getLogger(__name__)

SERVICE_NAME = "StreamBridge"

TWITCH_BROADCASTER_KEY = "twitch.broadcaster"
TWITCH_BOT_KEY = "twitch.bot"
TIKTOK_EULER_KEY = "tiktok.euler_key"


class SecretStore(Protocol):
    """Somewhere to keep secrets by key."""

    def get(self, key: str) -> str | None:
        """Return the secret for ``key``, or ``None`` if there is none."""
        ...

    def set(self, key: str, value: str) -> None:
        """Save ``value`` under ``key`` (replacing any old value)."""
        ...

    def delete(self, key: str) -> None:
        """Remove ``key``; doing nothing if it does not exist."""
        ...


class KeyringStore:
    """Secrets in the Windows Credential Manager (via ``keyring``)."""

    def __init__(self, service: str = SERVICE_NAME) -> None:
        """Create a store for one service name."""
        self.service = service

    def get(self, key: str) -> str | None:
        """Return the secret for ``key``, or ``None`` if missing or unreadable."""
        try:
            return keyring.get_password(self.service, key)
        except KeyringError as error:
            logger.warning("Could not read secret %s: %s", key, error)
            return None

    def set(self, key: str, value: str) -> None:
        """Save a secret. Raises ``KeyringError`` if Windows refuses."""
        keyring.set_password(self.service, key, value)

    def delete(self, key: str) -> None:
        """Remove a secret if it exists."""
        with contextlib.suppress(PasswordDeleteError):
            keyring.delete_password(self.service, key)


class MemoryStore:
    """Secrets kept only in memory (for tests)."""

    def __init__(self) -> None:
        """Start empty."""
        self.values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        """Return the secret for ``key``, or ``None``."""
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        """Save a secret."""
        self.values[key] = value

    def delete(self, key: str) -> None:
        """Remove a secret if it exists."""
        self.values.pop(key, None)


def save_json(store: SecretStore, key: str, data: dict[str, Any]) -> None:
    """Save a small JSON object as one secret."""
    store.set(key, json.dumps(data, separators=(",", ":")))


def load_json(store: SecretStore, key: str) -> dict[str, Any] | None:
    """Load a JSON object saved with ``save_json``; ``None`` if missing or broken."""
    text = store.get(key)
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Stored secret %s is not valid JSON; ignoring it", key)
        return None
    return data if isinstance(data, dict) else None
