"""Simulated TikTok LIVE that produces random events (for development and tests).

On purpose it also sends spam, links, rude words, repeated messages, gift
streaks and repeated likes, so every filter rule can be seen working.
"""

import asyncio
import random

from streambridge.core.events import ConnectionStatus, RelayEvent
from streambridge.sources.base import EmitEvent, ReportStatus, Source

VIEWERS: tuple[tuple[str, str], ...] = (
    ("Budi", "budi_77"),
    ("Sari", "sari.id"),
    ("Andi", "andi_gaming"),
    ("Putri", "putri_cantik"),
    ("Rizky", "rizky.f"),
    ("Dewi", "dewi_lestari"),
    ("Alex", "alex_us"),
    ("Maria", "maria.br"),
    ("Kenji", "kenji_jp"),
    ("Fatima", "fatima_ae"),
    ("Lucas", "lucas.fr"),
    ("Siti", "siti_nur"),
)

NORMAL_CHAT: tuple[str, ...] = (
    "halo kak!",
    "mantap bang",
    "dari Surabaya hadir",
    "gas terus",
    "hello from Brazil",
    "this stream is great",
    "lagi main apa?",
    "first time here 👋",
    "wkwkwk lucu banget",
    "semangat kak 💪",
    "nice play!",
    "salam dari Medan",
)

SPECIAL_CHAT: tuple[str, ...] = (
    "follow me guys",  # spam, dropped
    "cek bio aku ya",  # spam, dropped
    "mampir ke https://example.com",  # link, replaced
    "anjing seru banget",  # rude word, censored
    "what the fuck was that",  # rude word, censored
)

GIFTS: tuple[str, ...] = ("Rose", "TikTok", "Finger Heart", "Doughnut", "Galaxy", "Lion")

# Relative chance of each event kind.
KIND_WEIGHTS: dict[str, int] = {
    "chat": 50,
    "like": 20,
    "gift": 15,
    "follow": 5,
    "share": 5,
    "repost": 5,
}


class FakeSource(Source):
    """Emits a random event every ``interval`` seconds."""

    name = "fake"

    def __init__(
        self, interval: float = 0.5, seed: int | None = None, max_events: int | None = None
    ) -> None:
        """Create a fake source.

        Args:
            interval: Seconds between events.
            seed: Fixed random seed for repeatable runs.
            max_events: Stop producing after this many events (``None`` = forever).
        """
        self.interval = interval
        self.max_events = max_events
        self._random = random.Random(seed)
        self._last_chat: tuple[tuple[str, str], str] | None = None
        self._last_gift: tuple[tuple[str, str], str] | None = None

    async def run(self, emit: EmitEvent, report_status: ReportStatus) -> None:
        """Emit random events until cancelled (or ``max_events`` is reached)."""
        report_status(ConnectionStatus.CONNECTED, "fake LIVE")
        count = 0
        while self.max_events is None or count < self.max_events:
            emit(self.next_event())
            count += 1
            await asyncio.sleep(self.interval)
        await asyncio.Event().wait()

    def next_event(self) -> RelayEvent:
        """Create one random event."""
        kinds = list(KIND_WEIGHTS)
        kind = self._random.choices(kinds, weights=[KIND_WEIGHTS[k] for k in kinds])[0]
        if kind == "chat":
            return self._chat()
        if kind == "gift":
            return self._gift()
        viewer = self._random.choice(VIEWERS)
        return RelayEvent(kind=kind, platform="tiktok", user=viewer[0], user_id=viewer[1])

    def _chat(self) -> RelayEvent:
        """A chat message: mostly normal, sometimes special or a repeat."""
        roll = self._random.random()
        if self._last_chat is not None and roll < 0.1:
            viewer, text = self._last_chat  # same viewer, same text: duplicate
        else:
            viewer = self._random.choice(VIEWERS)
            pool = SPECIAL_CHAT if roll < 0.25 else NORMAL_CHAT
            text = self._random.choice(pool)
        self._last_chat = (viewer, text)
        return RelayEvent(
            kind="chat", platform="tiktok", user=viewer[0], user_id=viewer[1], text=text
        )

    def _gift(self) -> RelayEvent:
        """A gift: often the same viewer and gift again (a streak)."""
        if self._last_gift is not None and self._random.random() < 0.5:
            viewer, gift_name = self._last_gift
        else:
            viewer = self._random.choice(VIEWERS)
            gift_name = self._random.choice(GIFTS)
        self._last_gift = (viewer, gift_name)
        return RelayEvent(
            kind="gift",
            platform="tiktok",
            user=viewer[0],
            user_id=viewer[1],
            gift_name=gift_name,
            gift_count=self._random.choice((1, 1, 1, 5, 10)),
        )
