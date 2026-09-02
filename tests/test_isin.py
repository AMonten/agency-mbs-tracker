import pytest

from agency_mbs.isin import (
    InvalidCUSIPError,
    InvalidISINError,
    isin_to_cusip,
    resolve_identifier,
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


def test_resolve_identifier_from_isin():
    assert resolve_identifier(" us38384cna35 ") == "38384CNA3"


def test_resolve_identifier_from_valid_cusip():
    assert resolve_identifier("38384CNA3") == "38384CNA3"


def test_resolve_identifier_accepts_non_checksummed_9_char_cusip():
    # Real data: Ginnie Mae's own shared placeholder CUSIP for REMIC
    # tranches without an individually-assigned CUSIP fails a real
    # checksum (its own check digit would be '5', not '9') — must still
    # resolve, since it's a real, storable identifier in this project's
    # own database, not a typo.
    assert resolve_identifier("C99999999") == "C99999999"


def test_resolve_identifier_rejects_bad_isin_check_digit():
    with pytest.raises(InvalidISINError):
        resolve_identifier("US38384CNA30")


def test_resolve_identifier_rejects_wrong_length():
    with pytest.raises(InvalidCUSIPError):
        resolve_identifier("short")
