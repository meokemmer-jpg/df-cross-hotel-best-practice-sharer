"""LC2 Cross-Hotel-Anonymization Tests [CRUX-MK].

5+ Pflicht-Tests per W46-E Patch-6 Brief:
- test_pii_redacted_in_cross_hotel_share
- test_credit_card_blocks_share
- test_tenant_id_anonymized
- test_no_pii_passes_through_unchanged
- test_anonymization_audit_logged

Plus zusaetzliche Edge-Cases.
[CRUX-MK]
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Stelle sicher dass src/ importierbar ist
_DF_ROOT = Path(__file__).resolve().parent.parent
if str(_DF_ROOT) not in sys.path:
    sys.path.insert(0, str(_DF_ROOT))

from src.best_practice_repository import BestPractice  # noqa: E402
from src.lc2_anonymization import (  # noqa: E402
    AnonymizationEvent,
    CrossHotelAnonymizer,
    anonymize_tenant_id,
)


def _bp(pattern_id: str, source: str, description: str) -> BestPractice:
    return BestPractice(
        pattern_id=pattern_id,
        source_tenant=source,
        description=description,
        kpi_improvement=0.15,
        confidence=0.8,
        tags=("test",),
    )


def test_pii_redacted_in_cross_hotel_share() -> None:
    """Email + Phone in description werden geredacted, share trotzdem allowed."""
    audit: list[AnonymizationEvent] = []
    anonymizer = CrossHotelAnonymizer(audit_sink=audit)

    bp = _bp(
        "bp-test-email",
        "hildesheim",
        "Send report to guest@example.com or call +49 89 1234567 daily",
    )

    result = anonymizer.share_best_practice(bp, target_tenant="munich")

    assert result.action == "redacted", f"expected redacted, got {result.action}"
    assert result.anonymized_bp is not None
    desc = result.anonymized_bp.description
    assert "guest@example.com" not in desc, "email leaked into shared description"
    assert "+49 89 1234567" not in desc, "phone leaked into shared description"
    assert "[REDACTED:email" in desc or "[REDACTED:phone" in desc
    assert result.event is not None
    assert result.event.event_type == "share_redacted"
    assert "email" in result.event.pii_types_detected or "phone" in result.event.pii_types_detected


def test_credit_card_blocks_share() -> None:
    """Credit-Card in description blockt komplette Share-Operation."""
    audit: list[AnonymizationEvent] = []
    anonymizer = CrossHotelAnonymizer(audit_sink=audit)

    bp = _bp(
        "bp-test-cc",
        "hildesheim",
        "Booking confirmed for 4111 1111 1111 1111 visa card",
    )

    result = anonymizer.share_best_practice(bp, target_tenant="cape-coral")

    assert result.action == "blocked", f"expected blocked, got {result.action}"
    assert result.anonymized_bp is None, "anonymized_bp must be None on BLOCK"
    assert result.event is not None
    assert result.event.event_type == "share_blocked"
    assert "credit_card" in result.event.pii_types_detected
    # Tenant-IDs muessen trotzdem anonymisiert sein
    assert result.anonymized_source.startswith("tenant:")
    assert result.anonymized_target.startswith("tenant:")


def test_tenant_id_anonymized() -> None:
    """source_tenant + target_tenant werden via Hotel-Salt-Hash anonymisiert."""
    audit: list[AnonymizationEvent] = []
    anonymizer = CrossHotelAnonymizer(audit_sink=audit, tenant_salt="lc2-test-salt")

    bp = _bp("bp-test-tenant", "hildesheim", "Plain operational note no pii")

    result = anonymizer.share_best_practice(bp, target_tenant="munich")

    assert result.action == "allowed"
    assert result.anonymized_bp is not None
    # Tenant-ID darf NICHT als Klartext im output erscheinen.
    assert result.anonymized_bp.source_tenant != "hildesheim", "source_tenant not anonymized"
    assert result.anonymized_bp.source_tenant.startswith("tenant:")
    assert result.anonymized_target.startswith("tenant:") and "munich" not in result.anonymized_target
    # Deterministisch: gleicher Input + Salt -> gleicher Output.
    assert anonymize_tenant_id("hildesheim", "lc2-test-salt") == result.anonymized_source
    # Verschiedene Inputs -> verschiedene Outputs.
    assert anonymize_tenant_id("hildesheim", "lc2-test-salt") != anonymize_tenant_id("munich", "lc2-test-salt")


def test_no_pii_passes_through_unchanged() -> None:
    """description ohne PII bleibt unveraendert (nur tenant_id anonymisiert)."""
    audit: list[AnonymizationEvent] = []
    anonymizer = CrossHotelAnonymizer(audit_sink=audit)

    original_desc = "Optimized housekeeping route saves 12 minutes per floor"
    bp = _bp("bp-test-clean", "munich", original_desc)

    result = anonymizer.share_best_practice(bp, target_tenant="hildesheim")

    assert result.action == "allowed"
    assert result.anonymized_bp is not None
    assert result.anonymized_bp.description == original_desc, "description changed without PII"
    assert result.event is not None
    assert result.event.event_type == "share_allowed"
    assert result.event.pii_types_detected == ()


def test_anonymization_audit_logged() -> None:
    """Jede Share-Operation erzeugt genau einen AnonymizationEvent im audit_sink."""
    audit: list[AnonymizationEvent] = []
    anonymizer = CrossHotelAnonymizer(audit_sink=audit)

    bp1 = _bp("bp-1", "hildesheim", "Plain note one")
    bp2 = _bp("bp-2", "hildesheim", "Note with email user@host.com")
    bp3 = _bp("bp-3", "munich", "Note with card 4111 1111 1111 1111")

    anonymizer.share_best_practice(bp1, target_tenant="munich")
    anonymizer.share_best_practice(bp2, target_tenant="munich")
    anonymizer.share_best_practice(bp3, target_tenant="cape-coral")

    assert len(audit) == 3, f"expected 3 audit events, got {len(audit)}"
    assert audit[0].event_type == "share_allowed"
    assert audit[1].event_type == "share_redacted"
    assert audit[2].event_type == "share_blocked"
    # Source-Tenant immer anonymisiert im Audit-Log.
    for event in audit:
        assert event.source_tenant_hash.startswith("tenant:")
        assert event.target_tenant_hash.startswith("tenant:")
        # Klartext-Tenant-Namen duerfen NICHT im Hash erscheinen.
        assert "hildesheim" not in event.source_tenant_hash
        assert "munich" not in event.target_tenant_hash
        assert event.ts > 0


def test_iban_also_blocks_share() -> None:
    """IBAN triggert ebenfalls BLOCK (worst-case-wins)."""
    audit: list[AnonymizationEvent] = []
    anonymizer = CrossHotelAnonymizer(audit_sink=audit)

    bp = _bp(
        "bp-test-iban",
        "hildesheim",
        "Payment via DE89 3704 0044 0532 0130 00 received",
    )

    result = anonymizer.share_best_practice(bp, target_tenant="munich")

    assert result.action == "blocked"
    assert "iban" in result.event.pii_types_detected


def test_empty_tenant_id_handled() -> None:
    """Leerer tenant_id -> 'tenant:empty', kein Crash."""
    assert anonymize_tenant_id("") == "tenant:empty"
    assert anonymize_tenant_id("", "any-salt") == "tenant:empty"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
