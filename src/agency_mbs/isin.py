"""ISIN <-> CUSIP conversion and check-digit validation for US securities.

A US ISIN is: 2-letter country code ("US") + 9-character CUSIP + 1 ISIN check
digit. The CUSIP itself is 8 identifying characters + 1 CUSIP check digit.
Both check digits use a Luhn-style algorithm, but over different alphabets
and different digit windows, so they are implemented separately.
"""

from __future__ import annotations

_CUSIP_CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ*@#"


class InvalidISINError(ValueError):
    pass


class InvalidCUSIPError(ValueError):
    pass


def _digit_sum(n: int) -> int:
    return sum(int(d) for d in str(n))


def _char_value(ch: str) -> int:
    """Numeric value of a CUSIP/ISIN character (digits as-is, letters A-Z=10-35)."""
    if ch.isdigit():
        return int(ch)
    if ch in _CUSIP_CHARSET:
        return _CUSIP_CHARSET.index(ch)
    raise InvalidCUSIPError(f"Invalid CUSIP/ISIN character: {ch!r}")


def cusip_check_digit(cusip8: str) -> int:
    """Compute the CUSIP check digit for the first 8 characters of a CUSIP."""
    if len(cusip8) != 8:
        raise InvalidCUSIPError(f"Expected 8 characters, got {len(cusip8)}: {cusip8!r}")
    total = 0
    for i, ch in enumerate(cusip8):
        v = _char_value(ch)
        if i % 2 == 1:  # even position (1-indexed): double
            v *= 2
        total += _digit_sum(v)
    return (10 - (total % 10)) % 10


def validate_cusip(cusip: str) -> str:
    """Validate a 9-character CUSIP (8 chars + check digit). Returns it uppercased."""
    cusip = cusip.strip().upper()
    if len(cusip) != 9:
        raise InvalidCUSIPError(f"CUSIP must be 9 characters, got {len(cusip)}: {cusip!r}")
    expected = cusip_check_digit(cusip[:8])
    if int(cusip[8]) != expected:
        raise InvalidCUSIPError(
            f"Bad CUSIP check digit for {cusip!r}: expected {expected}, got {cusip[8]}"
        )
    return cusip


def _isin_numeric_string(isin11: str) -> str:
    """Expand the first 11 ISIN characters into a digit string (letters -> 2 digits)."""
    digits = []
    for ch in isin11:
        if ch.isdigit():
            digits.append(ch)
        elif ch.isalpha():
            digits.append(str(_CUSIP_CHARSET.index(ch.upper())))
        else:
            raise InvalidISINError(f"Invalid ISIN character: {ch!r}")
    return "".join(digits)


def isin_check_digit(isin11: str) -> int:
    """Compute the ISIN check digit given the first 11 characters (country + NSIN)."""
    if len(isin11) != 11:
        raise InvalidISINError(f"Expected 11 characters, got {len(isin11)}: {isin11!r}")
    numeric = _isin_numeric_string(isin11)
    total = 0
    # Luhn: double every second digit counting from the rightmost digit.
    for i, ch in enumerate(reversed(numeric)):
        v = int(ch)
        if i % 2 == 0:
            v *= 2
        total += _digit_sum(v)
    return (10 - (total % 10)) % 10


def validate_isin(isin: str) -> str:
    """Validate a 12-character ISIN. Returns it uppercased."""
    isin = isin.strip().upper()
    if len(isin) != 12:
        raise InvalidISINError(f"ISIN must be 12 characters, got {len(isin)}: {isin!r}")
    expected = isin_check_digit(isin[:11])
    if int(isin[11]) != expected:
        raise InvalidISINError(
            f"Bad ISIN check digit for {isin!r}: expected {expected}, got {isin[11]}"
        )
    return isin


def isin_to_cusip(isin: str, *, validate: bool = True) -> str:
    """Extract the 9-character CUSIP from a 12-character US ISIN.

    Strips the 2-character country prefix and the 1-digit ISIN check digit.
    With validate=True (default), both the ISIN and the resulting CUSIP
    check digits are verified, catching transcription errors early.
    """
    isin = isin.strip().upper()
    if len(isin) != 12:
        raise InvalidISINError(f"ISIN must be 12 characters, got {len(isin)}: {isin!r}")
    if validate:
        validate_isin(isin)
    cusip = isin[2:11]
    if validate:
        validate_cusip(cusip)
    return cusip


def resolve_identifier(identifier: str) -> str:
    """Resolve a user-supplied lookup identifier (CLI/API) to a CUSIP.

    12 characters -> treated as an ISIN, fully validated (both the ISIN's
    own check digit and the extracted CUSIP's).

    9 characters -> treated as a raw CUSIP, length-checked only — NOT
    checksum-validated. Some real data this project stores uses
    non-checksummed placeholder CUSIPs (e.g. "C99999999", which Ginnie Mae
    assigns to REMIC tranches without an individually-issued CUSIP — see
    agency_mbs.store's module docstring); rejecting those here would make
    real, already-stored data unlookupable. A lookup on a genuinely wrong
    CUSIP just returns no rows, which is a fine outcome for a typo.

    Any other length is almost certainly a transcription error, so it's
    rejected rather than silently attempted.
    """
    identifier = identifier.strip().upper()
    if len(identifier) == 12:
        return isin_to_cusip(identifier)
    if len(identifier) == 9:
        return identifier
    raise InvalidCUSIPError(
        f"Expected a 9-character CUSIP or 12-character ISIN, got {len(identifier)} "
        f"characters: {identifier!r}"
    )
