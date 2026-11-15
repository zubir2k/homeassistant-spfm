"""New-bill event, bill attributes and the authenticated PDF proxy."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.spfm.const import EVENT_NEW_BILL, PAY_URL

from .test_config_flow import _entry, _listen, _patch_client
from .test_parsing import NEW_BILL


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def test_new_bill_event_and_attributes(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    client = _patch_client()
    events = _listen(hass, EVENT_NEW_BILL)
    with patch("custom_components.spfm.SPFMClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert events == []  # first poll baselines existing bills

        coord = entry.runtime_data
        client.get_billing_and_payment.return_value = NEW_BILL + client.get_billing_and_payment.return_value
        await coord.async_refresh()
        await hass.async_block_till_done()
        await coord.async_refresh()  # same bill again: no second event
        await hass.async_block_till_done()

    assert len(events) == 1
    ev = events[0].data
    assert ev["reference_no"] == "JKRIV2611000001" and ev["amount"] == 183.25 and ev["due"] == "2026-11-21"
    assert ev["outstanding_balance"] == 183.25
    assert ev["pdf_path"] == "/api/spfm/document/1/BILL/3000001"
    assert ev["pay_url"] == PAY_URL

    bal = next(s for s in hass.states.async_all("sensor") if s.entity_id.endswith("outstanding_balance"))
    assert float(bal.state) == 183.25
    assert bal.attributes["pay_url"] == PAY_URL
    assert bal.attributes["bills"][0]["pdf_path"] == "/api/spfm/document/1/BILL/3000001"
    last = next(s for s in hass.states.async_all("sensor") if s.entity_id.endswith("last_bill_amount"))
    assert last.attributes["pdf_path"] == "/api/spfm/document/1/BILL/3000001"


async def test_document_view(hass: HomeAssistant, hass_client) -> None:
    entry = _entry(hass)
    client = _patch_client()
    client.download_document.return_value = (b"%PDF-1.4 test", "application/pdf", "JKRIV.pdf")
    with patch("custom_components.spfm.SPFMClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    http = await hass_client()
    resp = await http.get("/api/spfm/document/1/BILL/3000001")
    assert resp.status == 200
    assert await resp.read() == b"%PDF-1.4 test"
    assert "JKRIV.pdf" in resp.headers["Content-Disposition"]
    assert client.download_document.await_args.args[1:] == ("BILL", "3000001")
    assert (await http.get("/api/spfm/document/1/FOO/1")).status == 400
    assert (await http.get("/api/spfm/document/9/BILL/1")).status == 404


async def test_document_view_requires_auth(hass: HomeAssistant, hass_client_no_auth) -> None:
    entry = _entry(hass)
    with patch("custom_components.spfm.SPFMClient", return_value=_patch_client()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    http = await hass_client_no_auth()
    assert (await http.get("/api/spfm/document/1/BILL/3000001")).status == 401
