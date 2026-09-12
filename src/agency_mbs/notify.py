"""Telegram notifications for scheduled ingestion.

Reuses the same Telegram bot the operator's other, separate Windows-side
automation already uses for unrelated task alerts — same bot, same
chat_id. That side reads the token from a Windows-only environment
variable store not visible from WSL, so this side reads the same two
values from local, gitignored files instead
(`data/telegram_bot_token.txt`, `data/telegram_chat_id.txt`) — same
secret-handling convention already used for the Ginnie Mae/Freddie Mac
session cookies in this project.

Silent no-op if either file is missing, empty, or the request fails — a
notification failure must never break the actual ingest run. Sent via
`requests.post(..., json=...)`, which encodes UTF-8 correctly by
construction.
"""

from __future__ import annotations

from pathlib import Path

import requests

BOT_TOKEN_PATH = Path(__file__).resolve().parents[2] / "data" / "telegram_bot_token.txt"
CHAT_ID_PATH = Path(__file__).resolve().parents[2] / "data" / "telegram_chat_id.txt"


def send_telegram_message(
    text: str, *, bot_token_path: Path = BOT_TOKEN_PATH, chat_id_path: Path = CHAT_ID_PATH
) -> bool:
    """Best-effort Telegram notification. Returns whether it was actually sent."""
    if not bot_token_path.exists() or not chat_id_path.exists():
        return False
    token = bot_token_path.read_text().strip()
    chat_id = chat_id_path.read_text().strip()
    if not token or not chat_id:
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        return resp.ok
    except requests.RequestException:
        return False
