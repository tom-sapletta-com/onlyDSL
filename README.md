# onlyDSL -> IFURI Runtime Lab 0.3


## AI Cost Tracking

![PyPI](https://img.shields.io/badge/pypi-costs-blue) ![Version](https://img.shields.io/badge/version-0.0.2-blue) ![Python](https://img.shields.io/badge/python-3.9+-blue) ![License](https://img.shields.io/badge/license-Apache--2.0-green)
![AI Cost](https://img.shields.io/badge/AI%20Cost-$0.15-orange) ![Human Time](https://img.shields.io/badge/Human%20Time-2.0h-blue) ![Model](https://img.shields.io/badge/Model-openrouter%2Fqwen%2Fqwen3--coder--next-lightgrey)

- 🤖 **LLM usage:** $0.1532 (1 commits)
- 👤 **Human dev:** ~$200 (2.0h @ $100/h, 30min dedup)

Generated on 2026-08-08 using [openrouter/qwen/qwen3-coder-next](https://openrouter.ai/qwen/qwen3-coder-next)

---



POC łączący wcześniejszy **DSL-only LLM boundary** z docelowym kernelem:

- CQRS,
- Event Sourcing,
- Protobuf bez gRPC jako fundamentu,
- location-independent `ifuri://` capability addressing,
- jawny `CapabilityRegistry` + deterministyczny resolver,
- `InProcessTransport`,
- Core NATS request/reply,
- JetStream durable events/replay,
- PostgreSQL authoritative event store,
- transactional outbox,
- logiczne artifact URI z lokalnym `file://` placement adapterem,
- LLM jako normalna capability wywoływana przez `IfEnvelope`.

## Docelowy przepływ

```text
application/runtime
      │
      ├─ command/query payload ───────────────┐
      │                                       │
      └─ logs/state/tools → ContextDSL        │
                             │                │
                             ▼                ▼
                      protobuf payload   protobuf payload
                             │                │
                             └──────┬─────────┘
                                    ▼
                              IFURI Envelope
                                    │
                                    ▼
                         CapabilityRegistry
                                    │
                             deterministic
                               Resolver
                                    │
                     ┌──────────────┼──────────────┐
                     ▼              ▼              ▼
                   inproc         NATS         future HTTP/MQTT
                                   │
                          ┌────────┴─────────┐
                          ▼                  ▼
                     request/reply       JetStream

write side:
Command → Aggregate → Domain Event → PostgreSQL ES + Outbox (one transaction)
                                      │
                                      ▼ after commit
                                  JetStream
                                      │
                                      ▼
                                  projections
```

## IFURI

Canonical form:

```text
ifuri://<bounded-context>/<entity>/<identity>/<kind>/<operation>
```

Examples:

```text
ifuri://scenario/scenario/9f7/commands/execute
ifuri://scenario/scenario/9f7/queries/status
ifuri://scenario/scenario/9f7/events/executed
ifuri://artifact/document/spec42/artifacts/content
ifuri://llm/reasoner/default/commands/analyze
```

Transport placement is not encoded in the logical URI. The NATS adapter can map the first example to a subject such as:

```text
ifuri.cmd.scenario.scenario.9f7.execute
```

See `docs/IFURI_SPEC.md`.

## Protobuf without gRPC

`contracts/ifuri/v1/envelope.proto` defines the common wire envelope. The POC serializes it directly over NATS; no gRPC package or stub is required.

`contracts/ifuri/v1/dsl.proto` defines `DslDocument`, used by the LLM gateway. Runtime context reaches the model only as `contextdsl`, and the returned reasoning program is `intentdsl`.

## Resolver without hidden magic

Routes live in `manifests/capabilities.yaml`.

Each route declares:

- logical URI pattern,
- Protobuf input/output contract,
- command/query/event semantics,
- idempotency/durability hints,
- logical runtime placement,
- preferred and fallback transports.

`CapabilityRegistry.explain(uri)` returns every candidate, specificity, extracted parameters, transport order and final selection. Equal-best ambiguous matches fail closed.

## CQRS + Event Sourcing

`ifuri_core/cqrs.py` provides the minimal aggregate/repository contract.

Stores:

- `SqliteEventStore` — local/unit-test reference adapter,
- `PostgresEventStore` — authoritative Docker/production-like adapter.

`append()` performs optimistic concurrency checking and writes:

1. event stream row,
2. serialized Protobuf event,
3. outbox row,
4. stream version update,

inside one database transaction.

`OutboxPublisher` publishes only committed rows to JetStream. Delivery is intentionally treated as **at-least-once**; projections should deduplicate by `event_id`.

## NATS / JetStream

The POC contains a small dependency-free Core NATS protocol client in `ifuri_core/transport.py` so the kernel does not depend on a specific NATS language SDK.

Implemented POC surface:

- CONNECT,
- SUB/UNSUB,
- PUB,
- request/reply inbox,
- wildcard capability subscription,
- JetStream stream creation,
- durable publish acknowledgement,
- stream info,
- message retrieval,
- replay.

A production implementation can replace this adapter with the official language client without changing `IfUri`, manifests, envelopes or domain code.

## LLM invariant

Forbidden:

```text
raw log/state/tool result → LLM
```

Required:

```text
raw runtime context
      ↓
ContextCompiler
      ↓
ContextDSL fenced block
      ↓
DslDocument protobuf
      ↓
IfEnvelope
      ↓
ifuri://llm/reasoner/default/commands/analyze
      ↓
LLM Gateway
      ↓
IntentDSL fenced block
```

`server.py` does not import/call `llm_client` directly. The LLM call is isolated in `ifuri_core/llm_gateway.py` and architectural tests enforce this boundary.

## Unit tests

```bash
./run-tests.sh
```

Coverage includes:

- IFURI grammar and forbidden transport location fields,
- deterministic manifest routing,
- ambiguity fail-closed,
- Protobuf round-trip,
- message-kind/URI semantic validation,
- inproc/NATS fallback routing,
- Core NATS wire request/reply against a test broker,
- CQRS/ES optimistic concurrency,
- event + outbox atomic commit,
- post-commit outbox publication,
- artifact logical/physical URI separation,
- DSL-only LLM capability,
- proactive IntentDSL runtime,
- architecture invariants including absence of a gRPC dependency.

## Docker integration

```bash
./docker-test.sh
```

Equivalent manual flow:

```bash
docker compose build
docker compose run --rm integration
```

The Compose integration uses:

- NATS with JetStream,
- PostgreSQL,
- the POC application image.

It executes:

```text
IFURI query → Core NATS request/reply
Domain Event → PostgreSQL ES + outbox → JetStream → replay
ContextDSL → IfEnvelope → LLM capability → IntentDSL
```

See `docs/DOCKER_TESTS.md`.

## Web POC

```bash
python3 server.py
# http://127.0.0.1:8787
```

Useful endpoints:

```text
GET  /api/health
GET  /api/ifuri/capabilities
GET  /api/ifuri/route?uri=ifuri://scenario/scenario/abc/queries/status
POST /api/ifuri/analyze-context
POST /api/ifuri/compile-source
```

## Important files

```text
ifuri_core/uri.py               IFURI parser + subject mapping
ifuri_core/envelope.py          Protobuf envelope codec/validation
ifuri_core/manifest.py          CapabilityRegistry + deterministic resolver
ifuri_core/runtime.py           logical call/emit dispatcher
ifuri_core/transport.py         InProc + NATS Core + JetStream adapter
ifuri_core/event_store.py       SQLite ES/outbox reference
ifuri_core/postgres_store.py    PostgreSQL authoritative ES/outbox
ifuri_core/outbox.py            post-commit JetStream publisher
ifuri_core/cqrs.py              aggregate/repository core
ifuri_core/artifacts.py         logical artifact → physical file placement
ifuri_core/llm_gateway.py       single LLM capability boundary
contracts/ifuri/v1/*.proto      wire contracts
manifests/capabilities.yaml     explicit routing table
docs/IFURI_SPEC.md              URI grammar
docs/ARCHITECTURE_V03.md        architecture decisions
docs/DOCKER_TESTS.md            Docker verification
```


## License

Licensed under Apache-2.0.
