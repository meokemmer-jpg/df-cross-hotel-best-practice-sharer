from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class PracticePattern:
    pattern_id: str
    title: str
    category: str
    description: str
    source_hotel: str
    successes: int
    failures: int
    provenance: str
    validation_score: float
    metadata: Dict[str, object] = field(default_factory=dict)

    def posterior_mean(self, alpha_prior: float = 1.0, beta_prior: float = 1.0) -> float:
        alpha = alpha_prior + max(0, self.successes)
        beta = beta_prior + max(0, self.failures)
        return alpha / (alpha + beta)

    def evidence_volume(self) -> int:
        return max(0, self.successes) + max(0, self.failures)


class BestPracticeRepository:
    def __init__(self, storage_path: Optional[os.PathLike] = None) -> None:
        self.storage_path = Path(storage_path) if storage_path else None
        self._patterns: Dict[str, PracticePattern] = {}

    def add_pattern(self, pattern: PracticePattern) -> None:
        if not pattern.provenance:
            raise ValueError("provenance is required")
        if not (0.0 <= pattern.validation_score <= 1.0):
            raise ValueError("validation_score must be between 0 and 1")
        self._patterns[pattern.pattern_id] = pattern

    def get_pattern(self, pattern_id: str) -> PracticePattern:
        return self._patterns[pattern_id]

    def patterns_for_hotel(self, hotel_name: str) -> List[PracticePattern]:
        return [p for p in self._patterns.values() if p.source_hotel == hotel_name]

    def all_patterns(self) -> List[PracticePattern]:
        return list(self._patterns.values())

    def save(self) -> None:
        if self.storage_path is None:
            raise ValueError("storage_path is not configured")
        payload = [self._pattern_to_dict(p) for p in self.all_patterns()]
        self.storage_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, storage_path: os.PathLike) -> "BestPracticeRepository":
        repo = cls(storage_path=storage_path)
        path = Path(storage_path)
        if not path.exists():
            return repo
        raw = json.loads(path.read_text(encoding="utf-8"))
        for item in raw:
            repo.add_pattern(cls._pattern_from_dict(item))
        return repo

    @staticmethod
    def _pattern_to_dict(pattern: PracticePattern) -> Dict[str, object]:
        return {
            "pattern_id": pattern.pattern_id,
            "title": pattern.title,
            "category": pattern.category,
            "description": pattern.description,
            "source_hotel": pattern.source_hotel,
            "successes": pattern.successes,
            "failures": pattern.failures,
            "provenance": pattern.provenance,
            "validation_score": pattern.validation_score,
            "metadata": pattern.metadata,
        }

    @staticmethod
    def _pattern_from_dict(data: Dict[str, object]) -> PracticePattern:
        return PracticePattern(
            pattern_id=str(data["pattern_id"]),
            title=str(data["title"]),
            category=str(data["category"]),
            description=str(data["description"]),
            source_hotel=str(data["source_hotel"]),
            successes=int(data["successes"]),
            failures=int(data["failures"]),
            provenance=str(data["provenance"]),
            validation_score=float(data["validation_score"]),
            metadata=dict(data.get("metadata", {})),
        )


def bayesian_transfer_score(
    pattern: PracticePattern,
    target_hotel: str,
    target_profile: Optional[Dict[str, object]] = None,
    alpha_prior: float = 1.0,
    beta_prior: float = 1.0,
) -> float:
    if not target_hotel:
        raise ValueError("target_hotel is required")
    if not pattern.provenance:
        raise ValueError("provenance is required")

    target_profile = target_profile or {}
    transferable_categories = set(target_profile.get("transferable_categories", []))
    category_match = 1.0 if not transferable_categories or pattern.category in transferable_categories else 0.55

    target_tags = set(target_profile.get("tags", []))
    source_tags = set(pattern.metadata.get("tags", [])) if isinstance(pattern.metadata.get("tags", []), list) else set()
    overlap = len(source_tags & target_tags)
    union = len(source_tags | target_tags)
    contextual_match = 1.0 if union == 0 else 0.7 + 0.3 * (overlap / union)

    posterior = pattern.posterior_mean(alpha_prior=alpha_prior, beta_prior=beta_prior)
    validation_weight = 0.5 + 0.5 * pattern.validation_score

    score = posterior * category_match * contextual_match * validation_weight
    return round(max(0.0, min(1.0, score)), 6)


def suggest_adaptations(
    source_hotel: str,
    target_hotels: Iterable[str],
    repository: BestPracticeRepository,
    hotel_profiles: Optional[Dict[str, Dict[str, object]]] = None,
    min_score: float = 0.6,
) -> Dict[str, List[Dict[str, object]]]:
    hotel_profiles = hotel_profiles or {}
    source_patterns = repository.patterns_for_hotel(source_hotel)
    results: Dict[str, List[Dict[str, object]]] = {}

    for target_hotel in target_hotels:
        suggestions: List[Dict[str, object]] = []
        for pattern in source_patterns:
            score = bayesian_transfer_score(
                pattern=pattern,
                target_hotel=target_hotel,
                target_profile=hotel_profiles.get(target_hotel),
            )
            if score < min_score:
                continue
            suggestions.append(
                {
                    "target_hotel": target_hotel,
                    "pattern_id": pattern.pattern_id,
                    "title": pattern.title,
                    "score": score,
                    "confidence_band": _confidence_band(score, pattern.evidence_volume()),
                    "provenance": pattern.provenance,
                    "adaptation_candidate": {
                        "category": pattern.category,
                        "description": pattern.description,
                        "source_hotel": source_hotel,
                    },
                }
            )
        suggestions.sort(key=lambda item: (-item["score"], item["pattern_id"]))
        results[target_hotel] = suggestions
    return results


def _confidence_band(score: float, evidence_volume: int) -> str:
    if score >= 0.8 and evidence_volume >= 8:
        return "high"
    if score >= 0.65 and evidence_volume >= 4:
        return "medium"
    return "low"


class AuditLogger:
    def __init__(self, secret: str, log_path: os.PathLike) -> None:
        self._secret = secret.encode("utf-8")
        self.log_path = Path(log_path)

    def log_event(self, event_type: str, payload: Dict[str, object]) -> Dict[str, object]:
        record = {
            "event_id": str(uuid.uuid4()),
            "ts": int(time.time()),
            "event_type": event_type,
            "payload": copy.deepcopy(payload),
        }
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        record["signature"] = hmac.new(self._secret, canonical, hashlib.sha256).hexdigest()
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        return record

    def verify_record(self, record: Dict[str, object]) -> bool:
        signature = record.get("signature")
        if not isinstance(signature, str):
            return False
        unsigned = dict(record)
        unsigned.pop("signature", None)
        canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")
        expected = hmac.new(self._secret, canonical, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)


@contextmanager
def spawn_mutex(name: str, base_dir: Optional[os.PathLike] = None):
    root = Path(base_dir) if base_dir else Path(tempfile.gettempdir())
    lock_dir = root / f"{name}.lock"
    try:
        lock_dir.mkdir()
    except FileExistsError as exc:
        raise RuntimeError(f"mutex already held: {name}") from exc
    try:
        yield lock_dir
    finally:
        try:
            lock_dir.rmdir()
        except FileNotFoundError:
            pass


def run_sharing_cycle(
    source_hotel: str,
    target_hotels: Iterable[str],
    patterns: Iterable[PracticePattern],
    storage_path: os.PathLike,
    audit_log_path: os.PathLike,
    audit_secret: str,
    hotel_profiles: Optional[Dict[str, Dict[str, object]]] = None,
    real_enabled: Optional[bool] = None,
) -> Tuple[Dict[str, List[Dict[str, object]]], Dict[str, object]]:
    real_mode = bool(real_enabled) if real_enabled is not None else (
        os.getenv("DF_CROSS_HOTEL_REAL_ENABLED", "").lower() == "true"
    )
    if real_mode and not os.getenv("PHRONESIS_TICKET"):
        raise RuntimeError("PHRONESIS_TICKET is required in real mode")

    repo = BestPracticeRepository(storage_path=storage_path)
    for pattern in patterns:
        repo.add_pattern(pattern)
    repo.save()

    with spawn_mutex("df-cross-hotel-best-practice-sharer", base_dir=Path(storage_path).parent):
        suggestions = suggest_adaptations(
            source_hotel=source_hotel,
            target_hotels=target_hotels,
            repository=repo,
            hotel_profiles=hotel_profiles,
        )

    logger = AuditLogger(secret=audit_secret, log_path=audit_log_path)
    event = logger.log_event(
        "sharing_cycle_completed",
        {
            "mode": "real" if real_mode else "sandbox",
            "source_hotel": source_hotel,
            "target_hotels": list(target_hotels),
            "suggestion_counts": {hotel: len(items) for hotel, items in suggestions.items()},
        },
    )
    return suggestions, event


def main() -> Dict[str, List[Dict[str, object]]]:
    temp_root = Path(tempfile.gettempdir())
    storage_path = temp_root / "cross_hotel_best_practices.json"
    audit_path = temp_root / "cross_hotel_audit.jsonl"

    demo_patterns = [
        PracticePattern(
            pattern_id="late-checkin-playbook",
            title="Late Check-in Playbook",
            category="operations",
            description="Proactive SMS and key-lockbox flow reduced after-hours escalations.",
            source_hotel="Hildesheim",
            successes=11,
            failures=2,
            provenance="daily-drive-anchor://hildesheim/ops/late-checkin",
            validation_score=0.92,
            metadata={"tags": ["city", "self-service", "late-arrival"]},
        ),
        PracticePattern(
            pattern_id="breakfast-queue-redesign",
            title="Breakfast Queue Redesign",
            category="guest_experience",
            description="Split buffet lanes lowered guest wait time during peak period.",
            source_hotel="Hildesheim",
            successes=7,
            failures=3,
            provenance="daily-drive-anchor://hildesheim/fnb/breakfast-queue",
            validation_score=0.88,
            metadata={"tags": ["breakfast", "peak-hours"]},
        ),
    ]

    suggestions, _event = run_sharing_cycle(
        source_hotel="Hildesheim",
        target_hotels=["Cape Coral", "Munich"],
        patterns=demo_patterns,
        storage_path=storage_path,
        audit_log_path=audit_path,
        audit_secret="sandbox-secret",
        hotel_profiles={
            "Cape Coral": {"transferable_categories": ["operations"], "tags": ["self-service", "late-arrival", "resort"]},
            "Munich": {"transferable_categories": ["operations", "guest_experience"], "tags": ["city", "breakfast"]},
        },
    )
    print(json.dumps(suggestions, indent=2, sort_keys=True))
    return suggestions


if __name__ == "__main__":
    main()
# [CRUX-MK]
