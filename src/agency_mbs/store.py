"""SQLite storage for monthly pool-factor history.

One row per (cusip, factor_date) — history is never overwritten, only
appended to, so amortization can be reconstructed month over month.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "agency_mbs.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pool_factors (
    cusip           TEXT    NOT NULL,
    pool_id         TEXT    NOT NULL,
    issuer          TEXT    NOT NULL,
    factor_date     TEXT    NOT NULL,  -- YYYY-MM-01
    current_factor  REAL    NOT NULL,
    prior_factor    REAL,
    wac             REAL,
    wam             INTEGER,
    upb_original    REAL,
    upb_current     REAL,
    loaded_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (cusip, factor_date)
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
            (cusip, pool_id, issuer, factor_date, current_factor, prior_factor,
             wac, wam, upb_original, upb_current)
        VALUES
            (:cusip, :pool_id, :issuer, :factor_date, :current_factor, :prior_factor,
             :wac, :wam, :upb_original, :upb_current)
        ON CONFLICT (cusip, factor_date) DO UPDATE SET
            pool_id=excluded.pool_id, issuer=excluded.issuer,
            current_factor=excluded.current_factor, prior_factor=excluded.prior_factor,
            wac=excluded.wac, wam=excluded.wam,
            upb_original=excluded.upb_original, upb_current=excluded.upb_current,
            loaded_at=datetime('now')
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def get_factor_history(conn: sqlite3.Connection, cusip: str) -> list[sqlite3.Row]:
    """Return factor history for a CUSIP, oldest first."""
    cursor = conn.execute(
        "SELECT * FROM pool_factors WHERE cusip = ? ORDER BY factor_date ASC",
        (cusip,),
    )
    return cursor.fetchall()
