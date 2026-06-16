import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
# [CRUX-MK]
from cross_hotel_best_practice_sharer import (
    BestPracticeRepository,
    BayesianKnowledgeTransfer,
    PracticeRecord,
    suggest_adaptations,
)


def test_cross_hotel_best_practice_transfer_and_persistence(tmp_path):
    repo_path = tmp_path / "best_practices.json"
    repo = BestPracticeRepository(str(repo_path))

    repo.add_practice(
        PracticeRecord(
            hotel="Hildesheim",
            pattern_id="mobile-checkin",
            category="front-desk",
            description="Offer pre-arrival mobile check-in with room-ready SMS.",
            successes=9,
            failures=1,
            provenance="ops-report-2026-06-10",
        )
    )
    repo.add_practice(
        PracticeRecord(
            hotel="Hildesheim",
            pattern_id="late-breakfast",
            category="fnb",
            description="Extend breakfast by 30 minutes on weekends.",
            successes=1,
            failures=6,
            provenance="ops-report-2026-06-11",
        )
    )

    repo.add_feedback("Munich", "mobile-checkin", successes=3, failures=1)
    repo.add_feedback("Cape Coral", "mobile-checkin", successes=0, failures=2)

    repo.save()

    loaded = BestPracticeRepository(str(repo_path))
    suggestions = suggest_adaptations(
        repository=loaded,
        source_hotel="Hildesheim",
        target_hotels=["Munich", "Cape Coral"],
        min_confidence=0.60,
        bayes=BayesianKnowledgeTransfer(alpha=1, beta=1),
    )

    assert [item["target_hotel"] for item in suggestions] == ["Munich", "Cape Coral"]
    assert [item["pattern_id"] for item in suggestions] == ["mobile-checkin", "mobile-checkin"]

    munich = suggestions[0]
    cape_coral = suggestions[1]

    assert munich["provenance"] == "ops-report-2026-06-10"
    assert munich["posterior_mean"] == 0.8125  # (1 + 9 + 3) / (2 + 9 + 3 + 1 + 1)
    assert cape_coral["posterior_mean"] == 0.714286  # rounded from 10 / 14

    assert munich["posterior_mean"] > cape_coral["posterior_mean"]

    assert all(item["pattern_id"] != "late-breakfast" for item in suggestions)

