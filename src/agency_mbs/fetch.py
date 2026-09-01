"""Download of Ginnie Mae bulk disclosure files.

STATUS: not yet implemented against a verified endpoint.

Ginnie Mae publishes daily/weekly/monthly/factor disclosure files in bulk
(not just per-CUSIP search) at https://bulk.ginniemae.gov/, with file
layouts documented separately at
https://www.ginniemae.gov/disclosure/disclosure-resources/disclosure-data-download-layouts-and-sample-files
and a data dictionary (MBS_SingleFamily_Pool_DataDictionary). The exact
request shape for the monthly pool-level factor file (query params vs. a
static path per period, auth/session requirements, file naming convention)
has NOT been confirmed yet — bulk.ginniemae.gov renders through JavaScript,
so it needs a manual look (browser devtools network tab) before this module
can make real requests.

Next step before this is real: open bulk.ginniemae.gov in a browser, find
the request that fetches one month of Single Family Pool factor data, and
port that request here.
"""

from __future__ import annotations

from pathlib import Path

BULK_DISCLOSURE_BASE_URL = "https://bulk.ginniemae.gov"

RAW_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"


def fetch_monthly_factor_file(period: str, *, dest_dir: Path = RAW_DATA_DIR) -> Path:
    """Download the Single Family pool-level factor file for a given period.

    Args:
        period: "YYYY-MM" for the disclosure month.
        dest_dir: directory to save the raw file into.

    Raises:
        NotImplementedError: the real bulk.ginniemae.gov request shape has
            not been confirmed yet (see module docstring).
    """
    raise NotImplementedError(
        "bulk.ginniemae.gov request shape not yet confirmed — "
        "see agency_mbs.fetch module docstring before implementing."
    )
