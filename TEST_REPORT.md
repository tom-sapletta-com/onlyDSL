# onlyDSL 0.0.11 — test report

Current local verification: 2026-08-10

## Verdict

**CURRENT_LOCAL_TESTS_PASS — 119/119**

The current source tree passes the complete local pytest suite and the current
0.0.11 image passes the Docker integration workflow. Historical HTTP and
real-provider evidence is retained below with its original version and date;
it was not silently relabeled as a current rerun.

## Automated unit/integration-style suite

Command:

```bash
uv run pytest -q
```

Result:

```text
119 passed in 1.21s
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
- exact-revision and exact-Twin-hash BuildPlanDSL generation,
- persistent twin revision history.
- GuidanceDSL/IncidentDSL/EventDSL persistence,
- strict PatchDSL parsing, base-hash and path policy checks,
- verified autonomous patch application,
- automatic byte-for-byte rollback after a failed test.
- canonical Subactor `aql:contract/v1` authorization of OQL plus exact URI Process,
- schema-compatible process envelopes, EQL outcomes and SODL receipts,
- immutable governance kernel and opaque, preaccepted secret references.
- native TestQL startup scenarios, TestQLDSL persistence and failure-to-observation routing.
- SpatialClassDSL, AssumptionDSL, ParameterContractDSL and EvidenceSetDSL contracts,
- system-owned AuthorityProjectionDSL and RepairPlanDSL,
- ProjectIntegrity finding → AQL/OQL exact URI → TestQL/EQL → closure receipt E2E.
- rejected development evidence → system-owned repair URI without weakening acceptance.
- append-only RepairPlanDSL identity across equal findings on different Twin revisions.
- deterministic SourceIndexDSL with execution time outside its semantic hash.
- ClaimDSL and TrustDSL accepted-evidence contracts.
- SSOT Merkle manifest, candidate validation, semantic diff, single-writer promotion,
  exact add/remove operations, immutable evidence URIs, stale-base rejection,
  authority isolation, append-only receipts and federated registry.

## Current HTTP health observation

The already-running local `live-app` was queried on 2026-08-09:

```text
GET http://127.0.0.1:18787/api/health
version=0.0.11, ok=true, runtime_profile=demo
request_transport=inproc, event_store=file, cqrs_es=false
```

This is a liveness and configuration observation, not a rerun of the complete
HTTP workflow or proof that the web request path uses PostgreSQL/NATS.

## Recorded HTTP end-to-end evidence — 0.0.7

The following sequence is retained from the 2026-08-08 run of version 0.0.7.

A local HTTP server was started with:

```text
LLM_BACKEND=demo
```

Verified sequence:

```text
GET  /api/health                 -> 0.0.7
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

## Current Docker integration — 2026-08-10

An isolated Compose project rebuilt the 0.0.11 image and completed
`docker compose run --rm --build integration`. The run verified NATS 2.14.4
request/reply, JetStream event publication and replay, PostgreSQL authoritative
Event Store plus transactional outbox, and the DSL-only LLM/digital-twin flow
through TwinDSL revision 2 and BuildPlanDSL. The temporary containers, network
and volumes were removed after the run.

## Earlier Docker/evolution evidence — 2026-08-08

Docker execution was verified on 2026-08-08. At that time the regular stack and
the guarded live-evolution profile built successfully, and the evolution
profile was healthy on `127.0.0.1:18787` with `EVOLUTION_MODE=observe` and an
empty active incident queue.

The rebuilt `0.0.7` image also passed the installed-package SSOT smoke outside
the source working directory. `onlydsl ssot init`, `status` and the candidate
`--remove` contract were available; the initialized manifest verified to a
stable revision. The TestQL startup container continues to return success for
onlyDSL and the expected failure for the deliberately blocked Digital Twin
geometry candidate.

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
