"""Services: approve or reject a walk-in visitor waiting at the guardhouse."""

from __future__ import annotations

from enum import StrEnum

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from spfm import SPFMError, SPFMUnit
from .const import DOMAIN
from .coordinator import SPFMDataUpdateCoordinator


class SPFMService(StrEnum):
    """SPFM services."""

    APPROVE_VISITOR = "approve_visitor"
    REJECT_VISITOR = "reject_visitor"


class SPFMServiceArgument(StrEnum):
    """SPFM service arguments."""

    VISITOR_ID = "visitor_id"
    UNIT_ID = "unit_id"


SERVICE_APPROVE = SPFMService.APPROVE_VISITOR
SERVICE_REJECT = SPFMService.REJECT_VISITOR

SCHEMA = vol.Schema(
    {
        vol.Required(SPFMServiceArgument.VISITOR_ID.value): vol.Any(cv.positive_int, cv.string),
        vol.Optional(SPFMServiceArgument.UNIT_ID.value): vol.Any(cv.positive_int, cv.string),
    }
)


def _find(
    hass: HomeAssistant,
    unit_id: str | int | None,
    visitor_id: str | int | None = None,
) -> tuple[SPFMDataUpdateCoordinator, SPFMUnit]:
    loaded_entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    if unit_id is not None:
        for entry in loaded_entries:
            coord = entry.runtime_data
            for unit in coord.units:
                if unit.key == str(unit_id):
                    return coord, unit
    else:
        # When unit_id is omitted, search pending visitors across all units first.
        if visitor_id is not None:
            for entry in loaded_entries:
                coord = entry.runtime_data
                act_data = coord.activity.data if coord.activity is not None else None
                if not act_data:
                    continue
                for unit in coord.units:
                    vis = (act_data.get(unit.key) or {}).get("visitors") or {}
                    for pending in vis.get("pending") or []:
                        if str(pending.get("id")) == str(visitor_id):
                            return coord, unit
        for entry in loaded_entries:
            coord = entry.runtime_data
            if coord.units:
                return coord, coord.units[0]

    raise ServiceValidationError(
        f"No loaded SPFM unit matches unit_id={unit_id}",
        translation_domain=DOMAIN,
        translation_key="unit_not_found",
        translation_placeholders={"unit_id": str(unit_id)},
    )


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SPFMService.APPROVE_VISITOR):
        return

    async def _respond(call: ServiceCall, approve: bool) -> None:
        visitor_id = call.data[SPFMServiceArgument.VISITOR_ID]
        unit_id = call.data.get(SPFMServiceArgument.UNIT_ID)
        coord, unit = _find(hass, unit_id, visitor_id)
        try:
            await coord.client.respond_pending_visitor(unit, visitor_id, approve)
        except SPFMError as err:
            raise HomeAssistantError(
                f"SPFM rejected the request: {err}",
                translation_domain=DOMAIN,
                translation_key="visitor_action_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        if coord.activity is not None:
            await coord.activity.async_request_refresh()

    async def _approve(call: ServiceCall) -> None:
        await _respond(call, True)

    async def _reject(call: ServiceCall) -> None:
        await _respond(call, False)

    hass.services.async_register(DOMAIN, SPFMService.APPROVE_VISITOR, _approve, schema=SCHEMA)
    hass.services.async_register(DOMAIN, SPFMService.REJECT_VISITOR, _reject, schema=SCHEMA)
