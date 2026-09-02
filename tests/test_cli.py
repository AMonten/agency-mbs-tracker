import argparse
from datetime import date
from unittest.mock import patch

from agency_mbs.cli import _months_ago, cmd_backfill, cmd_notify


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


@patch("agency_mbs.cli.send_telegram_message")
def test_cmd_notify_always_exits_zero_when_sent(mock_send, capsys):
    mock_send.return_value = True
    args = argparse.Namespace(message="hola")
    result = cmd_notify(args)
    assert result == 0
    mock_send.assert_called_once_with("hola")
    assert "enviada" in capsys.readouterr().out


@patch("agency_mbs.cli.send_telegram_message")
def test_cmd_notify_always_exits_zero_when_not_sent(mock_send, capsys):
    mock_send.return_value = False
    args = argparse.Namespace(message="hola")
    result = cmd_notify(args)
    assert result == 0
    assert "no enviada" in capsys.readouterr().err
