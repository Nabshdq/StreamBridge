"""Smoke test: the package can be imported and reports a version."""

import streambridge


def test_package_has_version() -> None:
    """The package exposes a non-empty version string."""
    assert isinstance(streambridge.__version__, str)
    assert streambridge.__version__
