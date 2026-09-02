import argparse
from datetime import date

from agency_mbs.cli import _months_ago, cmd_backfill


def test_months_ago_same_year():
    assert _months_ago(1, today=date(2026, 9, 1)) == date(2026, 8, 1)


def test_months_ago_crosses_year_boundary():
    assert _months_ago(1, today=date(2026, 1, 15)) == date(2025, 12, 1)


def test_months_ago_twelve_months():
    assert _months_ago(12, today=date(2026, 9, 2)) == date(2025, 9, 1)


def test_months_ago_defaults_to_today():
    assert _months_ago(0) == date.today().replace(day=1)


def test_cmd_backfill_rejects_unsupported_prefix(capsys):
    args = argparse.Namespace(prefix="factorA1", months=12)
    result = cmd_backfill(args)
    assert result == 1
    assert "backfill no soportado" in capsys.readouterr().err
