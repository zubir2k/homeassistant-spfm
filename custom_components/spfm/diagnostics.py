"""Diagnostics support for the SPFM integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import SPFMConfigEntry
from .const import CONF_ACCOUNT_ID

TO_REDACT = {
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_ACCOUNT_ID,
    "account_id",
    "token",
    "access_token",
    "member_id",
    "email",
    "mobile",
    "phone",
    "ic_no",
    # Property & unit identifiers
    "unit_no",
    "project_name",
    "unit_id",
    "unit_key",
    "project_id",
    # Visitor personal data
    "name",
    "visitor_name",
    "appointment_name",
    "vehicle",
    "vehicle_reg_no",
    "company",
    "link",
    "appointment_link",
    "image_url",
    "purpose",
    "appointment_purpose",
    # Notification & announcement personal messages
    "message",
    "short_message",
    "title",
    "url",
    "pdf_url",
    "pdf_path",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SPFMConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    activity = coordinator.activity
    return async_redact_data(
        {
            "entry": {
                "title": entry.title,
                "data": dict(entry.data),
                "options": dict(entry.options),
            },
            "units": [u.as_dict() for u in coordinator.units],
            "billing_data": coordinator.data,
            "activity_data": activity.data if activity is not None else None,
        },
        TO_REDACT,
    )
