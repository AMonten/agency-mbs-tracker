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
- [Usage](#usage)
- [Testing](#testing)
- [Roadmap](#roadmap)

## Status

**Pre-alpha / scaffold.** What actually works today:

- ✅ `agency_mbs.isin` — ISIN → CUSIP extraction, with real check-digit
  validation on both the ISIN and the CUSIP (tested against a real Ginnie
  Mae ISIN).
- ✅ `agency_mbs.store` — SQLite schema + upsert/read for monthly pool-factor
  history.
- ✅ `agency_mbs.cli` — `agency-mbs lookup <ISIN|CUSIP>` against whatever is
  already in the local database.
- ❌ `agency_mbs.fetch` / `agency_mbs.parse` — **not implemented yet.**
  `bulk.ginniemae.gov` is confirmed as the right source (see below) but it
  renders through JavaScript, so the exact request shape for one month of
  Single Family pool-level factor data still needs to be captured from a
  browser before the fetcher can be written for real. See the module
  docstrings in `src/agency_mbs/fetch.py` and `src/agency_mbs/parse.py`.

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

- **Ginnie Mae** — bulk disclosure downloads: <https://bulk.ginniemae.gov/>
  (daily/weekly/monthly/factor files, Single Family pool level). Layout
  documentation: [Disclosure Data Download Layouts and Sample
  Files](https://www.ginniemae.gov/disclosure/disclosure-resources/disclosure-data-download-layouts-and-sample-files)
  and the `MBS_SingleFamily_Pool_DataDictionary`. Per-CUSIP lookup (useful
  for spot-checking, not bulk ingestion):
  [Tax and Factor Data Search](https://www.ginniemae.gov/disclosure/disclosure-search-tools/tax-and-factor-data-search).
  Ginnie Mae is a wholly-owned U.S. government corporation (HUD); it is not
  an agency or establishment of the U.S. Government.
- **Freddie Mac** — not wired up yet. Needs its own bulk-file source
  confirmed (avoid scraping third-party fronts like
  `freddiemac.mbs-securities.com` if an official bulk download exists —
  TBD).

## Architecture

```
fetch.py   -> downloads the raw monthly bulk disclosure file, saved as-is under data/raw/
parse.py   -> normalizes a raw file into pool-factor records
store.py   -> SQLite: one row per (cusip, factor_date), history never overwritten
isin.py    -> ISIN <-> CUSIP, with check-digit validation on both
cli.py     -> `agency-mbs lookup <ISIN|CUSIP>` over what's in the local database
```

Normalized schema (`pool_factors` table): `cusip, pool_id, issuer,
factor_date, current_factor, prior_factor, wac, wam, upb_original,
upb_current`.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

```bash
agency-mbs lookup US38384CNA35
agency-mbs lookup 38384CNA3
```

Until `fetch`/`parse` are implemented, the local database will be empty —
the CLI will say so rather than pretending there's data.

## Testing

```bash
pytest --cov=agency_mbs --cov-report=term-missing
ruff check src/ tests/
```

## Roadmap

- [ ] Capture the real `bulk.ginniemae.gov` request for one month of Single
      Family pool-level factor data; implement `fetch.py` against it.
- [ ] Get a real sample file + confirm layout against the data dictionary;
      implement `parse.py` against it.
- [ ] Monthly scheduled ingestion (cron/systemd timer).
- [ ] Freddie Mac source.
- [ ] REST API / Streamlit dashboard on top of the local database.
