# onlyDSL -> IntentDSL Lab 0.2 — DSL-only LLM Boundary

POC sprawdzający zasadę:

> **Każdy styk kontekstu aplikacji z LLM musi przejść przez DSL generowany przez runtime/aplikację.**

Nie tylko odpowiedź modelu ma być strukturalna. Również **wejście do modelu** nie może zawierać surowych logów, wyjątków, stanu, wyników narzędzi ani nieustrukturyzowanego kontekstu.

## Pipeline

```text
runtime / logs / events / state / tools / metrics / RAG / memory
                         │
                         ▼
                 ContextCompiler
                         │
                         ▼
                  ```contextdsl```
                         │
                         ▼
                    BoundaryGate
                         │
                         ▼
                         LLM
                         │
                         ▼
                   ```intentdsl```
                         │
                         ▼
 parser → semantic validator → capability validator → runtime
```

## Uruchomienie

```bash
cp .env.example .env
./run.sh
# http://127.0.0.1:8787
```

Tryb `demo` nie wymaga żadnych paczek pip ani modelu.

## Testy

```bash
python3 -m unittest discover -s tests -v
```

Aktualny zestaw obejmuje m.in.:

- IntentDSL parser/runtime,
- ContextDSL compiler/parser,
- semantic events,
- legacy log adapter,
- zakaz raw/prose na LLM boundary,
- SourceDSL dla user text,
- capability validation,
- proactive runtime,
- codegen Python/TypeScript/JavaScript/PHP.

## Najważniejsze pliki

- `contextdsl.py` — deterministyczny kompilator kontekstu aplikacji.
- `boundary.py` — twardy gate `DSL-only` przed każdym wywołaniem LLM.
- `llm_client.py` — klient modelu; publiczna analiza runtime przyjmuje tylko ContextDSL.
- `intentdsl.py` — parser, AST, semantic validation, capability validation, runtime i codegen.
- `server.py` — prosta aplikacja HTTP.
- `grammar/intentdsl.gbnf` — constrained output; model zwraca pojedynczy fenced `intentdsl` block.
- `docs/LLM_BOUNDARY_ARCHITECTURE.md` — pełna zasada architektoniczna.
- `docs/OQLOS_INTEGRATION.md` — plan spięcia z OQLos/connect-scenario.

## DSL-native logs

Preferowane:

```python
compiler.event(DslContextEvent(
    source="auth_service",
    code="token_refresh_failed",
    severity="error",
    fields={"status": 401, "attempt": 1},
))
```

Niepreferowane:

```python
llm("ERROR auth_service refresh failed status=401 ...")
```

Legacy log można przepuścić przez `legacy_log()`, ale adapter jest jawnie `lossy` i nie udostępnia modelowi pełnej surowej linii.

## Capability registry

ContextDSL może zadeklarować:

```contextdsl
CAPABILITY action refresh_token
CAPABILITY event auth_error
```

Wtedy IntentDSL zawierający:

```intentdsl
DO delete_database
```

jest odrzucany przed wykonaniem.

## LLM backends

### vLLM

```dotenv
LLM_BACKEND=vllm
LLM_BASE_URL=http://localhost:8000/v1
LLM_MODEL=<model>
```

Klient używa `structured_outputs.grammar`.

### llama.cpp

```dotenv
LLM_BACKEND=llamacpp
LLM_BASE_URL=http://localhost:8080/v1
LLM_MODEL=<model>
```

Klient przekazuje GBNF w `grammar`.

### OpenAI-compatible

```dotenv
LLM_BACKEND=openai_compat
```

Tryb kontrolny bez gwarancji gramatycznej po stronie serwera. Boundary validation nadal obowiązuje przed i po wywołaniu.

## Ważne rozróżnienie: ContextDSL vs SourceDSL

Operational context powinien być generowany semantycznie przez runtime.

Dowolny dokument/polecenie natural-language może zostać przesłany do dedykowanego semantic compiler tylko jako:

```sourcedsl
SOURCE user_text
LANG en
MEDIA text
PAYLOAD "..."
END_SOURCE
```

Nie wolno mieszać raw source z logami/state/tool outputs w jednym prompt-cie.

## Docelowa integracja

POC ma działać jako meta-warstwa przed istniejącym runtime:

```text
ContextDSL → LLM → IntentDSL AST → OQL/CQL AST → existing validator → existing executor
```

Czyli nie tworzymy drugiego hardware interpretera. `DO` mapujemy do istniejącego FUNC/TASK/mapping registry.


## License

Licensed under Apache-2.0.
