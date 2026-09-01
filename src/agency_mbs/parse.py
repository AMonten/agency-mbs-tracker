"""Parsing of Ginnie Mae Single Family pool-level disclosure files.

STATUS: not yet implemented against a verified layout.

Ginnie Mae documents the exact fixed-width/delimited layout of each
disclosure file in its data dictionary (see agency_mbs.fetch docstring for
the source). This module should parse a raw file (as saved by
agency_mbs.fetch) into a list of dicts matching the schema used by
agency_mbs.store.upsert_factor_records:
    cusip, pool_id, issuer, factor_date, current_factor, prior_factor,
    wac, wam, upb_original, upb_current

Next step before this is real: get one real sample file (Ginnie Mae
publishes sample files alongside the layout docs), confirm column
positions/names against the data dictionary, and implement the parser
against that concrete sample.
"""

from __future__ import annotations

from pathlib import Path


def parse_monthly_factor_file(path: Path) -> list[dict]:
    """Parse one raw monthly factor file into normalized pool-factor records.

    Raises:
        NotImplementedError: the real file layout has not been confirmed
            yet (see module docstring).
    """
    raise NotImplementedError(
        "Ginnie Mae disclosure file layout not yet confirmed against a real "
        "sample — see agency_mbs.parse module docstring before implementing."
    )
