"""The SPFM (Sunway Property Facility Management) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .api import SPFMAuthError, SPFMClient, SPFMError, SPFMUnit
from .const import CONF_UNITS, DOMAIN, PLATFORMS, VERSION
from .coordinator import SPFMActivityCoordinator, SPFMDataUpdateCoordinator
from .frontend import async_register_card
from .services import async_setup_services
from .views import async_register_views

type SPFMConfigEntry = ConfigEntry[SPFMDataUpdateCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the SPFM integration."""
    async_setup_services(hass)
    async_register_views(hass)
    await async_register_card(hass, VERSION)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SPFMConfigEntry) -> bool:
    """Set up SPFM from a config entry."""
    client = SPFMClient(
        async_get_clientsession(hass),
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    try:
        await client.login()
    except SPFMAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except SPFMError as err:
        raise ConfigEntryNotReady(str(err)) from err

    selected = set(entry.options.get(CONF_UNITS, entry.data.get(CONF_UNITS, [])))
    try:
        units = [u for u in await client.get_units() if not selected or u.key in selected]
    except SPFMError as err:
        raise ConfigEntryNotReady(str(err)) from err

    # Remove deselected unit devices from the device registry (stale-devices).
    device_reg = dr.async_get(hass)
    active_unit_keys = {u.key for u in units}
    for device_entry in dr.async_entries_for_config_entry(device_reg, entry.entry_id):
        if any(
            domain == DOMAIN and ident not in active_unit_keys
            for domain, ident in device_entry.identifiers
        ):
            device_reg.async_remove_device(device_entry.id)

    coordinator = SPFMDataUpdateCoordinator(
        hass, client, units, storage_key=entry.entry_id, config_entry=entry
    )
    await coordinator.async_load_seen()
    await coordinator.async_config_entry_first_refresh()

    # The member id is needed for the notification feed; tolerate failure.
    try:
        member_id = (await client.get_account()).get("id")
    except SPFMAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except SPFMError:
        member_id = None
    activity = SPFMActivityCoordinator(
        hass,
        client,
        units,
        member_id,
        coordinator,
        storage_key=entry.entry_id,
        config_entry=entry,
    )
    await activity.async_load_seen()
    await activity.async_refresh()  # best-effort; entities go unavailable on failure
    coordinator.activity = activity
    entry.runtime_data = coordinator
    async_setup_services(hass)
    async_register_views(hass)
    await async_register_card(hass, VERSION)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SPFMConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: SPFMConfigEntry) -> None:
    """Delete stored announcement state when the entry is removed."""
    for suffix, version in (("announcements", 1), ("activity", 2), ("billing", 1)):
        await Store(hass, version, f"{DOMAIN}.{entry.entry_id}_{suffix}").async_remove()


async def _async_update_listener(hass: HomeAssistant, entry: SPFMConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


__all__ = ["SPFMConfigEntry", "SPFMUnit"]
