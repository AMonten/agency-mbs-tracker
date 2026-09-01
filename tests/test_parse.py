from pathlib import Path

import pytest

from agency_mbs.parse import (
    parse_factor_a1_line,
    parse_monthly_factor_file,
    period_from_filename,
)

FIXTURE = Path(__file__).parent / "fixtures" / "factorA1_202607.txt"


def test_period_from_filename():
    assert period_from_filename("factorA1_202607.zip") == "2026-07"
    assert period_from_filename("factorAplat_202607.txt") == "2026-07"


def test_period_from_filename_rejects_missing_period():
    with pytest.raises(ValueError):
        period_from_filename("factorA1.zip")


def test_parse_factor_a1_line_real_row():
    # First data row from the agency's own public sample file.
    real_line = FIXTURE.read_text().splitlines()[4]
    record = parse_factor_a1_line(real_line)
    assert record is not None
    assert record["cusip"] == "36177XQT8"
    assert record["pool_id"] == "AA1366"
    assert record["issuer"] == "GNMA"
    assert 0 < record["current_factor"] <= 1
    assert record["wac"] > 0
    assert record["upb_original"] > 0
    assert record["upb_current"] > 0


def test_parse_factor_a1_line_skips_non_data_lines():
    assert parse_factor_a1_line("Factor A G1 Sample:") is None
    assert parse_factor_a1_line("") is None
    assert parse_factor_a1_line("HDR.S81106.E00.CGNMA.S9998 040512") is None


def test_parse_monthly_factor_file_end_to_end():
    records = parse_monthly_factor_file(FIXTURE)
    assert len(records) == 15  # 15 real pool records in the agency's sample file
    assert all(r["factor_date"] == "2026-07-01" for r in records)
    cusips = {r["cusip"] for r in records}
    assert "36177XQT8" in cusips
