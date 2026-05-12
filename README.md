# df-cross-hotel-best-practice-sharer [CRUX-MK]

**Welle:** 47 (W45-B-RETRY)
**Type:** foundation-df
**Sandbox-Default:** ja (Mock-Hotels, kein Real-Service-Call)

## Zweck

Cross-Hotel Best-Practice-Sharing: extrahiert erfolgreiche Patterns aus einem Hotel
(z.B. Hildesheim) und schlaegt sie als Adaptions-Kandidaten fuer andere Hotels vor
(z.B. Cape Coral, Munich). Bayesian-Knowledge-Transfer (Mock-Default).

## Architektur

```
src/
  best_practice_repository.py    # Pattern-Storage (Dict + JSON-Persist)
  bayesian_knowledge_transfer.py # Mock-Bayesian-Update (Beta-Distribution)
  adapter_orchestrator.py        # LaunchAgent Entry-Point main()
  audit_logger.py                # HMAC-SHA256-signed JSONL audit
```

## CRUX-Konformitaet

- **K11 Cascade-Containment:** hard isolation, blast_radius=1
- **K12 Distillation-Resistenz:** provenance_required=true, non_llm_validation_layer=true
- **K13 Independent-Ground-Truth:** drive_filesystem anchor, daily
- **K14 Human-Override:** single_command, weekly review
- **K15 Entropy-Budget:** ~600 LOC, 3 concepts
- **K16 Concurrent-Spawn-Mutex:** mkdir-atomic + pgrep
- **LC1-LC5:** Lose-Coupling vollstaendig

## Run

```bash
# Sandbox (Default)
python3 -m src.adapter_orchestrator

# Real-Mode (Phronesis Pflicht)
export DF_CROSS_HOTEL_REAL_ENABLED=true
export PHRONESIS_TICKET=PT-2026-05-XX-XXX
python3 -m src.adapter_orchestrator
```

## Tests

```bash
python3 -m pytest tests/ -q
```

[CRUX-MK]
