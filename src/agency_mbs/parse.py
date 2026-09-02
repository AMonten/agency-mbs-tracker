"""Parsing of Ginnie Mae and Freddie Mac pool/tranche-factor files.

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
this parser doesn't need and ignores either way. `factorAAdd_layout.pdf`
("Factor File A 'Additional' Layout — Ginnie II Pools") uses the exact
same first 171 bytes plus 7 more (a filler byte and a 6-digit "Factor
Percentage Complete" field, MIP-only, out of scope for this project) —
its documented record length is 178, but the *real* production file
(confirmed via an authenticated download, not just its sample) has every
one of its 308,073 rows at 171 bytes: the trailing MIP-only tail is
entirely omitted, not space-padded, when blank. `parse_pool_factor_line` /
`parse_monthly_factor_file` take a `valid_lengths` override for this
reason — `factorAAdd` passes `(171, 178)` so either shape parses, while
factorA1/A2/Aplat still only accept the exact 171. One function covers all
four prefixes: `factorA1` (Ginnie I), `factorA2` (Ginnie II), `factorAplat`
(Platinum), `factorAAdd` (Additional).

Each covered against its own real public sample file
(factorA1_sample.txt / factorA2_sample.txt / factorAplat_sample.txt /
factorAAdd_sample.txt, same directory, checked into tests/fixtures/) —
every data line in each sample slices cleanly per this layout (the
factorAAdd sample's lines are 171 chars too, for the same real reason).

Fields NOT available in these files (left as None, not guessed):
- prior_factor: these files only carry the current period's factor: the
  previous month's value has to come from our own stored history, not from
  the source file (see agency_mbs.store).
- wam: these files have issue/maturity dates for the *security*, not a
  loan-level weighted average maturity. Real WAM needs loan-level data,
  which is a different disclosure file (llmon).

`rate_type` ("fixed" or "floating") is derived from the "Original Interest
Rate" field (byte range 141-145), which the agency's own Platinum layout
notes document as "Populated for ARM Pools only" — confirmed against real
production data: blank for every "SF" (fixed) pool checked, populated for
every real "RF" (reverse-mortgage ARM) pool checked (18,352 of them in the
real August 2026 factorA2 file). Blank -> "fixed", populated -> "floating".

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

This file has no fixed/floating indicator at all (unlike the pool-level
files' "Original Interest Rate" signal) — REMIC tranche records always get
`rate_type: None` rather than a guessed value. A tranche name prefix like
"F"/"S" often hints at floater/inverse-floater in practice, but that's a
market convention, not something the agency's own layout documents, so
it's not relied on here.

Freddie Mac layout (`parse_freddie_factor_line` / `parse_monthly_freddie_file`)
confirmed against Freddie's own Disclosure Guide (v6.2,
capitalmarkets.freddiemac.com/mbs/docs/disclosure_guide.pdf, "Security Core
File" section) and a real authenticated download (fd260806.zip, 461,779
pool records) — see agency_mbs.fetch_freddie for the source. Pipe-delimited
text **with a header row** naming every column (98 of them) — much simpler
than Ginnie Mae's fixed-width COBOL-style layout, since fields are looked
up by name instead of hardcoded byte position.

Only a handful of the 98 columns are used: Prefix + Security Identifier
(-> pool_id), CUSIP, Security Factor Date (MMCCYY -> factor_date), Security
Factor (-> current_factor), Issuance/Current Investor Security UPB (->
upb_original/upb_current), WA Net Interest Rate (-> coupon_rate: the rate
net of servicing/guarantee fees, i.e. what's actually passed through to
the investor — this is NOT collateral WAC, see agency_mbs.store's module
docstring for that distinction), and WA Current Remaining Months to
Maturity (-> wam — Freddie actually discloses this; Ginnie Mae's
pool-level files don't).

`rate_type` is derived from "WA Mortgage Margin", which the Disclosure
Guide documents as ARM-only with `77.777` as an explicit "Not Applicable"
sentinel (used instead of a blank in some rows) — blank or `77.777` ->
"fixed", any other value -> "floating". Confirmed against real rows: two
real ARM securities (margin 2.468 and 2.250, each with a populated
"Index" too) and two real fixed securities (margin and Index both blank)
in the same production file.

`issuer` is read directly from the file's own "Issuer" column rather than
hardcoded to "FRE" — the field is documented as "FNM = Fannie Mae, FRE =
Freddie Mac", so a Freddie-distributed file can in principle carry
Fannie-issued rows (not observed yet, but worth preserving rather than
overwriting).
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
    ("original_interest_rate", 141, 145),
    ("cusip", 163, 171),
]
POOL_FACTOR_RECORD_LENGTH = 171
# factorAAdd's documented length (171 bytes plus a filler + MIP-only tail
# field this project doesn't use) — its real production rows are 171 bytes
# whenever that tail is blank, which is effectively always so far.
ADDITIONAL_RECORD_LENGTH = 178

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


def parse_pool_factor_line(
    line: str, *, valid_lengths: tuple[int, ...] = (POOL_FACTOR_RECORD_LENGTH,)
) -> dict | None:
    """Parse one fixed-width pool-factor data line (factorA1/A2/Aplat/AAdd).

    Returns None for header/footer/blank lines — anything whose length
    isn't in `valid_lengths`. factorAAdd passes `(171, 178)` since its real
    rows may or may not carry the MIP-only tail (see module docstring);
    the other three prefixes use the default, exact-171 check.
    """
    if len(line) not in valid_lengths:
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
    # This is the security's own pass-through rate, NOT collateral WAC.
    coupon_rate = pool_interest_rate / 1000 if pool_interest_rate is not None else None
    # Amounts are 9(13)v9(2): implied 2 decimal places.
    upb_original = original_aggregate_amount / 100 if original_aggregate_amount is not None else None
    upb_current = remaining_security_rpb / 100 if remaining_security_rpb is not None else None
    # "Original Interest Rate" is only populated for ARM pools (see module
    # docstring) — its presence, not its value, is the fixed/floating signal.
    rate_type = "floating" if fields["original_interest_rate"] else "fixed"

    return {
        "cusip": fields["cusip"],
        "pool_id": fields["pool_number"],
        "issuer": "GNMA",
        "current_factor": current_factor,
        "prior_factor": None,
        "coupon_rate": coupon_rate,
        "rate_type": rate_type,
        "wam": None,
        "upb_original": upb_original,
        "upb_current": upb_current,
    }


def parse_monthly_factor_file(
    path: Path, *, valid_lengths: tuple[int, ...] = (POOL_FACTOR_RECORD_LENGTH,)
) -> list[dict]:
    """Parse one factorA1/A2/Aplat/AAdd-format raw file into pool-factor records.

    `factor_date` is derived from the filename's YYYYMM period (e.g.
    "factorA1_202607.zip" -> "2026-07-01"). Pass `valid_lengths=(171, 178)`
    for factorAAdd — see parse_pool_factor_line.
    """
    path = Path(path)
    factor_date = f"{period_from_filename(path.name)}-01"
    records = []
    with open(path, encoding="latin-1") as f:
        for line in f:
            record = parse_pool_factor_line(line.rstrip("\n").rstrip("\r"), valid_lengths=valid_lengths)
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
        "coupon_rate": _float_or_none(fields["coupon_rate"]),  # the tranche's own rate, not collateral WAC
        "rate_type": None,  # not derivable from this file, see module docstring
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


# "Not Applicable" sentinel Freddie Mac uses in several ARM-only numeric
# fields (e.g. WA Mortgage Margin) instead of leaving them blank.
_FREDDIE_NOT_APPLICABLE = "77.777"


def _freddie_date_to_iso(mmccyy: str) -> str | None:
    """Convert a Freddie "MMCCYY" date (e.g. "082026") to "YYYY-MM-01"."""
    if not mmccyy:
        return None
    month, year = mmccyy[:2], mmccyy[2:]
    return f"{year}-{month}-01"


def parse_freddie_factor_line(fields: dict[str, str]) -> dict:
    """Normalize one row of Freddie Mac's pipe-delimited Security Core File.

    `fields` is a dict already mapping the file's own header column names
    to that row's raw string values (see parse_monthly_freddie_file).
    """
    margin = fields["WA Mortgage Margin"]
    rate_type = "fixed" if margin in ("", _FREDDIE_NOT_APPLICABLE) else "floating"

    return {
        "cusip": fields["CUSIP"],
        "pool_id": f"{fields['Prefix']}-{fields['Security Identifier']}",
        "issuer": fields["Issuer"],
        "factor_date": _freddie_date_to_iso(fields["Security Factor Date"]),
        "current_factor": _float_or_none(fields["Security Factor"]),
        "prior_factor": None,
        "coupon_rate": _float_or_none(fields["WA Net Interest Rate"]),
        "rate_type": rate_type,
        "wam": _int_or_none(fields["WA Current Remaining Months to Maturity"]),
        "upb_original": _float_or_none(fields["Issuance Investor Security UPB"]),
        "upb_current": _float_or_none(fields["Current Investor Security UPB"]),
    }


def parse_monthly_freddie_file(path: Path) -> list[dict]:
    """Parse one Freddie Mac "fd*.txt" Security Core File into factor records.

    Uses the file's own header row to map columns by name — no hardcoded
    positions, unlike the Ginnie Mae parsers.
    """
    path = Path(path)
    records = []
    with open(path, encoding="latin-1") as f:
        header = f.readline().rstrip("\n").rstrip("\r").split("|")
        for line in f:
            values = line.rstrip("\n").rstrip("\r").split("|")
            fields = dict(zip(header, values, strict=True))
            records.append(parse_freddie_factor_line(fields))
    return records
