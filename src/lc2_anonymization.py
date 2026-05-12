"""LC2 Cross-Hotel-Anonymization-Guardrails [CRUX-MK].

W46-E Cross-LLM-3OF3 Patch-6:
"df-cross-hotel MODIFY wegen fehlender Anonymization-Guardrails fuer
Cross-Hotel-Datenfluss."

Anwendung: Bevor Best-Practices/Proposals von Hotel-A nach Hotel-B geteilt werden,
laeuft jeder geteilte Output durch PrivacyRouter + Tenant-ID-Hash.

Pflicht-Pfade (Cross-Hotel-Datenfluss):
1. BestPractice.description (Free-Text aus Source-Tenant)
2. tenant_id (source_tenant, target_tenant) - Anonymisierung via Hotel-Salt-Hash
3. Audit-Logging jedes Cross-Hotel-Anonymization-Events

Reference: _df_common/privacy_router.py
[CRUX-MK]
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional

# _df_common Reference-Import
_PARENT = Path(__file__).resolve().parents[2]
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

from _df_common.privacy_router import (  # noqa: E402
    PolicyAction,
    PolicyRoutingDecision,
    PrivacyRouter,
)

from .best_practice_repository import BestPractice  # noqa: E402

logger = logging.getLogger(__name__)


# Hotel-Salt aus Env-Var oder Default (NICHT in Code committen, nur Default fuer Dev).
HOTEL_SALT_ENV = "DF_CROSS_HOTEL_TENANT_SALT"
HOTEL_SALT_DEFAULT = "lc2-default-salt-2026-w46"


@dataclass(frozen=True)
class AnonymizationEvent:
    """Audit-Trail-Entry pro Cross-Hotel-Anonymization."""

    event_type: str  # "share_allowed" | "share_redacted" | "share_blocked"
    source_tenant_hash: str
    target_tenant_hash: str
    pattern_id: str
    pii_types_detected: tuple[str, ...] = field(default_factory=tuple)
    reason: str = ""
    ts: int = 0


def get_tenant_salt() -> str:
    """Hotel-Salt aus Env-Var, sonst Default."""
    return os.environ.get(HOTEL_SALT_ENV, HOTEL_SALT_DEFAULT)


def anonymize_tenant_id(tenant_id: str, salt: Optional[str] = None) -> str:
    """Anonymisiere tenant_id via Hotel-Salt-Hash (10 chars sufficient).

    Beispiel: 'hildesheim' -> 'tenant:a3f2c1b9d4'
    Deterministisch: gleicher Input + gleicher Salt -> gleicher Output.
    """
    if not tenant_id:
        return "tenant:empty"
    real_salt = salt if salt is not None else get_tenant_salt()
    h = hashlib.sha256(f"{real_salt}:{tenant_id}".encode()).hexdigest()[:10]
    return f"tenant:{h}"


class CrossHotelAnonymizer:
    """LC2-Guardrail-Pipeline fuer Cross-Hotel-Sharing.

    Usage:
        anonymizer = CrossHotelAnonymizer()
        result = anonymizer.share_best_practice(bp, target_tenant="munich")
        if result.action == "blocked":
            return
        anonymized_bp = result.anonymized_bp  # safe to forward to target
    """

    def __init__(
        self,
        router: Optional[PrivacyRouter] = None,
        tenant_salt: Optional[str] = None,
        audit_sink: Optional[list[AnonymizationEvent]] = None,
    ):
        # Default-Router: BLOCK auf Credit-Card+IBAN+SSN, REDACT auf Email+Phone.
        self.router = router or PrivacyRouter(
            block_on_credit_card=True,
            block_on_iban=True,
            redact_on_email=True,
            redact_on_phone=True,
        )
        self.tenant_salt = tenant_salt or get_tenant_salt()
        self.audit_sink = audit_sink if audit_sink is not None else []

    @dataclass(frozen=True)
    class ShareResult:
        """Result einer Cross-Hotel-Share-Operation."""

        action: str  # "allowed" | "redacted" | "blocked"
        anonymized_bp: Optional[BestPractice] = None
        anonymized_source: str = ""
        anonymized_target: str = ""
        pii_decision: Optional[PolicyRoutingDecision] = None
        event: Optional[AnonymizationEvent] = None

    def share_best_practice(
        self,
        bp: BestPractice,
        target_tenant: str,
    ) -> "CrossHotelAnonymizer.ShareResult":
        """Bereite BestPractice fuer Cross-Hotel-Share vor.

        Pflicht-Schritte:
        1. PII-Detection in bp.description (PrivacyRouter)
        2. BLOCK bei Credit-Card/IBAN/SSN
        3. REDACT bei Email/Phone (description wird ersetzt)
        4. Anonymisiere source_tenant + target_tenant via Hash
        5. Schreibe AnonymizationEvent in audit_sink
        """
        anon_source = anonymize_tenant_id(bp.source_tenant, self.tenant_salt)
        anon_target = anonymize_tenant_id(target_tenant, self.tenant_salt)

        decision = self.router.route(bp.description or "")
        pii_types = tuple(d.pii_type.value for d in decision.detections)

        if decision.action == PolicyAction.BLOCK:
            event = AnonymizationEvent(
                event_type="share_blocked",
                source_tenant_hash=anon_source,
                target_tenant_hash=anon_target,
                pattern_id=bp.pattern_id,
                pii_types_detected=pii_types,
                reason=decision.reason,
                ts=int(time.time()),
            )
            self.audit_sink.append(event)
            logger.warning(
                "LC2 BLOCK pattern_id=%s source=%s target=%s reason=%s",
                bp.pattern_id, anon_source, anon_target, decision.reason,
            )
            return self.ShareResult(
                action="blocked",
                anonymized_bp=None,
                anonymized_source=anon_source,
                anonymized_target=anon_target,
                pii_decision=decision,
                event=event,
            )

        if decision.action == PolicyAction.REDACT:
            redacted_description = decision.redacted_text or ""
            anonymized_bp = replace(
                bp,
                source_tenant=anon_source,
                description=redacted_description,
            )
            event = AnonymizationEvent(
                event_type="share_redacted",
                source_tenant_hash=anon_source,
                target_tenant_hash=anon_target,
                pattern_id=bp.pattern_id,
                pii_types_detected=pii_types,
                reason=decision.reason,
                ts=int(time.time()),
            )
            self.audit_sink.append(event)
            return self.ShareResult(
                action="redacted",
                anonymized_bp=anonymized_bp,
                anonymized_source=anon_source,
                anonymized_target=anon_target,
                pii_decision=decision,
                event=event,
            )

        # ALLOW / AUDIT_ALLOW: tenant-IDs trotzdem anonymisieren.
        anonymized_bp = replace(bp, source_tenant=anon_source)
        event = AnonymizationEvent(
            event_type="share_allowed",
            source_tenant_hash=anon_source,
            target_tenant_hash=anon_target,
            pattern_id=bp.pattern_id,
            pii_types_detected=pii_types,
            reason=decision.reason or "no-pii-detected",
            ts=int(time.time()),
        )
        self.audit_sink.append(event)
        return self.ShareResult(
            action="allowed",
            anonymized_bp=anonymized_bp,
            anonymized_source=anon_source,
            anonymized_target=anon_target,
            pii_decision=decision,
            event=event,
        )
