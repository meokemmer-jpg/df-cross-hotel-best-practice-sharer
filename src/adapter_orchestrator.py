"""Adapter-Orchestrator: LaunchAgent Entry-Point [CRUX-MK]."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from .audit_logger import AuditLogger
from .bayesian_knowledge_transfer import BayesianKnowledgeTransfer
from .best_practice_repository import (
    BestPractice,
    BestPracticeRepository,
    is_real_mode_enabled,
)


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

    audit.log({
        "event": "run_complete",
        "patterns_registered": len(repo.list_all()),
        "proposals_by_pattern": proposals_by_pattern,
        "source": "mock",
        "checked_at": int(time.time()),
    })

    return {
        "patterns_registered": len(repo.list_all()),
        "proposals_by_pattern": proposals_by_pattern,
        "chain_intact": audit.verify_chain(),
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
