"""Minimal async client for the SPFM (Sunway Property Facility Management) selfcare portal.

The portal at https://spfm.com.my/prod/ is a Vue SPA backed by a Laravel API
under https://spfm.com.my/service. Authentication is a Laravel Passport
"password" grant using the public client credentials shipped in the SPA bundle,
with ``provider=members`` for owner/resident (selfcare) accounts.

This module has no Home Assistant imports so it can be tested standalone.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

PORTAL_BASE = "https://spfm.com.my/prod"
SERVICE_BASE = "https://spfm.com.my/service"
API_BASE = f"{SERVICE_BASE}/api"

# Public Passport client used by the SPFM web app (visible in its JS bundle).
CLIENT_ID = "2"
CLIENT_SECRET = "OiyeoNx5slPvbtYjwqV0R3i91VtTPjXrI1aXTGcv"
PROVIDER = "members"

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=45)
USER_AGENT = "HomeAssistant-SPFM/0.1 (+https://github.com/zubir2k/homeassistant-spfm)"


class SPFMError(Exception):
    """Base error."""

    retryable = False


class SPFMAuthError(SPFMError):
    """Credentials rejected or session cannot be re-established."""


class SPFMTwoFactorRequired(SPFMAuthError):
    """Account has 2FA (OTP) enabled; not supported by this integration."""


class SPFMConnectionError(SPFMError):
    """Network problem or 5xx from the portal (safe to retry)."""

    retryable = True


class SPFMApiError(SPFMError):
    """Unexpected 4xx / malformed payload."""


DOCUMENT_PATHS = {
    "BILL": "selfcare/billing/download-invoice",
    "RECEIPT": "selfcare/billing/download-receipt",
    "CN": "selfcare/billing/download-crnote",
    "DN": "selfcare/billing/download-dbnote",
}


@dataclass(frozen=True, slots=True)
class SPFMUnit:
    """A unit the member owns or occupies."""

    unit_id: int
    unit_no: str
    project_id: int
    company_id: int
    project_name: str = ""
    company_name: str = ""

    @property
    def key(self) -> str:
        return str(self.unit_id)

    @property
    def label(self) -> str:
        return f"{self.unit_no} · {self.project_name}".strip(" ·")

    def as_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "unit_no": self.unit_no,
            "project_id": self.project_id,
            "company_id": self.company_id,
            "project_name": self.project_name,
            "company_name": self.company_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SPFMUnit:
        return cls(
            unit_id=int(data["unit_id"]),
            unit_no=str(data.get("unit_no", "")),
            project_id=int(data["project_id"]),
            company_id=int(data["company_id"]),
            project_name=str(data.get("project_name", "")),
            company_name=str(data.get("company_name", "")),
        )


class SPFMClient:
    """Async client. Pass an aiohttp session (HA's shared one in production)."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        *,
        access_token: str | None = None,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._token = access_token
        self._login_lock = asyncio.Lock()

    @property
    def username(self) -> str:
        return self._username

    @property
    def access_token(self) -> str | None:
        return self._token

    # ------------------------------------------------------------------ auth
    async def login(self) -> str:
        """Run the Passport password grant and store the bearer token."""
        payload = {
            "grant_type": "password",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": "*",
            "username": self._username,
            "password": self._password,
            "provider": PROVIDER,
        }
        try:
            async with self._session.post(
                f"{SERVICE_BASE}/oauth/token",
                json=payload,
                headers={"Accept": "application/json", "User-Agent": USER_AGENT},
                timeout=DEFAULT_TIMEOUT,
            ) as resp:
                body = await _json_or_text(resp)
                if resp.status in (400, 401):
                    raise SPFMAuthError(_message(body) or "Invalid credentials")
                if resp.status >= 500:
                    raise SPFMConnectionError(f"Login HTTP {resp.status}")
                if resp.status != 200 or not isinstance(body, dict):
                    raise SPFMApiError(f"Login HTTP {resp.status}: {body!r:.200}")
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise SPFMConnectionError(f"Login failed: {err}") from err

        token = body.get("access_token")
        if not token:
            raise SPFMApiError("Login response had no access_token")
        self._token = token

        # The SPA only asks for an OTP when the token says 2fa AND the member has it on
        # (or the server forces it). We cannot complete an OTP headlessly.
        if body.get("2fa") and (body.get("force_2fa") is True):
            raise SPFMTwoFactorRequired("This SPFM account requires an OTP")
        if body.get("2fa"):
            account = await self.get_account()
            if int(account.get("enable2fa") or 0) == 1:
                raise SPFMTwoFactorRequired("This SPFM account has 2FA enabled")
        return token

    # --------------------------------------------------------------- request
    async def _get(self, path: str, params: dict[str, Any] | None = None, *, base: str = API_BASE) -> Any:
        return await self._request("GET", path, params=params, base=base)

    async def _put(self, path: str, payload: dict[str, Any], *, base: str = API_BASE) -> Any:
        return await self._request("PUT", path, json=payload, base=base)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        base: str = API_BASE,
    ) -> Any:
        if not self._token:
            async with self._login_lock:
                if not self._token:
                    await self.login()
        for attempt in (1, 2):
            used_token = self._token
            try:
                async with self._session.request(
                    method,
                    f"{base}/{path.lstrip('/')}",
                    params={k: v for k, v in (params or {}).items() if v is not None} or None,
                    json=json,
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {used_token}",
                        "User-Agent": USER_AGENT,
                    },
                    timeout=DEFAULT_TIMEOUT,
                ) as resp:
                    body = await _json_or_text(resp)
                    if resp.status == 401 and attempt == 1:
                        _LOGGER.debug("SPFM token rejected, logging in again")
                        async with self._login_lock:
                            if self._token == used_token:
                                await self.login()
                        continue
                    if resp.status == 401:
                        raise SPFMAuthError("Session rejected after re-login")
                    if resp.status >= 500:
                        raise SPFMConnectionError(f"{method} {path} HTTP {resp.status}")
                    if resp.status not in (200, 201):
                        raise SPFMApiError(f"{method} {path} HTTP {resp.status}: {_message(body)}")
                    return body
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise SPFMConnectionError(f"{method} {path} failed: {err}") from err
        raise SPFMApiError("unreachable")

    # ------------------------------------------------------------- endpoints
    async def get_account(self) -> dict[str, Any]:
        body = await self._get("api/selfcare/my-account", base=SERVICE_BASE)
        return (body or {}).get("data") or {}

    async def get_units(self) -> list[SPFMUnit]:
        """Discover every unit linked to this member, with project/company names."""
        units_b, projects_b, companies_b = await asyncio.gather(
            self._get("selfcare/my-unit"),
            self._get("selfcare/my-project", {"type": ""}),
            self._get("selfcare/my-company", {"type": ""}),
        )
        projects = {p["id"]: p for p in (projects_b or {}).get("data") or []}
        companies = {c["id"]: c for c in (companies_b or {}).get("data") or []}
        units: list[SPFMUnit] = []
        for u in (units_b or {}).get("data") or []:
            proj = projects.get(u.get("project_id"), {})
            units.append(
                SPFMUnit(
                    unit_id=int(u["id"]),
                    unit_no=str(u.get("unit_no", "")),
                    project_id=int(u["project_id"]),
                    company_id=int(u["company_id"]),
                    project_name=str(proj.get("name", "")),
                    company_name=str(
                        proj.get("company_name")
                        or companies.get(u.get("company_id"), {}).get("name", "")
                    ),
                )
            )
        return units

    def _unit_params(self, unit: SPFMUnit) -> dict[str, Any]:
        return {
            "project_id": unit.project_id,
            "company_id": unit.company_id,
            "my_username": self._username,
            "my_unit_id": unit.unit_id,
        }

    async def get_billing_and_payment(self, unit: SPFMUnit, rows: int = 200) -> list[dict[str, Any]]:
        """Statement lines: BILL (per charge item), RECEIPT, DN, CN, newest first."""
        body = await self._get(
            "selfcare/billing/billing-and-payment",
            {**self._unit_params(unit), "page": 1, "rows_per_page": rows, "descending": "true"},
        )
        return list((body or {}).get("data") or [])

    async def get_outstanding(self, unit: SPFMUnit) -> list[dict[str, Any]]:
        """Unpaid items (empty list when fully paid)."""
        body = await self._get(
            "selfcare/billing/outstanding",
            {**self._unit_params(unit), "page": 1, "rows_per_page": 999, "cleared": 0},
        )
        data = (body or {}).get("data") or {}
        if isinstance(data, dict):
            return list(data.get("data") or [])
        return list(data)

    async def download_document(self, unit: SPFMUnit, doc_type: str, record_id: int | str) -> tuple[bytes, str, str | None]:
        """PDF for a statement line, as the portal's Print button fetches it.

        Returns (body, content_type, filename). Needs the bearer token, so Home
        Assistant proxies it rather than linking to SPFM directly.
        """
        path = DOCUMENT_PATHS.get(str(doc_type).upper())
        if path is None:
            raise SPFMApiError(f"No document for type {doc_type!r}")
        if not self._token:
            async with self._login_lock:
                if not self._token:
                    await self.login()
        for attempt in (1, 2):
            used_token = self._token
            try:
                async with self._session.get(
                    f"{API_BASE}/{path}/{record_id}",
                    params=self._unit_params(unit),
                    headers={"Authorization": f"Bearer {used_token}", "User-Agent": USER_AGENT},
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status == 401 and attempt == 1:
                        async with self._login_lock:
                            if self._token == used_token:
                                await self.login()
                        continue
                    if resp.status == 401:
                        raise SPFMAuthError("Session rejected after re-login")
                    if resp.status != 200:
                        raise SPFMApiError(f"Document HTTP {resp.status}")
                    disp = resp.headers.get("Content-Disposition", "")
                    m = re.search(r'filename="?([^";]+)"?', disp)
                    return await resp.read(), resp.content_type or "application/pdf", m.group(1) if m else None
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise SPFMConnectionError(f"Document download failed: {err}") from err
        raise SPFMApiError("unreachable")

    async def get_announcements(self, unit: SPFMUnit, max_pages: int = 5) -> list[dict[str, Any]]:
        """Announcements visible to this unit (title, start/end date, HTML message, attachments).

        The endpoint is paginated server-side at 10 per page and ignores
        ``rows_per_page``, so walk ``meta.last_page`` (capped) and de-duplicate.
        """
        items: list[dict[str, Any]] = []
        seen: set[Any] = set()
        page = 1
        while page <= max_pages:
            body = await self._get(
                "selfcare/announcement",
                {
                    "project_id": unit.project_id,
                    "company_id": unit.company_id,
                    "username": self._username,
                    "unit_id": unit.unit_id,
                    "page": page,
                    "rows_per_page": 50,
                    "per_page": 50,
                    "descending": "true",
                },
            )
            rows = list((body or {}).get("data") or []) if isinstance(body, dict) else []
            for row in rows:
                if row.get("id") not in seen:
                    seen.add(row.get("id"))
                    items.append(row)
            meta = (body or {}).get("meta") or {} if isinstance(body, dict) else {}
            try:
                last = int(meta.get("last_page") or 1)
            except (TypeError, ValueError):
                last = 1
            if not rows or page >= last:
                break
            page += 1
        return items

    def _member_params(self, unit: SPFMUnit) -> dict[str, Any]:
        return {
            "project_id": unit.project_id,
            "company_id": unit.company_id,
            "unit_id": unit.unit_id,
            "username": self._username,
        }

    async def get_dashboard_announcements(self, unit: SPFMUnit) -> list[dict[str, Any]]:
        """Mobile-app feed: every notice for the project incl. expired ones (no attachments)."""
        body = await self._get(
            "selfcare/dashboard/announcement/",
            {**self._member_params(unit), "filter": "start_date", "sort_by": "start_date", "descending": "true"},
        )
        return list((body or {}).get("data") or []) if isinstance(body, dict) else []

    async def get_notifications(self, unit: SPFMUnit, member_id: int | str, rows: int = 30) -> list[dict[str, Any]]:
        """The app's Notifications tab (the same items the SPFM push sends).

        Items: id, module (ANNOUNCEMENT, OWNER_MANUAL, FORM, BOOKING, ...),
        object_id (id of the announcement/form/...), message, created_at.
        """
        body = await self._get(
            "selfcare/selfcare-notification",
            {
                **self._member_params(unit),
                "user_id": member_id,
                "rows_per_page": str(rows),
                "sort_by": "created_at",
                "descending": "true",
            },
        )
        return list((body or {}).get("data") or []) if isinstance(body, dict) else []

    async def get_appointments(self, unit: SPFMUnit) -> list[dict[str, Any]]:
        """Visitor appointments registered for the unit (guests, contractors, deliveries)."""
        body = await self._get(
            "selfcare/appointment/",
            {**self._member_params(unit), "sort_by": "datetime", "descending": "true"},
        )
        return list((body or {}).get("data") or []) if isinstance(body, dict) else []

    async def get_pending_visitors(self, unit: SPFMUnit) -> list[dict[str, Any]]:
        """Walk-in visitors waiting at the guardhouse for the resident's approval."""
        body = await self._get("selfcare/appointment-guest-pending", {**self._member_params(unit), "descending": "true"})
        return list((body or {}).get("data") or []) if isinstance(body, dict) else []

    async def respond_pending_visitor(self, unit: SPFMUnit, visitor_id: int | str, approve: bool) -> Any:
        """Approve or reject a pending walk-in visitor (same call the app makes)."""
        action = "approve" if approve else "reject"
        return await self._put(
            f"selfcare/appointment/appointment-guest-pending/{visitor_id}/{action}",
            self._member_params(unit),
        )

    async def get_recurring_payment(self, unit: SPFMUnit) -> list[dict[str, Any]]:
        body = await self._get("selfcare/billing/recurring-payment", self._unit_params(unit))
        return list((body or {}).get("data") or [])


async def _json_or_text(resp: aiohttp.ClientResponse) -> Any:
    try:
        return await resp.json(content_type=None)
    except (aiohttp.ContentTypeError, ValueError):
        return await resp.text()


def _message(body: Any) -> str:
    if isinstance(body, dict):
        return str(body.get("message") or body.get("error_description") or body.get("error") or "")
    return str(body)[:200]
