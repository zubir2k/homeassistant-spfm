"""API client tests (no network)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from spfm import SPFMClient, SPFMUnit

UNIT = SPFMUnit(1, "A-01-01", 53, 38, "RESIDENSI JERNIH KAJANG", "DAKSINA HARTA SDN. BHD.")


async def test_announcements_walk_all_pages():
    client = SPFMClient(None, "a@b.com", "x")
    pages = {
        1: {"data": [{"id": i} for i in range(1, 11)], "meta": {"current_page": 1, "last_page": 2, "per_page": "10"}},
        2: {"data": [{"id": 11}, {"id": 10}], "meta": {"current_page": 2, "last_page": 2, "per_page": "10"}},
    }
    client._get = AsyncMock(side_effect=lambda path, params: pages[params["page"]])
    items = await client.get_announcements(UNIT)
    assert [i["id"] for i in items] == list(range(1, 12))
    assert client._get.await_count == 2


async def test_announcements_single_page():
    client = SPFMClient(None, "a@b.com", "x")
    client._get = AsyncMock(return_value={"data": [{"id": 1}], "meta": {"last_page": 1}})
    assert [i["id"] for i in await client.get_announcements(UNIT)] == [1]
    assert client._get.await_count == 1


async def test_concurrent_401_relogins_only_once():
    """Concurrent requests that hit 401 with the same expired token only re-login once."""

    class FakeResp:
        def __init__(self, status: int, body: dict):
            self.status = status
            self._body = body

        async def json(self, content_type=None):
            return self._body

        async def __aenter__(self):
            await asyncio.sleep(0.01)
            return self

        async def __aexit__(self, *args):
            pass

    class FakeSession:
        def request(self, method, url, **kwargs):
            auth = kwargs.get("headers", {}).get("Authorization", "")
            if auth == "Bearer expired-token":
                return FakeResp(401, {"message": "Unauthenticated"})
            return FakeResp(200, {"data": []})

    client = SPFMClient(FakeSession(), "a@b.com", "x", access_token="expired-token")
    login_calls = 0

    async def fake_login():
        nonlocal login_calls
        login_calls += 1
        await asyncio.sleep(0.01)
        client._token = "fresh-token"
        return "fresh-token"

    client.login = fake_login  # type: ignore[method-assign]

    await asyncio.gather(
        client._get("selfcare/my-unit"),
        client._get("selfcare/my-project"),
        client._get("selfcare/my-company"),
    )
    assert login_calls == 1

