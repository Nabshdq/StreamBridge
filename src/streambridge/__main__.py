"""Entry point for ``python -m streambridge``.

The real app (Qt window) is added in Phase 5. For now this only prints the version.
"""

from streambridge import __version__


def main() -> None:
    """Start StreamBridge."""
    print(f"StreamBridge {__version__}")


if __name__ == "__main__":
    main()
