# Changelog

## 2026-09-01

- Repo scaffolded: `src/` layout, MIT license, CI (ruff + pytest on 3.10-3.12).
- `agency_mbs.isin`: ISIN → CUSIP extraction with real check-digit validation
  on both ISIN and CUSIP, tested against a real Ginnie Mae ISIN
  (`US38384CNA35` → `38384CNA3`).
- `agency_mbs.store`: SQLite schema (`pool_factors`) + upsert/read helpers.
- `agency_mbs.cli`: `agency-mbs lookup <ISIN|CUSIP>`.
- Reverse-engineered `bulk.ginniemae.gov`'s Angular bundle to find its real
  backend API: `bulk-content/api` (catalog + layout/sample files — public,
  no auth) and `disclosure-api/api/download` (actual bulk files — confirmed
  via a real request that it 302-redirects to a login page without a
  session cookie).
- `agency_mbs.fetch`: implemented and tested against the live API — public
  catalog/sample endpoints work end-to-end; `download_bulk_file` is ready
  but needs a logged-in session (`gm_up_token` cookie) that only the operator's
  own account can provide.
- `agency_mbs.parse`: real fixed-width parser for the Ginnie Mae I
  ("FACTOR A G I" / `factorA1`) file, built against the agency's own
  published layout PDF and verified against its real public sample file
  (checked into `tests/fixtures/factorA1_202607.txt`, 15/15 records parse
  correctly). Other factor file types (Ginnie II, Platinum, Additional,
  REMIC/CMO) not parsed yet — same pattern, needs their own layout PDF.
- Registered a Ginnie Mae account and confirmed the authenticated bulk
  download for real: `agency_mbs.fetch.load_session_cookie()` reads a
  `gm_up_token` session cookie from a local, gitignored
  `data/session_cookie.txt` (never committed, never logged).
- Ran the full real July 2026 "FACTOR A G I" bulk file (106,393 pool
  records, ~18MB) through the parser: parses cleanly in well under a
  second. Found and handled a real data quirk — ~2.5% of rows
  (`pool_type == "SP"`) have the RPB Factor / Remaining Security RPB
  fields blank rather than zero-filled; `parse.py` now preserves that as
  `None` instead of crashing or coercing to 0, and `store.py`'s
  `current_factor` column is nullable to match.
- New `agency-mbs ingest <prefix>` CLI command wires fetch -> unzip ->
  parse -> store together. Verified end-to-end against the live API:
  106,393 records stored (103,725 with a factor, 2,668 legitimately
  blank).
