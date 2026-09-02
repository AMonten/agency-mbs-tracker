from unittest.mock import Mock, patch

import requests

from agency_mbs.notify import send_telegram_message


def test_send_telegram_message_missing_files_is_noop(tmp_path):
    result = send_telegram_message(
        "hola", bot_token_path=tmp_path / "token.txt", chat_id_path=tmp_path / "chat.txt"
    )
    assert result is False


def test_send_telegram_message_empty_files_is_noop(tmp_path):
    token_path = tmp_path / "token.txt"
    chat_path = tmp_path / "chat.txt"
    token_path.write_text("")
    chat_path.write_text("12345")
    result = send_telegram_message("hola", bot_token_path=token_path, chat_id_path=chat_path)
    assert result is False


@patch("agency_mbs.notify.requests.post")
def test_send_telegram_message_calls_real_api(mock_post, tmp_path):
    token_path = tmp_path / "token.txt"
    chat_path = tmp_path / "chat.txt"
    token_path.write_text("fake-token\n")
    chat_path.write_text("5989296164\n")
    mock_post.return_value = Mock(ok=True)

    result = send_telegram_message("hola", bot_token_path=token_path, chat_id_path=chat_path)

    mock_post.assert_called_once_with(
        "https://api.telegram.org/botfake-token/sendMessage",
        json={"chat_id": "5989296164", "text": "hola"},
        timeout=10,
    )
    assert result is True


@patch("agency_mbs.notify.requests.post")
def test_send_telegram_message_request_failure_is_noop(mock_post, tmp_path):
    token_path = tmp_path / "token.txt"
    chat_path = tmp_path / "chat.txt"
    token_path.write_text("fake-token")
    chat_path.write_text("5989296164")
    mock_post.side_effect = requests.exceptions.ConnectionError("network down")

    result = send_telegram_message("hola", bot_token_path=token_path, chat_id_path=chat_path)

    assert result is False


@patch("agency_mbs.notify.requests.post")
def test_send_telegram_message_non_ok_response(mock_post, tmp_path):
    token_path = tmp_path / "token.txt"
    chat_path = tmp_path / "chat.txt"
    token_path.write_text("fake-token")
    chat_path.write_text("5989296164")
    mock_post.return_value = Mock(ok=False)

    result = send_telegram_message("hola", bot_token_path=token_path, chat_id_path=chat_path)

    assert result is False
