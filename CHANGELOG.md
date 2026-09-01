# Changelog

## 2026-09-01

- Repo scaffolded: `src/` layout, MIT license, CI (ruff + pytest on 3.10-3.12).
- `agency_mbs.isin`: ISIN → CUSIP extraction with real check-digit validation
  on both ISIN and CUSIP, tested against a real Ginnie Mae ISIN
  (`US38384CNA35` → `38384CNA3`).
- `agency_mbs.store`: SQLite schema (`pool_factors`) + upsert/read helpers.
- `agency_mbs.cli`: `agency-mbs lookup <ISIN|CUSIP>`.
- `agency_mbs.fetch` / `agency_mbs.parse`: stubbed, not implemented — confirmed
  `bulk.ginniemae.gov` as the real bulk-disclosure source, but the exact
  request shape (JS-rendered site) still needs to be captured from a browser
  before implementing for real.
