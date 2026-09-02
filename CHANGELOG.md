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

## 2026-09-01 (continued) — Ginnie II, Platinum, and REMIC/CMO

- Confirmed `factorA2` (Ginnie II) and `factorAplat` (Platinum) share the
  exact same 171-char column layout as `factorA1` for every field this
  project uses — one parser (renamed `parse_factor_a1_line` ->
  `parse_pool_factor_line`) now covers all three, verified against each
  one's own real public sample file.
- Added `remic1`/`remic2` (REMIC/CMO tranche factors) support: a genuinely
  different 117-char tranche-level layout (`parse_remic_tranche_line` /
  `parse_monthly_remic_file`), confirmed against `remic1_layout.pdf` /
  `remic2_layout.pdf` ("MTF FILE LAYOUT") and their real sample files.
- **Found and fixed a real correctness bug while ingesting the actual
  production REMIC files**: Ginnie Mae uses shared placeholder CUSIP
  values (e.g. `"C99999999"`) for tranches that aren't individually
  CUSIP-eligible — 185 distinct real tranches in the real `remic1` file
  all carried that one CUSIP. Storage was keyed on `(cusip, factor_date)`,
  so all 185 silently collapsed into a single row. Fixed by re-keying
  `pool_factors` on `(pool_id, factor_date)` instead — `pool_id` (pool
  number, or `<series>-<tranche_name>` for REMIC) is what Ginnie Mae
  actually assigns uniquely; `cusip` stays indexed for lookup but isn't
  the storage key. `agency-mbs lookup` on a shared CUSIP now lists every
  tranche that shares it (and says so) instead of showing just one.
- Added `tests/test_store.py` (previously untested) with a regression test
  for the shared-CUSIP case, and expanded `tests/test_parse.py` for
  Ginnie II/Platinum/REMIC1/REMIC2 — all against real fixture files, not
  synthetic data. 33/33 tests passing, `ruff`+`mypy` clean.
- Verified all 5 supported prefixes end-to-end against the live,
  authenticated API for the real July 2026 files: 106,393 Ginnie I
  records, 308,073 Ginnie II, 6,979 Platinum, 37,969 REMIC1 tranches,
  154,085 REMIC2 tranches. Cross-checked overlaps: Ginnie II and Platinum
  share exactly 4,311 CUSIPs (Platinum pools cross-referenced as blank
  stubs inside the Ginnie II file — Platinum's real data correctly wins
  on ingest order), REMIC1/REMIC2 share only 3.

## 2026-09-01 (continued) — fixed/floating rate indicator

- Added `rate_type` (`"fixed"`/`"floating"`) to pool-level records
  (Ginnie I/II/Platinum), derived from the "Original Interest Rate" field
  — the agency's own Platinum layout notes document it as "Populated for
  ARM Pools only". Confirmed against real data: blank for every `"SF"`
  fixed pool checked, populated for all 18,352 real `"RF"`
  (reverse-mortgage ARM) pools in the July 2026 Ginnie II file (289,721
  fixed vs 18,352 floating out of 308,073 total).
  REMIC tranches get `rate_type: None` — that file has no fixed/floating
  signal at all, so it's left unknown rather than guessed from tranche
  naming conventions.
- `pool_factors` gained a `rate_type` column; `agency-mbs lookup` now
  prints the interest rate and fixed/floating label per period (e.g.
  `tasa=4.700% (flotante)`), and its existing multi-period history already
  covers the "historico" ask.

## 2026-09-01 (continued) — factorAAdd (Additional)

- Added `factorAAdd` (Ginnie II "Additional" factor file) support.
  `factorAAdd_layout.pdf` documents 178 bytes (the same first 171 as
  factorA1/A2/Aplat, plus a filler byte and a 6-digit MIP-only "Factor
  Percentage Complete" field this project doesn't use) — but confirmed
  against the real production file that every one of its 308,073 rows is
  actually 171 bytes, since that trailing MIP tail is omitted rather than
  space-padded when blank (its own sample file showed the same, initially
  looking like a discrepancy from the spec until checked against real
  data). `parse_pool_factor_line`/`parse_monthly_factor_file` gained a
  `valid_lengths` parameter so `factorAAdd` accepts either 171 or 178
  while the other three prefixes keep their strict, exact-171 check.
- Verified end-to-end against the live API: 308,073 records stored
  (303,762 with a factor, 4,311 blank) — matching factorA2's real file
  count and blank-count exactly, confirming factorAAdd covers the same
  Ginnie II pool universe as a separate feed. 38/38 tests passing,
  `ruff`+`mypy` clean.

## 2026-09-01 (continued) — Freddie Mac support

- Confirmed the official Freddie Mac bulk source: not the third-party-look
  `freddiemac.mbs-securities.com` we worried about earlier — it's directly
  linked from Freddie's own capitalmarkets.freddiemac.com and carries
  Freddie's own branding/analytics. Reverse-engineered its React bundle
  and, with the operator capturing real authenticated requests from his own
  browser session (`Copy as fetch` / cURL), found the real API:
  `/api/report/freddie/listyears/<category_id>/<slug>` (which years have
  data — Freddie's goes back to at least 2018, unlike Ginnie Mae's
  current-month-only catalog), `/api/report/freddie/list/<category_id>/<year>`
  (document catalog for that year, `{headingKey, document: {id, name,
  effectiveDate}}`), and `/api/report/download/<document_id>/<file_name>`
  (the actual file). All three need a logged-in session; confirmed via a
  real 403 without one.
- New `fetch_freddie.py` module (separate from the Ginnie-specific
  `fetch.py`) implementing all three calls, plus
  `load_freddie_session()` reading a `Cookie` header and `x-csrf-token`
  from two local gitignored files (`data/freddie_cookie.txt`,
  `data/freddie_csrf_token.txt`) — never committed, never echoed back in
  any tool output after being saved.
- Found and fixed a real gotcha the hard way: Akamai's edge WAF returns a
  403 "Access Denied" (a different failure than the app-level session
  check) unless every request carries a same-origin `referer` header —
  independent of cookie validity or User-Agent, confirmed by toggling each
  header individually via curl. `agency_mbs.requests` calls were failing
  with this until the header was added.
- `parse_monthly_freddie_file`/`parse_freddie_factor_line`: Freddie's
  "Security Core File" (`fd<YYMMDD>.zip`) is pipe-delimited **with its own
  header row** naming all 98 columns — parsed by column name, not
  hardcoded byte positions, unlike every Ginnie Mae parser so far. `wac`
  comes from "WA Net Interest Rate" (the investor's actual pass-through
  rate); `wam` from "WA Current Remaining Months to Maturity" — a real WAM,
  which none of the Ginnie Mae pool-level files provide at all. `rate_type`
  is derived from "WA Mortgage Margin" (blank or its documented `77.777`
  "Not Applicable" sentinel -> fixed; any other value -> floating),
  confirmed against two real ARM rows and two real fixed rows in the same
  production file.
- Verified end-to-end against the live, authenticated API: the real
  August 2026 file, 462,779 records, all with a factor (Freddie's file
  reports paid-off securities as factor `0.0`, not blank, unlike some
  Ginnie Mae pool types). New `agency-mbs ingest freddie` command.
  49/49 tests passing (`fetch_freddie.py` at 100% coverage), `ruff`+`mypy`
  clean.

## 2026-09-01 (continued) — Freddie Mac historical backfill + a naming fix

- New `agency-mbs backfill freddie [--months N]` (default 12) walks
  Freddie's `listyears`/`list` endpoints, collects every "Factors for
  pools" document with `effectiveDate` in that window, and
  downloads+parses+stores each one — `list_factor_documents()` in
  `fetch_freddie.py` only queries the years that could actually contain a
  match instead of every year Freddie has. Verified against the live API:
  12 real periods (Sept 2025 - Aug 2026), 5,241,866 records total. The
  extracted `.txt` is deleted after parsing (the files run ~150MB
  uncompressed each); the much smaller `.zip` stays in `data/raw/`.
- **Renamed `wac` -> `coupon_rate` everywhere** (schema column, parser
  output, CLI display) after the operator pointed out a real domain error: what
  this project was calling "WAC" is actually the security/tranche's own
  investor-facing interest rate (Ginnie's "Pool Interest Rate", Freddie's
  "WA Net Interest Rate", REMIC's "Coupon Rate") — not the underlying
  collateral's true Weighted Average Coupon. WAC and coupon_rate are
  related (`coupon_rate = WAC - servicing/guaranty fees`) but genuinely
  different numbers that drift apart over time as the pool's loan
  composition changes, even when the security's own rate stays fixed.
  True collateral WAC isn't available in any file this project parses —
  it lives in the agencies' loan-level disclosure files, not the
  pool/security-level factor files used here. No new columns needed for
  "tranche vs. collateral" separation: each stored row is already scoped
  to one security or one REMIC tranche, so `coupon_rate` unambiguously
  means that row's own rate.
- Confirmed the rate-history ask ("store the interest rate history, at
  least for floating ones") was already satisfied by the existing
  one-row-per-`(pool_id, factor_date)` design — no schema change needed,
  just data: backfilling multiple periods naturally captures each
  period's `coupon_rate`, including real month-to-month resets for
  floating-rate securities.

## 2026-09-01 (continued) — investigated Ginnie Mae historical backfill (no code change)

- Confirmed, not just left unexplored, that Ginnie Mae has no bulk
  historical backfill available. Checked both leads from the roadmap:
  - The "FRR"/"SRF HISTORY FILES" catalog entries are NOT archives —
    despite the name, "FRR" is the Floater Tranche Reset Rate File
    (current-period REMIC floater resets) and "SRF" is the REMIC Series
    Factor File (current-period series-level factor + WAC/WARM/WALA) —
    both are just more current-month-only disclosures, per their own
    layout PDFs.
  - Re-grepped `bulk.ginniemae.gov`'s JS bundle for any
    history/archive/year-related API strings: none exist. The only data
    endpoints are the ones already used (`disclosure-data`,
    `layouts-sample-files`, the `dlfile` download) — there is no
    per-period listing endpoint like Freddie's `listyears`/`list`.
  - A real per-CUSIP history product does exist — Ginnie Mae's "Tax and
    Factor Data Search" tool produces a pipe-delimited "Pool RPB, Tax and
    Factor History Download File" (CUSIP, Pool Factor, Current Interest
    Rate, one row per Reporting Period). But it's capped at 20
    CUSIPs/pools per query with ~12 months of history, and the tool has
    moved off the old `TFDSearch.aspx` page onto Ginnie Mae's newer site
    (same SPA family as `bulk.ginniemae.gov`), meaning its real API isn't
    reverse-engineered yet. the operator's call: not worth pursuing right now
    — it's a per-CUSIP lookup tool, not a bulk backfill, and would need
    its own research effort for a capped, narrower payoff than Freddie's.
  - Decision: no Ginnie Mae backfill for now. History accumulates
    naturally, one row per `(pool_id, factor_date)`, as `ingest` runs
    forward each month — same mechanism that already gives Freddie Mac
    its history.

## 2026-09-01 (continued) — monthly scheduled ingestion

- New `scripts/monthly_ingest.sh`: runs `agency-mbs ingest <prefix>` for
  all 7 supported sources (6 Ginnie Mae prefixes + `freddie`), continuing
  past any single prefix's failure (e.g. Freddie's session cookie
  expiring) instead of aborting the whole run, and exiting non-zero at
  the end if anything failed so `journalctl` surfaces it.
- New `systemd/agency-mbs-monthly-ingest.{service,timer}`, following this
  environment's existing pattern (see `~/README.md`'s
  `sync-win-host-ip.timer`): day 10 of each month (buffer past the
  ~4th-6th-business-day publish schedule both agencies actually use),
  `Persistent=true` so a run missed while the WSL/Windows host was off
  fires once as soon as it's next up. Verified the unit files parse with
  `systemd-analyze verify` and the script's syntax with `bash -n`; not
  auto-installed since it needs `sudo` (interactive password, no
  `NOPASSWD` in this environment) — documented as a manual install step
  in the README instead.
- Installed and enabled on the operator's machine (`agency-mbs-monthly-ingest.timer`
  active/waiting, next trigger 2026-09-10 06:00 EST). Found along the way
  that an AI coding assistant's `!`-prefix bridge doesn't allocate a TTY, so `sudo`
  can't prompt through it (`sudo: a terminal is required to read the
  password`) — the operator had to run the install commands from his own real
  terminal instead. Documented in the README so this isn't rediscovered
  next time.
- New `agency-mbs notify <message>` + `agency_mbs.notify.send_telegram_message`:
  the monthly script now sends a one-line ✅/❌ summary via Telegram at the
  end of each run, reusing the exact same bot the operator's Windows-side
  scripts already use for Refinitiv/BNY2.0 alerts (same bot, same
  `chat_id` — see `C:\Users\operator\Scripts\README.md`'s
  "Alertas de Telegram" section). That side reads the token from Windows
  user environment variables (not visible from WSL); this side reads the
  same two values from local gitignored files
  (`data/telegram_bot_token.txt`, `data/telegram_chat_id.txt`) instead —
  same secret-handling convention as the Ginnie/Freddie session cookies.
  Silently no-ops if either file is missing or the request fails, matching
  `Send-TelegramAlert.ps1`'s own "never let an alert break the real
  automation" philosophy. This was necessary because a cloud-routine
  ("/schedule" skill) approach to checking on the timer turned out to be
  the wrong tool entirely — cloud agents have no access to a local
  machine's `systemd`/`journalctl` at all, so a self-notifying script was
  the only real solution to "let me know when this runs."

## 2026-09-01 (continued) — REST API

- New `agency_mbs.api` (FastAPI, needs the new `api` extra:
  `pip install -e ".[api]"`) — a thin read-only layer over
  `agency_mbs.store`, no business logic duplicated: `GET /health` and
  `GET /lookup/{identifier}` (12-char ISIN or 9-char CUSIP, same rule as
  the CLI). New `agency-mbs serve [--host] [--port]` runs it, binding
  `127.0.0.1` by default — no auth layer exists, so it isn't meant to be
  exposed on the network.
- **Found and fixed a real threading bug, not just a test artifact:**
  FastAPI can resolve a sync dependency (`get_db`) and run the route's own
  sync body in two different threadpool worker threads for the same
  request; SQLite's default `check_same_thread=True` rejects that even
  though only one thread ever touches the connection at a time.
  `agency_mbs.store.get_connection` gained a `check_same_thread` keyword
  (default unchanged) so the API can opt into `False`. Confirmed this
  wasn't just a `TestClient` quirk by reproducing it against a real
  running `uvicorn` server via curl.
- **Found and fixed a real, separate bug this surfaced in the existing
  CLI too:** Ginnie Mae's shared placeholder CUSIP for non-CUSIP-eligible
  REMIC tranches (`"C99999999"`, from the earlier shared-CUSIP fix) fails
  a real CUSIP checksum by construction — it's a sentinel, not an assigned
  identifier. The CLI's `lookup` (and the new API) both ran every 9-char
  identifier through `validate_cusip`, meaning `agency-mbs lookup
  C99999999` would have 400'd on real, already-stored data. Centralized
  the previously-duplicated CLI/API resolution logic into
  `agency_mbs.isin.resolve_identifier`: a 12-char identifier is still
  fully checksum-validated as an ISIN (a mistyped ISIN is a real, common
  failure worth catching), but a 9-char one is now only length-checked,
  not checksum-validated — a genuinely wrong CUSIP just returns no rows,
  a harmless outcome for a typo.
- 77/77 tests passing (`tests/test_api.py` didn't exist before this
  change), `ruff`+`mypy` clean (added a documented per-file ignore for
  ruff's B008 on `api.py` — FastAPI's `Depends(...)` default-argument
  pattern is idiomatic, not the mutable-default bug that rule normally
  catches).
