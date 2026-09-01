"""Parsing of Ginnie Mae pool-level factor files and REMIC/CMO tranche files.

Pool-level layout (`parse_pool_factor_line` / `parse_monthly_factor_file`)
confirmed against the agency's own published specs, all downloaded from
https://www.ginniemae.gov/s3/sites/default/files/disclosure_data_files/:
"Factor File Layout — Ginnie I Pools" (factorA1_layout.pdf), "...Ginnie II
Pools" (factorA2_layout.pdf), and "Platinum Pool Factor A File Layout"
(factorAplat_layout.pdf, v1.0). All three use the exact same 171-character,
column-for-column layout for the fields this project cares about (pool
number, issuer name, amounts, RPB factor, interest rate, dates, CUSIP) —
Ginnie II/Platinum just also define ARM-specific fields (margin, interest
adjustment dates, etc.) in the byte range factorA1 leaves as filler, which
this parser doesn't need and ignores either way. One function covers all
three prefixes: `factorA1` (Ginnie I), `factorA2` (Ginnie II), `factorAplat`
(Platinum). `factorAAdd` (Additional) is not confirmed to share this layout
yet — check its own layout PDF before assuming it does.

Each covered against its own real public sample file
(factorA1_sample.txt / factorA2_sample.txt / factorAplat_sample.txt, same
directory, checked into tests/fixtures/) — every data line in each sample
is exactly 171 characters and slices cleanly per this layout.

Fields NOT available in these files (left as None, not guessed):
- prior_factor: these files only carry the current period's factor: the
  previous month's value has to come from our own stored history, not from
  the source file (see agency_mbs.store).
- wam: these files have issue/maturity dates for the *security*, not a
  loan-level weighted average maturity. Real WAM needs loan-level data,
  which is a different disclosure file (llmon).

Confirmed against the real full production factorA1_202607.txt (106,393
pool records, downloaded via a real authenticated session — not just the
small sample): ~2.5% of rows (2,668 of 106,393), all with `pool_type ==
"SP"`, have the RPB Factor and Remaining Security RPB fields entirely
blank (space-filled) rather than zero-filled. This looks like a real
characteristic of certain pool types, not a parsing bug — `current_factor`
/`upb_current` are left as `None` for those rows rather than coerced to 0,
so history stays honest about what the agency actually reported. Not yet
confirmed whether Ginnie II/Platinum production files have the same
quirk — only their small samples have been checked so far.

REMIC/CMO tranche layout (`parse_remic_tranche_line` /
`parse_monthly_remic_file`) confirmed against remic1_layout.pdf /
remic2_layout.pdf ("MTF FILE LAYOUT") — both prefixes publish the exact
same layout and, in the agency's own sample files, identical sample data;
the agency's docs don't explain what actually differs between `remic1`
and `remic2` in production beyond that. This is a different file shape
from the pool-level factor files: one header line (record indicator "1"),
one data line per tranche (indicator "2", 117 characters, CUSIP + tranche
factor + coupon rate + balances — numeric fields here have a literal
decimal point in the text, unlike the pool files' implied decimals), and
one footer line with aggregate totals (indicator "3"). Only data lines are
parsed; header/footer are skipped.
"""

from __future__ import annotations

import re
from pathlib import Path

# (name, begin, end) — 1-indexed, inclusive. Shared by factorA1/factorA2/
# factorAplat; see module docstring for why one layout covers all three.
POOL_FACTOR_LAYOUT = [
    ("pool_number", 1, 6),
    ("pool_indicator", 7, 7),
    ("issuer_number", 8, 11),
    ("issuer_name", 13, 72),
    ("original_aggregate_amount", 73, 87),
    ("remaining_security_rpb", 88, 102),
    ("rpb_factor", 103, 111),
    ("pool_interest_rate", 112, 116),
    ("pool_type", 117, 118),
    ("pool_issue_date", 119, 124),
    ("pool_maturity_date", 125, 130),
    ("cusip", 163, 171),
]
POOL_FACTOR_RECORD_LENGTH = 171

# (name, begin, end) — 1-indexed, inclusive, for a REMIC data line
# (record indicator "2") per remic1_layout.pdf / remic2_layout.pdf.
REMIC_TRANCHE_LAYOUT = [
    ("series", 2, 16),
    ("tranche_name", 17, 25),
    ("cusip", 26, 34),
    ("tranche_factor", 35, 45),
    ("coupon_rate", 46, 56),
    ("final_distribution_date", 57, 65),
    ("original_balance", 66, 82),
    ("current_balance", 83, 99),
    ("payment_date", 100, 108),
    ("first_accrual_date", 109, 117),
]
REMIC_RECORD_LENGTH = 117
REMIC_DATA_RECORD_INDICATOR = "2"

_PERIOD_RE = re.compile(r"(\d{4})(\d{2})")


def _slice(line: str, begin: int, end: int) -> str:
    return line[begin - 1 : end].strip()


def _int_or_none(s: str) -> int | None:
    return int(s) if s else None


def _float_or_none(s: str) -> float | None:
    return float(s) if s else None


def period_from_filename(filename: str) -> str:
    """Extract "YYYY-MM" from a bulk filename like "factorA1_202607.zip"."""
    match = _PERIOD_RE.search(filename)
    if not match:
        raise ValueError(f"Could not find a YYYYMM period in filename: {filename!r}")
    return f"{match.group(1)}-{match.group(2)}"


def parse_pool_factor_line(line: str) -> dict | None:
    """Parse one fixed-width pool-factor data line (factorA1/A2/Aplat).

    Returns None for header/footer/blank lines (anything not exactly
    POOL_FACTOR_RECORD_LENGTH characters).
    """
    if len(line) != POOL_FACTOR_RECORD_LENGTH:
        return None
    fields = {name: _slice(line, begin, end) for name, begin, end in POOL_FACTOR_LAYOUT}

    # Numeric fields are occasionally blank (space-filled) rather than
    # zero-filled in real production files (see module docstring) — treat
    # blank as "not reported", not as zero.
    rpb_factor = _int_or_none(fields["rpb_factor"])
    pool_interest_rate = _int_or_none(fields["pool_interest_rate"])
    original_aggregate_amount = _int_or_none(fields["original_aggregate_amount"])
    remaining_security_rpb = _int_or_none(fields["remaining_security_rpb"])

    # RPB Factor is 9(1)v9(8): 9 digits, implied decimal after the 1st digit.
    current_factor = rpb_factor / 1e8 if rpb_factor is not None else None
    # Pool Interest Rate is 9(2)v9(3): 5 digits, implied decimal after the 2nd.
    wac = pool_interest_rate / 1000 if pool_interest_rate is not None else None
    # Amounts are 9(13)v9(2): implied 2 decimal places.
    upb_original = original_aggregate_amount / 100 if original_aggregate_amount is not None else None
    upb_current = remaining_security_rpb / 100 if remaining_security_rpb is not None else None

    return {
        "cusip": fields["cusip"],
        "pool_id": fields["pool_number"],
        "issuer": "GNMA",
        "current_factor": current_factor,
        "prior_factor": None,
        "wac": wac,
        "wam": None,
        "upb_original": upb_original,
        "upb_current": upb_current,
    }


def parse_monthly_factor_file(path: Path) -> list[dict]:
    """Parse one factorA1/A2/Aplat-format raw file into pool-factor records.

    `factor_date` is derived from the filename's YYYYMM period (e.g.
    "factorA1_202607.zip" -> "2026-07-01").
    """
    path = Path(path)
    factor_date = f"{period_from_filename(path.name)}-01"
    records = []
    with open(path, encoding="latin-1") as f:
        for line in f:
            record = parse_pool_factor_line(line.rstrip("\n").rstrip("\r"))
            if record is not None:
                record["factor_date"] = factor_date
                records.append(record)
    return records


def parse_remic_tranche_line(line: str) -> dict | None:
    """Parse one REMIC/CMO tranche data line (record indicator "2").

    Returns None for header/footer/blank lines — anything not exactly
    REMIC_RECORD_LENGTH characters starting with the data record
    indicator.
    """
    if len(line) != REMIC_RECORD_LENGTH or not line.startswith(REMIC_DATA_RECORD_INDICATOR):
        return None
    fields = {name: _slice(line, begin, end) for name, begin, end in REMIC_TRANCHE_LAYOUT}

    return {
        "cusip": fields["cusip"],
        "pool_id": f"{fields['series']}-{fields['tranche_name']}",
        "issuer": "GNMA",
        "current_factor": _float_or_none(fields["tranche_factor"]),
        "prior_factor": None,
        "wac": _float_or_none(fields["coupon_rate"]),
        "wam": None,
        "upb_original": _float_or_none(fields["original_balance"]),
        "upb_current": _float_or_none(fields["current_balance"]),
    }


def parse_monthly_remic_file(path: Path) -> list[dict]:
    """Parse one remic1/remic2-format raw file into tranche-factor records.

    `pool_id` holds "<series>-<tranche_name>" (e.g. "GNMA-1994-001-PK"),
    since a REMIC tranche isn't identified by a single pool number.
    `factor_date` is derived from the filename's YYYYMM period, same
    convention as parse_monthly_factor_file.
    """
    path = Path(path)
    factor_date = f"{period_from_filename(path.name)}-01"
    records = []
    with open(path, encoding="latin-1") as f:
        for line in f:
            record = parse_remic_tranche_line(line.rstrip("\n").rstrip("\r"))
            if record is not None:
                record["factor_date"] = factor_date
                records.append(record)
    return records
