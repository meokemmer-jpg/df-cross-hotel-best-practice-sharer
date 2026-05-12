"""Best-Practice-Repository: Pattern-Storage (Dict + JSON-Persist) [CRUX-MK]."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Lock


@dataclass(frozen=True)
class BestPractice:
    """One best-practice pattern observed in a source-hotel."""

    pattern_id: str
    source_tenant: str
    description: str = ""
    kpi_improvement: float = 0.0  # observed delta (e.g., 0.18 = +18%)
    confidence: float = 0.5  # Bayesian prior confidence [0,1]
    tags: tuple[str, ...] = field(default_factory=tuple)


class BestPracticeRepository:
    """Thread-safe in-memory + JSON-persisted pattern store."""

    def __init__(self, persist_path: Path | None = None) -> None:
        self._patterns: dict[str, BestPractice] = {}
        self._lock = Lock()
        self.persist_path = Path(persist_path) if persist_path else None
        if self.persist_path and self.persist_path.exists():
            self._load()

    def register(self, bp: BestPractice) -> None:
        """Register a best-practice pattern. Idempotent on pattern_id."""
        with self._lock:
            self._patterns[bp.pattern_id] = bp
            if self.persist_path:
                self._save()

    def get(self, pattern_id: str) -> BestPractice | None:
        with self._lock:
            return self._patterns.get(pattern_id)

    def list_all(self) -> list[BestPractice]:
        with self._lock:
            return list(self._patterns.values())

    def list_by_source(self, source_tenant: str) -> list[BestPractice]:
        with self._lock:
            return [bp for bp in self._patterns.values() if bp.source_tenant == source_tenant]

    def top_n_by_confidence(self, n: int = 5) -> list[BestPractice]:
        with self._lock:
            sorted_bp = sorted(
                self._patterns.values(),
                key=lambda b: (b.confidence, b.kpi_improvement),
                reverse=True,
            )
            return sorted_bp[:n]

    def _save(self) -> None:
        """Persist to JSON (caller holds lock)."""
        if not self.persist_path:
            return
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.persist_path.with_suffix(".tmp")
        with tmp.open("w") as f:
            json.dump(
                {pid: asdict(bp) for pid, bp in self._patterns.items()},
                f,
                indent=2,
            )
        os.replace(tmp, self.persist_path)

    def _load(self) -> None:
        """Load from JSON (caller holds lock or is in __init__)."""
        if not self.persist_path or not self.persist_path.exists():
            return
        with self.persist_path.open("r") as f:
            data = json.load(f)
        for pid, raw in data.items():
            raw["tags"] = tuple(raw.get("tags", ()))
            self._patterns[pid] = BestPractice(**raw)


def is_real_mode_enabled() -> bool:
    """Real-Mode-Gate via ENV-Var. Sandbox-Default ist mock."""
    flag = os.environ.get("DF_CROSS_HOTEL_REAL_ENABLED", "").lower()
    return flag == "true"
