"""Smoke test: the package can be imported and reports a version."""

from importlib.metadata import version as installed_version

from packaging.version import Version

import streambridge


def test_package_has_version() -> None:
    """The package exposes a non-empty version string."""
    assert isinstance(streambridge.__version__, str)
    assert streambridge.__version__


def test_version_is_valid_pep440() -> None:
    """The version parses, so the update check can compare it with release tags."""
    Version(streambridge.__version__)


def test_installed_metadata_matches_version() -> None:
    """pyproject.toml reads its version from __init__.py: they must never differ."""
    assert installed_version("streambridge") == streambridge.__version__


def test_release_tag_orders_above_dev_version() -> None:
    """The beta tag v0.1.0-beta is 0.1.0b0, which is newer than 0.1.0.dev0.

    A build that still says dev0 would offer the beta as an update; the release
    step must bump __version__ to the beta first.
    """
    tag = Version("v0.1.0-beta")
    assert tag == Version("0.1.0b0")
    assert tag > Version("0.1.0.dev0")
    assert tag < Version("0.1.0")
