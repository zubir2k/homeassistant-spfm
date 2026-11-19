"""Authenticated proxy for SPFM bill/receipt PDFs.

SPFM's Print links need the member's bearer token, which never leaves Home
Assistant. The card asks HA to sign this path (auth/sign_path), then opens it.
"""

from __future__ import annotations

from http import HTTPStatus

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from spfm import DOCUMENT_PATHS, SPFMError
from .const import DOMAIN

DOCUMENT_URL = f"/api/{DOMAIN}/document/{{unit_id}}/{{doc_type}}/{{record_id}}"


def document_path(unit_id: str | int, doc_type: str | None, record_id: str | int | None) -> str | None:
    if not record_id or str(doc_type or "").upper() not in DOCUMENT_PATHS:
        return None
    return f"/api/{DOMAIN}/document/{unit_id}/{str(doc_type).upper()}/{record_id}"


class SPFMDocumentView(HomeAssistantView):
    url = DOCUMENT_URL
    name = f"api:{DOMAIN}:document"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request: web.Request, unit_id: str, doc_type: str, record_id: str) -> web.Response:
        if doc_type.upper() not in DOCUMENT_PATHS or not record_id.isdigit():
            return web.Response(status=HTTPStatus.BAD_REQUEST)
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.state is not ConfigEntryState.LOADED:
                continue
            coord = entry.runtime_data
            unit = next((u for u in coord.units if u.key == unit_id), None)
            if unit is None:
                continue
            try:
                body, ctype, filename = await coord.client.download_document(unit, doc_type, record_id)
            except SPFMError as err:
                return web.Response(status=HTTPStatus.BAD_GATEWAY, text=str(err))
            name = filename or f"spfm-{doc_type.lower()}-{record_id}.pdf"
            return web.Response(
                body=body,
                content_type=ctype,
                headers={"Content-Disposition": f'inline; filename="{name}"', "Cache-Control": "private, max-age=3600"},
            )
        return web.Response(status=HTTPStatus.NOT_FOUND)


def async_register_views(hass: HomeAssistant) -> None:
    key = f"{DOMAIN}_views"
    if hass.data.get(key) or getattr(hass, "http", None) is None:
        return
    hass.http.register_view(SPFMDocumentView(hass))
    hass.data[key] = True
