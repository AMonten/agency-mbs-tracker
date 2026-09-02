#!/usr/bin/env bash
# Runs `agency-mbs ingest <prefix>` for every supported source. Meant to be
# invoked monthly by systemd/agency-mbs-monthly-ingest.timer — see the repo
# README's "Scheduled ingestion" section for how to install it.
#
# Continues past a single prefix's failure (e.g. Freddie Mac's session
# cookie expiring — it's a real browser login, not an API key, and WILL
# expire eventually) so one broken source doesn't block the others; exits
# non-zero at the end if anything failed, so systemd/journalctl surface it.
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
    echo "=== Monthly ingest finished with failures: ${FAILED[*]} ==="
    exit 1
fi
echo "=== Monthly ingest finished OK ==="
