"""Config flow + setup tests (needs pytest-homeassistant-custom-component)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.spfm.api import SPFMAuthError, SPFMUnit
from custom_components.spfm.const import CONF_UNITS, DOMAIN

UNIT = SPFMUnit(1, "A-01-01", 53, 38, "RESIDENSI JERNIH KAJANG", "DAKSINA HARTA SDN. BHD.")
UNIT2 = SPFMUnit(2, "B-02-02", 53, 38, "RESIDENSI JERNIH KAJANG", "DAKSINA HARTA SDN. BHD.")
ANN = json.loads((Path(__file__).parent / "fixture_announcements.json").read_text())
NOTIF = json.loads((Path(__file__).parent / "fixture_notifications.json").read_text())
APPTS = json.loads((Path(__file__).parent / "fixture_appointments.json").read_text())
LINES = json.loads((Path(__file__).parent / "fixture_billing_and_payment.json").read_text())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def _patch_client(units=(UNIT,), login_side_effect=None):
    client = AsyncMock()
    client.login.side_effect = login_side_effect
    client.get_account.return_value = {"id": 99, "name": "Test User"}
    client.get_units.return_value = list(units)
    client.get_billing_and_payment.return_value = LINES
    client.get_outstanding.return_value = []
    client.get_announcements.return_value = ANN
    client.get_dashboard_announcements.return_value = []
    client.get_notifications.return_value = NOTIF
    client.get_appointments.return_value = APPTS
    client.get_pending_visitors.return_value = []
    return client


async def test_user_flow_single_unit(hass: HomeAssistant) -> None:
    client = _patch_client()
    with patch("custom_components.spfm.config_flow.SPFMClient", return_value=client), patch(
        "custom_components.spfm.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "a@b.com", CONF_PASSWORD: "x"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_UNITS] == ["1"]
    assert result["result"].unique_id == "99"


async def test_user_flow_multi_unit(hass: HomeAssistant) -> None:
    client = _patch_client(units=(UNIT, UNIT2))
    with patch("custom_components.spfm.config_flow.SPFMClient", return_value=client), patch(
        "custom_components.spfm.async_setup_entry", return_value=True
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "a@b.com", CONF_PASSWORD: "x"}
        )
        assert result["step_id"] == "units"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_UNITS: ["2"]})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_UNITS] == ["2"]


async def test_user_flow_bad_auth(hass: HomeAssistant) -> None:
    client = _patch_client(login_side_effect=SPFMAuthError("nope"))
    with patch("custom_components.spfm.config_flow.SPFMClient", return_value=client):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "a@b.com", CONF_PASSWORD: "x"}
        )
    assert result["errors"] == {"base": "invalid_auth"}


async def test_setup_creates_sensors(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="99",
        data={CONF_USERNAME: "a@b.com", CONF_PASSWORD: "x", CONF_UNITS: ["1"]},
    )
    entry.add_to_hass(hass)
    client = _patch_client()
    client.get_notifications.return_value = NOTIF[1:]  # newest push is a listed notice
    with patch("custom_components.spfm.SPFMClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    states = {s.entity_id: s for s in hass.states.async_all("sensor")}
    bal = next(s for e, s in states.items() if e.endswith("outstanding_balance"))
    assert float(bal.state) == 0
    pay = next(s for e, s in states.items() if e.endswith("last_payment_amount"))
    assert float(pay.state) == 1253.5
    sc = next(s for e, s in states.items() if e.endswith("service_charge"))
    assert float(sc.state) == 666.4
    assert len(states) == 12
    latest = next(s for e, s in states.items() if e.endswith("latest_announcement"))
    assert latest.state == "JERNIH RESIDENCE – PARCEL AND FOOD DELIVERY COLLECTION"
    assert latest.attributes["url"].endswith("/announcement/detail/15318")
    assert latest.attributes["pdf_url"].endswith(".pdf")
    assert latest.attributes["notice"] is True
    assert latest.attributes["announcements"][0]["pdf_url"].endswith(".pdf")
    active = next(s for e, s in states.items() if e.endswith("_notices"))
    assert len(active.attributes["announcements"]) == 4


async def test_calendar_events(hass: HomeAssistant) -> None:
    from datetime import date

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="99",
        data={CONF_USERNAME: "a@b.com", CONF_PASSWORD: "x", CONF_UNITS: ["1"]},
    )
    entry.add_to_hass(hass)
    client = _patch_client()
    with patch("custom_components.spfm.SPFMClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    cals = [s for s in hass.states.async_all("calendar") if s.entity_id.endswith("_announcements")]
    assert len(cals) == 1
    cal_id = cals[0].entity_id
    resp = await hass.services.async_call(
        "calendar",
        "get_events",
        {"entity_id": cal_id, "start_date_time": "2026-01-01 00:00:00", "end_date_time": "2027-01-01 00:00:00"},
        blocking=True,
        return_response=True,
    )
    events = resp[cal_id]["events"]
    assert len(events) == len(ANN)
    pool = next(e for e in events if "POOL" in e["summary"])
    assert pool["start"] == "2026-10-09" and pool["end"] == "2026-10-14"  # 9-13 Oct inclusive
    parcel = next(e for e in events if "PARCEL" in e["summary"])
    assert parcel["start"] == "2026-10-09" and parcel["end"] == "2026-10-10"
    assert "Portal: https://spfm.com.my/prod/selfcare/announcement/detail/15318" in parcel["description"]
    assert "PDF: " in parcel["description"]


def _entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="99",
        data={CONF_USERNAME: "a@b.com", CONF_PASSWORD: "x", CONF_UNITS: ["1"]},
    )
    entry.add_to_hass(hass)
    return entry


def _listen(hass, *types):
    events = []
    for t in types:
        hass.bus.async_listen(t, lambda e: events.append(e))
    return events


async def test_notification_feed_fires_announcement(hass: HomeAssistant) -> None:
    """A push in the app's notification feed fires even if the notice is missing from listings."""
    from custom_components.spfm.const import EVENT_NEW_ANNOUNCEMENT, EVENT_NOTIFICATION

    entry = _entry(hass)
    client = _patch_client()
    client.get_notifications.return_value = NOTIF[1:]
    events = _listen(hass, EVENT_NEW_ANNOUNCEMENT, EVENT_NOTIFICATION)
    with patch("custom_components.spfm.SPFMClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert events == []  # baseline
        client.get_notifications.return_value = NOTIF
        await entry.runtime_data.activity.async_refresh()
        await hass.async_block_till_done()
        await entry.runtime_data.activity.async_refresh()  # no repeat
        await hass.async_block_till_done()
    types = sorted(e.event_type for e in events)
    assert types == ["spfm_new_announcement", "spfm_notification"]
    ann = next(e for e in events if e.event_type == EVENT_NEW_ANNOUNCEMENT).data
    assert ann["id"] == 15357
    assert ann["title"] == "NOTICE 16_10_2026_ ENHANCEMENT WORKS AT LEVEL 2A CARPARK"
    assert ann["url"].endswith("/announcement/detail/15357")
    assert ann["renotified"] is False
    ann_state = next(s for s in hass.states.async_all("sensor") if s.entity_id.endswith("latest_announcement"))
    assert ann_state.state.startswith("NOTICE 16_10_2026_")
    assert ann_state.attributes["notice"] is False
    assert ann_state.attributes["message"].startswith("NOTICE 16_10_2026_")
    assert ann_state.attributes["announcements"][0]["id"] == 15357
    notices = next(s for s in hass.states.async_all("sensor") if s.entity_id.endswith("_notices"))
    assert all(a["id"] != 15357 for a in notices.attributes["announcements"])
    assert not any(s.entity_id.endswith("latest_notification") for s in hass.states.async_all("sensor"))


async def test_resent_announcement_is_renotified(hass: HomeAssistant) -> None:
    from custom_components.spfm.const import EVENT_NEW_ANNOUNCEMENT

    entry = _entry(hass)
    client = _patch_client()
    events = _listen(hass, EVENT_NEW_ANNOUNCEMENT)
    with patch("custom_components.spfm.SPFMClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        resend = {**NOTIF[1], "id": 99999999, "created_at": "2026-10-16T16:00:00+08:00"}
        client.get_notifications.return_value = [resend, *NOTIF]
        await entry.runtime_data.activity.async_refresh()
        await hass.async_block_till_done()
    assert len(events) == 1 and events[0].data["renotified"] is True
    assert events[0].data["id"] == NOTIF[1]["object_id"]


async def test_activity_survives_restart(hass: HomeAssistant, hass_storage) -> None:
    from custom_components.spfm.const import EVENT_NEW_ANNOUNCEMENT

    entry = _entry(hass)
    key = f"{DOMAIN}.{entry.entry_id}_activity"
    hass_storage[key] = {
        "version": 2,
        "key": key,
        "data": {"seen": {UNIT.key: {
            "notifications": [n["id"] for n in NOTIF[1:]],
            "announced": [n["object_id"] for n in NOTIF[1:]],
            "pending": [], "in": [a["id"] for a in APPTS], "out": [],
        }}},
    }
    client = _patch_client()
    events = _listen(hass, EVENT_NEW_ANNOUNCEMENT)
    with patch("custom_components.spfm.SPFMClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert [e.data["id"] for e in events] == [15357]


async def test_visitor_events_and_services(hass: HomeAssistant) -> None:
    from custom_components.spfm.const import EVENT_VISITOR_ARRIVED, EVENT_VISITOR_PENDING

    entry = _entry(hass)
    client = _patch_client()
    events = _listen(hass, EVENT_VISITOR_PENDING, EVENT_VISITOR_ARRIVED)
    with patch("custom_components.spfm.SPFMClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        client.get_pending_visitors.return_value = [
            {"id": 555, "visitor_name": "Lalamove rider", "visitor_type": {"id": 4, "label": "DELIVERY"},
             "vehicle_reg_no": "ABC123", "company_name": "Lalamove"}
        ]
        arrived = [dict(a) for a in APPTS]
        arrived[0]["scan_in_time"] = "2026-10-16T15:00:00+08:00"
        client.get_appointments.return_value = arrived
        await entry.runtime_data.activity.async_refresh()
        await hass.async_block_till_done()
        assert sorted(e.event_type for e in events) == ["spfm_visitor_arrived", "spfm_visitor_pending"]
        pending = next(e for e in events if e.event_type == EVENT_VISITOR_PENDING).data
        assert pending["id"] == 555 and pending["type"] == "DELIVERY"
        state = next(s for s in hass.states.async_all("sensor") if s.entity_id.endswith("pending_visitors"))
        assert state.state == "1"

        await hass.services.async_call("spfm", "approve_visitor", {"visitor_id": 555}, blocking=True)
        client.respond_pending_visitor.assert_awaited_with(UNIT, 555, True)
        await hass.services.async_call("spfm", "reject_visitor", {"visitor_id": 555}, blocking=True)
        client.respond_pending_visitor.assert_awaited_with(UNIT, 555, False)


async def test_visitor_calendar(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    client = _patch_client()
    with patch("custom_components.spfm.SPFMClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    cal = next(s.entity_id for s in hass.states.async_all("calendar") if s.entity_id.endswith("_visitors"))
    resp = await hass.services.async_call(
        "calendar", "get_events",
        {"entity_id": cal, "start_date_time": "2026-07-01 00:00:00", "end_date_time": "2026-09-01 00:00:00"},
        blocking=True, return_response=True,
    )
    evs = resp[cal]["events"]
    assert len(evs) == 2
    assert evs[0]["summary"] == "Test Contractor (Contractor)"
    assert "Purpose: Fibre installation" in evs[0]["description"]


async def test_failed_appointments_on_first_poll_does_not_flood_on_recovery(hass: HomeAssistant) -> None:
    """If appointments fail on the baseline poll, recovering on the next poll must baseline instead of flooding."""
    from custom_components.spfm.api import SPFMConnectionError
    from custom_components.spfm.const import EVENT_VISITOR_ARRIVED, EVENT_VISITOR_DEPARTED

    entry = _entry(hass)
    client = _patch_client()
    # First poll: appointments fail, but pending succeeds.
    client.get_appointments.side_effect = SPFMConnectionError("timeout")
    events = _listen(hass, EVENT_VISITOR_ARRIVED, EVENT_VISITOR_DEPARTED)
    with patch("custom_components.spfm.SPFMClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert events == []

        # Second poll: appointments succeed with historical scan_in/scan_out records.
        scanned = [dict(a, scan_in_time="2026-08-01T10:00:00+08:00", scan_out_time="2026-08-01T11:00:00+08:00") for a in APPTS]
        client.get_appointments.side_effect = None
        client.get_appointments.return_value = scanned
        await entry.runtime_data.activity.async_refresh()
        await hass.async_block_till_done()
        assert events == []  # must baseline, not flood!


async def test_reconfigure_flow_and_diagnostics(hass: HomeAssistant) -> None:
    from custom_components.spfm.diagnostics import async_get_config_entry_diagnostics

    entry = _entry(hass)
    client = _patch_client()
    with patch("custom_components.spfm.SPFMClient", return_value=client), patch(
        "custom_components.spfm.config_flow.SPFMClient", return_value=client
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        diag = await async_get_config_entry_diagnostics(hass, entry)
        assert diag["entry"]["data"][CONF_USERNAME] == "**REDACTED**"
        assert diag["entry"]["data"][CONF_PASSWORD] == "**REDACTED**"
        assert diag["units"][0]["unit_no"] == "A-01-01"

        result = await entry.start_reconfigure_flow(hass)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reconfigure"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_USERNAME: "a@b.com", CONF_PASSWORD: "new-password"}
        )
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "reconfigure_successful"
        assert entry.data[CONF_PASSWORD] == "new-password"

