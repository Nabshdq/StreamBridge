"""Entry point for ``python -m streambridge``.

Opens the desktop window. ``--fake`` relays simulated events (for trying the UI).
"""

import sys


def main() -> int:
    """Start StreamBridge."""
    from streambridge.app import run

    return run()


if __name__ == "__main__":
    sys.exit(main())
