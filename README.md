# agency-mbs-tracker

[![CI](https://github.com/AMonten/agency-mbs-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/AMonten/agency-mbs-tracker/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-pre--alpha-orange.svg)](#status)

Open-source tracker for the monthly amortization history of agency MBS/CMO
pools (Ginnie Mae and Freddie Mac). Agency MBS/CMO paydown is
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
- [Scheduled ingestion](#scheduled-ingestion)
- [REST API](#rest-api)
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
    `factorAplat` (Platinum), `factorAAdd` (Additional) — all four share
    one parser (`parse_pool_factor_line` / `parse_monthly_factor_file`).
    `factorAAdd`'s own layout PDF documents 178 bytes (171 + a filler +
    an MIP-only field this project doesn't use), but its real production
    rows are 171 bytes whenever that tail is blank — the parser accepts
    either length for that one prefix.
  - REMIC/CMO tranche factors: `remic1`, `remic2` — a different, 117-char
    tranche-level layout (`parse_remic_tranche_line` /
    `parse_monthly_remic_file`).
  - Freddie Mac pool factors: `parse_monthly_freddie_file` — a pipe-delimited
    file **with its own header row** (98 named columns), so fields are
    looked up by name instead of hardcoded byte positions. Verified
    against a real authenticated download (461,779 records). Freddie also
    discloses a real WAM (`WA Current Remaining Months to Maturity`),
    which Ginnie Mae's pool-level files don't have at all.
- ✅ `agency_mbs.store` — SQLite schema + upsert/read for monthly
  pool/tranche-factor history, keyed on `pool_id` (not `cusip` — see
  [Architecture](#architecture) for why that matters).
- ✅ `agency_mbs.cli` — `agency-mbs lookup <ISIN|CUSIP>` against whatever is
  already in the local database.
- ✅ **Full pipeline works end-to-end against real, live, authenticated
  data** for all 6 Ginnie Mae prefixes plus Freddie Mac:
  `agency-mbs ingest <prefix>` downloads the current bulk file (each
  agency needs its own session — see [Authentication](#authentication)),
  unzips it, parses it, and stores it. Verified against real files:
  106,393 Ginnie I records, 308,073 Ginnie II, 308,073 Additional, 6,979
  Platinum, 37,969 REMIC1 tranches, 154,085 REMIC2 tranches (all July
  2026), and 462,779 Freddie Mac records (August 2026). Freddie Mac also
  has a real 12-month backfill (5,241,866 records) via `agency-mbs
  backfill freddie`.
- ✅ `scripts/monthly_ingest.sh` + `systemd/` — **installed and running**
  on the operator's machine (`agency-mbs-monthly-ingest.timer` enabled, next
  fire 2026-09-10), runs `ingest` for all 7 sources monthly, continuing
  past any single source's failure, and sends a ✅/❌ Telegram summary via
  `agency-mbs notify` (optional, reuses the same bot the Windows-side
  scripts already use) — see [Scheduled ingestion](#scheduled-ingestion).
- ✅ `agency_mbs.api` — a read-only REST API (`agency-mbs serve`, needs
  the `api` extra) over `get_factor_history`, with interactive docs at
  `/docs` (FastAPI's default). Verified end-to-end against a real running
  server, not just `TestClient` — see [REST API](#rest-api).

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
- **Freddie Mac** — bulk disclosure via its own Capital Markets site
  (<https://capitalmarkets.freddiemac.com/mbs/security-data/mbs-disclosure-resources>),
  which links directly to <https://freddiemac.mbs-securities.com/> — a
  React SPA (confirmed as Freddie's own, not a third-party front: its own
  branding/favicon/Google Analytics id) for the actual bulk downloads. Its
  real backend API (reverse-engineered from its JS bundle and confirmed
  request captures — see `fetch_freddie.py`'s docstring) needs a logged-in
  session for every call, including just listing available files. Layout
  documented in Freddie's own [Disclosure
  Guide](https://capitalmarkets.freddiemac.com/mbs/docs/disclosure_guide.pdf)
  (v6.2, "Security Core File" section).

## Architecture

```
fetch.py         -> Ginnie Mae: catalog/sample endpoints (public) + bulk file
                     download (needs a session); downloads saved as-is under data/raw/
fetch_freddie.py -> Freddie Mac: years/document-list/download endpoints (all need a session)
parse.py         -> normalizes a raw file into pool/tranche-factor records, both agencies
store.py         -> SQLite: one row per (pool_id, factor_date), history never overwritten
isin.py          -> ISIN <-> CUSIP, with check-digit validation on both;
                     resolve_identifier() is the shared CLI+API lookup rule
notify.py        -> Telegram notifications (optional, best-effort)
api.py           -> read-only REST API over store.py (needs the `api` extra)
cli.py           -> `agency-mbs ingest/backfill/lookup/notify/serve`
```

Normalized schema (`pool_factors` table): `pool_id, cusip, issuer,
factor_date, current_factor, prior_factor, coupon_rate, rate_type, wam,
upb_original, upb_current`. `current_factor`/`upb_current`/`coupon_rate`
can be `NULL` — some real pool records (`pool_type == "SP"`) report those
fields blank, and the parser preserves that rather than coercing to 0.

**`coupon_rate` is the security/tranche's own investor-facing interest
rate — NOT the underlying collateral's Weighted Average Coupon (WAC).**
These are genuinely different numbers: WAC is what the pooled mortgages
pay; `coupon_rate` is WAC minus servicing/guaranty fees, i.e. what's
actually passed through to the security. They drift apart over time as
the pool's composition changes through amortization/prepayment, even when
the security's own coupon stays fixed — this project's earlier field name
(`wac`) was wrong and got renamed after review. True collateral WAC isn't
in any file parsed here — it lives in the agencies' loan-level disclosure
files, a different (unparsed) product. Each row's `coupon_rate` is
correctly scoped already: pool-level for Ginnie/Freddie pool records, and
the tranche's own rate for REMIC — a CMO tranche's rate is independent of
its collateral's WAC and can be fixed, floating, inverse, or IO.

`rate_type` is `"fixed"` or `"floating"` for pool-level records (Ginnie
I/II/Platinum) — derived from the "Original Interest Rate" field, which
the agency's own layout notes document as populated for ARM pools only;
confirmed against real data (blank for every fixed pool checked, populated
for all 18,352 real ARM/reverse-mortgage pools in the July 2026 Ginnie II
file). It's `NULL` for REMIC tranches — that file has no fixed/floating
signal at all, so it's left unknown rather than guessed.

Because history is one row per `(pool_id, factor_date)`, `coupon_rate`'s
own month-to-month history (real for floating-rate securities, whose rate
resets periodically) comes for free from ingesting/backfilling multiple
periods — no separate tracking needed.

**Storage is keyed on `pool_id`, not `cusip`.** Confirmed against real
REMIC production data: Ginnie Mae uses shared placeholder CUSIP values
(e.g. `"C99999999"`) for tranches that aren't individually CUSIP-eligible
— in the real August 2026 `remic1` file, 185 distinct real tranches all
carried that one CUSIP. Keying on `cusip` alone silently collapsed them
into a single row; `pool_id` (the real pool number, or
`<series>-<tranche_name>` for REMIC) is what Ginnie Mae actually assigns
uniquely, so `agency-mbs lookup` on one of these shared CUSIPs correctly
returns every tranche that shares it, not just the last one ingested.

**Lookup (`resolve_identifier`, shared by the CLI and the REST API) never
checksum-validates a 9-character CUSIP, only its length.** These
placeholder values (like `"C99999999"`) fail a real CUSIP check digit by
construction — they're sentinels, not assigned identifiers — so a strict
checksum would make real, already-stored data unlookupable. A 12-char
ISIN is still fully checksum-validated on both the ISIN and the CUSIP it
resolves to, since a mistyped ISIN is a real, common failure mode worth
catching early; a wrong-but-real-shaped CUSIP just returns no rows, which
is a harmless outcome for a typo.

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

**Freddie Mac** needs a session for *every* call, including just listing
files. Get one from a logged-in browser session at
freddiemac.mbs-securities.com:

1. Log in (register a free account if you don't have one), then go to
   Single Class -> Monthly.
2. Open DevTools -> Network, click any file, and find an `/api/report/...`
   request.
3. From that request's **Headers** tab (not Application/Cookies — those
   show pre-login cookies too), copy the full `Cookie` request header and
   the `x-csrf-token` request header. Save each directly from your own
   terminal:
   ```bash
   echo -n "<Cookie header value>" > data/freddie_cookie.txt
   echo -n "<x-csrf-token value>" > data/freddie_csrf_token.txt
   ```
   Both files are gitignored and only read by
   `agency_mbs.fetch_freddie.load_freddie_session()`.

## Usage

```bash
agency-mbs ingest factorA1          # Ginnie I pool factors
agency-mbs ingest factorA2          # Ginnie II pool factors
agency-mbs ingest factorAplat       # Platinum pool factors
agency-mbs ingest factorAAdd        # Additional (Ginnie II, MIP-aware) pool factors
agency-mbs ingest remic1            # REMIC/CMO tranche factors
agency-mbs ingest remic2            # REMIC/CMO tranche factors (2nd feed)
agency-mbs ingest freddie           # Freddie Mac pool factors (latest monthly file)
agency-mbs backfill freddie                # last 12 months (default)
agency-mbs backfill freddie --months 24    # last 24 months
agency-mbs lookup US38384CNA35
agency-mbs lookup 38384CNA3
```

`backfill` currently only supports `freddie` — Freddie Mac's
`listyears`/`list` endpoints expose real history (back to 2018), unlike
Ginnie Mae's catalog, which only ever shows the current month. Each
period downloads a full ~30MB (compressed) monthly file and stores
~450-460k rows; the extracted `.txt` is deleted after parsing to save
disk, but the (much smaller) `.zip` is kept in `data/raw/`.

**Ginnie Mae has no bulk historical backfill** — confirmed, not just
unexplored. Its bulk portal's own JS bundle has no history/archive/year
API at all (only the current-month catalog this project already uses).
The "FRR"/"SRF HISTORY FILES" catalog entries turned out to be
current-month-only disclosures too (floater reset rates and REMIC
series-level factors, despite the "HISTORY" in their titles) — not
archives. A genuine per-CUSIP history product does exist (the "Tax and
Factor Data Search" tool's "Pool RPB, Tax and Factor History Download
File", pipe-delimited, one row per reporting period per pool), but it's
capped at 20 CUSIPs/pools per query with ~12 months of history — a lookup
tool, not a bulk archive, and it lives on Ginnie Mae's newer site with its
own API not yet reverse-engineered. Ginnie Mae history will accumulate
naturally instead, one row per `(pool_id, factor_date)`, as `ingest` runs
forward each month.

## Scheduled ingestion

`scripts/monthly_ingest.sh` runs `agency-mbs ingest <prefix>` for all 7
supported sources (the 6 Ginnie Mae prefixes + `freddie`), continuing past
any single prefix's failure so one broken source (e.g. Freddie's session
cookie expiring — see [Authentication](#authentication)) doesn't block
the others; it exits non-zero at the end if anything failed, so
`journalctl` surfaces it. `systemd/` has the matching timer/service pair,
following this environment's existing pattern (see `~/README.md`'s
`sync-win-host-ip.timer` section) — day 10 of each month, `Persistent=true`
so a missed run (WSL/Windows host off at the scheduled time) fires once
as soon as it's next up, instead of waiting a full month.

Installing the timer needs `sudo` (interactive password, no `NOPASSWD` in
this environment), so it's not run automatically — install it yourself,
**from a real terminal** (an AI coding assistant's `!`-prefix bridge does not
allocate a TTY, so `sudo` can't prompt for a password through it —
confirmed: `sudo: a terminal is required to read the password`):

```bash
sudo cp systemd/agency-mbs-monthly-ingest.service systemd/agency-mbs-monthly-ingest.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now agency-mbs-monthly-ingest.timer

# Check it's scheduled, and inspect a run's output:
systemctl list-timers agency-mbs-monthly-ingest.timer
journalctl -u agency-mbs-monthly-ingest.service -n 50 --no-pager
```

**Telegram notifications** — `scripts/monthly_ingest.sh` sends a one-line
✅/❌ summary via `agency-mbs notify` at the end of each run, reusing the
same bot the operator's Windows-side scripts already use for Refinitiv/BNY2.0
alerts (see `C:\Users\operator\Scripts\README.md`'s "Alertas de
Telegram" section) — same bot, same `chat_id`. That side reads the token
from Windows user environment variables, which aren't visible from WSL,
so this side reads the same two values from local, gitignored files
instead:

```bash
echo -n "<bot token>" > data/telegram_bot_token.txt
echo -n "<chat id>" > data/telegram_chat_id.txt
```

Both are optional — `send_telegram_message` (and `agency-mbs notify`)
silently no-ops if either file is missing, matching
`Send-TelegramAlert.ps1`'s own "never let an alert failure break the real
automation" philosophy on the Windows side.

## REST API

A thin, read-only HTTP layer over the same `agency_mbs.store` functions
the CLI's `lookup` uses — no business logic duplicated in `api.py`.

```bash
pip install -e ".[api]"
agency-mbs serve                    # binds 127.0.0.1:8000 by default
curl http://127.0.0.1:8000/lookup/US38384CNA35
curl http://127.0.0.1:8000/lookup/38384CNA3
```

Interactive docs (FastAPI's default) at `http://127.0.0.1:8000/docs`.

- `GET /health` — `{"status": "ok"}`.
- `GET /lookup/{identifier}` — 12-char ISIN or 9-char CUSIP, same
  resolution rule as the CLI (`agency_mbs.isin.resolve_identifier`).
  Returns `{cusip, distinct_pool_count, periods}`, oldest period first.
  `distinct_pool_count > 1` means this CUSIP is one of Ginnie Mae's shared
  placeholder values for non-CUSIP-eligible REMIC tranches (see
  [Architecture](#architecture)) — `periods` then covers every tranche
  that shares it. An identifier of the wrong length is a `400`; a
  well-formed one with no matching data is a `200` with `periods: []`
  (not a `404` — a CUSIP not yet ingested isn't an error).

**No authentication** — this binds to `127.0.0.1` by default precisely
because there's no auth layer to protect a `0.0.0.0` bind; it's meant for
local/same-machine use (e.g. a Streamlit app or a notebook on the same
box), not for exposing over a network.

**A real threading gotcha, fixed, not just avoided in tests:** FastAPI can
resolve a sync dependency (`get_db`) and run the route's own sync body in
two *different* threadpool worker threads for the same request — SQLite's
default `check_same_thread=True` rejects that even though only one thread
ever touches the connection at a time. `agency_mbs.store.get_connection`
gained a `check_same_thread` keyword (default unchanged, `True`) so
`agency_mbs.api.get_db` can opt into `False` specifically; confirmed this
was a real bug (not a test artifact) by reproducing it against a live
`uvicorn` server, not just `TestClient`.

## Testing

```bash
pytest --cov=agency_mbs --cov-report=term-missing
ruff check src/ tests/
```

## Roadmap

- [x] Monthly scheduled ingestion — see [Scheduled ingestion](#scheduled-ingestion).
      Freddie Mac's session cookie will still need periodic manual
      refreshing since it's a browser login, not an API key — the timer
      just surfaces that failure via `journalctl` rather than fixing it.
- [ ] (Optional, not planned) Ginnie Mae per-CUSIP history lookup via the
      "Tax and Factor Data Search" tool — capped at 20 CUSIPs/query, needs
      its own reverse-engineering; no bulk backfill exists for Ginnie Mae
      (confirmed — see the [Usage](#usage) note above).
- [x] REST API — see [REST API](#rest-api). Streamlit dashboard still
      not started (the operator chose REST API first).
