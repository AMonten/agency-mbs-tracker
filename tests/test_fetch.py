from unittest.mock import Mock, patch

import pytest

from agency_mbs.fetch import (
    BULK_CONTENT_API,
    DISCLOSURE_API,
    download_bulk_file,
    fetch_disclosure_catalog,
    fetch_layout_sample_files,
)


@patch("agency_mbs.fetch.requests.get")
def test_fetch_disclosure_catalog_calls_real_endpoint(mock_get):
    mock_get.return_value = Mock(json=lambda: {"Factor Files": []})
    mock_get.return_value.raise_for_status = lambda: None
    result = fetch_disclosure_catalog()
    mock_get.assert_called_once_with(f"{BULK_CONTENT_API}/disclosure-data", timeout=30)
    assert result == {"Factor Files": []}


@patch("agency_mbs.fetch.requests.get")
def test_fetch_layout_sample_files_calls_real_endpoint(mock_get):
    mock_get.return_value = Mock(json=lambda: {"Factor Files": []})
    mock_get.return_value.raise_for_status = lambda: None
    result = fetch_layout_sample_files()
    mock_get.assert_called_once_with(f"{BULK_CONTENT_API}/layouts-sample-files", timeout=30)
    assert result == {"Factor Files": []}


def test_download_bulk_file_without_cookie_raises():
    with pytest.raises(RuntimeError, match="logged-in"):
        download_bulk_file("data_bulk", "factorA1_202607.zip", session_cookie="")


@patch("agency_mbs.fetch.requests.get")
def test_download_bulk_file_sends_session_cookie(mock_get, tmp_path):
    mock_get.return_value = Mock(content=b"raw file bytes")
    mock_get.return_value.raise_for_status = lambda: None
    dest = download_bulk_file(
        "data_bulk", "factorA1_202607.zip", session_cookie="abc123", dest_dir=tmp_path
    )
    mock_get.assert_called_once_with(
        f"{DISCLOSURE_API}/download?dlfile=data_bulk%2FfactorA1_202607.zip",
        cookies={"gm_up_token": "abc123"},
        timeout=120,
    )
    assert dest.read_bytes() == b"raw file bytes"
