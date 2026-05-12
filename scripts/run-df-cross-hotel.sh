#!/usr/bin/env bash
# [CRUX-MK] K16 Concurrent-Spawn-Mutex (mkdir-atomic) + EXIT/INT/TERM-Trap.
set -euo pipefail

LOCK_DIR="/tmp/df-cross-hotel-best-practice-sharer.lock"
LOCK_AGE_LIMIT_S=21600  # 6h

# Stale-lock auto-claim
if [ -d "$LOCK_DIR" ]; then
    LOCK_AGE_S=$(( $(date +%s) - $(stat -f %m "$LOCK_DIR" 2>/dev/null || echo 0) ))
    if [ "$LOCK_AGE_S" -gt "$LOCK_AGE_LIMIT_S" ]; then
        rm -rf "$LOCK_DIR"
    fi
fi

# Atomic mkdir-lock
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "K16-VETO: another instance running" >&2
    exit 3
fi
echo "$$" > "$LOCK_DIR/pid"
trap 'rm -rf "$LOCK_DIR"' EXIT INT TERM

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Sandbox-Default (real-mode requires explicit PHRONESIS_TICKET)
exec /usr/bin/env python3 -m src.adapter_orchestrator
