"""Tests for SPFM diagnostics."""

from unittest.mock import MagicMock

from custom_components.spfm.const import CONF_ACCOUNT_ID, CONF_UNITS
from custom_components.spfm.diagnostics import async_get_config_entry_diagnostics
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant


async def test_diagnostics_redaction(hass: HomeAssistant) -> None:
    """Test that all personal and authentication data are redacted."""
    entry = MagicMock()
    entry.title = "SPFM (Zubir Jamal)"
    entry.data = {
        CONF_USERNAME: "secret_user",
        CONF_PASSWORD: "secret_password",
        CONF_ACCOUNT_ID: 12345,
        CONF_UNITS: ["100"],
    }
    entry.options = {}

    unit_mock = MagicMock()
    unit_mock.as_dict.return_value = {
        "unit_id": 100,
        "unit_no": "A-10-01",
        "project_id": 56,
        "company_id": 78,
        "project_name": "Jernih Residence",
        "company_name": "SPFM",
    }

    coordinator = MagicMock()
    coordinator.units = [unit_mock]
    coordinator.data = {
        "100": {
            "outstanding_balance": 100.0,
            "announcements": {
                "items": [
                    {
                        "id": 1,
                        "title": "Maintenance Announcement",
                        "message": "Dear resident, maintenance will happen tomorrow.",
                        "url": "https://portal.spfm.com.my/notice/1",
                        "pdf_url": "https://portal.spfm.com.my/notice/1.pdf",
                    }
                ]
            },
        }
    }

    activity = MagicMock()
    activity.data = {
        "100": {
            "visitors": {
                "items": [
                    {
                        "id": 501,
                        "name": "Jane Visitor",
                        "type": "CONTRACTOR",
                        "company": "Grab",
                        "purpose": "Delivery",
                        "vehicle": "ABC 1234",
                        "link": "https://portal.spfm.com.my/visitor/501",
                        "image_url": "https://portal.spfm.com.my/visitor/501.jpg",
                    }
                ]
            },
            "notifications": {
                "items": [
                    {
                        "id": 999,
                        "title": "Visitor Arrived",
                        "message": "Jane Visitor has arrived at guardhouse.",
                        "url": "https://portal.spfm.com.my/notif/999",
                    }
                ]
            },
        }
    }
    coordinator.activity = activity
    entry.runtime_data = coordinator

    diag = await async_get_config_entry_diagnostics(hass, entry)

    # Entry title & credentials redacted
    assert diag["entry"]["title"] == "**REDACTED**"
    assert diag["entry"]["data"][CONF_USERNAME] == "**REDACTED**"
    assert diag["entry"]["data"][CONF_PASSWORD] == "**REDACTED**"
    assert diag["entry"]["data"][CONF_ACCOUNT_ID] == "**REDACTED**"
    assert diag["entry"]["data"][CONF_UNITS] == "**REDACTED**"

    # Unit & property identifiers redacted
    unit = diag["units"][0]
    assert unit["unit_id"] == "**REDACTED**"
    assert unit["unit_no"] == "**REDACTED**"
    assert unit["project_id"] == "**REDACTED**"
    assert unit["project_name"] == "**REDACTED**"
    assert unit["company_name"] == "**REDACTED**"

    # Visitor personal data redacted
    visitor = diag["activity_data"]["100"]["visitors"]["items"][0]
    assert visitor["name"] == "**REDACTED**"
    assert visitor["company"] == "**REDACTED**"
    assert visitor["purpose"] == "**REDACTED**"
    assert visitor["vehicle"] == "**REDACTED**"
    assert visitor["link"] == "**REDACTED**"
    assert visitor["image_url"] == "**REDACTED**"

    # Notifications redacted
    notif = diag["activity_data"]["100"]["notifications"]["items"][0]
    assert notif["title"] == "**REDACTED**"
    assert notif["message"] == "**REDACTED**"
    assert notif["url"] == "**REDACTED**"

    # Announcements redacted
    ann = diag["billing_data"]["100"]["announcements"]["items"][0]
    assert ann["title"] == "**REDACTED**"
    assert ann["message"] == "**REDACTED**"
    assert ann["url"] == "**REDACTED**"
    assert ann["pdf_url"] == "**REDACTED**"
