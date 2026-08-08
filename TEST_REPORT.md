# IFURI Digital Twin Lab 0.4 — test report

Date: 2026-08-08

## Verdict

**LOCAL_TESTS_PASS**

The delivered source tree passes all tests that can be executed in the current runtime.

## Automated unit/integration-style suite

Command:

```bash
python3 -m unittest discover -s tests -v
```

Result:

```text
Ran 44 tests
OK
```

Coverage includes:

- IFURI canonical parsing and NATS subject mapping,
- logical URI architecture invariant (no host:port transport identity),
- deterministic capability manifest resolution and ambiguous-route fail-closed behavior,
- Protobuf envelope round-trip,
- CQRS/Event Store optimistic concurrency,
- atomic Event + transactional Outbox commit,
- NATS wire request/reply behavior,
- Python/Node/PHP IFURI parity,
- DSL-only ContextDSL boundary,
- proactive IntentDSL runtime,
- source text wrapped as application-generated SourceDSL,
- OpenRouter provider configuration and dedicated `OPENROUTER_API_KEY`,
- OpenRouter request endpoint/model/header wiring using a mocked network call,
- fail-closed OpenRouter repair loop that does not re-feed rejected raw model output,
- DigitalTwinDSL bootstrap and validation,
- immutable intent fingerprint,
- deterministic `sources/*.md -> SourceIndexDSL`,
- stable source IDs when files are added,
- source-document digest evolution across twin revisions,
- source provenance in TwinDSL,
- BuildPlanDSL generation,
- persistent twin revision history.

## HTTP end-to-end test

A local HTTP server was started with:

```text
LLM_BACKEND=demo
```

Verified sequence:

```text
GET  /api/health                 -> 0.4.0
POST /api/twin/bootstrap         -> TwinDSL revision 1, VALID
GET  /api/twin/sources           -> 2 Markdown documents, SourceIndexDSL VALID
POST /api/twin/update            -> TwinDSL revision 2, VALID, 3 provenance sources
POST /api/twin/plan              -> BuildPlanDSL VALID
POST /api/ifuri/analyze-context  -> IntentDSL VALID, proactive runtime halted as expected
```

Observed IFURI capability routes:

```text
llm.twin.bootstrap
llm.twin.update
llm.builder.plan
llm.reasoner.analyze
```

All selected the registered `inproc` adapter without changing logical IFURI addresses.

## OpenRouter real network test

The package now contains a real-provider smoke test:

```bash
docker compose --profile llm run --rm openrouter-smoke
```

It requires:

```text
OPENROUTER_API_KEY
```

The current execution environment did **not** contain an OpenRouter key, therefore no paid/external model request was made. Running the smoke script without a key correctly returns:

```text
OPENROUTER_SMOKE_SKIPPED: OPENROUTER_API_KEY is not set
```

The OpenRouter network path itself is covered by tests using a mocked HTTP response, including endpoint, Bearer key forwarding, model selection, DSL-only request content and repair-loop behavior.

## Docker execution status

`docker`, `podman`, and `/var/run/docker.sock` are unavailable in the current execution environment. Therefore an actual `docker compose build/run` cannot be truthfully marked as executed here.

The Compose file was parsed by the architecture test suite and includes:

- `nats` with JetStream configuration,
- `postgres`,
- `app`,
- `integration`,
- `openrouter-smoke` under profile `llm`.

The Docker integration script now covers:

```text
NATS request/reply
Postgres authoritative Event Store
transactional outbox
JetStream publish + replay
Protobuf IfEnvelope
ContextDSL -> LLM capability -> IntentDSL
SourceDSL -> TwinDSL r1
TwinDSL + SourceIndexDSL -> TwinDSL r2
TwinDSL r2 -> BuildPlanDSL
```

Run on a Docker host:

```bash
docker compose build
docker compose run --rm integration
```

For the real OpenRouter path:

```bash
cp .env.example .env
# set OPENROUTER_API_KEY and LLM_BACKEND=openrouter
docker compose up -d nats postgres app
docker compose --profile llm run --rm openrouter-smoke
```

## Security/invariant checks

- No real API key is included in the package.
- `.env` is excluded from Docker build context.
- Domain/server code does not import `llm_client` directly.
- All LLM provider access goes through registered IFURI LLM capabilities.
- Runtime/user/source context is encoded as DSL before the provider boundary.
- Rejected raw provider output is not used as retry context.
