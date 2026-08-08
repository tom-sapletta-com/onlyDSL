# Integracja z OQLos / connect-scenario

Docelowo POC nie powinien tworzyć konkurencyjnego hardware runtime.

## Warstwa wejściowa do LLM

OQLos/connect-scenario powinny emitować semantyczne zdarzenia do wspólnego `ContextCompiler`:

```text
CQL/OQL runtime state ─┐
hardware events ───────┤
validator violations ──┤
execution trace ───────┤→ ContextDSL → LLM
mapping/capabilities ──┤
health/diagnosis ──────┘
```

Przykładowe mapowanie:

```text
hardware plugin health  → RECORD event hardware <health_code>
validator violation     → RECORD error validator <rule_id>
execution step          → RECORD trace runtime <step_code>
current variables       → STATE <name> <type> = <value>
metrics                 → METRIC <name> = <value>
FUNC/TASK registry      → CAPABILITY action <symbol>
allowed runtime events  → CAPABILITY event <symbol>
```

## Warstwa wyjściowa LLM

```text
IntentDSL
  ↓
Intent parser
  ↓
semantic + capability validation
  ↓
Intent AST
  ↓
translator
  ↓
OQL/CQL AST
  ↓
existing serializer/validator
  ↓
existing executor
```

`DO` nie powinno wykonywać Python/JS bezpośrednio. Powinno zostać rozwiązane przez istniejący registry/mapping layer.

## Co powinno zniknąć z promptów

- pełne tracebacki,
- `repr()` obiektów,
- raw HTTP body,
- raw tool JSON,
- całe log files,
- pełne repo files, jeżeli agent potrzebuje tylko symbol facts,
- nieprzefiltrowane historie wykonania.

Zastępujemy je typed facts w ContextDSL.
