"""Bayesian Knowledge-Transfer: Mock-Bayesian-Update [CRUX-MK].

Reines Mock-Modell (Beta-Distribution-Konjugat). Kein scipy/numpy noetig.
Adaptation-Proposal-Score = posterior_mean * source_kpi_improvement.
"""

from __future__ import annotations

from dataclasses import dataclass

from .best_practice_repository import BestPractice


@dataclass(frozen=True)
class AdaptationProposal:
    """Vorschlag: source-Pattern P fuer target-Hotel T adaptieren."""

    pattern_id: str
    source_tenant: str
    target_tenant: str
    posterior_mean: float  # adapted-confidence in [0,1]
    expected_improvement: float  # posterior_mean * source_kpi_improvement
    rationale: str = ""


class BayesianKnowledgeTransfer:
    """Mock Beta-Update fuer Source -> Target Adaptions-Confidence.

    Initial prior alpha=2, beta=2 (uniform-ish). Pro positive Beobachtung
    alpha += 1, pro negative beta += 1. posterior_mean = alpha / (alpha + beta).
    """

    def __init__(self, prior_alpha: float = 2.0, prior_beta: float = 2.0) -> None:
        if prior_alpha <= 0 or prior_beta <= 0:
            raise ValueError("priors must be > 0")
        self.prior_alpha = prior_alpha
        self.prior_beta = prior_beta
        # (source_tenant, target_tenant) -> (alpha, beta)
        self._state: dict[tuple[str, str], tuple[float, float]] = {}

    def observe(self, source: str, target: str, success: bool) -> tuple[float, float]:
        """Record one observation. Returns updated (alpha, beta)."""
        a, b = self._state.get((source, target), (self.prior_alpha, self.prior_beta))
        if success:
            a += 1.0
        else:
            b += 1.0
        self._state[(source, target)] = (a, b)
        return a, b

    def posterior_mean(self, source: str, target: str) -> float:
        a, b = self._state.get((source, target), (self.prior_alpha, self.prior_beta))
        return a / (a + b)

    def propose(self, pattern: BestPractice, target_tenant: str) -> AdaptationProposal:
        """Berechne Adaptation-Proposal fuer ein konkretes (pattern, target)."""
        if pattern.source_tenant == target_tenant:
            raise ValueError("source and target must differ")
        mean = self.posterior_mean(pattern.source_tenant, target_tenant)
        # Combine posterior with source-confidence multiplicatively
        adapted_confidence = mean * pattern.confidence
        expected = adapted_confidence * pattern.kpi_improvement
        rationale = (
            f"posterior_mean={mean:.3f} * source_conf={pattern.confidence:.3f} "
            f"= adapted_conf={adapted_confidence:.3f}; "
            f"expected_improvement={expected:.3f}"
        )
        return AdaptationProposal(
            pattern_id=pattern.pattern_id,
            source_tenant=pattern.source_tenant,
            target_tenant=target_tenant,
            posterior_mean=adapted_confidence,
            expected_improvement=expected,
            rationale=rationale,
        )

    def rank_targets(
        self, pattern: BestPractice, targets: list[str], top_n: int = 5
    ) -> list[AdaptationProposal]:
        """Rank possible target-hotels for a given pattern (descending)."""
        proposals = [
            self.propose(pattern, t) for t in targets if t != pattern.source_tenant
        ]
        proposals.sort(key=lambda p: p.expected_improvement, reverse=True)
        return proposals[:top_n]
