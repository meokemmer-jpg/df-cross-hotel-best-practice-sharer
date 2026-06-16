import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
# [CRUX-MK]
from cross_hotel_best_practice_sharer import (
    AuditLogger,
    BestPracticeRepository,
    PracticePattern,
    run_sharing_cycle,
)


def test_run_sharing_cycle_persists_patterns_and_emits_verified_audit(tmp_path):
    storage_path = tmp_path / "patterns.json"
    audit_path = tmp_path / "audit.jsonl"

    patterns = [
        PracticePattern(
            pattern_id="late-checkin-playbook",
            title="Late Check-in Playbook",
            category="operations",
            description="Self-service late arrival process.",
            source_hotel="Hildesheim",
            successes=12,
            failures=2,
            provenance="daily-drive-anchor://hildesheim/ops/late-checkin",
            validation_score=0.95,
            metadata={"tags": ["city", "self-service", "late-arrival"]},
        ),
        PracticePattern(
            pattern_id="spa-upsell-flow",
            title="Spa Upsell Flow",
            category="revenue",
            description="Arrival-day spa offer via SMS.",
            source_hotel="Hildesheim",
            successes=2,
            failures=6,
            provenance="daily-drive-anchor://hildesheim/revenue/spa-upsell",
            validation_score=0.7,
            metadata={"tags": ["upsell", "resort"]},
        ),
    ]

    suggestions, event = run_sharing_cycle(
        source_hotel="Hildesheim",
        target_hotels=["Cape Coral", "Munich"],
        patterns=patterns,
        storage_path=storage_path,
        audit_log_path=audit_path,
        audit_secret="test-secret",
        hotel_profiles={
            "Cape Coral": {
                "transferable_categories": ["operations"],
                "tags": ["self-service", "late-arrival", "resort"],
            },
            "Munich": {
                "transferable_categories": ["operations", "revenue"],
                "tags": ["city", "late-arrival"],
            },
        },
    )

    repo = BestPracticeRepository.load(storage_path)
    assert len(repo.all_patterns()) == 2
    assert repo.get_pattern("late-checkin-playbook").title == "Late Check-in Playbook"

    assert "Cape Coral" in suggestions
    assert "Munich" in suggestions
    assert len(suggestions["Cape Coral"]) == 1
    assert suggestions["Cape Coral"][0]["pattern_id"] == "late-checkin-playbook"
    assert suggestions["Cape Coral"][0]["score"] >= 0.6
    assert suggestions["Cape Coral"][0]["confidence_band"] in {"medium", "high"}

    # The weaker revenue pattern should not survive the default score threshold.
    assert all(item["pattern_id"] != "spa-upsell-flow" for item in suggestions["Cape Coral"])
    assert all(item["pattern_id"] != "spa-upsell-flow" for item in suggestions["Munich"])

    logger = AuditLogger(secret="test-secret", log_path=audit_path)
    assert logger.verify_record(event) is True

    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert '"event_type": "sharing_cycle_completed"' in lines[0]
