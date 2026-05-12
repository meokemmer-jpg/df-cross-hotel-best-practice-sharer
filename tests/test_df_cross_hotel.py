"""Tests fuer df-cross-hotel-best-practice-sharer [CRUX-MK]."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.adapter_orchestrator import load_mock_patterns, mock_targets, run_once
from src.audit_logger import AuditLogger
from src.bayesian_knowledge_transfer import BayesianKnowledgeTransfer
from src.best_practice_repository import (
    BestPractice,
    BestPracticeRepository,
    is_real_mode_enabled,
)


def test_repository_register_and_get(tmp_path: Path) -> None:
    repo = BestPracticeRepository(persist_path=tmp_path / "patterns.json")
    bp = BestPractice(pattern_id="p1", source_tenant="hildesheim", kpi_improvement=0.1, confidence=0.5)
    repo.register(bp)
    assert repo.get("p1") == bp
    assert len(repo.list_all()) == 1


def test_repository_persistence_roundtrip(tmp_path: Path) -> None:
    persist = tmp_path / "patterns.json"
    repo = BestPracticeRepository(persist_path=persist)
    repo.register(BestPractice(pattern_id="p1", source_tenant="hildesheim", confidence=0.8))
    repo.register(BestPractice(pattern_id="p2", source_tenant="munich", confidence=0.6))
    # neue Instanz -> laed Persist
    repo2 = BestPracticeRepository(persist_path=persist)
    assert len(repo2.list_all()) == 2
    assert repo2.get("p1").source_tenant == "hildesheim"


def test_repository_list_by_source() -> None:
    repo = BestPracticeRepository()
    repo.register(BestPractice(pattern_id="p1", source_tenant="hildesheim"))
    repo.register(BestPractice(pattern_id="p2", source_tenant="munich"))
    repo.register(BestPractice(pattern_id="p3", source_tenant="hildesheim"))
    by_source = repo.list_by_source("hildesheim")
    assert len(by_source) == 2
    assert {bp.pattern_id for bp in by_source} == {"p1", "p3"}


def test_repository_top_n_by_confidence() -> None:
    repo = BestPracticeRepository()
    repo.register(BestPractice(pattern_id="p1", source_tenant="a", confidence=0.5))
    repo.register(BestPractice(pattern_id="p2", source_tenant="b", confidence=0.9))
    repo.register(BestPractice(pattern_id="p3", source_tenant="c", confidence=0.7))
    top2 = repo.top_n_by_confidence(2)
    assert [bp.pattern_id for bp in top2] == ["p2", "p3"]


def test_bayesian_prior_validation() -> None:
    with pytest.raises(ValueError):
        BayesianKnowledgeTransfer(prior_alpha=0)
    with pytest.raises(ValueError):
        BayesianKnowledgeTransfer(prior_beta=-1)


def test_bayesian_posterior_increases_with_success() -> None:
    bkt = BayesianKnowledgeTransfer()
    before = bkt.posterior_mean("h", "c")
    bkt.observe("h", "c", success=True)
    bkt.observe("h", "c", success=True)
    after = bkt.posterior_mean("h", "c")
    assert after > before


def test_bayesian_posterior_decreases_with_failure() -> None:
    bkt = BayesianKnowledgeTransfer()
    before = bkt.posterior_mean("h", "c")
    bkt.observe("h", "c", success=False)
    bkt.observe("h", "c", success=False)
    after = bkt.posterior_mean("h", "c")
    assert after < before


def test_bayesian_propose_rejects_same_source_target() -> None:
    bkt = BayesianKnowledgeTransfer()
    bp = BestPractice(pattern_id="p1", source_tenant="hildesheim")
    with pytest.raises(ValueError):
        bkt.propose(bp, target_tenant="hildesheim")


def test_bayesian_rank_targets_orders_by_expected() -> None:
    bkt = BayesianKnowledgeTransfer()
    bkt.observe("hildesheim", "cape-coral", success=True)
    bkt.observe("hildesheim", "cape-coral", success=True)
    bp = BestPractice(
        pattern_id="p1", source_tenant="hildesheim", kpi_improvement=0.2, confidence=0.9
    )
    ranked = bkt.rank_targets(bp, ["cape-coral", "munich"])
    assert len(ranked) == 2
    assert ranked[0].target_tenant == "cape-coral"
    # source is excluded
    assert all(r.target_tenant != "hildesheim" for r in ranked)


def test_audit_logger_chain_intact(tmp_path: Path) -> None:
    audit = AuditLogger(tmp_path / "audit.jsonl")
    audit.log({"event": "a"})
    audit.log({"event": "b"})
    audit.log({"event": "c"})
    assert audit.verify_chain() is True
    entries = audit.read_all()
    assert len(entries) == 3
    assert all("chain_hash" in e for e in entries)


def test_audit_logger_detects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    audit = AuditLogger(path)
    audit.log({"event": "a"})
    audit.log({"event": "b"})
    # Tampering: modifiziere eine Zeile
    lines = path.read_text().splitlines()
    rec = json.loads(lines[0])
    rec["event"] = "tampered"
    lines[0] = json.dumps(rec)
    path.write_text("\n".join(lines) + "\n")
    audit2 = AuditLogger(path)
    assert audit2.verify_chain() is False


def test_is_real_mode_enabled_default_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DF_CROSS_HOTEL_REAL_ENABLED", raising=False)
    assert is_real_mode_enabled() is False
    monkeypatch.setenv("DF_CROSS_HOTEL_REAL_ENABLED", "true")
    assert is_real_mode_enabled() is True
    monkeypatch.setenv("DF_CROSS_HOTEL_REAL_ENABLED", "1")
    # Strict: only "true" enables
    assert is_real_mode_enabled() is False


def test_run_once_smoke_mock(tmp_path: Path) -> None:
    result = run_once(tmp_path / "audit.jsonl", tmp_path / "patterns.json")
    assert result["patterns_registered"] == 3
    assert result["chain_intact"] is True
    # Proposals existieren fuer alle Patterns
    assert set(result["proposals_by_pattern"].keys()) == {
        "bp-hildesheim-checkin-flow",
        "bp-hildesheim-upsell-script",
        "bp-munich-housekeeping-route",
    }


def test_run_once_proposals_exclude_source(tmp_path: Path) -> None:
    result = run_once(tmp_path / "audit.jsonl", tmp_path / "patterns.json")
    for pattern_id, proposals in result["proposals_by_pattern"].items():
        for prop in proposals:
            if pattern_id.startswith("bp-hildesheim"):
                assert prop["target"] != "hildesheim"
            elif pattern_id.startswith("bp-munich"):
                assert prop["target"] != "munich"


def test_mock_data_consistency() -> None:
    patterns = load_mock_patterns()
    targets = mock_targets()
    assert len(patterns) == 3
    assert len(targets) == 3
    # Alle source_tenants existieren in targets-Liste
    for bp in patterns:
        assert bp.source_tenant in targets
