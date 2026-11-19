"""Standalone tests for the statement parser (no Home Assistant needed)."""

import importlib.util
import json
from pathlib import Path

from spfm import parsing

LINES = json.loads((Path(__file__).parent / "fixture_billing_and_payment.json").read_text())


def test_fully_paid_summary():
    s = parsing.summarize(LINES, [])
    assert s["outstanding_balance"] == 0
    assert s["next_due_date"] is None
    assert s["last_payment"]["amount"] == 1253.5
    assert s["last_payment"]["date"] == "2026-06-06"
    assert s["service_charge"]["amount"] == 666.4
    assert s["service_charge"]["period"] == "2026-07"
    assert s["sinking_fund"]["amount"] == 66.65
    # three invoices; bill lines grouped by invoice number
    assert len(s["invoices"]) == 3
    inv = {i["reference_no"]: i for i in s["invoices"]}
    assert inv["JKRIV2610001976"]["amount"] == 733.05
    assert s["last_bill"]["date"] == "2026-05-29"


def test_outstanding_from_statement_lines():
    lines = [dict(r) for r in LINES]
    for r in lines:
        if r["reference_no"] == "JKRIV2610001976":
            r["outstanding"] = r["amount"]
    s = parsing.summarize(lines, [])
    assert s["outstanding_balance"] == 733.05
    assert s["next_due_date"] == "2026-10-31"


def test_outstanding_endpoint_preferred():
    out = [{"type": "BILL", "reference_no": "X1", "date": 1782748800, "due": "1793376000", "amount": "100.00", "outstanding": "40.00"}]
    s = parsing.summarize(LINES, out)
    assert s["outstanding_balance"] == 40.0
    assert s["next_due_date"] == "2026-10-31"


ANN = json.loads((Path(__file__).parent / "fixture_announcements.json").read_text())


def test_announcements_summary():
    from datetime import datetime

    now = datetime(2026, 10, 13, 22, 30, tzinfo=parsing.MYT)
    s = parsing.summarize_announcements(ANN, now)
    assert s["total"] == 4
    latest = s["latest"]
    assert latest["id"] == 15318  # newest by created_at, not API order
    assert latest["url"] == "https://spfm.com.my/prod/selfcare/announcement/detail/15318"
    assert latest["attachments"][0]["url"].endswith(".pdf")
    assert latest["published"].startswith("2026-10-09T18:42")
    assert "Dear Valued Owners" in latest["summary"] and "<" not in latest["summary"]
    pool = next(a for a in s["items"] if a["id"] == 15312)
    assert pool["end_date"] == "2026-10-13" and pool["active"] is False
    assert s["active_count"] == 3


def test_portal_datetime_formats():
    assert parsing.parse_portal_datetime("2026-10-09T14:30:00+08:00").hour == 14
    assert parsing.parse_portal_datetime("Fri 2026-10-09 2:30 PM (UTC+08:00)").hour == 14
    assert parsing.parse_portal_datetime("Fri 2026-10-09 12:05 AM (UTC+08:00)").hour == 0
    assert parsing.parse_portal_datetime(None) is None


def test_announcement_feed_matches_notice_shape():
    from spfm import announcement_feed

    notices = {"items": [
        {"id": 1, "title": "CUSTOMER SERVICE AND MANAGEMENT OFFICE CONTACT INFORMATION & SERVICE REQUEST GUIDELINES",
         "active": True, "url": "u1", "text": "Full body", "start_date": "2026-10-09", "end_date": None,
         "attachments": [{"name": "a.pdf", "url": "https://x/a.pdf"}]},
    ]}
    notif = {"items": [
        {"id": 9, "module": "ANNOUNCEMENT", "object_id": 2, "title": "Carpark works", "created": "2026-10-16T13:26:00+08:00", "url": "u2"},
        {"id": 8, "module": "ANNOUNCEMENT", "object_id": 1, "title": "CUSTOMER SERVICE AND MANAGEMENT OFFICE CONTACT INFORMATIO", "created": "2026-10-09T16:10:00+08:00", "url": "u1"},
        {"id": 7, "module": "ANNOUNCEMENT", "object_id": 1, "title": "CUSTOMER SERVICE AND MANAGEMENT OFFICE CONTACT INFORMATIO", "created": "2026-10-09T14:43:00+08:00", "url": "u1"},
        {"id": 6, "module": "OWNER_MANUAL", "object_id": 294, "title": "AC plan", "created": "2026-07-25T16:51:00+08:00"},
    ]}
    feed = announcement_feed(notif, notices)
    rows = feed["items"]
    assert [r["id"] for r in rows] == [2, 1]
    assert all(set(r) == {"id", "title", "published", "active", "url", "pdf_url", "notice"} for r in rows)
    assert rows[0] == {"id": 2, "title": "Carpark works", "published": "2026-10-16T13:26:00+08:00",
                       "active": None, "url": "u2", "pdf_url": None, "notice": False}
    assert rows[1]["title"].endswith("SERVICE REQUEST GUIDELINES") and rows[1]["pdf_url"] == "https://x/a.pdf"
    assert rows[1]["notice"] is True and rows[1]["published"] == "2026-10-09T16:10:00+08:00"
    assert feed["latest"]["message"] == "Carpark works" and feed["total"] == 2
    linked = announcement_feed({"items": notif["items"][1:]}, notices)["latest"]
    assert linked["message"] == "Full body" and linked["start_date"] == "2026-10-09"


# November 2026 style bill: two charge lines on one invoice, both unpaid.
NEW_BILL = [
    {"type": "BILL", "record_id": 3000001, "reference_no": "JKRIV2611000001", "charge_item_name": "SINKING FUND",
     "charge_code": "IVSF", "date": 1793462400, "due": 1795190400, "amount": "16.65", "outstanding": "16.65",
     "year_month_str": "202611"},
    {"type": "BILL", "record_id": 3000002, "reference_no": "JKRIV2611000001", "charge_item_name": "CHARGES",
     "charge_code": "IVSC", "date": 1793462400, "due": 1795190400, "amount": "166.60", "outstanding": "166.60",
     "year_month_str": "202611"},
]


def test_outstanding_bill_grouped_from_statement():
    s = parsing.summarize(NEW_BILL + LINES, [])
    assert s["outstanding_balance"] == 183.25
    assert s["next_due_date"] == "2026-11-21"
    [bill] = s["outstanding_bills"]
    assert bill["reference_no"] == "JKRIV2611000001" and bill["amount"] == 183.25
    assert bill["record_id"] == 3000001 and bill["type"] == "BILL"
    assert [i["item"] for i in bill["items"]] == ["SINKING FUND", "CHARGES"]
    assert s["invoices"][0]["record_id"] == 3000001


def test_outstanding_feed_rows_borrow_statement_fields():
    # The outstanding feed's shape is unverified; a sparse row still links up.
    sparse = [{"reference_no": "JKRIV2611000001", "charge_item_name": "CHARGES", "amount": "166.60", "outstanding": "166.60"}]
    s = parsing.summarize(NEW_BILL + LINES, sparse)
    [bill] = s["outstanding_bills"]
    assert bill["record_id"] == 3000002 and bill["due"] == "2026-11-21" and bill["amount"] == 166.6
