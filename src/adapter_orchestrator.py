"""Adapter-Orchestrator: LaunchAgent Entry-Point [CRUX-MK]."""

from __future__ import annotations

import json
import logging
import os
import sys
import sys as _sys
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .audit_logger import AuditLogger
from .bayesian_knowledge_transfer import BayesianKnowledgeTransfer
from .best_practice_repository import (
    BestPractice,
    BestPracticeRepository,
    is_real_mode_enabled,
)

# W49-D K12+K13 Foundation
_DF_ROOT = Path(__file__).resolve().parent.parent.parent
_sys.path.insert(0, str(_DF_ROOT))
try:
    from _df_common.full_provenance_envelope import build_full_envelope  # type: ignore
    from _df_common.rfc3161_anchor import rfc3161_timestamp  # type: ignore
    W49D_FOUNDATION = True
except ImportError:
    W49D_FOUNDATION = False

_K12_HMAC_SECRET = os.environ.get(
    "DF_CROSS_HOTEL_HMAC_SECRET", "df-cross-hotel-best-practice-sharer-dev-hmac-secret-v1"
)
_K12_ENVELOPE_TTL_S = int(os.environ.get("DF_CROSS_HOTEL_ENVELOPE_TTL_S", "86400"))

_logger = logging.getLogger(__name__)


def load_mock_patterns() -> list[BestPractice]:
    """Sandbox-Mock-Default: 3 Best-Practice-Patterns."""
    return [
        BestPractice(
            pattern_id="bp-hildesheim-checkin-flow",
            source_tenant="hildesheim",
            description="Express check-in via mobile QR-Code",
            kpi_improvement=0.18,
            confidence=0.85,
            tags=("checkin", "mobile"),
        ),
        BestPractice(
            pattern_id="bp-hildesheim-upsell-script",
            source_tenant="hildesheim",
            description="Upsell-Script bei Spa-Buchungen",
            kpi_improvement=0.12,
            confidence=0.72,
            tags=("upsell", "spa"),
        ),
        BestPractice(
            pattern_id="bp-munich-housekeeping-route",
            source_tenant="munich",
            description="Optimierte Housekeeping-Routenplanung",
            kpi_improvement=0.09,
            confidence=0.68,
            tags=("housekeeping", "ops"),
        ),
    ]


def mock_targets() -> list[str]:
    """Sandbox-Mock-Default: 3 Target-Hotels."""
    return ["hildesheim", "cape-coral", "munich"]


def run_once(audit_path: Path, repo_path: Path | None = None) -> dict:
    """LaunchAgent Entry-Point: extract patterns + propose adaptations."""
    audit = AuditLogger(audit_path)
    audit.log({"event": "run_start", "real_mode_enabled": is_real_mode_enabled()})

    repo = BestPracticeRepository(persist_path=repo_path)
    for bp in load_mock_patterns():
        repo.register(bp)

    bkt = BayesianKnowledgeTransfer()
    # Seed mit synthetischen Beobachtungen fuer Sandbox-Realismus
    bkt.observe("hildesheim", "cape-coral", success=True)
    bkt.observe("hildesheim", "cape-coral", success=True)
    bkt.observe("hildesheim", "munich", success=True)
    bkt.observe("munich", "cape-coral", success=False)

    proposals_by_pattern: dict[str, list[dict]] = {}
    targets = mock_targets()
    for bp in repo.list_all():
        ranked = bkt.rank_targets(bp, targets, top_n=3)
        proposals_by_pattern[bp.pattern_id] = [
            {
                "target": p.target_tenant,
                "expected_improvement": round(p.expected_improvement, 4),
                "posterior_mean": round(p.posterior_mean, 4),
            }
            for p in ranked
        ]

    run_id = f"cross-hotel-{datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    summary = {
        "event": "run_complete",
        "run_id": run_id,
        "patterns_registered": len(repo.list_all()),
        "proposals_by_pattern": proposals_by_pattern,
        "source": "mock",
        "checked_at": int(time.time()),
    }
    audit.log(summary)

    # W49-D K12: FullProvenanceEnvelope (HMAC + chain-predecessor)
    chain_hash_for_anchor: str | None = None
    if W49D_FOUNDATION:
        try:
            provenance_full_dir = Path(audit_path).parent / "provenance-full"
            provenance_full_dir.mkdir(parents=True, exist_ok=True)
            predecessor_hash: str | None = None
            files = sorted(provenance_full_dir.glob("*.envelope.json"), key=lambda p: p.stat().st_mtime)
            if files:
                try:
                    with files[-1].open("r", encoding="utf-8") as f:
                        predecessor_hash = json.load(f).get("payload_hash")
                except (OSError, json.JSONDecodeError) as e:
                    _logger.warning(f"K12 predecessor read failed: {e}")
            envelope = build_full_envelope(
                operation_id=run_id,
                operation_type="df-cross-hotel-best-practice-share",
                issuer="df-cross-hotel-best-practice-sharer",
                payload_dict=summary,
                secret=_K12_HMAC_SECRET,
                predecessor_hash=predecessor_hash,
                tenant_id="cross-hotel-aggregate",
                ttl_seconds=_K12_ENVELOPE_TTL_S,
            )
            env_out = provenance_full_dir / f"{run_id}.envelope.json"
            with env_out.open("w", encoding="utf-8") as f:
                json.dump(asdict(envelope), f, indent=2, default=str, ensure_ascii=False)
            chain_hash_for_anchor = envelope.payload_hash
        except Exception as e:
            _logger.warning(f"K12 envelope build failed (non-fatal): {e}")

    # W49-D K13: RFC3161 External-Anchor
    if W49D_FOUNDATION and chain_hash_for_anchor:
        try:
            rfc_anchor = rfc3161_timestamp(chain_hash_for_anchor, provider="freetsa")
            anchors_dir = Path(audit_path).parent / "anchors"
            anchors_dir.mkdir(parents=True, exist_ok=True)
            with (anchors_dir / "rfc3161-anchors.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(rfc_anchor)) + "\n")
        except Exception as e:
            _logger.warning(f"K13 RFC3161 anchor failed (non-fatal): {e}")

    return {
        "patterns_registered": len(repo.list_all()),
        "proposals_by_pattern": proposals_by_pattern,
        "chain_intact": audit.verify_chain(),
        "run_id": run_id,
    }


def main() -> int:
    """CLI entry-point."""
    audit_path = Path.home() / ".df-cross-hotel-best-practice-sharer" / "audit.jsonl"
    repo_path = Path.home() / ".df-cross-hotel-best-practice-sharer" / "patterns.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    result = run_once(audit_path, repo_path)
    success = result["patterns_registered"] > 0 and result["chain_intact"]
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
