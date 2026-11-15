"""Calendar platform: SPFM announcements as calendar events.

Each notice becomes an all-day event:
- with an end date: spans start_date..end_date (end date inclusive), so the
  calendar is "on" during e.g. a pool-maintenance window;
- without one: a single day on the date it was published.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import SPFMConfigEntry
from .api import SPFMUnit
from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import SPFMActivityCoordinator, SPFMDataUpdateCoordinator
from .parsing import MYT

PARALLEL_UPDATES = 0


def _device_info(unit: SPFMUnit) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, unit.key)},
        name=f"{unit.project_name.title()} {unit.unit_no}".strip(),
        manufacturer=MANUFACTURER,
        model=MODEL,
        entry_type=DeviceEntryType.SERVICE,
        configuration_url="https://spfm.com.my/prod/selfcare/dashboard",
    )


def _published_date(item: dict[str, Any]) -> date | None:
    if item.get("published"):
        try:
            return datetime.fromisoformat(item["published"]).astimezone(MYT).date()
        except ValueError:
            pass
    return date.fromisoformat(item["start_date"]) if item.get("start_date") else None


def announcement_to_event(item: dict[str, Any]) -> CalendarEvent | None:
    """Map a normalized announcement to an all-day CalendarEvent."""
    if item.get("end_date"):
        start = date.fromisoformat(item["start_date"]) if item.get("start_date") else _published_date(item)
        end = date.fromisoformat(item["end_date"]) + timedelta(days=1)  # exclusive
    else:
        start = _published_date(item)
        end = start + timedelta(days=1) if start else None
    if start is None or end is None:
        return None
    if end <= start:
        end = start + timedelta(days=1)

    lines = [item.get("text") or item.get("summary") or ""]
    links = [f"PDF: {a['url']}" for a in item.get("attachments") or []]
    links.append(f"Portal: {item.get('url')}")
    description = "\n\n".join(p for p in (lines[0].strip(), "\n".join(links)) if p)

    return CalendarEvent(
        start=start,
        end=end,
        summary=item.get("title") or "SPFM announcement",
        description=description,
        uid=f"spfm-{item.get('id')}",
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: SPFMConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[CalendarEntity] = [SPFMAnnouncementCalendar(coordinator, unit) for unit in coordinator.units]
    if coordinator.activity is not None:
        entities += [SPFMVisitorCalendar(coordinator.activity, unit) for unit in coordinator.units]
    async_add_entities(entities)


class SPFMAnnouncementCalendar(CoordinatorEntity[SPFMDataUpdateCoordinator], CalendarEntity):
    """Management notices for one unit."""

    _attr_has_entity_name = True
    _attr_translation_key = "announcements"
    _attr_icon = "mdi:bullhorn-variant-outline"

    def __init__(self, coordinator: SPFMDataUpdateCoordinator, unit: SPFMUnit) -> None:
        super().__init__(coordinator)
        self._unit = unit
        self._attr_unique_id = f"{unit.unit_id}_announcements_calendar"
        self._attr_device_info = _device_info(unit)

    def _events(self) -> list[CalendarEvent]:
        data = (self.coordinator.data or {}).get(self._unit.key) or {}
        items = (data.get("announcements") or {}).get("items") or []
        events = [e for e in (announcement_to_event(i) for i in items) if e]
        events.sort(key=lambda e: (e.start, e.summary))
        return events

    @property
    def available(self) -> bool:
        return super().available and self._unit.key in (self.coordinator.data or {})

    @property
    def event(self) -> CalendarEvent | None:
        """The current or next notice; falls back to the most recent one."""
        today = dt_util.now().astimezone(MYT).date()
        events = self._events()
        current = [e for e in events if e.start <= today < e.end]
        if current:
            return current[-1]
        upcoming = [e for e in events if e.start > today]
        if upcoming:
            return upcoming[0]
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        lo = dt_util.as_local(start_date).date()
        hi = dt_util.as_local(end_date).date()
        return [e for e in self._events() if e.start <= hi and e.end > lo]


VISIT_LENGTH = timedelta(hours=1)


def visitor_to_event(v: dict[str, Any]) -> CalendarEvent | None:
    """A registered visit as a timed event (1 h, or scan-in to scan-out when scanned)."""
    if not v.get("datetime"):
        return None
    start = datetime.fromisoformat(v["datetime"])
    if v.get("scan_in"):
        start = min(start, datetime.fromisoformat(v["scan_in"]))
    end = datetime.fromisoformat(v["scan_out"]) if v.get("scan_out") else start + VISIT_LENGTH
    if end <= start:
        end = start + VISIT_LENGTH
    who = v.get("name") or "Visitor"
    kind = (v.get("type") or "").title()
    lines = [
        f"{label}: {v[key]}"
        for label, key in (
            ("Type", "type"),
            ("Company", "company"),
            ("Purpose", "purpose"),
            ("Vehicle", "vehicle"),
            ("Status", "status"),
            ("Checked in", "scan_in"),
            ("Checked out", "scan_out"),
            ("Pass", "link"),
        )
        if v.get(key)
    ]
    return CalendarEvent(
        start=start,
        end=end,
        summary=f"{who} ({kind})" if kind else who,
        description="\n".join(lines),
        uid=f"spfm-visit-{v.get('id')}",
    )


class SPFMVisitorCalendar(CoordinatorEntity[SPFMActivityCoordinator], CalendarEntity):
    """Registered visitors, contractors and deliveries for one unit."""

    _attr_has_entity_name = True
    _attr_translation_key = "visitors"
    _attr_icon = "mdi:account-group-outline"

    def __init__(self, coordinator: SPFMActivityCoordinator, unit: SPFMUnit) -> None:
        super().__init__(coordinator)
        self._unit = unit
        self._attr_unique_id = f"{unit.unit_id}_visitors_calendar"
        self._attr_device_info = _device_info(unit)

    def _events(self) -> list[CalendarEvent]:
        data = (self.coordinator.data or {}).get(self._unit.key) or {}
        items = (data.get("visitors") or {}).get("items") or []
        events = [e for e in (visitor_to_event(v) for v in items) if e]
        events.sort(key=lambda e: e.start)
        return events

    @property
    def available(self) -> bool:
        return super().available and self._unit.key in (self.coordinator.data or {})

    @property
    def event(self) -> CalendarEvent | None:
        now = dt_util.now()
        events = self._events()
        current = [e for e in events if e.start <= now < e.end]
        if current:
            return current[0]
        return next((e for e in events if e.start > now), None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [e for e in self._events() if e.start < end_date and e.end > start_date]
