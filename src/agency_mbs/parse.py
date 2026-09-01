"""Parsing of Ginnie Mae Single Family pool-level factor files.

Layout confirmed against the agency's own published spec ("Factor File
Layout — Ginnie I Pools -- One Record per Pool", from
factorA1_layout.pdf, downloaded from
https://www.ginniemae.gov/s3/sites/default/files/disclosure_data_files/factorA1_layout.pdf)
and cross-checked against the real public sample file
(factorA1_sample.txt, same directory) — every data line in the sample is
exactly 171 characters and slices cleanly per this layout, including a
plausible CUSIP in the last 9 characters.

This covers the "FACTOR A G I" file (`factorA1`, Ginnie Mae I single-family
factors) only. The other Factor Files entries (factorA2 = Ginnie II,
factorAplat = Platinum, factorAAdd = Additional, remic1/remic2 = REMIC/CMO
tranches) each have their own layout PDF under the same
disclosure_data_files/ path and are NOT parsed yet — same shape of work,
just not done.

Fields NOT available in this file (left as None, not guessed):
- prior_factor: this file only carries the current period's factor: the
  previous month's value has to come from our own stored history, not from
  this source file (see agency_mbs.store).
- wam: this file has issue/maturity dates for the *security*, not a
  loan-level weighted average maturity. Real WAM needs loan-level data,
  which is a different disclosure file (llmon).

Confirmed against the real full production file (factorA1_202607.txt,
106,393 pool records, downloaded via a real authenticated session — not
just the small sample): ~2.5% of rows (2,668 of 106,393), all with
`pool_type == "SP"`, have the RPB Factor and Remaining Security RPB fields
entirely blank (space-filled) rather than zero-filled. This looks like a
real characteristic of certain pool types in this file, not a parsing bug
— `current_factor`/`upb_current` are left as `None` for those rows rather
than coerced to 0, so history stays honest about what the agency actually
reported.
"""

from __future__ import annotations

import re
from pathlib import Path

# (name, begin, end) — 1-indexed, inclusive, per the agency's own layout PDF.
FACTOR_A1_LAYOUT = [
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
FACTOR_A1_RECORD_LENGTH = 171

_PERIOD_RE = re.compile(r"(\d{4})(\d{2})")


def _slice(line: str, begin: int, end: int) -> str:
    return line[begin - 1 : end].strip()


def _int_or_none(s: str) -> int | None:
    return int(s) if s else None


def period_from_filename(filename: str) -> str:
    """Extract "YYYY-MM" from a bulk filename like "factorA1_202607.zip"."""
    match = _PERIOD_RE.search(filename)
    if not match:
        raise ValueError(f"Could not find a YYYYMM period in filename: {filename!r}")
    return f"{match.group(1)}-{match.group(2)}"


def parse_factor_a1_line(line: str) -> dict | None:
    """Parse one fixed-width data line. Returns None for header/blank lines."""
    if len(line) != FACTOR_A1_RECORD_LENGTH:
        return None
    fields = {name: _slice(line, begin, end) for name, begin, end in FACTOR_A1_LAYOUT}

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
    """Parse one factorA1-format raw file into normalized pool-factor records.

    `factor_date` is derived from the filename's YYYYMM period (e.g.
    "factorA1_202607.zip" -> "2026-07-01").
    """
    path = Path(path)
    factor_date = f"{period_from_filename(path.name)}-01"
    records = []
    with open(path, encoding="latin-1") as f:
        for line in f:
            record = parse_factor_a1_line(line.rstrip("\n").rstrip("\r"))
            if record is not None:
                record["factor_date"] = factor_date
                records.append(record)
    return records
