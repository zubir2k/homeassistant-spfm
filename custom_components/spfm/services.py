"""Services: approve or reject a walk-in visitor waiting at the guardhouse."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import SPFMError
from .const import DOMAIN

SERVICE_APPROVE = "approve_visitor"
SERVICE_REJECT = "reject_visitor"

SCHEMA = vol.Schema(
    {
        vol.Required("visitor_id"): vol.Any(cv.positive_int, cv.string),
        vol.Optional("unit_id"): vol.Any(cv.positive_int, cv.string),
    }
)


def _find(hass: HomeAssistant, unit_id: str | None):
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is not ConfigEntryState.LOADED:
            continue
        coord = entry.runtime_data
        for unit in coord.units:
            if unit_id is None or unit.key == str(unit_id):
                return coord, unit
    raise ServiceValidationError(f"No loaded SPFM unit matches unit_id={unit_id}")


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_APPROVE):
        return

    async def _respond(call: ServiceCall, approve: bool) -> None:
        coord, unit = _find(hass, call.data.get("unit_id"))
        try:
            await coord.client.respond_pending_visitor(unit, call.data["visitor_id"], approve)
        except SPFMError as err:
            raise HomeAssistantError(f"SPFM rejected the request: {err}") from err
        if coord.activity is not None:
            await coord.activity.async_request_refresh()

    async def _approve(call: ServiceCall) -> None:
        await _respond(call, True)

    async def _reject(call: ServiceCall) -> None:
        await _respond(call, False)

    hass.services.async_register(DOMAIN, SERVICE_APPROVE, _approve, schema=SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REJECT, _reject, schema=SCHEMA)
