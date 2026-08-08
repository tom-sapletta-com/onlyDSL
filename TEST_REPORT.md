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
Ran 62 tests
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
- GuidanceDSL/IncidentDSL/EventDSL persistence,
- strict PatchDSL parsing, base-hash and path policy checks,
- verified autonomous patch application,
- automatic byte-for-byte rollback after a failed test.
- canonical Subactor `aql:contract/v1` authorization of OQL plus exact URI Process,
- schema-compatible process envelopes, EQL outcomes and SODL receipts,
- immutable governance kernel and opaque, preaccepted secret references.
- native TestQL startup scenarios, TestQLDSL persistence and failure-to-observation routing.

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

The real provider was reached with a configured key. Authentication and response delivery worked, but the end-to-end twin smoke remained fail-closed because the selected model emitted non-canonical IFURI (`command` instead of `commands`) after all repair attempts. No invalid TwinDSL was accepted.

The autonomous repair capability was also exercised against OpenRouter while diagnosing a supervisor false alarm. Provider output was rejected before application because it did not conform to PatchDSL (`patchdsl.v1` fence, followed by a non-canonical block form). The contract and parser were subsequently made explicit and the safe `BLOCK` alias received regression coverage. No provider-generated patch was applied during this diagnostic.

Running the smoke script without a key still returns:

```text
OPENROUTER_SMOKE_SKIPPED: OPENROUTER_API_KEY is not set
```

The OpenRouter network path itself is covered by tests using a mocked HTTP response, including endpoint, Bearer key forwarding, model selection, DSL-only request content and repair-loop behavior.

## Docker execution status

Docker execution was verified on 2026-08-08. The regular stack and the guarded live-evolution profile built successfully. The evolution profile is currently healthy on `127.0.0.1:18787` with `EVOLUTION_MODE=apply` and an empty active incident queue.

The Compose file was parsed by the architecture test suite and includes:

- `nats` with JetStream configuration,
- `postgres`,
- `app`,
- `integration`,
- `openrouter-smoke` under profile `llm`.
- `live-app` and `evolution-agent` under profile `evolution`.

The live supervisor detected a source change, recorded `application_reload_requested` as EventDSL, restarted the child server and returned to healthy state. A controlled container restart no longer produces a new process-exit incident. Historical failed incidents from diagnosing that race remain in the ignored runtime audit directory.

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
