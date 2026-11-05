"""The "new version available" check.

StreamBridge only *notifies*: it asks GitHub for the list of releases and, if a newer
one exists, tells the user where to download it. Nothing is downloaded or installed.

Two layers, so most of the logic can be tested without any network:

* ``pick_update`` is a pure function: releases in, "newer release or nothing" out.
* ``check_for_update`` does the HTTP call and never raises.

GitHub's ``/releases/latest`` endpoint skips prereleases, and the first StreamBridge
release is a beta, so the full ``/releases`` list is used.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx
from packaging.version import InvalidVersion, Version

logger = logging.getLogger(__name__)

REPO = "Nabshdq/StreamBridge"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
REQUEST_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class UpdateInfo:
    """A release that is newer than the running program."""

    version: str
    url: str


def _parse(tag: object) -> Version | None:
    """Turn a release tag such as ``v0.1.0-beta`` into a Version, or None if it is not one."""
    if not isinstance(tag, str):
        return None
    try:
        return Version(tag.strip())
    except InvalidVersion:
        logger.debug("Ignoring release tag that is not a version: %r", tag)
        return None


def _safe_url(release: dict[str, Any]) -> str:
    """The release page, but only if it really is one of our own GitHub release pages."""
    url = release.get("html_url")
    if isinstance(url, str) and url.startswith(RELEASES_PAGE + "/"):
        return url
    return RELEASES_PAGE


def pick_update(releases: object, current: str) -> UpdateInfo | None:
    """Return the newest release that is newer than ``current``, or None.

    Rules: drafts and tags that are not versions are skipped. A user on a beta is
    offered both betas and stable releases; a user on a stable version is only
    offered stable releases.
    """
    try:
        running = Version(current)
    except InvalidVersion:
        logger.debug("Running version %r is not a valid version; no update check", current)
        return None
    if not isinstance(releases, list):
        return None

    best: tuple[Version, dict[str, Any]] | None = None
    for release in releases:
        if not isinstance(release, dict) or release.get("draft"):
            continue
        version = _parse(release.get("tag_name"))
        if version is None:
            continue
        is_beta = bool(release.get("prerelease")) or version.is_prerelease
        if is_beta and not running.is_prerelease:
            continue
        if version > running and (best is None or version > best[0]):
            best = (version, release)

    if best is None:
        return None
    return UpdateInfo(version=str(best[0]), url=_safe_url(best[1]))


def _new_client() -> httpx.Client:
    """The HTTP client for the real check.

    Redirects are followed: GitHub answers a renamed repository with a 301, and a
    check that silently stopped working could never tell anyone about its own fix.
    """
    return httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True)


def check_for_update(current: str, *, client: httpx.Client | None = None) -> UpdateInfo | None:
    """Ask GitHub for the releases and return a newer one, or None.

    Never raises: offline, rate-limited (HTTP 403/429), a timeout or an unexpected
    answer all simply mean "no update to show". ``client`` is for tests.
    """
    own_client = client is None
    http = client or _new_client()
    try:
        response = http.get(
            RELEASES_API,
            params={"per_page": 20},
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"StreamBridge/{current}",
            },
        )
        if response.status_code != 200:
            logger.info("Update check skipped: GitHub answered HTTP %s", response.status_code)
            return None
        update = pick_update(response.json(), current)
    except (httpx.HTTPError, ValueError) as error:
        logger.info("Update check skipped: %s", error)
        return None
    finally:
        if own_client:
            http.close()

    if update is None:
        logger.info("Update check: no newer release than %s", current)
    else:
        logger.info("Update check: version %s is available", update.version)
    return update
