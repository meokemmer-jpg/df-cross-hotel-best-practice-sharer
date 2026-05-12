"""Audit-Logger: HMAC-SHA256-signed JSONL [CRUX-MK]."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from threading import Lock


class AuditLogger:
    """Append-only JSONL audit-trail with HMAC-SHA256 chain. Thread-safe."""

    def __init__(self, path: Path, secret: bytes | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        # Sandbox-Default-Secret (NOT production-grade, only chain-integrity)
        self._secret = secret or os.environ.get(
            "DF_AUDIT_SECRET", "df-cross-hotel-sandbox-secret"
        ).encode("utf-8")
        self._last_hash = self._compute_last_hash()

    def _compute_last_hash(self) -> str:
        """Recompute last chain-hash from existing entries (idempotent)."""
        if not self.path.exists():
            return "0" * 64
        last = "0" * 64
        with self.path.open("r") as f:
            for line in f:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    last = rec.get("chain_hash", last)
        return last

    def log(self, entry: dict) -> str:
        """Append one HMAC-SHA256-chained JSONL entry. Returns chain_hash."""
        with self._lock:
            payload = {
                "ts": time.time(),
                "iso_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "df_id": "df-cross-hotel-best-practice-sharer",
                "prev_hash": self._last_hash,
                **entry,
            }
            payload_json = json.dumps(payload, sort_keys=True)
            chain_hash = hmac.new(
                self._secret,
                (self._last_hash + payload_json).encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            payload["chain_hash"] = chain_hash
            with self.path.open("a") as f:
                f.write(json.dumps(payload) + "\n")
            self._last_hash = chain_hash
            return chain_hash

    def read_all(self) -> list[dict]:
        """Read all entries (for tests + audits)."""
        if not self.path.exists():
            return []
        with self.path.open("r") as f:
            return [json.loads(line) for line in f if line.strip()]

    def verify_chain(self) -> bool:
        """Verify the entire chain integrity. Returns True if intact."""
        entries = self.read_all()
        if not entries:
            return True
        prev_hash = "0" * 64
        for rec in entries:
            stored = rec.get("chain_hash")
            payload = {k: v for k, v in rec.items() if k != "chain_hash"}
            payload_json = json.dumps(payload, sort_keys=True)
            expected = hmac.new(
                self._secret,
                (prev_hash + payload_json).encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            if stored != expected:
                return False
            prev_hash = stored
        return True
