"""Read-only REST API over the local `pool_factors` database.

A thin HTTP layer over `agency_mbs.store`/`agency_mbs.isin` — no business
logic duplicated here; every endpoint just calls the same functions the
CLI's `lookup` command already uses. This is a local research tool: no
authentication, and `agency-mbs serve` binds to `127.0.0.1` by default
(see `agency_mbs.cli.cmd_serve`) rather than exposing it on the network,
since there's no auth layer to protect it.

Run with `agency-mbs serve` (needs the `api` extra: `pip install -e
".[api]"`), or directly with `uvicorn agency_mbs.api:app`. Interactive
docs at `/docs` once running (FastAPI's default).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from agency_mbs.isin import InvalidCUSIPError, InvalidISINError, resolve_identifier
from agency_mbs.store import get_connection, get_factor_history, init_db

app = FastAPI(
    title="agency-mbs-tracker API",
    description="Read-only lookup over locally ingested agency MBS/CMO pool-factor history.",
    version="0.1.0",
)


class FactorPeriod(BaseModel):
    pool_id: str
    cusip: str
    issuer: str
    factor_date: str
    current_factor: float | None
    prior_factor: float | None
    coupon_rate: float | None
    rate_type: str | None
    wam: int | None
    upb_original: float | None
    upb_current: float | None


class LookupResponse(BaseModel):
    cusip: str
    distinct_pool_count: int
    periods: list[FactorPeriod]


def get_db() -> Generator[sqlite3.Connection, None, None]:
    # check_same_thread=False: FastAPI can resolve this dependency and run
    # the route's sync body in different threadpool worker threads (see
    # agency_mbs.store.get_connection's docstring) — only one thread ever
    # touches this connection at a time, so it's safe to relax here.
    conn = get_connection(check_same_thread=False)
    init_db(conn)
    try:
        yield conn
    finally:
        conn.close()


def _row_to_period(row: sqlite3.Row) -> FactorPeriod:
    return FactorPeriod(
        pool_id=row["pool_id"],
        cusip=row["cusip"],
        issuer=row["issuer"],
        factor_date=row["factor_date"],
        current_factor=row["current_factor"],
        prior_factor=row["prior_factor"],
        coupon_rate=row["coupon_rate"],
        rate_type=row["rate_type"],
        wam=row["wam"],
        upb_original=row["upb_original"],
        upb_current=row["upb_current"],
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/lookup/{identifier}", response_model=LookupResponse)
def lookup(identifier: str, conn: sqlite3.Connection = Depends(get_db)) -> LookupResponse:
    """Factor/rate history for an ISIN or CUSIP, oldest period first.

    `distinct_pool_count > 1` means this CUSIP is one of Ginnie Mae's
    shared placeholder values for non-CUSIP-eligible REMIC tranches (see
    agency_mbs.store's module docstring) — `periods` then covers every
    tranche that shares it, not just one security.
    """
    try:
        cusip = resolve_identifier(identifier)
    except (InvalidISINError, InvalidCUSIPError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rows = get_factor_history(conn, cusip)
    return LookupResponse(
        cusip=cusip,
        distinct_pool_count=len({row["pool_id"] for row in rows}),
        periods=[_row_to_period(row) for row in rows],
    )
