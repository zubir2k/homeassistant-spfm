"""DataUpdateCoordinator for the SPFM integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SPFMAuthError, SPFMClient, SPFMError, SPFMUnit
from .const import (
    ACTIVITY_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    EVENT_NEW_BILL,
    EVENT_NOTIFICATION,
    PAY_URL,
    EVENT_VISITOR_ARRIVED,
    EVENT_VISITOR_DEPARTED,
    EVENT_VISITOR_PENDING,
    DEFAULT_RETRY_ATTEMPTS,
    DEFAULT_RETRY_BACKOFF_FACTOR,
    DEFAULT_RETRY_BASE_DELAY,
    DOMAIN,
    EVENT_NEW_ANNOUNCEMENT,
)
from .parsing import (
    merge_announcements,
    summarize,
    summarize_announcements,
    summarize_notifications,
    summarize_visitors,
)
from .retry import with_retry

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")

STORAGE_VERSION = 2


class SPFMDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Fetch billing data for each configured unit. Data is keyed by unit_id (str)."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: SPFMClient,
        units: list[SPFMUnit],
        storage_key: str | None = None,
    ) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=DEFAULT_POLL_INTERVAL)
        self.client = client
        self.units = units
        self.activity: SPFMActivityCoordinator | None = None
        # {unit_key: [bill reference numbers already announced]}
        self._bills_seen: dict[str, list[str]] = {}
        self._store: Store | None = (
            Store(hass, 1, f"{DOMAIN}.{storage_key}_billing") if storage_key else None
        )

    async def async_load_seen(self) -> None:
        if self._store is None:
            return
        stored = await self._store.async_load()
        if isinstance(stored, dict) and isinstance(stored.get("bills"), dict):
            self._bills_seen = stored["bills"]

    def _fire_new_bills(self, data: dict[str, dict[str, Any]]) -> None:
        """Fire spfm_new_bill once per new invoice. The first poll only baselines."""
        from .views import document_path

        changed = False
        for unit in self.units:
            udata = data.get(unit.key)
            if not udata:
                continue
            invoices = udata.get("invoices") or []
            refs = [i["reference_no"] for i in invoices if i.get("reference_no")]
            if unit.key not in self._bills_seen:
                self._bills_seen[unit.key] = refs[:50]
                changed = True
                continue
            known = set(self._bills_seen[unit.key])
            new = [i for i in invoices if i.get("reference_no") and i["reference_no"] not in known]
            for inv in reversed(new):  # oldest first
                _LOGGER.info("SPFM new bill %s for %s: RM%.2f", inv["reference_no"], unit.unit_no, inv["amount"])
                self.hass.bus.async_fire(
                    EVENT_NEW_BILL,
                    {
                        "unit_id": unit.unit_id,
                        "unit_no": unit.unit_no,
                        "project": unit.project_name,
                        "reference_no": inv["reference_no"],
                        "date": inv["date"],
                        "due": inv["due"],
                        "amount": inv["amount"],
                        "outstanding": inv["outstanding"],
                        "items": inv["items"],
                        "outstanding_balance": udata.get("outstanding_balance"),
                        "pdf_path": document_path(unit.key, "BILL", inv.get("record_id")),
                        "pay_url": PAY_URL,
                    },
                )
            if new:
                self._bills_seen[unit.key] = (refs + [r for r in self._bills_seen[unit.key] if r not in refs])[:50]
                changed = True
        if changed and self._store is not None:
            self._store.async_delay_save(lambda: {"bills": self._bills_seen}, 1)

    async def _retry(self, send: Callable[[], Awaitable[T]]) -> T:
        return await with_retry(
            send,
            attempts=DEFAULT_RETRY_ATTEMPTS,
            base_delay=DEFAULT_RETRY_BASE_DELAY,
            backoff_factor=DEFAULT_RETRY_BACKOFF_FACTOR,
            logger=_LOGGER,
        )

    async def _fetch_unit(self, unit: SPFMUnit) -> dict[str, Any]:
        async def _billing() -> dict[str, Any]:
            lines, outstanding = await asyncio.gather(
                self.client.get_billing_and_payment(unit),
                self.client.get_outstanding(unit),
            )
            return summarize(lines, outstanding)

        result = await self._retry(_billing)

        # Announcements are best-effort: a failure keeps the previous list
        # rather than taking the billing sensors down with it.
        try:
            web, dash = await asyncio.gather(
                self._retry(lambda: self.client.get_announcements(unit)),
                self._retry(lambda: self.client.get_dashboard_announcements(unit)),
                return_exceptions=True,
            )
            for part in (web, dash):
                if isinstance(part, SPFMAuthError):
                    raise part
            if isinstance(web, Exception) and isinstance(dash, Exception):
                raise web
            result["announcements"] = summarize_announcements(
                merge_announcements(
                    None if isinstance(web, Exception) else web,
                    None if isinstance(dash, Exception) else dash,
                )
            )
        except SPFMAuthError:
            raise
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("SPFM announcements failed for unit %s: %s", unit.unit_no, err)
            prev = (self.data or {}).get(unit.key) or {}
            result["announcements"] = prev.get("announcements")
        return result

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        if not self.units:
            return {}
        try:
            results = await asyncio.gather(
                *(self._fetch_unit(u) for u in self.units), return_exceptions=True
            )
        except SPFMAuthError as err:  # pragma: no cover - gather returns exceptions
            raise ConfigEntryAuthFailed(str(err)) from err

        # Keep last-known values for a unit that blips while others succeed.
        data: dict[str, dict[str, Any]] = dict(self.data or {})
        ok = 0
        for unit, result in zip(self.units, results, strict=True):
            if isinstance(result, SPFMAuthError):
                raise ConfigEntryAuthFailed(str(result)) from result
            if isinstance(result, Exception):
                _LOGGER.warning("SPFM fetch failed for unit %s: %s", unit.unit_no, result)
                continue
            data[unit.key] = result
            ok += 1

        if ok == 0:
            err = next((r for r in results if isinstance(r, Exception)), None)
            if isinstance(err, SPFMError):
                raise UpdateFailed(f"SPFM API error: {err}") from err
            raise UpdateFailed(f"SPFM update failed: {err}")

        data = {u.key: data[u.key] for u in self.units if u.key in data}
        self._fire_new_bills(data)
        return data


class SPFMActivityCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Fast poll of what the SPFM app pushes: notifications and visitors.

    Fires events for new notifications/announcements, new walk-in visitors
    waiting for approval, and visitor arrival/departure scans. What has been
    fired is persisted so restarts neither replay nor swallow anything.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client: SPFMClient,
        units: list[SPFMUnit],
        member_id: int | None,
        billing: SPFMDataUpdateCoordinator,
        storage_key: str | None = None,
    ) -> None:
        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_activity", update_interval=ACTIVITY_POLL_INTERVAL)
        self.client = client
        self.units = units
        self.member_id = member_id
        self.billing = billing
        # {unit_key: {"notifications": [...ids], "announced": [...object ids],
        #             "pending": [...ids], "in": [...ids], "out": [...ids]}}
        self._seen: dict[str, dict[str, list]] = {}
        self._store: Store | None = (
            Store(hass, STORAGE_VERSION, f"{DOMAIN}.{storage_key}_activity") if storage_key else None
        )

    async def async_load_seen(self) -> None:
        if self._store is None:
            return
        stored = await self._store.async_load()
        if isinstance(stored, dict) and isinstance(stored.get("seen"), dict):
            self._seen = stored["seen"]

    async def _fetch_unit(self, unit: SPFMUnit) -> dict[str, Any]:
        calls: dict[str, Awaitable[Any]] = {
            "appointments": self.client.get_appointments(unit),
            "pending": self.client.get_pending_visitors(unit),
        }
        if self.member_id is not None:
            calls["notifications"] = self.client.get_notifications(unit, self.member_id)
        results = dict(zip(calls, await asyncio.gather(*calls.values(), return_exceptions=True), strict=True))
        prev = (self.data or {}).get(unit.key) or {}
        out: dict[str, Any] = {}
        for key, res in results.items():
            if isinstance(res, SPFMAuthError):
                raise res
            if isinstance(res, Exception):
                _LOGGER.debug("SPFM %s failed for %s: %s", key, unit.unit_no, res)
                results[key] = None
        if all(v is None for v in results.values()):
            raise UpdateFailed(f"SPFM activity fetch failed for {unit.unit_no}")
        if results.get("notifications") is not None:
            out["notifications"] = summarize_notifications(results["notifications"])
        else:
            out["notifications"] = prev.get("notifications")
        if results["appointments"] is None and results["pending"] is None:
            out["visitors"] = prev.get("visitors")
        else:
            old = prev.get("visitors") or {}
            out["visitors"] = summarize_visitors(
                results["appointments"] if results["appointments"] is not None else [],
                results["pending"] if results["pending"] is not None else [],
            )
            if results["appointments"] is None:
                out["visitors"].update({k: old.get(k, []) for k in ("items", "upcoming")})
                out["visitors"]["next"] = old.get("next")
            if results["pending"] is None:
                out["visitors"]["pending"] = old.get("pending", [])
        return out

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        if not self.units:
            return {}
        results = await asyncio.gather(*(self._fetch_unit(u) for u in self.units), return_exceptions=True)
        data: dict[str, dict[str, Any]] = dict(self.data or {})
        ok = 0
        for unit, result in zip(self.units, results, strict=True):
            if isinstance(result, SPFMAuthError):
                raise ConfigEntryAuthFailed(str(result)) from result
            if isinstance(result, Exception):
                _LOGGER.debug("SPFM activity failed for %s: %s", unit.unit_no, result)
                continue
            data[unit.key] = result
            ok += 1
        if ok == 0:
            raise UpdateFailed(f"SPFM activity update failed: {next(iter(results))}")
        data = {u.key: data[u.key] for u in self.units if u.key in data}
        for key, udata in data.items():
            # Expose the listings too so "latest announcement" can merge both feeds.
            udata["announcements"] = ((self.billing.data or {}).get(key) or {}).get("announcements")
        self._fire_events(data)
        return data

    # ------------------------------------------------------------- events
    def _announcement_details(self, unit: SPFMUnit, object_id: Any) -> dict[str, Any]:
        ann = ((self.billing.data or {}).get(unit.key) or {}).get("announcements") or {}
        return next((a for a in ann.get("items") or [] if a.get("id") == object_id), {})

    def _fire_events(self, data: dict[str, dict[str, Any]]) -> None:
        changed = False
        for unit in self.units:
            udata = data.get(unit.key) or {}
            base = {"unit_id": unit.unit_id, "unit_no": unit.unit_no, "project": unit.project_name}
            first = unit.key not in self._seen
            seen = self._seen.setdefault(unit.key, {})
            notif = (udata.get("notifications") or {}).get("items")
            vis = udata.get("visitors") or {}

            def track(bucket: str, ids: list[Any]) -> list[Any]:
                """Return ids not seen before in bucket (and remember all)."""
                nonlocal changed
                had = bucket in seen
                known = set(seen.get(bucket, []))
                new = [i for i in ids if i not in known]
                if new or not had:
                    seen[bucket] = list(known | set(ids))[-500:]
                    changed = True
                return new if had else []  # first sight of a bucket: baseline

            if notif is not None:
                new_ids = set(track("notifications", [n["id"] for n in notif]))
                announced = set(seen.get("announced", []))
                for n in reversed(notif):  # oldest first
                    if n["id"] not in new_ids:
                        continue
                    _LOGGER.info("SPFM notification %s for %s: %s", n["id"], unit.unit_no, n["message"])
                    self.hass.bus.async_fire(EVENT_NOTIFICATION, {**base, **n})
                    if n["module"] == "ANNOUNCEMENT":
                        det = self._announcement_details(unit, n["object_id"])
                        self.hass.bus.async_fire(
                            EVENT_NEW_ANNOUNCEMENT,
                            {
                                **base,
                                "id": n["object_id"],
                                "notification_id": n["id"],
                                "title": det.get("title") or n["title"],
                                "url": n["url"],
                                "published": n["created"],
                                "summary": det.get("summary"),
                                "attachments": det.get("attachments") or [],
                                "renotified": n["object_id"] in announced,
                            },
                        )
                track("announced", [n["object_id"] for n in notif if n["module"] == "ANNOUNCEMENT"])

            if vis:
                pending = vis.get("pending") or []
                new_pending = set(track("pending", [p["id"] for p in pending]))
                for v in (v for v in pending if v["id"] in new_pending):
                    _LOGGER.info("SPFM visitor waiting for approval at %s: %s", unit.unit_no, v["name"])
                    self.hass.bus.async_fire(EVENT_VISITOR_PENDING, {**base, **v})
                items = vis.get("items") or []
                for bucket, field, event in (("in", "scan_in", EVENT_VISITOR_ARRIVED), ("out", "scan_out", EVENT_VISITOR_DEPARTED)):
                    new = set(track(bucket, [v["id"] for v in items if v.get(field)]))
                    for v in items:
                        if v["id"] in new:
                            self.hass.bus.async_fire(event, {**base, **v})
            if first:
                _LOGGER.debug("SPFM activity baselined for %s", unit.unit_no)
        if changed and self._store is not None:
            self._store.async_delay_save(lambda: {"seen": self._seen}, 1)
