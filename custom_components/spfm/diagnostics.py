"""Diagnostics support for the SPFM integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import SPFMConfigEntry

TO_REDACT = {
    CONF_USERNAME,
    CONF_PASSWORD,
    "token",
    "access_token",
    "member_id",
    "email",
    "mobile",
    "phone",
    "ic_no",
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
                "data": dict(entry.data),
                "options": dict(entry.options),
            },
            "units": [u.as_dict() for u in coordinator.units],
            "billing_data": coordinator.data,
            "activity_data": activity.data if activity is not None else None,
        },
        TO_REDACT,
    )
