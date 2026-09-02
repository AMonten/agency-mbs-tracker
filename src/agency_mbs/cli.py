"""Command-line entry point: agency-mbs lookup / ingest."""

from __future__ import annotations

import argparse
import sys
import zipfile
from collections.abc import Callable
from datetime import date
from functools import partial
from pathlib import Path

from agency_mbs.fetch import (
    RAW_DATA_DIR,
    download_bulk_file,
    fetch_disclosure_catalog,
    load_session_cookie,
)
from agency_mbs.fetch_freddie import (
    download_document,
    fetch_monthly_years,
    latest_factor_document,
    list_factor_documents,
    load_freddie_session,
)
from agency_mbs.isin import InvalidCUSIPError, InvalidISINError, isin_to_cusip, validate_cusip
from agency_mbs.notify import send_telegram_message
from agency_mbs.parse import (
    ADDITIONAL_RECORD_LENGTH,
    POOL_FACTOR_RECORD_LENGTH,
    parse_monthly_factor_file,
    parse_monthly_freddie_file,
    parse_monthly_remic_file,
)
from agency_mbs.store import get_connection, get_factor_history, init_db, upsert_factor_records

# Prefixes agency_mbs.parse actually knows how to read today, and which
# parser handles each (pool-level factor files vs. REMIC tranche files).
_PREFIX_PARSERS: dict[str, Callable[[Path], list[dict]]] = {
    "factorA1": parse_monthly_factor_file,
    "factorA2": parse_monthly_factor_file,
    "factorAplat": parse_monthly_factor_file,
    "factorAAdd": partial(
        parse_monthly_factor_file, valid_lengths=(POOL_FACTOR_RECORD_LENGTH, ADDITIONAL_RECORD_LENGTH)
    ),
    "remic1": parse_monthly_remic_file,
    "remic2": parse_monthly_remic_file,
}


def _resolve_cusip(identifier: str) -> str:
    identifier = identifier.strip().upper()
    if len(identifier) == 12:
        return isin_to_cusip(identifier)
    return validate_cusip(identifier)


def cmd_lookup(args: argparse.Namespace) -> int:
    try:
        cusip = _resolve_cusip(args.identifier)
    except (InvalidISINError, InvalidCUSIPError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    conn = get_connection()
    init_db(conn)
    rows = get_factor_history(conn, cusip)
    if not rows:
        print(f"No hay historial cargado todavia para CUSIP {cusip}.")
        return 0

    distinct_pools = {row["pool_id"] for row in rows}
    print(f"CUSIP {cusip} — {len(rows)} periodos:")
    if len(distinct_pools) > 1:
        print(
            "  (nota: este CUSIP es compartido por varios pools/tranches distintos "
            "— comun en clases REMIC sin CUSIP propio)"
        )
    rate_type_label = {"fixed": "fija", "floating": "flotante"}
    for row in rows:
        factor_str = f"{row['current_factor']:.8f}" if row["current_factor"] is not None else "N/D"
        line = f"  {row['factor_date']}  pool_id={row['pool_id']}  factor={factor_str}"
        if row["coupon_rate"] is not None:
            tipo = rate_type_label.get(row["rate_type"], "tipo desconocido")
            line += f"  tasa={row['coupon_rate']:.3f}% ({tipo})"
        if row["upb_current"] is not None:
            line += f"  upb={row['upb_current']:,.2f}"
        print(line)
    return 0


def _extract_if_zipped(path: Path) -> Path:
    if path.suffix != ".zip":
        return path
    with zipfile.ZipFile(path) as zf:
        members = zf.namelist()
        if len(members) != 1:
            raise RuntimeError(f"Expected exactly one file inside {path}, found: {members}")
        zf.extract(members[0], path.parent)
        return path.parent / members[0]


def _store_records(records: list[dict]) -> int:
    conn = get_connection()
    init_db(conn)
    written = upsert_factor_records(conn, records)
    with_factor = sum(1 for r in records if r["current_factor"] is not None)
    print(f"{written} registros guardados ({with_factor} con factor, {written - with_factor} sin).")
    return 0


def _ingest_freddie() -> int:
    cookie, csrf_token = load_freddie_session()
    latest_year = max(fetch_monthly_years(cookie, csrf_token))
    document = latest_factor_document(cookie, csrf_token, latest_year)
    print(f"Descargando {document['name']}...")
    raw_path = download_document(
        cookie, csrf_token, document["id"], document["name"], dest_dir=RAW_DATA_DIR
    )
    data_path = _extract_if_zipped(raw_path)
    records = parse_monthly_freddie_file(data_path)
    return _store_records(records)


def _months_ago(months: int, today: date | None = None) -> date:
    """First-of-month date `months` months before `today` (default: today)."""
    today = today or date.today()
    total = today.year * 12 + (today.month - 1) - months
    year, month = divmod(total, 12)
    return date(year, month + 1, 1)


def cmd_backfill_freddie(args: argparse.Namespace) -> int:
    cookie, csrf_token = load_freddie_session()
    since = _months_ago(args.months)
    documents = list_factor_documents(cookie, csrf_token, since=since)
    if not documents:
        print(f"error: no hay documentos 'Factors for pools' desde {since.isoformat()}", file=sys.stderr)
        return 1

    print(f"{len(documents)} periodos a bajar desde {since.isoformat()}.")
    total_records = 0
    for document in documents:
        print(f"Descargando {document['name']} ({document['effectiveDate']})...")
        raw_path = download_document(
            cookie, csrf_token, document["id"], document["name"], dest_dir=RAW_DATA_DIR
        )
        data_path = _extract_if_zipped(raw_path)
        records = parse_monthly_freddie_file(data_path)
        _store_records(records)
        total_records += len(records)
        if data_path != raw_path:
            data_path.unlink()  # keep the (much smaller) zip, drop the extracted .txt

    print(f"Backfill completo: {len(documents)} periodos, {total_records} registros en total.")
    return 0


def cmd_backfill(args: argparse.Namespace) -> int:
    if args.prefix != "freddie":
        print(
            f"error: backfill no soportado todavia para {args.prefix!r} (solo 'freddie')",
            file=sys.stderr,
        )
        return 1
    return cmd_backfill_freddie(args)


def cmd_ingest(args: argparse.Namespace) -> int:
    if args.prefix == "freddie":
        return _ingest_freddie()

    parse_file = _PREFIX_PARSERS.get(args.prefix)
    if parse_file is None:
        print(
            f"error: no parser for prefix {args.prefix!r} yet "
            f"(supported: {sorted(_PREFIX_PARSERS)})",
            file=sys.stderr,
        )
        return 1

    cookie = load_session_cookie()
    catalog = fetch_disclosure_catalog()
    entry = next(
        (f for files in catalog.values() for f in files if f["field_prefix"] == args.prefix),
        None,
    )
    if entry is None:
        print(f"error: prefix {args.prefix!r} not found in the current catalog", file=sys.stderr)
        return 1

    print(f"Descargando {entry['fileName']}...")
    raw_path = download_bulk_file(
        entry["directoryName"], entry["fileName"], session_cookie=cookie, dest_dir=RAW_DATA_DIR
    )
    data_path = _extract_if_zipped(raw_path)
    records = parse_file(data_path)
    return _store_records(records)


def cmd_notify(args: argparse.Namespace) -> int:
    """Best-effort Telegram notification — always exits 0, never fails a caller's pipeline."""
    if send_telegram_message(args.message):
        print("Notificacion enviada.")
    else:
        print(
            "Notificacion no enviada (falta data/telegram_bot_token.txt o "
            "data/telegram_chat_id.txt, o fallo el request) — no es un error fatal.",
            file=sys.stderr,
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agency-mbs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    lookup = subparsers.add_parser("lookup", help="Show factor history for an ISIN or CUSIP")
    lookup.add_argument("identifier", help="12-char ISIN or 9-char CUSIP")
    lookup.set_defaults(func=cmd_lookup)

    ingest = subparsers.add_parser(
        "ingest", help="Download + parse + store the current bulk file for a prefix"
    )
    ingest.add_argument(
        "prefix",
        help="factorA1 (Ginnie I), factorA2 (Ginnie II), factorAplat (Platinum), "
        "factorAAdd (Additional), remic1/remic2 (REMIC/CMO tranches), "
        "freddie (Freddie Mac, latest monthly Security Core File)",
    )
    ingest.set_defaults(func=cmd_ingest)

    backfill = subparsers.add_parser(
        "backfill", help="Download + parse + store multiple historical periods for a source"
    )
    backfill.add_argument("prefix", help="Currently only 'freddie' supports backfill")
    backfill.add_argument(
        "--months", type=int, default=12, help="How many months back to fetch (default: 12)"
    )
    backfill.set_defaults(func=cmd_backfill)

    notify = subparsers.add_parser(
        "notify", help="Send a Telegram notification (used by scripts/monthly_ingest.sh)"
    )
    notify.add_argument("message", help="Message text to send")
    notify.set_defaults(func=cmd_notify)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
