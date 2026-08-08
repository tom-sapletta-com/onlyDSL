# DSL-only LLM boundary

## Invariant

**Żaden element kontekstu aplikacji nie może zostać przekazany do LLM w formie surowej.**

Dotyczy to w szczególności:

- logów,
- eventów,
- wyjątków i stack trace,
- runtime state,
- metryk,
- wyników narzędzi / API / MCP,
- danych RAG / retrieval,
- pamięci i historii agenta,
- rekordów bazodanowych,
- informacji o kodzie i repozytorium,
- capabilities / dostępnych funkcji,
- wyników poprzednich kroków modelu.

Każdy z tych elementów przechodzi najpierw przez deterministyczny adapter/kompilator aplikacyjny i dopiero jako fenced DSL może wejść do klienta LLM.

```text
RAW APPLICATION DATA
        │
        ▼
Context adapters / runtime instrumentation
        │
        ▼
ContextDSL / CapabilityDSL / SchemaDSL
        │
        ▼
BoundaryGate.assert_dsl_only()
        │
        ▼
LLM
        │
        ▼
IntentDSL / DecisionDSL / PatchDSL
        │
        ▼
parser → semantic validation → capability validation
        │
        ▼
runtime / tool registry / OQL-CQL compiler
```

## Najważniejsza zasada implementacyjna

Nie należy projektować tego jako:

```text
text log → prompt template → LLM
```

ani nawet:

```text
text log → ```contextdsl RAW "..."``` → LLM
```

Preferowana architektura to **DSL-native observability**:

```python
DslContextEvent(
    source="auth_service",
    code="token_refresh_failed",
    severity="error",
    fields={"status": 401, "attempt": 1},
)
```

czyli semantyczny event istnieje **zanim** powstanie potrzeba analizy przez model.

Legacy tekstowe logi są obsługiwane tylko przez adapter kompatybilności. Adapter:

- ekstrahuje severity/source/`key=value`,
- zamienia resztę wiadomości na kod zdarzenia,
- nie przekazuje surowej linii,
- dodaje `legacy=true`, `lossy=true`,
- zachowuje jedynie `raw_digest` do korelacji.

## Typy DSL na granicy

### Runtime → LLM

- `contextdsl` — stan, eventy, logi, wyjątki, tool results, metrics, retrieval, pamięć, fakty o kodzie.
- `capabilitydsl` — dozwolone funkcje/akcje/narzędzia oraz ich kontrakty.
- `schemadsl` — typy, pola, constraints i symbole.
- `taskdsl` — co model ma wykonać.
- `contractdsl` — protokół komunikacji i zakazy.
- `sourcedsl` — jedyny dopuszczony envelope dla treści źródłowej człowieka/dokumentu, gdy rzeczywiście potrzebna jest analiza naturalnego języka.

### LLM → runtime

- `intentdsl` — intencja i reguły wykonywalne.
- `decisiondsl` — decyzja bez bezpośredniego wykonania.
- `patchdsl` — żądane zmiany w istniejącym DSL/AST.

Model nie powinien zwracać prozy poza codeblockiem.

## SourceDSL a natural language

Nie da się semantycznie przetworzyć dowolnej treści angielskiej bez udostępnienia jej komponentowi rozumiejącemu język. Dlatego rozróżniamy:

1. **operational context** — powinien być semantycznym DSL generowanym przez aplikację/runtime; natural language nie jest potrzebny,
2. **source content** — np. polecenie użytkownika, dokument, issue; może istnieć jako `PAYLOAD` wewnątrz `sourcedsl`, ale nie wolno mieszać go z operational context ani dodawać nieustrukturyzowanej prozy do promptu.

Dla pipeline'ów wielomodelowych można dodać osobny ingestion compiler:

```text
SourceDSL → ingestion LLM → FactDSL → main LLM
```

Wtedy główny agent operuje już wyłącznie na semantycznym DSL.

## Capability validation

Sama poprawność gramatyczna nie wystarcza.

Jeżeli runtime deklaruje:

```contextdsl
CAPABILITY action refresh_token
CAPABILITY event auth_error
```

to odpowiedź:

```intentdsl
DO delete_database
```

musi zostać odrzucona przed wykonaniem, nawet jeżeli składnia DSL jest poprawna.

POC robi tę walidację w `validate_program(..., action_registry=..., event_registry=...)`.

## Tool calling

LLM nie powinien wywoływać narzędzia bezpośrednio.

```text
LLM
 ↓
IntentDSL: DO refresh_token
 ↓
semantic validator
 ↓
capability registry
 ↓
runtime adapter
 ↓
real tool/API
 ↓
Tool result
 ↓
ContextDSL compiler
 ↓
next LLM cycle
```

Dzięki temu tool result nigdy nie wraca do modelu jako surowy JSON/tekst.

## Exceptions

Stack trace jest szczególnie zły jako surowy prompt: jest duży, powtarzalny i może zawierać dane wrażliwe.

POC `ContextCompiler.exception()` emituje m.in.:

```contextdsl
RECORD exception api runtime_exception
  FIELD exception_type = "TimeoutError"
  FIELD message_digest = "..."
END
```

Docelowo runtime powinien dodać strukturalne frame IDs / module IDs / error codes, zamiast wysyłać pełny traceback.

## RAG / code context

Retrieval również powinien być traktowany jako boundary input.

Preferowane:

```contextdsl
RECORD retrieval docs retry_policy
  FIELD document_id = "auth_policy_v4"
  FIELD section = "refresh"
  FIELD retry_max = 2
END
```

zamiast wklejania pełnego dokumentu do głównego agenta.

Analogicznie kod:

```contextdsl
RECORD code auth_client refresh_token_contract
  FIELD symbol = "AuthClient.refresh_token"
  FIELD returns_status = true
  FIELD side_effect = "token_replace"
END
```

## Development invariant

W CI powinien istnieć test, że **każda publiczna metoda klienta LLM przyjmuje `DslBundle`, a nie `str | dict` z kontekstem**.

Jeżeli trzeba dodać nowy typ kontekstu, najpierw powstaje adapter do DSL, dopiero potem integracja z modelem.
