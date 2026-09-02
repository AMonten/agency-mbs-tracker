from datetime import date
from unittest.mock import Mock, patch

import pytest

from agency_mbs.fetch_freddie import (
    FREDDIE_API,
    MONTHLY_CATEGORY_ID,
    MONTHLY_REFERER,
    MONTHLY_SLUG,
    download_document,
    fetch_monthly_documents,
    fetch_monthly_years,
    latest_factor_document,
    list_factor_documents,
    load_freddie_session,
)

FAKE_COOKIE = "DISC_WEB_SSN_ID=abc; cssTCfreddie=valid"
FAKE_CSRF = "fake-csrf-token"


def test_load_freddie_session_missing_files_raises(tmp_path):
    with pytest.raises(RuntimeError, match="Missing Freddie Mac session files"):
        load_freddie_session(tmp_path / "cookie.txt", tmp_path / "csrf.txt")


def test_load_freddie_session_reads_both_files(tmp_path):
    cookie_path = tmp_path / "cookie.txt"
    csrf_path = tmp_path / "csrf.txt"
    cookie_path.write_text(f"{FAKE_COOKIE}\n")
    csrf_path.write_text(f"{FAKE_CSRF}\n")
    cookie, csrf = load_freddie_session(cookie_path, csrf_path)
    assert cookie == FAKE_COOKIE
    assert csrf == FAKE_CSRF


@patch("agency_mbs.fetch_freddie.requests.get")
def test_fetch_monthly_years_calls_real_endpoint(mock_get):
    mock_get.return_value = Mock(json=lambda: [2025, 2026])
    mock_get.return_value.raise_for_status = lambda: None
    result = fetch_monthly_years(FAKE_COOKIE, FAKE_CSRF)
    mock_get.assert_called_once_with(
        f"{FREDDIE_API}/freddie/listyears/{MONTHLY_CATEGORY_ID}/{MONTHLY_SLUG}",
        headers={"accept": "*/*", "x-csrf-token": FAKE_CSRF, "referer": MONTHLY_REFERER},
        cookies={"DISC_WEB_SSN_ID": "abc", "cssTCfreddie": "valid"},
        timeout=30,
    )
    assert result == [2025, 2026]


@patch("agency_mbs.fetch_freddie.requests.get")
def test_fetch_monthly_documents_calls_real_endpoint(mock_get):
    mock_get.return_value = Mock(json=lambda: [])
    mock_get.return_value.raise_for_status = lambda: None
    fetch_monthly_documents(FAKE_COOKIE, FAKE_CSRF, 2026)
    mock_get.assert_called_once_with(
        f"{FREDDIE_API}/freddie/list/{MONTHLY_CATEGORY_ID}/2026",
        headers={"accept": "*/*", "x-csrf-token": FAKE_CSRF, "referer": MONTHLY_REFERER},
        cookies={"DISC_WEB_SSN_ID": "abc", "cssTCfreddie": "valid"},
        timeout=30,
    )


@patch("agency_mbs.fetch_freddie.fetch_monthly_documents")
def test_latest_factor_document_picks_most_recent_fd_entry(mock_fetch_documents):
    mock_fetch_documents.return_value = [
        {
            "headingKey": "L1L2_MONTHLY_ONGOING_POOL_LEVEL",
            "document": {"id": "1", "name": "fd260706.zip", "effectiveDate": "2026-07-06"},
        },
        {
            "headingKey": "L1L2_MONTHLY_ONGOING_POOL_LEVEL",
            "document": {"id": "2", "name": "fd260806.zip", "effectiveDate": "2026-08-06"},
        },
        {
            # Different headingKey (loan-level) — must be ignored even though it's newer.
            "headingKey": "L1_MONTHLY_ONGOING_LOAN_LEVEL",
            "document": {"id": "3", "name": "fu260901.zip", "effectiveDate": "2026-09-01"},
        },
    ]
    result = latest_factor_document(FAKE_COOKIE, FAKE_CSRF, 2026)
    assert result == {"id": "2", "name": "fd260806.zip", "effectiveDate": "2026-08-06"}


@patch("agency_mbs.fetch_freddie.fetch_monthly_documents")
def test_latest_factor_document_raises_when_none_found(mock_fetch_documents):
    mock_fetch_documents.return_value = []
    with pytest.raises(RuntimeError, match="No 'L1L2_MONTHLY_ONGOING_POOL_LEVEL' fd\\* documents"):
        latest_factor_document(FAKE_COOKIE, FAKE_CSRF, 2026)


@patch("agency_mbs.fetch_freddie.fetch_monthly_documents")
@patch("agency_mbs.fetch_freddie.fetch_monthly_years")
def test_list_factor_documents_filters_heading_key_and_prefix(mock_years, mock_documents):
    mock_years.return_value = [2026]
    mock_documents.return_value = [
        {
            "headingKey": "L1L2_MONTHLY_ONGOING_POOL_LEVEL",
            "document": {"id": "1", "name": "fd260706.zip", "effectiveDate": "2026-07-06"},
        },
        {
            "headingKey": "L1L2_MONTHLY_ONGOING_POOL_LEVEL",
            "document": {"id": "2", "name": "fq260706.zip", "effectiveDate": "2026-07-06"},
        },
        {
            "headingKey": "L1_MONTHLY_ONGOING_LOAN_LEVEL",
            "document": {"id": "3", "name": "fd260706_other.zip", "effectiveDate": "2026-07-06"},
        },
    ]
    result = list_factor_documents(FAKE_COOKIE, FAKE_CSRF)
    assert result == [{"id": "1", "name": "fd260706.zip", "effectiveDate": "2026-07-06"}]


@patch("agency_mbs.fetch_freddie.fetch_monthly_documents")
@patch("agency_mbs.fetch_freddie.fetch_monthly_years")
def test_list_factor_documents_only_queries_years_since_onward(mock_years, mock_documents):
    mock_years.return_value = [2020, 2024, 2025, 2026]
    mock_documents.return_value = []
    list_factor_documents(FAKE_COOKIE, FAKE_CSRF, since=date(2025, 1, 1))
    queried_years = {call.args[2] for call in mock_documents.call_args_list}
    assert queried_years == {2025, 2026}


@patch("agency_mbs.fetch_freddie.fetch_monthly_documents")
@patch("agency_mbs.fetch_freddie.fetch_monthly_years")
def test_list_factor_documents_drops_entries_before_since_and_sorts(mock_years, mock_documents):
    mock_years.return_value = [2026]
    mock_documents.return_value = [
        {
            "headingKey": "L1L2_MONTHLY_ONGOING_POOL_LEVEL",
            "document": {"id": "2", "name": "fd260806.zip", "effectiveDate": "2026-08-06"},
        },
        {
            "headingKey": "L1L2_MONTHLY_ONGOING_POOL_LEVEL",
            "document": {"id": "1", "name": "fd260706.zip", "effectiveDate": "2026-07-06"},
        },
        {
            "headingKey": "L1L2_MONTHLY_ONGOING_POOL_LEVEL",
            "document": {"id": "0", "name": "fd260112.zip", "effectiveDate": "2026-01-12"},
        },
    ]
    result = list_factor_documents(FAKE_COOKIE, FAKE_CSRF, since=date(2026, 6, 1))
    assert [d["name"] for d in result] == ["fd260706.zip", "fd260806.zip"]


@patch("agency_mbs.fetch_freddie.requests.get")
def test_download_document_writes_file(mock_get, tmp_path):
    mock_get.return_value = Mock(content=b"zip bytes")
    mock_get.return_value.raise_for_status = lambda: None
    dest = download_document(FAKE_COOKIE, FAKE_CSRF, "3363664", "fd260806.zip", dest_dir=tmp_path)
    mock_get.assert_called_once_with(
        f"{FREDDIE_API}/download/3363664/fd260806.zip",
        headers={"accept": "*/*", "x-csrf-token": FAKE_CSRF, "referer": MONTHLY_REFERER},
        cookies={"DISC_WEB_SSN_ID": "abc", "cssTCfreddie": "valid"},
        timeout=120,
    )
    assert dest.read_bytes() == b"zip bytes"
