"""Download of Ginnie Mae bulk disclosure files.

Confirmed by inspecting the actual Angular bundle served at
https://bulk.ginniemae.gov/ (main-*.js) and its runtime config
(/assets/config/config.prod.json, selected because
window.location.hostname ends with ".ginniemae.gov" -> environment "prod"):

    bulkContentServiceUrl = https://www.ginniemae.gov/bulk-content/api
    disclosureWcfUrl      = https://www.ginniemae.gov/disclosure-api/api

Two real, public, unauthenticated endpoints:

- GET {bulkContentServiceUrl}/disclosure-data
  Full catalog of available bulk files across all categories (Factor
  Files, HMBS, MBS Single Family, Multifamily, Other Files, Platinum),
  each entry giving directoryName/fileName/fileSize/lastModified. The
  "Factor Files" category is what we want: factorA1/factorA2 (Ginnie
  I/II), factorAplat (Platinum), factorAAdd (Additional), remic1/remic2
  (REMIC/CMO tranches), FRR/SRF (history). Files are named
  "<field_prefix>_<YYYYMM>.zip" (or .txt), e.g. "factorA1_202607.zip".

- GET {bulkContentServiceUrl}/layouts-sample-files
  Layout PDFs and REAL sample data files per file type, served from S3
  under /s3/sites/default/files/disclosure_data_files/ — genuinely public,
  no login needed. This is what agency_mbs.parse's factorA1 layout was
  verified against.

One endpoint that is NOT public:

- GET {disclosureWcfUrl}/download?dlfile=<directoryName>/<fileName>
  This is how the actual monthly bulk data files (not samples) get
  downloaded. Confirmed via curl: with no session, it 302-redirects to
  https://www.ginniemae.gov/disclosure/download-login?src=... — i.e. it
  requires a logged-in session (cookie "gm_up_token", per the frontend's
  auth service). Getting a real bulk crawler working requires registering
  a (free, per the frontend's login flow) Ginnie Mae account and capturing
  that cookie — not something to script blind without the operator's own
  account and go-ahead.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import requests

BULK_CONTENT_API = "https://www.ginniemae.gov/bulk-content/api"
DISCLOSURE_API = "https://www.ginniemae.gov/disclosure-api/api"
GINNIE_MAE_BASE = "https://www.ginniemae.gov"

RAW_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
SESSION_COOKIE_PATH = Path(__file__).resolve().parents[2] / "data" / "session_cookie.txt"


def load_session_cookie(path: Path = SESSION_COOKIE_PATH) -> str:
    """Read the gm_up_token value from a local, gitignored file.

    Get this value by registering a free ginniemae.gov account, logging in
    via a browser, and copying the "gm_up_token" cookie — save it to this
    file directly from your own terminal (not through a shared/logged
    channel, since it's a session credential).
    """
    path = Path(path)
    if not path.exists():
        raise RuntimeError(
            f"No session cookie found at {path}. Log in to ginniemae.gov in a "
            "browser, copy the 'gm_up_token' cookie value, and save it to "
            "that file (plain text, no quotes/newline)."
        )
    return path.read_text().strip()


def fetch_disclosure_catalog() -> dict:
    """Full public catalog of available bulk files, keyed by category."""
    resp = requests.get(f"{BULK_CONTENT_API}/disclosure-data", timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_layout_sample_files() -> dict:
    """Public catalog of layout PDFs + real sample files, keyed by category."""
    resp = requests.get(f"{BULK_CONTENT_API}/layouts-sample-files", timeout=30)
    resp.raise_for_status()
    return resp.json()


def download_public_asset(field_media_file: str, dest_dir: Path) -> Path:
    """Download a public layout/sample asset (from fetch_layout_sample_files).

    `field_media_file` is the relative path+query as given by that catalog,
    e.g. "/s3/sites/default/files/disclosure_data_files/factorA1_sample.txt?VersionId=...".
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    url = f"{GINNIE_MAE_BASE}{field_media_file}"
    filename = field_media_file.split("/")[-1].split("?")[0]
    dest_path = dest_dir / filename
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    dest_path.write_bytes(resp.content)
    return dest_path


def download_bulk_file(
    directory_name: str,
    file_name: str,
    *,
    session_cookie: str,
    dest_dir: Path = RAW_DATA_DIR,
) -> Path:
    """Download a real monthly bulk file (requires a logged-in session).

    Args:
        directory_name: e.g. "data_bulk" (from fetch_disclosure_catalog()).
        file_name: e.g. "factorA1_202607.zip".
        session_cookie: value of the "gm_up_token" cookie from a logged-in
            ginniemae.gov browser session — register a free account, log in
            once via the browser, and copy the cookie value. Not something
            this library can obtain on its own.
        dest_dir: directory to save the raw file into.
    """
    if not session_cookie:
        raise RuntimeError(
            "download_bulk_file requires a logged-in ginniemae.gov session "
            "(cookie 'gm_up_token'). Without it the endpoint 302-redirects "
            "to /disclosure/download-login. Register an account, log in "
            "via a browser, and pass the resulting cookie value."
        )
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dlfile = quote(f"{directory_name}/{file_name}", safe="")
    url = f"{DISCLOSURE_API}/download?dlfile={dlfile}"
    resp = requests.get(url, cookies={"gm_up_token": session_cookie}, timeout=120)
    resp.raise_for_status()
    dest_path = dest_dir / file_name
    dest_path.write_bytes(resp.content)
    return dest_path
