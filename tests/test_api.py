import pytest
from fastapi.testclient import TestClient

from agency_mbs.api import app, get_db
from agency_mbs.store import get_connection, init_db, upsert_factor_records


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


@pytest.fixture
def client():
    conn = get_connection(":memory:", check_same_thread=False)
    init_db(conn)
    upsert_factor_records(
        conn,
        [
            _record(),
            _record(factor_date="2026-08-01", current_factor=0.85, coupon_rate=3.4),
            # Two distinct tranches sharing a placeholder CUSIP (REMIC pattern).
            _record(pool_id="GNMA-2013-073-B1", cusip="C99999999", rate_type=None),
            _record(pool_id="GNMA-2013-073-B2", cusip="C99999999", rate_type=None),
        ],
    )

    def override_get_db():
        yield conn

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    conn.close()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_lookup_by_cusip_returns_history_oldest_first(client):
    resp = client.get("/lookup/36177XQT8")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cusip"] == "36177XQT8"
    assert body["distinct_pool_count"] == 1
    assert [p["factor_date"] for p in body["periods"]] == ["2026-07-01", "2026-08-01"]
    assert body["periods"][1]["current_factor"] == pytest.approx(0.85)
    assert body["periods"][1]["coupon_rate"] == pytest.approx(3.4)


def test_lookup_by_isin_resolves_to_cusip(client):
    # US38384CNA35 isn't in this fixture's data, but AA1366's real ISIN
    # would be a different one — use the CUSIP's own real ISIN pairing
    # from the isin.py test suite: US38384CNA35 -> 38384CNA3. Just confirm
    # ISIN resolution works and returns an empty (not erroring) result for
    # a CUSIP not in this test's fixture data.
    resp = client.get("/lookup/US38384CNA35")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cusip"] == "38384CNA3"
    assert body["periods"] == []


def test_lookup_shared_placeholder_cusip_returns_multiple_pools(client):
    resp = client.get("/lookup/C99999999")
    assert resp.status_code == 200
    body = resp.json()
    assert body["distinct_pool_count"] == 2
    assert {p["pool_id"] for p in body["periods"]} == {
        "GNMA-2013-073-B1",
        "GNMA-2013-073-B2",
    }
    assert all(p["rate_type"] is None for p in body["periods"])


def test_lookup_unknown_cusip_returns_empty_not_error(client):
    resp = client.get("/lookup/000000000")
    assert resp.status_code == 200
    assert resp.json()["periods"] == []


def test_lookup_9_char_identifier_is_never_checksum_validated(client):
    # "TOO-SHORT" is 9 characters and fails a CUSIP checksum, but 9-char
    # identifiers are treated as raw CUSIPs (see resolve_identifier) —
    # must not 400 just because it's not a real check-digit-valid CUSIP.
    resp = client.get("/lookup/too-short")
    assert resp.status_code == 200
    assert resp.json()["periods"] == []


def test_lookup_wrong_length_identifier_returns_400(client):
    resp = client.get("/lookup/short")
    assert resp.status_code == 400


def test_lookup_bad_isin_check_digit_returns_400(client):
    resp = client.get("/lookup/US38384CNA30")  # last digit tampered
    assert resp.status_code == 400
