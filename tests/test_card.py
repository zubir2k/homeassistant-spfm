"""The bundled Lovelace card ships with the integration and is versioned with it."""

import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from custom_components.spfm import frontend
from custom_components.spfm.const import VERSION

ROOT = Path(__file__).parents[1] / "custom_components" / "spfm"


def test_card_version_matches_manifest() -> None:
    manifest = json.loads((ROOT / "manifest.json").read_text())
    js = (ROOT / "www" / frontend.CARD_FILE).read_text()
    assert manifest["version"] == VERSION
    assert re.search(r'CARD_VERSION = "([^"]+)"', js).group(1) == VERSION
    assert 'customElements.define("spfm-card"' in js


async def test_register_card_once(monkeypatch) -> None:
    hass = MagicMock()
    hass.data = {}
    hass.http.async_register_static_paths = AsyncMock()
    added: list[str] = []
    monkeypatch.setattr(
        "homeassistant.components.frontend.add_extra_js_url", lambda h, url: added.append(url)
    )
    await frontend.async_register_card(hass, "9.9.9")
    await frontend.async_register_card(hass, "9.9.9")
    hass.http.async_register_static_paths.assert_awaited_once()
    cfg = hass.http.async_register_static_paths.await_args.args[0][0]
    assert cfg.url_path == "/spfm/spfm-card.js" and Path(cfg.path).is_file()
    assert added == ["/spfm/spfm-card.js?v=9.9.9"]


async def test_register_card_without_http() -> None:
    hass = MagicMock()
    hass.data = {}
    hass.http = None
    await frontend.async_register_card(hass, "1")
    assert frontend._DATA_KEY not in hass.data


def test_ready_made_cards_and_brand() -> None:
    js = (ROOT / "www" / frontend.CARD_FILE).read_text()
    for tag in ("spfm-visitors-card", "spfm-updates-card", "spfm-bill-card"):
        assert f'customElements.define("{tag}"' in js
    for name in ("icon.png", "icon@2x.png", "logo.png", "logo@2x.png", "dark_logo.png", "dark_logo@2x.png"):
        assert (ROOT / "brand" / name).is_file()
