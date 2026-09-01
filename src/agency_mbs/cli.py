"""Command-line entry point: agency-mbs lookup <ISIN|CUSIP>."""

from __future__ import annotations

import argparse
import sys

from agency_mbs.isin import InvalidCUSIPError, InvalidISINError, isin_to_cusip, validate_cusip
from agency_mbs.store import get_connection, get_factor_history, init_db


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
        print("(El fetcher/parser de agency_mbs.fetch / agency_mbs.parse todavia no estan implementados.)")
        return 0

    print(f"CUSIP {cusip} — {len(rows)} periodos:")
    for row in rows:
        line = f"  {row['factor_date']}  factor={row['current_factor']:.8f}"
        if row["upb_current"] is not None:
            line += f"  upb={row['upb_current']:,.2f}"
        print(line)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agency-mbs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    lookup = subparsers.add_parser("lookup", help="Show factor history for an ISIN or CUSIP")
    lookup.add_argument("identifier", help="12-char ISIN or 9-char CUSIP")
    lookup.set_defaults(func=cmd_lookup)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
