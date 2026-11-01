"""Tests for the event model."""

import dataclasses

import pytest

from streambridge.core.events import (
    EVENT_KINDS,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    RelayEvent,
)


@pytest.mark.parametrize("kind", ["gift", "follow", "share", "repost"])
def test_high_priority_kinds(kind: str) -> None:
    """Gifts, follows, shares and reposts are sent first."""
    assert RelayEvent(kind=kind, platform="tiktok", user="Budi").priority == PRIORITY_HIGH


@pytest.mark.parametrize("kind", ["chat", "like"])
def test_low_priority_kinds(kind: str) -> None:
    """Chat and likes are sent after everything else."""
    assert RelayEvent(kind=kind, platform="tiktok", user="Budi").priority == PRIORITY_LOW


def test_all_six_kinds_exist() -> None:
    """The event model knows exactly the six supported kinds."""
    assert set(EVENT_KINDS) == {"chat", "gift", "follow", "like", "share", "repost"}


def test_event_is_frozen() -> None:
    """Events cannot be changed after creation."""
    event = RelayEvent(kind="chat", platform="tiktok", user="Budi", text="halo")
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.text = "changed"  # type: ignore[misc]


def test_user_key_prefers_id() -> None:
    """The user id identifies a viewer; the name is the fallback."""
    with_id = RelayEvent(kind="like", platform="tiktok", user="Budi", user_id="123")
    without_id = RelayEvent(kind="like", platform="tiktok", user="Budi")
    assert with_id.user_key == "123"
    assert without_id.user_key == "budi"
