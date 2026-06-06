# df-cross-hotel-best-practice-sharer — Output [CRUX-MK]
*Autonom aktiviert 2026-06-05T13:03:33.366068+00:00 | ollama-local/qwen2.5:14b-instruct*

# Dokumentation der Dark-Factory `df-cross-hotel-best-practice-sharer`

## Zweck und Architektur

Die Dark-Factory `df-cross-hotel-best-practice-sharer` ist spezialisiert da
darauf, erfolgreiche Praktiken aus einem Hotel zu extrahieren und diese als
als Anpassungsvorschläge für andere Hotels vorzuschlagen. Sie verwendet ein
eine bayessche Kenntnisübertragungslogik (Mock-Standard), um dieses Wissen 
effektiv zu transferieren.

### Architektur

Die Factory besteht aus folgenden Komponenten:

- `best_practice_repository.py`: Speichert erfolgreiche Muster in einem Dic
Dictionary und ermöglicht deren Persistierung als JSON-Datei.
- `bayesian_knowledge_transfer.py`: Implementiert die bayessche Übertragung
Übertragung von Kenntnissen basierend auf einer Beta-Distribution (Mock-Ver
(Mock-Version).
- `adapter_orchestrator.py`: Einstiegspunkt für LaunchAgent-Funktionen, die
dient als Kontrollpunkt für den gesamten Prozess.
- `audit_logger.py`: Loggt alle Aktivitäten mit HMAC-SHA256-gesignierten JS
JSONL-Datensätzen zur Sicherheitsüberwachung.

## CRUX-Konformität

Die Factory ist konform zum CRUX-Mustermodell und implementiert folgende Kr
Kriterien:

- **K11 Cascade-Containment**: Hart getrennte Isolation mit begrenztem Ausw
Auswirkungsradius.
- **K12 Distillation-Resistenz**: Erforderliche Herkunftsnachweise und ein 
zusätzliches Nicht-LLM-Wertebereich-Layer.
- **K13 Unabhängige Grundlagen-Wahrheit**: Ankerung an der Dateisystem-Disk
Dateisystem-Disk mit täglicher Synchronisation.
- **K14 Menschliche Überwachung**: Einzige Befehlsline zur Manuell-Aktion u
und wöchentlicher Prüfung erforderlich.
- **K15 Entropiebudget**: ~600 Zeilen Code, 3 Konzepte.
- **K16 Concurrent-Spawn-Mutex**: Atomeinheitliche Verzeichniserstellung un
und Prozessabfrage zur Synchronisation.

## Betriebsmodi

Die Factory kann in einer Sandbox-Umgebung ausgeführt werden, welche die St
Standardeinstellung darstellt. In der Real-Modus muss ein gültiger Phronesi
Phronesis-Ticket vorgelegt werden (`DF_CROSS_HOTEL_REAL_ENABLED=true`).

### Ausführung

```bash
# Sandbox (Standard)
python3 -m src.adapter_orchestrator

# Real-Modus (Phronesis Pflicht)
export DF_CROSS_HOTEL_REAL_ENABLED=true
export PHRONESIS_TICKET=PT-2026-05-XX-XXX
python3 -m src.adapter_orchestrator
```

### Tests

Die Integration und Funktionalität der Factory können durch pytest getestet
getestet werden.

```bash
python3 -m pytest tests/ -q
```

Diese Dokumentation legt die Grundlagen für den Einsatz und die Wartung der
der Dark-Factory `df-cross-hotel-best-practice-sharer`.