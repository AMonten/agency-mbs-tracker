"""SQLite storage for monthly pool/tranche-factor history.

One row per (pool_id, factor_date) — history is never overwritten, only
appended to, so amortization can be reconstructed month over month.

Keyed on pool_id, NOT cusip: confirmed against real REMIC production data
that Ginnie Mae uses placeholder CUSIP values (e.g. "C99999999") for
tranches that aren't individually CUSIP-eligible (IO/residual-style
classes, mostly) — in the real August 2026 remic1 file, 185 distinct real
tranches all shared the single CUSIP "C99999999". Keying on cusip alone
would have silently collapsed all of them into one row. pool_id (the raw
pool number for pool-level files, "<series>-<tranche_name>" for REMIC) is
what Ginnie Mae actually assigns uniquely per security, so it's the real
identity; cusip is a secondary business identifier, indexed for lookup but
not the storage key. See agency_mbs.store's get_factor_history: a cusip
lookup can legitimately return multiple pool_id rows for the same period
when the cusip is one of these placeholders — that's correct, not a bug.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "agency_mbs.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pool_factors (
    pool_id         TEXT    NOT NULL,
    cusip           TEXT    NOT NULL,
    issuer          TEXT    NOT NULL,
    factor_date     TEXT    NOT NULL,  -- YYYY-MM-01
    current_factor  REAL,  -- NULL when the source file reported it blank (real, not missing data)
    prior_factor    REAL,
    wac             REAL,
    rate_type       TEXT,  -- 'fixed' or 'floating'; NULL when not derivable (REMIC tranches)
    wam             INTEGER,
    upb_original    REAL,
    upb_current     REAL,
    loaded_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (pool_id, factor_date)
);

CREATE INDEX IF NOT EXISTS idx_pool_factors_cusip ON pool_factors (cusip);
"""


def get_connection(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


def upsert_factor_records(conn: sqlite3.Connection, records: Iterable[dict]) -> int:
    """Insert or replace pool-factor rows. Returns the number of rows written."""
    rows: Sequence[dict] = list(records)
    if not rows:
        return 0
    conn.executemany(
        """
        INSERT INTO pool_factors
            (pool_id, cusip, issuer, factor_date, current_factor, prior_factor,
             wac, rate_type, wam, upb_original, upb_current)
        VALUES
            (:pool_id, :cusip, :issuer, :factor_date, :current_factor, :prior_factor,
             :wac, :rate_type, :wam, :upb_original, :upb_current)
        ON CONFLICT (pool_id, factor_date) DO UPDATE SET
            cusip=excluded.cusip, issuer=excluded.issuer,
            current_factor=excluded.current_factor, prior_factor=excluded.prior_factor,
            wac=excluded.wac, rate_type=excluded.rate_type, wam=excluded.wam,
            upb_original=excluded.upb_original, upb_current=excluded.upb_current,
            loaded_at=datetime('now')
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def get_factor_history(conn: sqlite3.Connection, cusip: str) -> list[sqlite3.Row]:
    """Return factor history for a CUSIP, oldest first.

    Can return more than one row per factor_date if the CUSIP is one of
    Ginnie Mae's shared placeholder values for non-CUSIP-eligible tranches
    (see module docstring) — that reflects real, distinct securities, not
    a bug.
    """
    cursor = conn.execute(
        "SELECT * FROM pool_factors WHERE cusip = ? ORDER BY factor_date ASC, pool_id ASC",
        (cusip,),
    )
    return cursor.fetchall()
