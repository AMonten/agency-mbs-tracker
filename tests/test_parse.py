from pathlib import Path

import pytest

from agency_mbs.parse import (
    parse_monthly_factor_file,
    parse_monthly_remic_file,
    parse_pool_factor_line,
    parse_remic_tranche_line,
    period_from_filename,
)

FIXTURES = Path(__file__).parent / "fixtures"
FACTOR_A1 = FIXTURES / "factorA1_202607.txt"
FACTOR_A2 = FIXTURES / "factorA2_202607.txt"
FACTOR_APLAT = FIXTURES / "factorAplat_202607.txt"
REMIC1 = FIXTURES / "remic1_202607.txt"
REMIC2 = FIXTURES / "remic2_202607.txt"


def test_period_from_filename():
    assert period_from_filename("factorA1_202607.zip") == "2026-07"
    assert period_from_filename("factorAplat_202607.txt") == "2026-07"


def test_period_from_filename_rejects_missing_period():
    with pytest.raises(ValueError):
        period_from_filename("factorA1.zip")


def test_parse_pool_factor_line_real_row():
    # First data row from the agency's own public sample file (Ginnie I).
    real_line = FACTOR_A1.read_text().splitlines()[4]
    record = parse_pool_factor_line(real_line)
    assert record is not None
    assert record["cusip"] == "36177XQT8"
    assert record["pool_id"] == "AA1366"
    assert record["issuer"] == "GNMA"
    assert 0 < record["current_factor"] <= 1
    assert record["wac"] > 0
    assert record["rate_type"] == "fixed"  # Ginnie I has no ARM-specific fields at all
    assert record["upb_original"] > 0
    assert record["upb_current"] > 0


def test_parse_pool_factor_line_arm_pool_is_floating():
    # Real row from the production factorA2_202607.txt file, a "RF"
    # (reverse-mortgage ARM) pool. "Original Interest Rate" is populated
    # (04547 -> field non-blank) — that's the documented ARM-only signal.
    line = (
        "AA1681H9281 GINNIE MAE - REVERSE MORTGAGE FUNDING                       "
        "00000196353670000000000516469300026303004700RF100112092062"
        "    000000045470470000000000000036177X2N7"
    )
    assert len(line) == 171
    record = parse_pool_factor_line(line)
    assert record is not None
    assert record["cusip"] == "36177X2N7"
    assert record["rate_type"] == "floating"
    assert record["wac"] == pytest.approx(4.7)


def test_parse_pool_factor_line_blank_factor_is_none_not_zero():
    # Real row from the production factorA1_202607.txt file (pool_type="SP",
    # ~2.5% of that file's 106,393 rows have RPB Factor/remaining RPB blank
    # rather than zero-filled) — must not crash and must not fabricate 0.0.
    line = (
        "780412X9999 GNMA PLATINUM SECURITIES                                    "
        "000030027723900                        07500SP080196081526"
        "                                36225AN55"
    )
    record = parse_pool_factor_line(line)
    assert record is not None
    assert record["cusip"] == "36225AN55"
    assert record["current_factor"] is None
    assert record["upb_current"] is None
    assert record["upb_original"] == 300277239.00
    assert record["wac"] == 7.5


def test_parse_pool_factor_line_skips_non_data_lines():
    assert parse_pool_factor_line("Factor A G1 Sample:") is None
    assert parse_pool_factor_line("") is None
    assert parse_pool_factor_line("HDR.S81106.E00.CGNMA.S9998 040512") is None


def test_parse_monthly_factor_file_ginnie_i():
    records = parse_monthly_factor_file(FACTOR_A1)
    assert len(records) == 15  # 15 real pool records in the agency's sample file
    assert all(r["factor_date"] == "2026-07-01" for r in records)
    assert "36177XQT8" in {r["cusip"] for r in records}


def test_parse_monthly_factor_file_ginnie_ii():
    # Same 171-char layout as Ginnie I, confirmed against factorA2's own
    # real public sample (factorA2_layout.pdf defines the same column
    # positions for every field this project uses).
    records = parse_monthly_factor_file(FACTOR_A2)
    assert len(records) == 15
    assert "36177XAM0" in {r["cusip"] for r in records}


def test_parse_monthly_factor_file_platinum():
    # Same 171-char layout again (factorAplat_layout.pdf v1.0), confirmed
    # against factorAplat's own real public sample.
    records = parse_monthly_factor_file(FACTOR_APLAT)
    assert len(records) == 16
    assert "3622A3CT5" in {r["cusip"] for r in records}
    assert all(r["issuer"] == "GNMA" for r in records)


def test_parse_remic_tranche_line_real_row():
    # First data row from the agency's own real REMIC sample file.
    real_line = next(
        line for line in REMIC1.read_text().splitlines() if line.startswith("2")
    )
    record = parse_remic_tranche_line(real_line)
    assert record is not None
    assert record["cusip"] == "3837H0AG8"
    assert record["pool_id"] == "GNMA-1994-001-PK"
    assert record["issuer"] == "GNMA"
    assert record["current_factor"] == pytest.approx(0.21552923)
    assert record["wac"] == pytest.approx(7.9)
    assert record["upb_original"] == 26635000.00
    assert record["upb_current"] == pytest.approx(5740621.14)


def test_parse_remic_tranche_line_zero_factor_is_zero_not_none():
    # Real fully-paid-down tranche: factor and current balance are
    # genuinely 0, not blank — must be distinguished from the blank-field
    # case in the pool-level files.
    line = (
        "2GNMA-1994-002  A        3837H0AW3  .00000000    6.50000 20050416"
        "      38600000.00              .00 20120316 19940701"
    )
    record = parse_remic_tranche_line(line)
    assert record is not None
    assert record["current_factor"] == 0.0
    assert record["upb_current"] == 0.0


def test_parse_remic_tranche_line_skips_header_and_footer():
    assert parse_remic_tranche_line("1      03/14/2012  02/29/2012  TRANCHE FILE HEADER") is None
    assert (
        parse_remic_tranche_line(
            "3      TOTAL AGGREGATE:1465592866525.44   TOTAL BALANCE:798552116697.54 "
            "TOTAL NUMBER OF POOLS:          17913"
        )
        is None
    )
    assert parse_remic_tranche_line("") is None


def test_parse_monthly_remic_file_remic1():
    records = parse_monthly_remic_file(REMIC1)
    assert len(records) == 27  # 27 real tranche records in the agency's sample file
    assert all(r["factor_date"] == "2026-07-01" for r in records)
    assert "3837H0AG8" in {r["cusip"] for r in records}


def test_parse_monthly_remic_file_remic2():
    # Agency publishes the same layout and (in the samples, at least)
    # identical sample content for remic1 and remic2 — same parser covers
    # both prefixes.
    records = parse_monthly_remic_file(REMIC2)
    assert len(records) == 27
