# IFURI Digital Twin Lab 0.4


## AI Cost Tracking

![PyPI](https://img.shields.io/badge/pypi-costs-blue) ![Version](https://img.shields.io/badge/version-0.0.4-blue) ![Python](https://img.shields.io/badge/python-3.9+-blue) ![License](https://img.shields.io/badge/license-Apache--2.0-green)
![AI Cost](https://img.shields.io/badge/AI%20Cost-$0.45-orange) ![Human Time](https://img.shields.io/badge/Human%20Time-2.4h-blue) ![Model](https://img.shields.io/badge/Model-openrouter%2Fqwen%2Fqwen3--coder--next-lightgrey)

- 🤖 **LLM usage:** $0.4483 (3 commits)
- 👤 **Human dev:** ~$243 (2.4h @ $100/h, 30min dedup)

Generated on 2026-08-08 using [openrouter/qwen/qwen3-coder-next](https://openrouter.ai/qwen/qwen3-coder-next)

---

A reference implementation for building software from user intent and external Markdown sources while keeping the LLM behind a strict DSL-only boundary.

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

The wider runtime retains the previous architecture:

- logical `ifuri://...` capability addresses instead of host:port identities,
- Protobuf `IfEnvelope` as a transport-neutral wire contract,
- CQRS + Event Sourcing,
- PostgreSQL as the authoritative event store,
- transactional outbox,
- NATS Core for request/reply and JetStream for durable delivery/replay,
- no gRPC foundation dependency,
- Python/Node/PHP IFURI parity tests.

## Why `OPENROUTER_API_KEY` exists now

Version 0.3 had a generic `LLM_API_KEY` but no first-class OpenRouter provider. Version 0.4 adds a dedicated provider configuration and a Docker smoke profile.

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

## Quick test without spending API credits

The deterministic `demo` backend exercises the complete architecture without a network LLM:

```bash
python3 -m unittest discover -s tests -v
python3 server.py
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

If `OPENROUTER_API_KEY` is missing, the smoke script exits without making a paid request.

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

A provider can still produce invalid output. Version 0.4 therefore uses a repair loop:

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

### Provider status

```http
GET /api/llm/status
```

The API reports only whether a key is present; it never returns the key value.

### Bootstrap the twin

```http
POST /api/twin/bootstrap
Content-Type: application/json

{
  "intent": "Build an application ...",
  "reset": true
}
```

### Scan sources

```http
GET /api/twin/sources
```

### Update the twin

```http
POST /api/twin/update
Content-Type: application/json

{}
```

### Build plan

```http
POST /api/twin/plan
Content-Type: application/json

{}
```

### Current twin

```http
GET /api/twin
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
python3 -m unittest discover -s tests -v
```

Version 0.4 currently contains 62 tests covering packaging and architecture invariants, IFURI, Protobuf, Event Sourcing/outbox, NATS wire protocol, multi-runtime URI parity, ContextDSL, IntentDSL, DigitalTwinDSL, source ingestion, OpenRouter configuration, TestQL startup feedback, the embedded DSL dashboard, deterministic error-code diagnostics, the fail-closed response repair loop, AQL/URI authorization, process envelopes and guarded autonomous patch/defer/rollback behavior.

The browser detects and highlights JSON, JSONL, Mermaid and the project DSL family. Runtime values are HTML-escaped before token markup is added. Mermaid is rendered with its strict security profile; if the CDN renderer is unavailable, the highlighted source and an explicit error remain visible.

See `TEST_REPORT.md` for the exact execution status of the delivered package.


## License

Licensed under Apache-2.0.
