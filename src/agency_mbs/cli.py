"""Command-line entry point: agency-mbs lookup / ingest."""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

from agency_mbs.fetch import (
    RAW_DATA_DIR,
    download_bulk_file,
    fetch_disclosure_catalog,
    load_session_cookie,
)
from agency_mbs.isin import InvalidCUSIPError, InvalidISINError, isin_to_cusip, validate_cusip
from agency_mbs.parse import parse_monthly_factor_file
from agency_mbs.store import get_connection, get_factor_history, init_db, upsert_factor_records

# Prefixes agency_mbs.parse actually knows how to read today.
_SUPPORTED_PREFIXES = {"factorA1"}


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

    print(f"CUSIP {cusip} — {len(rows)} periodos:")
    for row in rows:
        factor_str = f"{row['current_factor']:.8f}" if row["current_factor"] is not None else "N/D"
        line = f"  {row['factor_date']}  factor={factor_str}"
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


def cmd_ingest(args: argparse.Namespace) -> int:
    if args.prefix not in _SUPPORTED_PREFIXES:
        print(
            f"error: no parser for prefix {args.prefix!r} yet "
            f"(supported: {sorted(_SUPPORTED_PREFIXES)})",
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

    records = parse_monthly_factor_file(data_path)
    conn = get_connection()
    init_db(conn)
    written = upsert_factor_records(conn, records)

    with_factor = sum(1 for r in records if r["current_factor"] is not None)
    print(f"{written} registros guardados ({with_factor} con factor, {written - with_factor} sin).")
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
    ingest.add_argument("prefix", help="e.g. factorA1 (Ginnie Mae I factors)")
    ingest.set_defaults(func=cmd_ingest)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
