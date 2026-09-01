# agency-mbs-tracker

[![CI](https://github.com/AMonten/agency-mbs-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/AMonten/agency-mbs-tracker/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-pre--alpha-orange.svg)](#status)

Open-source tracker for the monthly amortization history of agency MBS/CMO
pools (Ginnie Mae, and eventually Freddie Mac). Agency MBS/CMO paydown is
collateral-driven: the issuer reports, month by month, how much of the pool
has amortized based on scheduled principal, borrower prepayments, and other
returns of principal — expressed as a **pool factor** (remaining balance as
a fraction of original face). This project pulls that factor history in
bulk, straight from the agencies' own public disclosure data, and lets you
look it up by ISIN or CUSIP.

> This is not a market-data platform or a substitute for a paid data vendor
> (Bloomberg, etc.) — it's a way to reconstruct amortization history from
> public disclosure sources for research/analysis use.

## Contents

- [Status](#status)
- [Why this project exists](#why-this-project-exists)
- [Data sources](#data-sources)
- [Architecture](#architecture)
- [Installation](#installation)
- [Authentication](#authentication)
- [Usage](#usage)
- [Testing](#testing)
- [Roadmap](#roadmap)

## Status

**Pre-alpha.** What actually works today, against the real live API/data
(not mocked):

- ✅ `agency_mbs.isin` — ISIN → CUSIP extraction, with real check-digit
  validation on both the ISIN and the CUSIP (tested against a real Ginnie
  Mae ISIN).
- ✅ `agency_mbs.fetch` — public, unauthenticated endpoints: the full bulk
  file catalog (`fetch_disclosure_catalog`), layout/sample files
  (`fetch_layout_sample_files`), and downloading those public assets.
  Reverse-engineered from `bulk.ginniemae.gov`'s own Angular bundle — see
  the module docstring for exactly how.
- ✅ `agency_mbs.parse` — real fixed-width parsers, each built against the
  agency's own published layout PDF and verified against its real public
  sample file (checked into `tests/fixtures/`):
  - Pool-level factors: `factorA1` (Ginnie I), `factorA2` (Ginnie II),
    `factorAplat` (Platinum) — all three share one 171-char layout and one
    parser (`parse_pool_factor_line` / `parse_monthly_factor_file`).
  - REMIC/CMO tranche factors: `remic1`, `remic2` — a different, 117-char
    tranche-level layout (`parse_remic_tranche_line` /
    `parse_monthly_remic_file`).
  - `factorAAdd` (Additional) not confirmed to share the pool-level layout
    yet — not parsed.
- ✅ `agency_mbs.store` — SQLite schema + upsert/read for monthly
  pool/tranche-factor history, keyed on `pool_id` (not `cusip` — see
  [Architecture](#architecture) for why that matters).
- ✅ `agency_mbs.cli` — `agency-mbs lookup <ISIN|CUSIP>` against whatever is
  already in the local database.
- ✅ **Full pipeline works end-to-end against real, live, authenticated
  data** for all 5 supported prefixes: `agency-mbs ingest <prefix>`
  downloads the current month's real bulk file (needs a `gm_up_token`
  session cookie — see [Authentication](#authentication)), unzips it,
  parses it, and stores it. Verified against the real July 2026 files:
  106,393 Ginnie I records, 308,073 Ginnie II, 6,979 Platinum, 37,969
  REMIC1 tranches, 154,085 REMIC2 tranches.
- ❌ `factorAAdd` (Additional) not parsed yet — same pattern as the other
  pool-level files, just not done.

## Why this project exists

Pool factor / amortization history for agency MBS is public data, published
directly by Ginnie Mae and Freddie Mac for investor disclosure — but it's
normally consumed either one CUSIP at a time through each agency's own
search tool, or through a paid vendor (Bloomberg, etc.). This project treats
it as a bulk, versioned dataset instead: pull the agencies' own monthly bulk
files, normalize them into one schema, and keep full history (not just the
latest factor) so amortization behavior over time can be reconstructed and
analyzed directly.

## Data sources

- **Ginnie Mae** — bulk disclosure. The public site at
  <https://bulk.ginniemae.gov/> is an Angular SPA; its real backend API
  (reverse-engineered from the compiled bundle, see `fetch.py`'s docstring)
  lives at `https://www.ginniemae.gov/bulk-content/api` (catalog + samples,
  public) and `https://www.ginniemae.gov/disclosure-api/api` (actual file
  download, **requires a logged-in session**). Layout documentation and
  real sample files are served publicly per file type from
  `https://www.ginniemae.gov/s3/sites/default/files/disclosure_data_files/`.
  Per-CUSIP lookup (useful for spot-checking, not bulk ingestion):
  [Tax and Factor Data Search](https://www.ginniemae.gov/disclosure/disclosure-search-tools/tax-and-factor-data-search).
  Ginnie Mae is a wholly-owned U.S. government corporation (HUD); it is not
  an agency or establishment of the U.S. Government.
- **Freddie Mac** — not wired up yet. Needs its own bulk-file source
  confirmed (avoid scraping third-party fronts like
  `freddiemac.mbs-securities.com` if an official bulk download exists —
  TBD).

## Architecture

```
fetch.py   -> catalog/sample endpoints (public) + bulk file download (needs a session);
              downloads saved as-is under data/raw/
parse.py   -> normalizes a raw file into pool/tranche-factor records
store.py   -> SQLite: one row per (pool_id, factor_date), history never overwritten
isin.py    -> ISIN <-> CUSIP, with check-digit validation on both
cli.py     -> `agency-mbs ingest <prefix>` (fetch+parse+store) and
              `agency-mbs lookup <ISIN|CUSIP>` (read what's stored)
```

Normalized schema (`pool_factors` table): `pool_id, cusip, issuer,
factor_date, current_factor, prior_factor, wac, rate_type, wam,
upb_original, upb_current`. `current_factor`/`upb_current`/`wac` can be
`NULL` — some real pool records (`pool_type == "SP"`) report those fields
blank, and the parser preserves that rather than coercing to 0.

`rate_type` is `"fixed"` or `"floating"` for pool-level records (Ginnie
I/II/Platinum) — derived from the "Original Interest Rate" field, which
the agency's own layout notes document as populated for ARM pools only;
confirmed against real data (blank for every fixed pool checked, populated
for all 18,352 real ARM/reverse-mortgage pools in the July 2026 Ginnie II
file). It's `NULL` for REMIC tranches — that file has no fixed/floating
signal at all, so it's left unknown rather than guessed.

**Storage is keyed on `pool_id`, not `cusip`.** Confirmed against real
REMIC production data: Ginnie Mae uses shared placeholder CUSIP values
(e.g. `"C99999999"`) for tranches that aren't individually CUSIP-eligible
— in the real August 2026 `remic1` file, 185 distinct real tranches all
carried that one CUSIP. Keying on `cusip` alone silently collapsed them
into a single row; `pool_id` (the real pool number, or
`<series>-<tranche_name>` for REMIC) is what Ginnie Mae actually assigns
uniquely, so `agency-mbs lookup` on one of these shared CUSIPs correctly
returns every tranche that shares it, not just the last one ingested.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Authentication

Real bulk file downloads require a logged-in ginniemae.gov session — the
`disclosure-api/api/download` endpoint 302-redirects to a login page
without one (confirmed by request, not assumed). To unlock `ingest`:

1. Register a free account at ginniemae.gov and log in via a browser.
2. Copy the `gm_up_token` cookie value from your browser's dev tools.
3. Save it directly from your own terminal (not through a shared/logged
   channel — it's a session credential):
   ```bash
   echo -n "<cookie value>" > data/session_cookie.txt
   ```
   This file is gitignored and never read by anything except
   `agency_mbs.fetch.load_session_cookie()`.

The catalog/sample endpoints (used by `lookup` once ingested, and by the
parser's own test fixtures) need no login at all.

## Usage

```bash
agency-mbs ingest factorA1          # Ginnie I pool factors
agency-mbs ingest factorA2          # Ginnie II pool factors
agency-mbs ingest factorAplat       # Platinum pool factors
agency-mbs ingest remic1            # REMIC/CMO tranche factors
agency-mbs ingest remic2            # REMIC/CMO tranche factors (2nd feed)
agency-mbs lookup US38384CNA35
agency-mbs lookup 38384CNA3
```

## Testing

```bash
pytest --cov=agency_mbs --cov-report=term-missing
ruff check src/ tests/
```

## Roadmap

- [ ] Parser for `factorAAdd` (Additional) — needs its own layout PDF
      checked before assuming it matches the other pool-level files.
- [ ] Monthly scheduled ingestion (cron/systemd timer).
- [ ] Freddie Mac source.
- [ ] REST API / Streamlit dashboard on top of the local database.
