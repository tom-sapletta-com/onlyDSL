# onlyDSL — IFURI Digital Twin Lab


## AI Cost Tracking

![PyPI](https://img.shields.io/badge/pypi-costs-blue) ![Version](https://img.shields.io/badge/version-0.0.12-blue) ![Python](https://img.shields.io/badge/python-3.9+-blue) ![License](https://img.shields.io/badge/license-Apache--2.0-green)
![AI Cost](https://img.shields.io/badge/AI%20Cost-$3.43-orange) ![Human Time](https://img.shields.io/badge/Human%20Time-9.9h-blue) ![Model](https://img.shields.io/badge/Model-openrouter%2Fqwen%2Fqwen3--coder--next-lightgrey)

- 🤖 **LLM usage:** $3.4348 (18 commits)
- 👤 **Human dev:** ~$991 (9.9h @ $100/h, 30min dedup)

Generated on 2026-08-09 using [openrouter/qwen/qwen3-coder-next](https://openrouter.ai/qwen/qwen3-coder-next)

---

A reference implementation for building software from user intent and external Markdown sources while keeping the LLM behind a strict DSL-only boundary.

Current package version: **0.0.10**. Documents named `ARCHITECTURE_V03` and
`ARCHITECTURE_V04` are historical design records, not the current package
version or a claim that every described adapter is active in the HTTP server.

[Quick start](#quick-start) · [Project map](#project-map) ·
[Documentation](#documentation) · [API](#api) · [Tests](#tests)

## Project map

| Area | Important files |
| --- | --- |
| Documentation | [documentation menu](docs/README.md), [test evidence](TEST_REPORT.md), [changelog](CHANGELOG.md), [open work](TODO.md) |
| Contracts | [onlydsl-contracts](packages/onlydsl-contracts/README.md), [schemas](packages/onlydsl-contracts/src/onlydsl_contracts/schemas), [IFURI specification](docs/IFURI_SPEC.md) |
| Runtime | [HTTP service](server.py), [capability manifest](manifests/capabilities.yaml), [application contract](app.doql.less) |
| Packages | [onlydsl-core](packages/onlydsl-core/README.md), [onlydsl-ssot](packages/onlydsl-ssot/README.md), [workspace configuration](pyproject.toml), [locked dependencies](uv.lock) |
| Operations | [Compose stack](docker-compose.yml), [environment template](.env.example), [autonomous evolution guide](docs/AUTONOMOUS_EVOLUTION.md) |
| Governance | [Goal release policy](goal.yaml), [Planfile](planfile.yaml), [accepted-state layout](SSOT/README.md) |
| Verification | [test suite](tests), [TestQL scenarios](testql), [Docker tests](docs/DOCKER_TESTS.md) |
| Generated analysis | [project analysis index](project/README.md) — generated evidence, not the implementation source of truth |

`START.md`, when present, is an ignored local hand-off containing the observed
state of the currently running services. It is intentionally not linked as
repository documentation because it is host-specific and is not published.

## Documentation

The complete, categorized menu is maintained in [docs/README.md](docs/README.md).

- Architecture and boundaries: [LLM boundary](docs/LLM_BOUNDARY_ARCHITECTURE.md),
  [IFURI](docs/IFURI_SPEC.md), [Project Integrity Closure v2](docs/PROJECT_INTEGRITY_CLOSURE_V2.md),
  [SSOT](docs/SSOT_ACCEPTED_TRUTH.md).
- Operation and integration: [autonomous evolution](docs/AUTONOMOUS_EVOLUTION.md),
  [Docker tests](docs/DOCKER_TESTS.md), [OpenRouter test](docs/OPENROUTER_TEST.md),
  [OQL OS integration](docs/OQLOS_INTEGRATION.md).
- Historical evidence: [architecture v0.3](docs/ARCHITECTURE_V03.md),
  [architecture v0.4](docs/ARCHITECTURE_V04.md),
  [Docker/OpenRouter audit from 2026-08-08](docs/AUDYT_DOCKER_OPENROUTER_2026-08-08.md),
  [documentation intent audit from 2026-08-09](docs/DOCUMENTATION_INTENT_AUDIT_2026-08-09.md).

For current behavior, use code, schemas and executable tests first. The test
report records a concrete run; dated audits and historical architecture files
remain useful evidence but do not override the current implementation.

## Package workspace

The first reusable package boundary is now explicit:

```text
packages/onlydsl-contracts  pure DSL, IFURI, SSOT models and schemas
packages/onlydsl-core       capability routing, wire envelope, CQRS and ports
packages/onlydsl-ssot       candidate, manifest, validation port and atomic promotion
onlyDSL                     governance, runtime, adapters and service composition
```

`onlydsl-contracts` is independently buildable and has no runtime, transport,
LLM or authority dependencies. Existing `onlydsl.dsl.*`, `ifuri_core.uri` and
`onlydsl.ssot.model` imports remain compatibility facades, while new code may
depend directly on `onlydsl_contracts`. A uv workspace keeps all extracted
distributions on the same version during this extraction phase.

`onlydsl-core` depends only on contracts and Protobuf. NATS, PostgreSQL, SQLite,
filesystem artifacts, YAML file loading and the LLM gateway remain adapters in
the runtime distribution.

`onlydsl-ssot` depends only on contracts. It owns the domain-neutral accepted
state transaction and accepts a `TreeValidator` supplied by the application.
Digital Twin, source ingestion and Project Integrity parsers therefore remain
outside the storage package and cannot leak into reusable SSOT consumers.

```bash
uv sync
uv run pytest -q
uv build --package onlydsl-contracts
uv build --package onlydsl-core
uv build --package onlydsl-ssot
```

## Project Integrity Closure v2

onlyDSL now acts as a control plane above the external `twin-dsl` engine. It consumes live
`ProjectIntegrityDSL`, verifies its exact append-only iteration version, derives a
`RepairPlanDSL` from a system-owned process registry, projects AQL authority and requires
TestQL/EQL closure evidence. It does not implement CAD or execute model-supplied commands.

The six new contracts are `SpatialClassDSL`, `AssumptionDSL`, `ParameterContractDSL`,
`EvidenceSetDSL`, `AuthorityProjectionDSL` and `RepairPlanDSL`. See
[Project Integrity Closure v2](docs/PROJECT_INTEGRITY_CLOSURE_V2.md).

## SSOT — accepted project state

Projects may now materialize the existing DSL contracts as a transactional
`SSOT/` projection. In this context SSOT means **Single Source of Accepted
Truth**: primary code, Git, docs, CAD and telemetry remain evidence sources,
while `SSOT/current` records the interpretation accepted by ProjectIntegrity,
AQL, TestQL and EQL.

```bash
onlydsl ssot init . --project-id my-project
onlydsl ssot status .
onlydsl ssot reconcile . --section development/todo2code.dsl=/tmp/todo2code.dsl
onlydsl ssot candidate validate <candidate-id> .
onlydsl ssot promote <candidate-id> . \
  --authority-hash sha256:... \
  --testql urn:subactor:testql:sha256:... \
  --eql urn:subactor:eql:sha256:...
```

Authority, grants, locks and process packs stay under `.onlydsl/`, outside the
accepted truth tree and outside the LLM write boundary. See
[SSOT — Single Source of Accepted Truth](docs/SSOT_ACCEPTED_TRUTH.md).

## Core architecture

```text
user sentences
  -> runtime SourceDSL
  -> IFURI capability
  -> LLM Gateway
  -> DigitalTwinDSL revision 1

sources/*.md
  -> deterministic Markdown compiler
  -> SourceIndexDSL + SHA-256 provenance
  -> IFURI capability
  -> LLM Gateway
  -> validated DigitalTwinDSL revision N+1
  -> BuildPlanDSL
  -> future code-builder capability
```

The repository implements two distinct execution paths. The web service uses
the in-process adapter and file-backed twin state; `GET /api/health` reports
`request_transport=inproc`, `event_store=file` and `cqrs_es=false`. The separate
Compose `integration` service verifies:

- logical `ifuri://...` capability addresses instead of host:port identities,
- Protobuf `IfEnvelope` as a transport-neutral wire contract,
- CQRS + Event Sourcing,
- PostgreSQL as the authoritative event store,
- transactional outbox,
- NATS Core for request/reply and JetStream for durable delivery/replay,
- no gRPC foundation dependency,
- Python/Node/PHP IFURI parity tests.

Thus PostgreSQL is authoritative inside the integration contract, not inside
the current HTTP persistence path. Wiring that path to NATS/PostgreSQL remains
a future runtime change and is not presented as an implemented feature.

## Why `OPENROUTER_API_KEY` exists now

The v0.3 design used a generic `LLM_API_KEY`; the v0.4 design record introduced
a dedicated OpenRouter provider configuration and Docker smoke profile. The
current package keeps that provider boundary.

Create `.env`:

```bash
cp .env.example .env
```

Then edit:

```dotenv
LLM_BACKEND=openrouter
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=~openai/gpt-latest
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_HTTP_REFERER=http://localhost:8787
OPENROUTER_APP_TITLE=IFURI Digital Twin Lab
```

Do not commit the real key. `.env` is excluded by `.dockerignore`.

OpenRouter's official quickstart uses `https://openrouter.ai/api/v1/chat/completions`, Bearer authentication, and currently documents `~openai/gpt-latest` as a latest-model alias. `HTTP-Referer` and `X-OpenRouter-Title` are optional attribution headers.

Official references:

- https://openrouter.ai/docs/quickstart
- https://openrouter.ai/docs/api_reference/authentication

## Quick start

The deterministic `demo` backend exercises the complete architecture without a network LLM:

```bash
uv sync
uv run pytest -q
uv run onlydsl serve
```

Open:

```text
http://localhost:8787
```

Workflow in the UI:

1. Enter a few sentences describing the application you want.
2. Click **Bootstrap twin**.
3. Inspect generated TwinDSL and the rendered Mermaid SVG; the highlighted Mermaid source remains available in a collapsible detail view.
4. Put Markdown files under `sources/`.
5. Click **Scan sources/**.
6. Click **Update twin**.
7. Verify that the revision increments while `INTENT_FINGERPRINT` stays unchanged.
8. Click **Generate plan** to produce BuildPlanDSL.

## Real OpenRouter test

With a valid key in `.env`:

```bash
docker compose up -d nats postgres app
```

Then use the web UI, or run the isolated real-LLM smoke test:

```bash
docker compose --profile llm run --rm openrouter-smoke
```

The smoke test performs three actual LLM stages through the same IFURI gateway used by the application:

```text
SourceDSL -> ifuri://llm/twin/default/commands/bootstrap -> TwinDSL r1
TwinDSL + SourceIndexDSL -> ifuri://llm/twin/default/commands/update -> TwinDSL r2
TwinDSL r2 -> ifuri://llm/builder/default/commands/plan -> BuildPlanDSL
```

The smoke script has a preflight key guard. An unconfigured run reports
`OPENROUTER_SMOKE_SKIPPED: OPENROUTER_API_KEY is not set` and sends no paid
request.

## `sources/` design

Markdown is not concatenated directly into a prompt. `source_ingest.py` creates a deterministic representation:

```sourceindexdsl
SOURCE_INDEX markdown_sources
DOC source_1_architecture
  PATH "sources/architecture.md"
  SHA256 sha256:...
  HEADING 1 "Architecture"
  PARAGRAPH "..."
  BULLET "..."
  CODE python HASH sha256:... CONTENT "..."
END
END_SOURCE_INDEX
```

This means the LLM receives a typed source document with provenance rather than raw Markdown formatting.
`GENERATED_AT` is intentionally excluded from the semantic SourceIndexDSL. The
scan timestamp lives in a separate envelope, so equivalent inputs produce the
same DSL bytes and `contentHash`.

Limits can be configured:

```dotenv
SOURCE_MAX_FILES=64
SOURCE_MAX_CHARS=120000
```

## DigitalTwinDSL

The twin is an application model rather than generated source code. It records:

- immutable user intent fingerprint,
- current goals,
- nodes/services/actors/models,
- logical IFURI capabilities,
- graph edges,
- invariants,
- allowed/required/forbidden evolution,
- source references and hashes,
- open questions.

Example shape:

```twindsl
TWIN application
VERSION 1
REVISION 2
INTENT_FINGERPRINT sha256:...
INTENT_SUMMARY "..."
GOAL "..."

NODE digital_twin KIND model
  RESPONSIBILITY "Maintains the current source-backed application model."
  EVIDENCE user_intent
  EVIDENCE source_1_architecture
END

CAPABILITY update_from_sources
  URI ifuri://llm/twin/default/commands/update
  OWNER digital_twin
  INPUT ifuri.v1.DslDocument
  OUTPUT ifuri.v1.DslDocument
  RESPONSIBILITY "Refine the twin without replacing original intent."
END

INVARIANT preserve_user_intent
  ASSERT "Every revision keeps the original INTENT_FINGERPRINT."
  EVIDENCE user_intent
END

EVOLUTION
  ALLOW "Refine implementation details supported by sources."
  REQUIRE "Preserve user intent."
  FORBID "Invent unsupported product requirements."
END

SOURCE user_intent HASH sha256:...
SOURCE source_1_architecture HASH sha256:... PATH "sources/architecture.md"
END_TWIN
```

## Intent versus evidence

The design deliberately separates three things:

```text
user intent       = what the product is supposed to achieve
source evidence   = facts/constraints that may refine how it should work
implementation    = code produced from the validated current twin
```

A source cannot replace the user's original intent. The runtime enforces this by keeping `INTENT_FINGERPRINT` immutable between revisions and by refusing a TwinDSL update that removes existing invariants or invents unknown source identifiers.

Unsupported information should remain an `OPEN_QUESTION` instead of silently becoming a requirement.

## Fail-closed LLM repair

A provider can still produce invalid output. The current runtime therefore uses a repair loop:

```text
LLM output
 -> BoundaryGate
 -> TwinDSL parser/semantic validator
 -> reject if invalid
 -> original trusted DSL bundle + ValidationDSL errors
 -> retry
```

The rejected raw model response is never copied into the next prompt.

Configure retries with:

```dotenv
LLM_REPAIR_ATTEMPTS=2
```

## API

The route table below mirrors the handlers in [server.py](server.py). The API
reports only whether an LLM key is present; it never returns the key value.

| Method | Routes | Purpose |
| --- | --- | --- |
| `GET` | `/api/health`, `/api/llm/status` | Runtime and provider status |
| `GET` | `/api/ifuri/route`, `/api/ifuri/capabilities` | Explain IFURI resolution and list capabilities |
| `POST` | `/api/compile-context`, `/api/analyze-context`, `/api/ifuri/analyze-context` | Compile ContextDSL and run intent analysis |
| `POST` | `/api/convert`, `/api/ifuri/compile-source` | Compile source text to SourceDSL |
| `GET` | `/api/twin`, `/api/twin/sources` | Read the accepted twin and deterministic source index |
| `POST` | `/api/twin/bootstrap`, `/api/twin/update`, `/api/twin/plan` | Create or refine TwinDSL and derive BuildPlanDSL |
| `GET` | `/api/integrity/current` | Read live ProjectIntegrityDSL and the closure-v2 contracts |
| `POST` | `/api/integrity/repair-plan` | Derive a system-owned RepairPlanDSL from live integrity findings |
| `GET` | `/api/evolution/status`, `/api/evolution/diagnostics` | Inspect the guarded evolution loop |
| `POST` | `/api/evolution/guidance`, `/api/evolution/report` | Record GuidanceDSL or IncidentDSL |
| `POST` | `/api/validate`, `/api/run`, `/api/codegen` | Validate Markdown DSL, run IntentDSL, or generate code artifacts |

Example bootstrap request:

```http
POST /api/twin/bootstrap
Content-Type: application/json

{
  "intent": "Build an application ...",
  "reset": true
}
```

## Persistent state

The current twin is stored under:

```text
state/digital_twin.md
```

Each accepted revision is also written to:

```text
state/history/rev-XXXX-<timestamp>.md
```

Docker mounts `./state:/app/state` so accepted revisions survive container restarts.

## Docker integration suite

The `integration` service exercises:

- real NATS request/reply,
- JetStream stream/replay,
- PostgreSQL authoritative Event Store,
- transactional outbox,
- Protobuf envelopes,
- DSL-only ContextDSL → IntentDSL path,
- DigitalTwinDSL bootstrap,
- `sources/` update to revision 2,
- BuildPlanDSL generation.

Run:

```bash
docker compose build
docker compose run --rm integration
```

## Guarded autonomous evolution

The optional `evolution` profile records runtime guidance/incidents as DSL and uses the Subactor operational layering model: the LLM proposes only `PatchDSL`; a system-owned `aql:contract/v1` authorizes OQL plus exact URI Process routes; DOQL/EQL remain read-only; a hash-bound Process Envelope and independent receipt precede success. A one-shot TestQL service verifies onlyDSL and the live Digital Twin after startup, persists TestQLDSL, and routes failures into the appropriate next evolution cycle. Dependencies, Docker, runtime and the evolution implementation are governable through explicit AQL grants. Secret values never reach the model, and model-supplied commands are never executed.

Start in recording-only mode:

```bash
LOCAL_UID="$(id -u)" LOCAL_GID="$(id -g)" EVOLUTION_MODE=observe \
docker compose --profile evolution up -d --build live-app evolution-agent
```

After reviewing the policy, enable guarded application with `EVOLUTION_MODE=apply`. See [docs/AUTONOMOUS_EVOLUTION.md](docs/AUTONOMOUS_EVOLUTION.md) for the operating procedure, APIs, state layout and rollback rules.

## Tests

Local suite:

```bash
uv run pytest -q
```

The verified 2026-08-09 run contains 114 passing tests covering packaging and architecture invariants,
IFURI, Protobuf, Event Sourcing/outbox, NATS wire protocol, multi-runtime URI parity,
ContextDSL, IntentDSL, TwinDSL, source ingestion, OpenRouter, TestQL, the embedded dashboard,
deterministic diagnostics, AQL/URI authorization, process envelopes, guarded rollback and the
complete ProjectIntegrity → RepairPlan → TestQL/EQL closure cycle.

The browser detects and highlights JSON, JSONL, Mermaid and the project DSL family. Runtime values are HTML-escaped before token markup is added. Mermaid is rendered with its strict security profile; if the CDN renderer is unavailable, the highlighted source and an explicit error remain visible.

See [TEST_REPORT.md](TEST_REPORT.md) for the exact execution status and the
distinction between the current local run and retained historical Docker/HTTP
evidence.


## License

Licensed under Apache-2.0.
