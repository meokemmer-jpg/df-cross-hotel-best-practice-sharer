from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class PracticeRecord:
    hotel: str
    pattern_id: str
    category: str
    description: str
    successes: int
    failures: int
    provenance: str

    def validate(self) -> None:
        if not self.hotel.strip():
            raise ValueError("hotel must be non-empty")
        if not self.pattern_id.strip():
            raise ValueError("pattern_id must be non-empty")
        if not self.category.strip():
            raise ValueError("category must be non-empty")
        if not self.description.strip():
            raise ValueError("description must be non-empty")
        if self.successes < 0 or self.failures < 0:
            raise ValueError("successes/failures must be >= 0")
        if not self.provenance.strip():
            raise ValueError("provenance is required")


class BestPracticeRepository:
    def __init__(self, json_path: Optional[str] = None) -> None:
        self.json_path = Path(json_path) if json_path else None
        self._practices: Dict[Tuple[str, str], PracticeRecord] = {}
        self._feedback: Dict[Tuple[str, str], Dict[str, int]] = {}
        if self.json_path and self.json_path.exists():
            self.load()

    def add_practice(self, record: PracticeRecord) -> None:
        record.validate()
        self._practices[(record.hotel, record.pattern_id)] = record

    def add_feedback(
        self,
        target_hotel: str,
        pattern_id: str,
        successes: int,
        failures: int,
    ) -> None:
        if not target_hotel.strip():
            raise ValueError("target_hotel must be non-empty")
        if not pattern_id.strip():
            raise ValueError("pattern_id must be non-empty")
        if successes < 0 or failures < 0:
            raise ValueError("successes/failures must be >= 0")
        self._feedback[(target_hotel, pattern_id)] = {
            "successes": successes,
            "failures": failures,
        }

    def get_practices_for_hotel(self, hotel: str) -> List[PracticeRecord]:
        return [r for (h, _), r in self._practices.items() if h == hotel]

    def get_feedback(self, target_hotel: str, pattern_id: str) -> Dict[str, int]:
        return self._feedback.get((target_hotel, pattern_id), {"successes": 0, "failures": 0})

    def save(self) -> None:
        if not self.json_path:
            raise ValueError("json_path is not configured")
        payload = {
            "practices": [asdict(r) for r in self._practices.values()],
            "feedback": [
                {
                    "target_hotel": hotel,
                    "pattern_id": pattern_id,
                    "successes": counts["successes"],
                    "failures": counts["failures"],
                }
                for (hotel, pattern_id), counts in self._feedback.items()
            ],
        }
        self.json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def load(self) -> None:
        if not self.json_path:
            raise ValueError("json_path is not configured")
        payload = json.loads(self.json_path.read_text(encoding="utf-8"))
        self._practices.clear()
        self._feedback.clear()
        for item in payload.get("practices", []):
            record = PracticeRecord(**item)
            record.validate()
            self._practices[(record.hotel, record.pattern_id)] = record
        for item in payload.get("feedback", []):
            self.add_feedback(
                target_hotel=item["target_hotel"],
                pattern_id=item["pattern_id"],
                successes=item["successes"],
                failures=item["failures"],
            )


class BayesianKnowledgeTransfer:
    def __init__(self, alpha: int = 1, beta: int = 1) -> None:
        if alpha <= 0 or beta <= 0:
            raise ValueError("alpha and beta must be > 0")
        self.alpha = alpha
        self.beta = beta

    def posterior(self, successes: int, failures: int) -> Tuple[int, int]:
        if successes < 0 or failures < 0:
            raise ValueError("successes/failures must be >= 0")
        return self.alpha + successes, self.beta + failures

    def mean_probability(self, successes: int, failures: int) -> float:
        alpha_post, beta_post = self.posterior(successes, failures)
        return alpha_post / float(alpha_post + beta_post)


def suggest_adaptations(
    repository: BestPracticeRepository,
    source_hotel: str,
    target_hotels: Iterable[str],
    min_confidence: float = 0.60,
    bayes: Optional[BayesianKnowledgeTransfer] = None,
) -> List[Dict[str, object]]:
    if not 0.0 <= min_confidence <= 1.0:
        raise ValueError("min_confidence must be between 0 and 1")
    bayes = bayes or BayesianKnowledgeTransfer()

    suggestions: List[Dict[str, object]] = []
    for practice in repository.get_practices_for_hotel(source_hotel):
        practice.validate()
        for target_hotel in target_hotels:
            if target_hotel == source_hotel:
                continue
            feedback = repository.get_feedback(target_hotel, practice.pattern_id)
            combined_successes = practice.successes + feedback["successes"]
            combined_failures = practice.failures + feedback["failures"]
            probability = bayes.mean_probability(combined_successes, combined_failures)
            if probability < min_confidence:
                continue
            suggestions.append(
                {
                    "source_hotel": source_hotel,
                    "target_hotel": target_hotel,
                    "pattern_id": practice.pattern_id,
                    "category": practice.category,
                    "description": practice.description,
                    "provenance": practice.provenance,
                    "posterior_mean": round(probability, 6),
                    "source_evidence": {
                        "successes": practice.successes,
                        "failures": practice.failures,
                    },
                    "target_feedback": feedback,
                }
            )

    suggestions.sort(
        key=lambda item: (
            -float(item["posterior_mean"]),
            str(item["target_hotel"]),
            str(item["pattern_id"]),
        )
    )
    return suggestions
# [CRUX-MK]
