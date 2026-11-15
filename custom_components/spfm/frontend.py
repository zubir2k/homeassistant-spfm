"""Serve and auto-register the bundled Lovelace card (custom:spfm-card)."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CARD_FILE = "spfm-card.js"
CARD_URL = f"/{DOMAIN}/{CARD_FILE}"
_DATA_KEY = f"{DOMAIN}_card_registered"


async def async_register_card(hass: HomeAssistant, version: str) -> None:
    """Expose www/spfm-card.js and load it on every dashboard (once per HA run)."""
    if hass.data.get(_DATA_KEY) or getattr(hass, "http", None) is None:
        return
    path = Path(__file__).parent / "www" / CARD_FILE
    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(path), cache_headers=False)]
        )
    except Exception:  # noqa: BLE001 - never block the integration on the card
        _LOGGER.warning("Could not serve the SPFM card", exc_info=True)
        return
    try:
        from homeassistant.components.frontend import add_extra_js_url

        add_extra_js_url(hass, f"{CARD_URL}?v={version}")
    except Exception:  # noqa: BLE001 - frontend not loaded (e.g. headless)
        _LOGGER.debug("Frontend not loaded; add %s as a dashboard resource", CARD_URL)
    hass.data[_DATA_KEY] = True
