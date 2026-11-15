"""Turn raw SPFM statement lines into a per-unit summary (no HA imports)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

# Portal timestamps are midnights in Malaysia time (UTC+8).
MYT = ZoneInfo("Asia/Kuala_Lumpur")

TYPE_BILL = "BILL"
TYPE_RECEIPT = "RECEIPT"
TYPE_DEBIT_NOTE = "DN"
TYPE_CREDIT_NOTE = "CN"

CHARGE_SERVICE = "IVSC"  # service / maintenance charge
CHARGE_SINKING = "IVSF"  # sinking fund
CHARGE_INSURANCE = "IVIN"
CHARGE_WATER = "IVWA"  # assumed code for metered water; matched by name too


def _to_date(ts: Any) -> date | None:
    if ts in (None, "", 0, "0"):
        return None
    try:
        return datetime.fromtimestamp(int(float(ts)), MYT).date()
    except (TypeError, ValueError, OSError):
        return None


def _money(value: Any) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def _line(row: dict[str, Any]) -> dict[str, Any]:
    d = _to_date(row.get("date"))
    due = _to_date(row.get("due"))
    return {
        "type": row.get("type"),
        "reference_no": row.get("reference_no"),
        "date": d.isoformat() if d else None,
        "due": due.isoformat() if due else None,
        "item": row.get("charge_item_name") or None,
        "charge_code": row.get("charge_code") or None,
        "period": _period(row.get("year_month_str")),
        "amount": _money(row.get("amount")),
        "outstanding": _money(row.get("outstanding")),
        "record_id": row.get("record_id"),
    }


def _period(ym: Any) -> str | None:
    ym = str(ym or "")
    return f"{ym[:4]}-{ym[4:6]}" if len(ym) == 6 and ym.isdigit() else None


def summarize(lines: list[dict[str, Any]], outstanding_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build the coordinator payload for one unit."""
    parsed = [_line(r) for r in lines]
    parsed.sort(key=lambda r: (r["date"] or "", r["reference_no"] or ""), reverse=True)

    bills = [r for r in parsed if r["type"] == TYPE_BILL]
    receipts = [r for r in parsed if r["type"] == TYPE_RECEIPT]

    # Group bill lines by invoice number (one invoice = several charge items).
    invoices: dict[str, dict[str, Any]] = {}
    for r in bills:
        inv = invoices.setdefault(
            r["reference_no"],
            {"reference_no": r["reference_no"], "date": r["date"], "due": r["due"], "amount": 0.0,
             "outstanding": 0.0, "record_id": r["record_id"], "items": []},
        )
        inv["amount"] = round(inv["amount"] + r["amount"], 2)
        inv["outstanding"] = round(inv["outstanding"] + r["outstanding"], 2)
        inv["items"].append({"item": r["item"], "period": r["period"], "amount": r["amount"]})
    invoice_list = sorted(invoices.values(), key=lambda i: (i["date"] or "", i["reference_no"] or ""), reverse=True)

    # Outstanding: prefer the dedicated endpoint; fall back to statement lines.
    if outstanding_rows:
        out_lines = [_line(r) for r in outstanding_rows]
        balance = round(sum(r["outstanding"] or r["amount"] for r in out_lines), 2)
    else:
        out_lines = [r for r in parsed if r["outstanding"] > 0]
        balance = round(sum(r["outstanding"] for r in out_lines), 2)
    # The outstanding feed's row shape is unverified: borrow what it lacks
    # (record id, item name, dates) from the matching statement line.
    by_ref = {}
    for r in parsed:
        by_ref.setdefault((r["type"], r["reference_no"]), []).append(r)
    for r in out_lines:
        match = by_ref.get((r["type"] or TYPE_BILL, r["reference_no"])) or by_ref.get((TYPE_BILL, r["reference_no"])) or []
        twin = next((m for m in match if m["item"] == r["item"]), match[0] if match else None)
        if twin:
            for k in ("record_id", "item", "date", "due", "type", "period"):
                if not r.get(k):
                    r[k] = twin[k]
    due_dates = sorted(r["due"] for r in out_lines if r["due"])
    out_bills = group_outstanding(out_lines)

    def latest_item(code: str, name_hint: str) -> dict[str, Any] | None:
        for r in bills:
            if r["charge_code"] == code or (r["item"] or "").upper() == name_hint:
                return r
        return None

    last_invoice = invoice_list[0] if invoice_list else None
    last_receipt = receipts[0] if receipts else None
    service = latest_item(CHARGE_SERVICE, "CHARGES")
    sinking = latest_item(CHARGE_SINKING, "SINKING FUND")

    return {
        "outstanding_balance": balance,
        "outstanding_items": out_lines,
        "outstanding_bills": out_bills,
        "next_due_date": due_dates[0] if due_dates else None,
        "last_bill": last_invoice,
        "last_payment": last_receipt,
        "service_charge": service,
        "sinking_fund": sinking,
        "invoices": invoice_list[:12],
        "payments": receipts[:12],
        "statement": parsed[:30],
    }


def group_outstanding(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Unpaid lines grouped per document (one bill = several charge items), oldest due first."""
    groups: dict[tuple, dict[str, Any]] = {}
    for r in lines:
        g = groups.setdefault(
            (r["type"], r["reference_no"]),
            {"type": r["type"] or TYPE_BILL, "reference_no": r["reference_no"], "date": r["date"],
             "due": r["due"], "record_id": r["record_id"], "amount": 0.0, "items": []},
        )
        owed = r["outstanding"] or r["amount"]
        g["amount"] = round(g["amount"] + owed, 2)
        g["items"].append({"item": r["item"], "period": r["period"], "amount": owed})
        if not g["record_id"]:
            g["record_id"] = r["record_id"]
    return sorted(groups.values(), key=lambda g: (g["due"] or "9999", g["reference_no"] or ""))


# --------------------------------------------------------------------------
# Announcements
# --------------------------------------------------------------------------
import re  # noqa: E402
from html import unescape  # noqa: E402
from html.parser import HTMLParser  # noqa: E402

PORTAL_ANNOUNCEMENT_URL = "https://spfm.com.my/prod/selfcare/announcement/detail/{id}"
PORTAL_ANNOUNCEMENT_LIST_URL = "https://spfm.com.my/prod/selfcare/announcement/listing"

# The API returns ISO 8601 ("2026-10-09T14:30:00+08:00"); the web UI shows
# "Fri 2026-10-09 2:30 PM (UTC+08:00)". Accept both.
_PORTAL_DT = re.compile(r"(\d{4}-\d{2}-\d{2})\s+(\d{1,2}):(\d{2})\s*([AP]M)", re.I)


def parse_portal_datetime(value: Any) -> datetime | None:
    """Parse the portal's human timestamp into an aware datetime (MYT)."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=MYT)
    except ValueError:
        pass
    m = _PORTAL_DT.search(str(value))
    if not m:
        return None
    day, hh, mm, ampm = m.groups()
    hour = int(hh) % 12 + (12 if ampm.upper() == "PM" else 0)
    y, mo, d = (int(x) for x in day.split("-"))
    return datetime(y, mo, d, hour, int(mm), tzinfo=MYT)


class _TextExtractor(HTMLParser):
    _BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(html: str | None) -> str:
    if not html:
        return ""
    ex = _TextExtractor()
    ex.feed(html)
    text = unescape("".join(ex.parts)).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def _announcement(raw: dict[str, Any], now: datetime) -> dict[str, Any]:
    start = parse_portal_datetime(raw.get("start_date"))
    end = parse_portal_datetime(raw.get("end_date"))
    created = parse_portal_datetime(raw.get("created_at"))
    notified = parse_portal_datetime(raw.get("last_notification"))
    text = html_to_text(raw.get("message"))
    return {
        "id": raw.get("id"),
        "title": (raw.get("title") or "").strip(),
        "url": PORTAL_ANNOUNCEMENT_URL.format(id=raw.get("id")),
        "published": (notified or created or start).isoformat() if (notified or created or start) else None,
        "start_date": start.date().isoformat() if start else None,
        "end_date": end.date().isoformat() if end else None,
        "active": (start is None or start <= now) and (end is None or end > now),
        "summary": text[:400] + ("…" if len(text) > 400 else ""),
        "text": text,
        "attachments": [
            {"name": a.get("filename"), "url": a.get("url")}
            for a in raw.get("attachments") or []
            if a.get("url")
        ],
        "image": (raw.get("image") or {}).get("url") if isinstance(raw.get("image"), dict) else raw.get("image"),
        "_sort": (created or start or datetime.min.replace(tzinfo=MYT)).isoformat(),
    }


def summarize_announcements(raw_items: list[dict[str, Any]], now: datetime | None = None) -> dict[str, Any]:
    """Newest-first announcements plus counts. ``now`` is injectable for tests."""
    now = now or datetime.now(MYT)
    items = [_announcement(r, now) for r in raw_items if r.get("id") is not None]
    items.sort(key=lambda a: (a["_sort"], a["id"]), reverse=True)
    for a in items:
        a.pop("_sort", None)
    return {
        "latest": items[0] if items else None,
        "items": items,
        "active_count": sum(1 for a in items if a["active"]),
        "total": len(items),
        "list_url": PORTAL_ANNOUNCEMENT_LIST_URL,
    }


# ---------------------------------------------------------------- merging
def merge_announcements(
    web: list[dict[str, Any]] | None, dashboard: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """Union of the web listing (has attachments, hides expired) and the app's
    dashboard feed (all notices incl. expired, no attachments), keyed by id."""
    merged: dict[Any, dict[str, Any]] = {}
    for row in dashboard or []:
        if row.get("id") is not None:
            merged[row["id"]] = dict(row)
    for row in web or []:
        if row.get("id") is None:
            continue
        base = merged.get(row["id"], {})
        merged[row["id"]] = {**base, **{k: v for k, v in row.items() if v not in (None, "", [])}}
    return list(merged.values())


# ---------------------------------------------------------- notifications
_NOTIF_PREFIX = re.compile(r"^.*?\bNew\s+Announcement\s*-\s*", re.I)


def notification_title(message: str | None) -> str:
    """'RESIDENSI JERNIH KAJANG New Announcement - X' -> 'X'."""
    text = (message or "").strip()
    return _NOTIF_PREFIX.sub("", text, count=1).strip() or text


def _notification(raw: dict[str, Any]) -> dict[str, Any]:
    created = parse_portal_datetime(raw.get("created_at"))
    module = str(raw.get("module") or "").upper()
    obj = raw.get("object_id")
    return {
        "id": raw.get("id"),
        "module": module,
        "object_id": obj,
        "title": notification_title(raw.get("message")) if module == "ANNOUNCEMENT" else (raw.get("message") or "").strip(),
        "message": (raw.get("message") or "").strip(),
        "created": created.isoformat() if created else None,
        "url": PORTAL_ANNOUNCEMENT_URL.format(id=obj) if module == "ANNOUNCEMENT" and obj else None,
    }


def summarize_notifications(raw_items: list[dict[str, Any]]) -> dict[str, Any]:
    items = [_notification(r) for r in raw_items if r.get("id") is not None]
    items.sort(key=lambda n: (n["created"] or "", n["id"]), reverse=True)
    return {"latest": items[0] if items else None, "items": items, "total": len(items)}


# ---------------------------------------------------------------- visitors
def _label(value: Any) -> str | None:
    if isinstance(value, dict):
        return value.get("label") or value.get("name")
    return str(value) if value not in (None, "") else None


def _visitor(raw: dict[str, Any]) -> dict[str, Any]:
    when = parse_portal_datetime(raw.get("datetime") or raw.get("appointment_datetime"))
    scan_in = parse_portal_datetime(raw.get("scan_in_time"))
    scan_out = parse_portal_datetime(raw.get("scan_out_time"))
    return {
        "id": raw.get("id"),
        "name": (raw.get("visitor_name") or raw.get("appointment_name") or "").strip(),
        "type": _label(raw.get("visitor_type")),
        "datetime": when.isoformat() if when else None,
        "company": raw.get("company_name") or None,
        "purpose": raw.get("purpose") or raw.get("appointment_purpose") or None,
        "vehicle": raw.get("vehicle_reg_no") or None,
        "arrive_by": raw.get("arrive_by") or None,
        "persons": raw.get("no_of_person"),
        "status": _label(raw.get("status")),
        "scan_in": scan_in.isoformat() if scan_in else None,
        "scan_out": scan_out.isoformat() if scan_out else None,
        "link": raw.get("appointment_link") or None,
        "image_url": raw.get("image_url") or None,
        "recurring": bool(raw.get("is_recurring")),
    }


def summarize_visitors(
    appointments: list[dict[str, Any]] | None,
    pending: list[dict[str, Any]] | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(MYT)
    today = now.astimezone(MYT).replace(hour=0, minute=0, second=0, microsecond=0)
    items = [_visitor(r) for r in appointments or [] if r.get("id") is not None]
    items.sort(key=lambda v: (v["datetime"] or "", v["id"]), reverse=True)
    upcoming = sorted(
        (v for v in items if v["datetime"] and datetime.fromisoformat(v["datetime"]) >= today and not v["scan_out"]),
        key=lambda v: v["datetime"],
    )
    pend = [_visitor(r) for r in pending or [] if r.get("id") is not None]
    return {
        "items": items,
        "upcoming": upcoming,
        "next": upcoming[0] if upcoming else None,
        "pending": pend,
    }

def announcement_feed(
    notifications: dict[str, Any] | None,
    notices: dict[str, Any] | None,
    limit: int = 15,
) -> dict[str, Any]:
    """Announcements as the app's bell shows them, shaped like the notice list.

    One row per announcement (re-sent pushes fold into the newest). When an
    announcement points at an official notice (its object_id is a notice id),
    the notice's full title, text, dates and PDF are used and ``notice`` is
    true. Otherwise only the push text exists (SPFM cuts it at ~60 chars).
    """
    by_id = {a.get("id"): a for a in (notices or {}).get("items") or []}
    rows: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for n in (notifications or {}).get("items") or []:
        oid = n.get("object_id")
        if n.get("module") != "ANNOUNCEMENT" or oid in seen:
            continue
        seen.add(oid)
        linked = by_id.get(oid)
        rows.append(
            {
                "id": oid,
                "title": (linked or {}).get("title") or n.get("title"),
                "published": n.get("created"),
                "active": (linked or {}).get("active"),
                "url": n.get("url"),
                "pdf_url": next((x["url"] for x in (linked or {}).get("attachments") or []), None),
                "notice": linked is not None,
                # not exposed in the list; used for the latest row
                "_message": (linked or {}).get("text") or n.get("title"),
                "_start": (linked or {}).get("start_date"),
                "_end": (linked or {}).get("end_date"),
            }
        )
    latest = dict(rows[0]) if rows else None
    for r in rows:
        for k in ("_message", "_start", "_end"):
            r.pop(k, None)
    if latest:
        latest["message"] = latest.pop("_message")
        latest["start_date"] = latest.pop("_start")
        latest["end_date"] = latest.pop("_end")
    return {"latest": latest, "items": rows[:limit], "total": len(rows)}
