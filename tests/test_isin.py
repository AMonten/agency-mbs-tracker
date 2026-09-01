import pytest

from agency_mbs.isin import (
    InvalidCUSIPError,
    InvalidISINError,
    isin_to_cusip,
    validate_cusip,
    validate_isin,
)


def test_isin_to_cusip_real_ginnie_mae_example():
    assert isin_to_cusip("US38384CNA35") == "38384CNA3"


def test_isin_to_cusip_lowercase_and_whitespace_tolerant():
    assert isin_to_cusip(" us38384cna35 ") == "38384CNA3"


def test_validate_isin_accepts_valid_isin():
    assert validate_isin("US38384CNA35") == "US38384CNA35"


def test_validate_cusip_accepts_valid_cusip():
    assert validate_cusip("38384CNA3") == "38384CNA3"


def test_validate_isin_rejects_bad_check_digit():
    with pytest.raises(InvalidISINError):
        validate_isin("US38384CNA30")


def test_validate_cusip_rejects_bad_check_digit():
    with pytest.raises(InvalidCUSIPError):
        validate_cusip("38384CNA0")


def test_isin_to_cusip_rejects_wrong_length():
    with pytest.raises(InvalidISINError):
        isin_to_cusip("US38384CNA")


def test_isin_to_cusip_skip_validation():
    # Structural slice only, no check-digit verification.
    assert isin_to_cusip("US38384CNA30", validate=False) == "38384CNA3"
