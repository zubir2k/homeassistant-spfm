"""Config flow for the SPFM integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    SPFMAuthError,
    SPFMClient,
    SPFMConnectionError,
    SPFMError,
    SPFMTwoFactorRequired,
    SPFMUnit,
)
from .const import CONF_ACCOUNT_ID, CONF_UNITS, DOMAIN

_LOGGER = logging.getLogger(__name__)

CREDS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL, autocomplete="username")
        ),
        vol.Required(CONF_PASSWORD): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD, autocomplete="current-password")
        ),
    }
)


async def _login_and_discover(
    hass: HomeAssistant, username: str, password: str
) -> tuple[dict[str, Any], list[SPFMUnit]]:
    client = SPFMClient(async_get_clientsession(hass), username, password)
    await client.login()
    account = await client.get_account()
    units = await client.get_units()
    return account, units


def _errors_for(err: Exception) -> str:
    if isinstance(err, SPFMTwoFactorRequired):
        return "two_factor"
    if isinstance(err, SPFMAuthError):
        return "invalid_auth"
    if isinstance(err, SPFMConnectionError):
        return "cannot_connect"
    return "unknown"


def _units_schema(units: list[SPFMUnit], default: list[str]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_UNITS, default=default): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[selector.SelectOptionDict(value=u.key, label=u.label) for u in units],
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                )
            )
        }
    )


class SPFMConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SPFM."""

    VERSION = 1

    def __init__(self) -> None:
        self._creds: dict[str, str] = {}
        self._units: list[SPFMUnit] = []
        self._account: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            try:
                self._account, self._units = await _login_and_discover(self.hass, username, password)
            except SPFMError as err:
                errors["base"] = _errors_for(err)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error logging in to SPFM")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(str(self._account.get("id") or username.lower()))
                self._abort_if_unique_id_configured()
                if not self._units:
                    errors["base"] = "no_units"
                else:
                    self._creds = {CONF_USERNAME: username, CONF_PASSWORD: password}
                    if len(self._units) == 1:
                        return self._create([self._units[0].key])
                    return await self.async_step_units()
        return self.async_show_form(step_id="user", data_schema=CREDS_SCHEMA, errors=errors)

    async def async_step_units(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_UNITS]:
                errors["base"] = "select_at_least_one"
            else:
                return self._create(user_input[CONF_UNITS])
        return self.async_show_form(
            step_id="units",
            data_schema=_units_schema(self._units, [u.key for u in self._units]),
            errors=errors,
        )

    def _create(self, unit_keys: list[str]) -> ConfigFlowResult:
        name = self._account.get("name") or self._creds[CONF_USERNAME]
        return self.async_create_entry(
            title=f"SPFM ({name})",
            data={
                **self._creds,
                CONF_ACCOUNT_ID: self._account.get("id"),
                CONF_UNITS: unit_keys,
            },
        )

    # ------------------------------------------------------------- reauth
    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                await _login_and_discover(self.hass, entry.data[CONF_USERNAME], user_input[CONF_PASSWORD])
            except SPFMError as err:
                errors["base"] = _errors_for(err)
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    )
                }
            ),
            description_placeholders={"username": entry.data[CONF_USERNAME]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SPFMOptionsFlow()


class SPFMOptionsFlow(OptionsFlow):
    """Pick which units to monitor."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self.config_entry
        if user_input is not None:
            if not user_input[CONF_UNITS]:
                errors["base"] = "select_at_least_one"
            else:
                return self.async_create_entry(data={CONF_UNITS: user_input[CONF_UNITS]})
        try:
            _, units = await _login_and_discover(
                self.hass, entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
            )
        except SPFMError as err:
            return self.async_abort(reason=_errors_for(err))
        current = entry.options.get(CONF_UNITS, entry.data.get(CONF_UNITS, []))
        return self.async_show_form(
            step_id="init", data_schema=_units_schema(units, current), errors=errors
        )
