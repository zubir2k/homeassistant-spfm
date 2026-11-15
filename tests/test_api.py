"""API client tests (no network)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from custom_components.spfm.api import SPFMClient, SPFMUnit

UNIT = SPFMUnit(1, "A-01-01", 53, 38, "RESIDENSI JERNIH KAJANG", "DAKSINA HARTA SDN. BHD.")


def test_announcements_walk_all_pages():
    client = SPFMClient(None, "a@b.com", "x")
    pages = {
        1: {"data": [{"id": i} for i in range(1, 11)], "meta": {"current_page": 1, "last_page": 2, "per_page": "10"}},
        2: {"data": [{"id": 11}, {"id": 10}], "meta": {"current_page": 2, "last_page": 2, "per_page": "10"}},
    }
    client._get = AsyncMock(side_effect=lambda path, params: pages[params["page"]])
    items = asyncio.run(client.get_announcements(UNIT))
    assert [i["id"] for i in items] == list(range(1, 12))
    assert client._get.await_count == 2


def test_announcements_single_page():
    client = SPFMClient(None, "a@b.com", "x")
    client._get = AsyncMock(return_value={"data": [{"id": 1}], "meta": {"last_page": 1}})
    assert [i["id"] for i in asyncio.run(client.get_announcements(UNIT))] == [1]
    assert client._get.await_count == 1
