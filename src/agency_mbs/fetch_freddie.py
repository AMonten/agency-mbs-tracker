"""Download of Freddie Mac MBS disclosure files.

The official source is Freddie Mac's own Capital Markets site
(https://capitalmarkets.freddiemac.com/mbs/security-data/mbs-disclosure-resources),
which links directly to https://freddiemac.mbs-securities.com/ — a React SPA
("Disclosure | Freddie Mac" branding, Freddie's own Google Analytics id) for
the actual bulk downloads. Confirmed real by inspecting its JS bundle
(/static/app.freddie.js) and by capturing real authenticated requests from a
browser session (not guessed):

- GET /api/report/freddie/listyears/<category_id>/<page-slug>
  Which years have data for a section, e.g. category 2
  ("datafiles-singleclass-monthly") returned
  [2025,2026,2024,2019,2021,2022,2023,2018,2020] — Freddie's monthly
  factor history goes back to at least 2018, unlike Ginnie Mae's catalog
  which only ever exposes the current month.

- GET /api/report/freddie/list/<category_id>/<year>
  Full document catalog for that category/year: a list of
  {headingKey, document: {id, name, effectiveDate}}. Confirmed category 2 =
  Monthly (14 headingKeys: security/loan/supplemental/MF variants); the one
  we want is "L1L2_MONTHLY_ONGOING_POOL_LEVEL", whose documents are named
  "fd<YYMMDD>.zip" — this is "Monthly Security Core File 1: Factors for
  pools" per Freddie's own Disclosure Guide
  (capitalmarkets.freddiemac.com/mbs/docs/disclosure_guide.pdf).

- GET /api/report/download/<document_id>/<file_name>
  The actual file download. `document_id` is an opaque internal id from the
  `list` catalog above — NOT derivable from the filename/date, so a real
  ingest always has to call `list` first. Confirmed via curl that this
  requires an authenticated session: without one it's a 403.

`list_factor_documents` combines `listyears` + `list` into the fd-only,
date-filterable catalog `agency-mbs backfill freddie` walks over.

All three require a real Freddie Mac disclosure-portal login session (an
`x-csrf-token` header plus a `Cookie` header carrying `DISC_WEB_SSN_ID` and
friends) — see load_freddie_session(). They also require a same-origin
`referer` header: Akamai's edge WAF returns a 403 "Access Denied" (a
different failure than the app-level 403/401 for a bad/missing session)
without one, independent of cookie validity or User-Agent — confirmed by
toggling each header individually via curl.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import requests

FREDDIE_BASE = "https://freddiemac.mbs-securities.com"
FREDDIE_API = f"{FREDDIE_BASE}/api/report"

# Confirmed category id for the "Monthly" single-class section (referrer
# .../freddie/account/datafiles/singleclass/monthly). "Issuance" is
# category 1; other sections weren't explored.
MONTHLY_CATEGORY_ID = 2
MONTHLY_SLUG = "datafiles-singleclass-monthly"
MONTHLY_FACTOR_HEADING_KEY = "L1L2_MONTHLY_ONGOING_POOL_LEVEL"
MONTHLY_REFERER = f"{FREDDIE_BASE}/freddie/account/datafiles/singleclass/monthly"

RAW_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
SESSION_COOKIE_PATH = Path(__file__).resolve().parents[2] / "data" / "freddie_cookie.txt"
CSRF_TOKEN_PATH = Path(__file__).resolve().parents[2] / "data" / "freddie_csrf_token.txt"


def load_freddie_session(
    cookie_path: Path = SESSION_COOKIE_PATH, csrf_path: Path = CSRF_TOKEN_PATH
) -> tuple[str, str]:
    """Read (cookie, csrf_token) from local, gitignored files.

    Get these from a logged-in browser session at
    freddiemac.mbs-securities.com: open DevTools -> Network, click any
    /api/report/... request, and copy the "Cookie" request header (not the
    Application/Cookies tab — that shows pre-login cookies too) and the
    "x-csrf-token" request header. Save each to its own file directly from
    your own terminal, not through a shared/logged channel — they're
    session credentials.
    """
    if not cookie_path.exists() or not csrf_path.exists():
        raise RuntimeError(
            f"Missing Freddie Mac session files ({cookie_path}, {csrf_path}). "
            "Log in at freddiemac.mbs-securities.com, copy the 'Cookie' and "
            "'x-csrf-token' request headers from any /api/report/... call in "
            "DevTools Network, and save each to its file."
        )
    return cookie_path.read_text().strip(), csrf_path.read_text().strip()


def _headers(csrf_token: str) -> dict:
    # "referer" is required — Akamai's edge WAF returns a 403 "Access
    # Denied" (not a 401) without it, regardless of session cookie or
    # User-Agent; confirmed by isolating each header via curl.
    return {"accept": "*/*", "x-csrf-token": csrf_token, "referer": MONTHLY_REFERER}


def _cookies(cookie: str) -> dict:
    return dict(pair.split("=", 1) for pair in cookie.split("; "))


def fetch_monthly_years(cookie: str, csrf_token: str) -> list[int]:
    """Years with available data for the Monthly single-class section."""
    resp = requests.get(
        f"{FREDDIE_API}/freddie/listyears/{MONTHLY_CATEGORY_ID}/{MONTHLY_SLUG}",
        headers=_headers(csrf_token),
        cookies=_cookies(cookie),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_monthly_documents(cookie: str, csrf_token: str, year: int) -> list[dict]:
    """Full document catalog for the Monthly section for one year."""
    resp = requests.get(
        f"{FREDDIE_API}/freddie/list/{MONTHLY_CATEGORY_ID}/{year}",
        headers=_headers(csrf_token),
        cookies=_cookies(cookie),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def latest_factor_document(cookie: str, csrf_token: str, year: int) -> dict:
    """Most recent 'Factors for pools' document (fd*.zip) for a given year."""
    documents = fetch_monthly_documents(cookie, csrf_token, year)
    factor_docs = [
        d["document"]
        for d in documents
        if d["headingKey"] == MONTHLY_FACTOR_HEADING_KEY and d["document"]["name"].startswith("fd")
    ]
    if not factor_docs:
        raise RuntimeError(f"No '{MONTHLY_FACTOR_HEADING_KEY}' fd* documents found for {year}")
    return max(factor_docs, key=lambda d: d["effectiveDate"])


def list_factor_documents(cookie: str, csrf_token: str, *, since: date | None = None) -> list[dict]:
    """All 'Factors for pools' (fd*) documents, oldest to newest.

    With `since`, only queries the years that could contain a matching
    date (from `since.year` through the current year) instead of every
    year `fetch_monthly_years` returns, and drops documents whose
    `effectiveDate` falls before it.
    """
    available_years = fetch_monthly_years(cookie, csrf_token)
    years = available_years if since is None else [y for y in available_years if y >= since.year]

    documents = []
    for year in years:
        for entry in fetch_monthly_documents(cookie, csrf_token, year):
            if entry["headingKey"] != MONTHLY_FACTOR_HEADING_KEY:
                continue
            doc = entry["document"]
            if not doc["name"].startswith("fd"):
                continue
            if since is not None and date.fromisoformat(doc["effectiveDate"]) < since:
                continue
            documents.append(doc)

    documents.sort(key=lambda d: d["effectiveDate"])
    return documents


def download_document(
    cookie: str, csrf_token: str, document_id: str, file_name: str, *, dest_dir: Path = RAW_DATA_DIR
) -> Path:
    """Download one document by its internal id (from the `list` catalog)."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    resp = requests.get(
        f"{FREDDIE_API}/download/{document_id}/{file_name}",
        headers=_headers(csrf_token),
        cookies=_cookies(cookie),
        timeout=120,
    )
    resp.raise_for_status()
    dest_path = dest_dir / file_name
    dest_path.write_bytes(resp.content)
    return dest_path
