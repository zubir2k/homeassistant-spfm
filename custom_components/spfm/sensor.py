"""Sensor platform for the SPFM integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from . import SPFMConfigEntry
from .api import SPFMUnit
from .parsing import announcement_feed
from .const import CURRENCY_RM, DOMAIN, MANUFACTURER, MODEL, PAY_URL
from .views import document_path
from .coordinator import SPFMDataUpdateCoordinator

PARALLEL_UPDATES = 0


def _d(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _get(data: dict[str, Any], block: str, key: str) -> Any:
    return (data.get(block) or {}).get(key)


@dataclass(frozen=True, kw_only=True)
class SPFMSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], StateType | date]
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


MONEY = {"device_class": SensorDeviceClass.MONETARY, "native_unit_of_measurement": CURRENCY_RM, "suggested_display_precision": 2}

SENSORS: tuple[SPFMSensorDescription, ...] = (
    SPFMSensorDescription(
        key="outstanding_balance",
        translation_key="outstanding_balance",
        icon="mdi:cash-clock",
        **MONEY,
        value_fn=lambda d: d.get("outstanding_balance"),
        attrs_fn=lambda d: {
            "items": d.get("outstanding_items", []),
            "bills": d.get("outstanding_bills", []),
            "pay_url": PAY_URL,
        },
    ),
    SPFMSensorDescription(
        key="next_due_date",
        translation_key="next_due_date",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda d: _d(d.get("next_due_date")),
    ),
    SPFMSensorDescription(
        key="last_bill_amount",
        translation_key="last_bill_amount",
        icon="mdi:file-document-outline",
        **MONEY,
        value_fn=lambda d: _get(d, "last_bill", "amount"),
        attrs_fn=lambda d: {
            "reference_no": _get(d, "last_bill", "reference_no"),
            "bill_date": _get(d, "last_bill", "date"),
            "due_date": _get(d, "last_bill", "due"),
            "outstanding": _get(d, "last_bill", "outstanding"),
            "items": _get(d, "last_bill", "items"),
            "invoices": d.get("invoices", []),
        },
    ),
    SPFMSensorDescription(
        key="last_bill_date",
        translation_key="last_bill_date",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda d: _d(_get(d, "last_bill", "date")),
    ),
    SPFMSensorDescription(
        key="last_payment_amount",
        translation_key="last_payment_amount",
        icon="mdi:cash-check",
        **MONEY,
        value_fn=lambda d: _get(d, "last_payment", "amount"),
        attrs_fn=lambda d: {
            "receipt_no": _get(d, "last_payment", "reference_no"),
            "payments": d.get("payments", []),
        },
    ),
    SPFMSensorDescription(
        key="last_payment_date",
        translation_key="last_payment_date",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda d: _d(_get(d, "last_payment", "date")),
    ),
    SPFMSensorDescription(
        key="service_charge",
        translation_key="service_charge",
        icon="mdi:office-building-cog",
        **MONEY,
        value_fn=lambda d: _get(d, "service_charge", "amount"),
        attrs_fn=lambda d: {
            "period": _get(d, "service_charge", "period"),
            "reference_no": _get(d, "service_charge", "reference_no"),
        },
    ),
    SPFMSensorDescription(
        key="sinking_fund",
        translation_key="sinking_fund",
        icon="mdi:piggy-bank-outline",
        **MONEY,
        value_fn=lambda d: _get(d, "sinking_fund", "amount"),
        attrs_fn=lambda d: {
            "period": _get(d, "sinking_fund", "period"),
            "reference_no": _get(d, "sinking_fund", "reference_no"),
        },
    ),
)


def _notices(d: dict[str, Any]) -> dict[str, Any]:
    return d.get("announcements") or {}


def _feed(d: dict[str, Any]) -> dict[str, Any]:
    if "announcement_feed" in d and d["announcement_feed"] is not None:
        return d["announcement_feed"]
    return announcement_feed(d.get("notifications"), d.get("announcements"))


def _top(d: dict[str, Any]) -> dict[str, Any]:
    return _feed(d).get("latest") or {}


def _feed_attrs(d: dict[str, Any]) -> dict[str, Any]:
    feed = _feed(d)
    top = feed.get("latest") or {}
    return {
        **{
            k: top.get(k)
            for k in (
                "id",
                "title",
                "message",
                "published",
                "start_date",
                "end_date",
                "active",
                "url",
                "pdf_url",
                "notice",
            )
        },
        "total": feed.get("total"),
        "announcements": feed.get("items") or [],
    }


def _pdf(a: dict[str, Any]) -> str | None:
    return next((x["url"] for x in a.get("attachments") or []), None)


# Official notices (listings, with PDFs). Runs on the hourly coordinator.
NOTICE_SENSORS: tuple[SPFMSensorDescription, ...] = (
    SPFMSensorDescription(
        key="active_announcements",
        translation_key="active_announcements",
        icon="mdi:file-document-multiple-outline",
        native_unit_of_measurement="notices",
        value_fn=lambda d: _notices(d).get("active_count") if _notices(d) else None,
        attrs_fn=lambda d: {
            "total": _notices(d).get("total"),
            "list_url": _notices(d).get("list_url"),
            "announcements": [
                {
                    "id": a["id"],
                    "title": a["title"],
                    "published": a["published"],
                    "active": a["active"],
                    "url": a["url"],
                    "pdf_url": _pdf(a),
                }
                for a in _notices(d).get("items") or []
            ],
        },
    ),
)

# Announcements = the app's bell (push feed). Runs on the 2-minute coordinator.
FEED_SENSORS: tuple[SPFMSensorDescription, ...] = (
    SPFMSensorDescription(
        key="latest_announcement",
        translation_key="latest_announcement",
        icon="mdi:bullhorn-outline",
        value_fn=lambda d: (_top(d).get("title") or "")[:255] or None,
        attrs_fn=_feed_attrs,
    ),
)


def _vis(d: dict[str, Any]) -> dict[str, Any]:
    return d.get("visitors") or {}


def _visitor_attrs(v: dict[str, Any]) -> dict[str, Any]:
    keys = ("id", "name", "type", "datetime", "company", "purpose", "vehicle", "status", "scan_in", "scan_out", "link")
    return {k: v.get(k) for k in keys}


VISITOR_SENSORS: tuple[SPFMSensorDescription, ...] = (
    SPFMSensorDescription(
        key="pending_visitors",
        translation_key="pending_visitors",
        icon="mdi:account-clock-outline",
        native_unit_of_measurement="visitors",
        value_fn=lambda d: len(_vis(d).get("pending") or []) if _vis(d) else None,
        attrs_fn=lambda d: {
            "visitors": [
                {**_visitor_attrs(v), "image_url": v.get("image_url")}
                for v in _vis(d).get("pending") or []
            ]
        },
    ),
    SPFMSensorDescription(
        key="upcoming_visitors",
        translation_key="upcoming_visitors",
        icon="mdi:account-arrow-right-outline",
        native_unit_of_measurement="visitors",
        value_fn=lambda d: len(_vis(d).get("upcoming") or []) if _vis(d) else None,
        attrs_fn=lambda d: {
            "next": _visitor_attrs(_vis(d)["next"]) if _vis(d).get("next") else None,
            "visitors": [_visitor_attrs(v) for v in _vis(d).get("upcoming") or []],
            "recent": [_visitor_attrs(v) for v in (_vis(d).get("items") or [])[:10]],
        },
    ),
)




async def async_setup_entry(
    hass: HomeAssistant, entry: SPFMConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    activity = coordinator.activity
    entities: list[SPFMSensor] = [SPFMSensor(coordinator, unit, desc) for unit in coordinator.units for desc in SENSORS]
    entities += [SPFMSensor(coordinator, unit, desc) for unit in coordinator.units for desc in NOTICE_SENSORS]
    if activity is not None:
        entities += [
            SPFMSensor(activity, unit, desc)
            for unit in coordinator.units
            for desc in (*FEED_SENSORS, *VISITOR_SENSORS)
        ]

    # v0.5.0 folded "Latest notification" into the announcement sensors.
    registry = er.async_get(hass)
    for unit in coordinator.units:
        if old_id := registry.async_get_entity_id("sensor", DOMAIN, f"{unit.unit_id}_latest_notification"):
            registry.async_remove(old_id)
    async_add_entities(entities)


class SPFMSensor(CoordinatorEntity[DataUpdateCoordinator[dict[str, dict[str, Any]]]], SensorEntity):
    """One billing metric for one unit."""

    _attr_has_entity_name = True
    # Keep bulky lists out of the recorder database.
    _unrecorded_attributes = frozenset(
        {"announcements", "attachments", "summary", "invoices", "payments", "items", "bills",
         "notifications", "visitors", "recent", "next", "message"}
    )
    entity_description: SPFMSensorDescription

    def __init__(self, coordinator: DataUpdateCoordinator[dict[str, dict[str, Any]]], unit: SPFMUnit, desc: SPFMSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = desc
        self._unit = unit
        self._attr_unique_id = f"{unit.unit_id}_{desc.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unit.key)},
            name=f"{unit.project_name.title()} {unit.unit_no}".strip(),
            manufacturer=MANUFACTURER,
            model=MODEL,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://spfm.com.my/prod/selfcare/dashboard",
        )

    @property
    def _data(self) -> dict[str, Any] | None:
        return (self.coordinator.data or {}).get(self._unit.key)

    @property
    def available(self) -> bool:
        return super().available and self._data is not None

    @property
    def native_value(self) -> StateType | date:
        data = self._data
        return self.entity_description.value_fn(data) if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self._data
        base = {"unit_no": self._unit.unit_no, "unit_id": self._unit.key, "project": self._unit.project_name}
        if data and self.entity_description.attrs_fn:
            base.update(self.entity_description.attrs_fn(data))
            self._add_pdf_paths(base)
        return base

    def _add_pdf_paths(self, attrs: dict[str, Any]) -> None:
        """Give every bill/invoice row an HA path to its PDF (see views.py)."""
        for key in ("bills", "invoices"):
            if isinstance(attrs.get(key), list):
                attrs[key] = [
                    {**r, "pdf_path": document_path(self._unit.key, r.get("type") or "BILL", r.get("record_id"))}
                    for r in attrs[key]
                ]
        if self.entity_description.key == "last_bill_amount" and attrs.get("reference_no") is not None:
            last = (self._data or {}).get("last_bill") or {}
            attrs["pdf_path"] = document_path(self._unit.key, "BILL", last.get("record_id"))
