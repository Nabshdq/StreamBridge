"""Tests for the "new version available" check. No test touches the network."""

import httpx
import pytest

from streambridge.core import updates
from streambridge.core.updates import (
    RELEASES_PAGE,
    UpdateInfo,
    check_for_update,
    pick_update,
)

STABLE = "0.1.0"
BETA = "0.1.0b0"
DEV = "0.1.0.dev0"


def release(tag: str, *, prerelease: bool = False, draft: bool = False, url: str | None = None):
    """A release as GitHub returns it (only the fields we read)."""
    return {
        "tag_name": tag,
        "prerelease": prerelease,
        "draft": draft,
        "html_url": url or f"{RELEASES_PAGE}/tag/{tag}",
    }


def test_newer_stable_is_offered() -> None:
    update = pick_update([release("v0.2.0")], STABLE)
    assert update == UpdateInfo("0.2.0", f"{RELEASES_PAGE}/tag/v0.2.0")


def test_same_version_is_not_an_update() -> None:
    assert pick_update([release("v0.1.0")], STABLE) is None


def test_older_version_is_not_an_update() -> None:
    assert pick_update([release("v0.0.9")], STABLE) is None


def test_beta_tag_is_newer_than_a_dev_build() -> None:
    update = pick_update([release("v0.1.0-beta", prerelease=True)], DEV)
    assert update is not None
    assert update.version == "0.1.0b0"


def test_beta_is_not_offered_to_a_stable_user() -> None:
    assert pick_update([release("v0.2.0-beta", prerelease=True)], STABLE) is None


def test_prerelease_flag_alone_hides_a_release_from_a_stable_user() -> None:
    """A release flagged as prerelease on GitHub is a beta even if its tag looks stable."""
    assert pick_update([release("v0.2.0", prerelease=True)], STABLE) is None


def test_beta_user_is_offered_a_newer_beta() -> None:
    update = pick_update([release("v0.1.0-beta2", prerelease=True)], BETA)
    assert update is not None
    assert update.version == "0.1.0b2"


def test_beta_user_is_offered_the_stable_release() -> None:
    update = pick_update([release("v0.1.0")], BETA)
    assert update is not None
    assert update.version == "0.1.0"


def test_draft_is_ignored() -> None:
    assert pick_update([release("v9.9.9", draft=True)], STABLE) is None


def test_malformed_tag_is_ignored() -> None:
    releases = [release("nightly-build"), release(""), {"tag_name": None}, release("v0.2.0")]
    update = pick_update(releases, STABLE)
    assert update is not None
    assert update.version == "0.2.0"


def test_empty_list_means_no_update() -> None:
    assert pick_update([], STABLE) is None


def test_highest_of_several_wins() -> None:
    releases = [release("v0.2.0"), release("v0.4.0"), release("v0.3.0")]
    update = pick_update(releases, STABLE)
    assert update is not None
    assert update.version == "0.4.0"


@pytest.mark.parametrize("payload", [{"message": "Not Found"}, "oops", None, [1, "x", None]])
def test_unexpected_shapes_mean_no_update(payload: object) -> None:
    assert pick_update(payload, STABLE) is None


def test_invalid_running_version_means_no_update() -> None:
    assert pick_update([release("v0.2.0")], "not-a-version") is None


def test_foreign_release_url_falls_back_to_our_releases_page() -> None:
    """The link opened in the browser must always be on our own GitHub repository."""
    update = pick_update([release("v0.2.0", url="https://evil.example/download")], STABLE)
    assert update is not None
    assert update.url == RELEASES_PAGE


def make_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_check_returns_the_newer_release() -> None:
    seen: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(200, json=[release("v0.2.0")])

    update = check_for_update(STABLE, client=make_client(handler))
    assert update is not None
    assert update.version == "0.2.0"
    request = seen["request"]
    assert request.url.path == "/repos/Nabshdq/StreamBridge/releases"
    assert request.headers["User-Agent"] == "StreamBridge/0.1.0"
    assert request.headers["Accept"] == "application/vnd.github+json"


def test_check_with_no_releases_yet_is_quietly_none() -> None:
    client = make_client(lambda request: httpx.Response(200, json=[]))
    assert check_for_update(DEV, client=client) is None


@pytest.mark.parametrize("status", [403, 404, 429, 500])
def test_check_http_errors_are_swallowed(status: int) -> None:
    client = make_client(lambda request: httpx.Response(status, json={"message": "no"}))
    assert check_for_update(STABLE, client=client) is None


def test_check_timeout_is_swallowed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    assert check_for_update(STABLE, client=make_client(handler)) is None


def test_check_connection_error_is_swallowed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    assert check_for_update(STABLE, client=make_client(handler)) is None


def test_check_invalid_json_is_swallowed() -> None:
    client = make_client(lambda request: httpx.Response(200, content=b"<html>not json"))
    assert check_for_update(STABLE, client=client) is None


def test_real_client_follows_redirects_and_has_a_timeout() -> None:
    with updates._new_client() as client:
        assert client.follow_redirects is True
        assert client.timeout.read == updates.REQUEST_TIMEOUT_SECONDS


def test_check_follows_a_redirect_after_a_repository_rename() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/Nabshdq/StreamBridge/releases":
            return httpx.Response(
                301, headers={"Location": "https://api.github.com/repositories/1/releases"}
            )
        return httpx.Response(200, json=[release("v0.2.0")])

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    update = check_for_update(STABLE, client=client)
    assert update is not None
    assert update.version == "0.2.0"
