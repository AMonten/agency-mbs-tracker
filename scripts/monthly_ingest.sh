#!/usr/bin/env bash
# Runs `agency-mbs ingest <prefix>` for every supported source. Meant to be
# invoked monthly by systemd/agency-mbs-monthly-ingest.timer — see the repo
# README's "Scheduled ingestion" section for how to install it.
#
# Continues past a single prefix's failure (e.g. Freddie Mac's session
# cookie expiring — it's a real browser login, not an API key, and WILL
# expire eventually) so one broken source doesn't block the others; exits
# non-zero at the end if anything failed, so systemd/journalctl surface it.
# Also sends a Telegram summary via `agency-mbs notify` (same bot as the
# Windows-side scripts) — a no-op if data/telegram_*.txt aren't set up,
# never fatal to this script either way.
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"
# shellcheck source=/dev/null
source "$REPO_DIR/.venv/bin/activate"

PREFIXES=(factorA1 factorA2 factorAplat factorAAdd remic1 remic2 freddie)
FAILED=()

for prefix in "${PREFIXES[@]}"; do
    echo "=== $(date -Is) ingest $prefix ==="
    if ! agency-mbs ingest "$prefix"; then
        echo "=== $(date -Is) FAILED: $prefix ==="
        FAILED+=("$prefix")
    fi
done

if [ ${#FAILED[@]} -gt 0 ]; then
    SUMMARY="❌ agency-mbs-tracker: ingesta mensual con fallas (${FAILED[*]})"
else
    SUMMARY="✅ agency-mbs-tracker: ingesta mensual OK (${#PREFIXES[@]}/${#PREFIXES[@]} fuentes)"
fi
echo "=== $SUMMARY ==="
agency-mbs notify "$SUMMARY" || true

if [ ${#FAILED[@]} -gt 0 ]; then
    exit 1
fi
