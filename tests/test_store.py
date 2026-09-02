import sqlite3

import pytest

from agency_mbs.store import get_connection, get_factor_history, init_db, upsert_factor_records


@pytest.fixture
def conn():
    connection = get_connection(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def _record(**overrides):
    base = {
        "pool_id": "AA1366",
        "cusip": "36177XQT8",
        "issuer": "GNMA",
        "factor_date": "2026-07-01",
        "current_factor": 0.9,
        "prior_factor": None,
        "coupon_rate": 3.5,
        "rate_type": "fixed",
        "wam": None,
        "upb_original": 1000.0,
        "upb_current": 900.0,
    }
    base.update(overrides)
    return base


def test_upsert_and_read_back(conn):
    written = upsert_factor_records(conn, [_record()])
    assert written == 1
    rows = get_factor_history(conn, "36177XQT8")
    assert len(rows) == 1
    assert rows[0]["pool_id"] == "AA1366"
    assert rows[0]["current_factor"] == 0.9
    assert rows[0]["coupon_rate"] == 3.5
    assert rows[0]["rate_type"] == "fixed"


def test_rate_type_null_for_remic_tranches(conn):
    upsert_factor_records(conn, [_record(rate_type=None)])
    rows = get_factor_history(conn, "36177XQT8")
    assert rows[0]["rate_type"] is None


def test_upsert_same_pool_and_period_overwrites(conn):
    upsert_factor_records(conn, [_record(current_factor=0.9)])
    upsert_factor_records(conn, [_record(current_factor=0.85)])
    rows = get_factor_history(conn, "36177XQT8")
    assert len(rows) == 1
    assert rows[0]["current_factor"] == 0.85


def test_history_accumulates_across_periods(conn):
    upsert_factor_records(conn, [_record(factor_date="2026-06-01", current_factor=0.95)])
    upsert_factor_records(conn, [_record(factor_date="2026-07-01", current_factor=0.90)])
    rows = get_factor_history(conn, "36177XQT8")
    assert [r["factor_date"] for r in rows] == ["2026-06-01", "2026-07-01"]


def test_shared_placeholder_cusip_keeps_distinct_tranches(conn):
    # Regression test: Ginnie Mae REMIC files use a shared placeholder CUSIP
    # (e.g. "C99999999") for tranches without an individually-assigned
    # CUSIP — confirmed against real production data, 185 distinct tranches
    # sharing one CUSIP in a single remic1 file. Keying storage on cusip
    # alone silently collapsed all of them into one row; keying on pool_id
    # must keep them all.
    upsert_factor_records(
        conn,
        [
            _record(pool_id="GNMA-2013-073-B1", cusip="C99999999", current_factor=1.0),
            _record(pool_id="GNMA-2013-073-B2", cusip="C99999999", current_factor=0.5),
            _record(pool_id="GNMA-2013-073-B3", cusip="C99999999", current_factor=0.0),
        ],
    )
    rows = get_factor_history(conn, "C99999999")
    assert len(rows) == 3
    assert {r["pool_id"] for r in rows} == {
        "GNMA-2013-073-B1",
        "GNMA-2013-073-B2",
        "GNMA-2013-073-B3",
    }


def test_null_current_factor_is_preserved(conn):
    upsert_factor_records(conn, [_record(current_factor=None, upb_current=None)])
    rows = get_factor_history(conn, "36177XQT8")
    assert rows[0]["current_factor"] is None


def test_get_factor_history_unknown_cusip_returns_empty(conn):
    assert get_factor_history(conn, "000000000") == []


def test_upsert_empty_list_is_a_noop(conn):
    assert upsert_factor_records(conn, []) == 0


def test_get_connection_uses_row_factory(conn):
    assert conn.row_factory is sqlite3.Row
