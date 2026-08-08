# IFURI Runtime Lab 0.3 architecture

## Invariants

1. **IFURI is identity, not placement.** Domain code never selects host:port.
2. **Protobuf is the wire contract, not gRPC.** There is no gRPC dependency in the kernel.
3. **Capability manifests are explicit.** Resolver behavior is inspectable and ambiguity fails closed.
4. **Postgres is the authoritative event store.** Event + outbox record are committed atomically.
5. **JetStream is durable transport/replay, not the authoritative ES in this phase.**
6. **Core NATS is request/reply transport for immediate command/query calls.**
7. **LLM is a normal capability.** Operational context reaches it only as a Protobuf `DslDocument` containing validated fenced DSL.
8. **Raw context never crosses the LLM boundary.** Legacy text logs are reduced by the application-side ContextDSL compiler before model access.

## Layers

```text
Domain / CQRS
    │
    │  logical IFURI + typed protobuf payload
    ▼
IfuriRuntime
    │
    ├─ CapabilityRegistry / deterministic Resolver
    │
    └─ transport policy from manifest
         │
         ├─ InProcessTransport
         ├─ NatsTransport (Core request/reply)
         └─ JetStream publish/replay for durable events

Event-sourced write side
    │
    ▼
PostgresEventStore
    ├─ event stream
    └─ transactional outbox
          │ commit completed
          ▼
     OutboxPublisher
          ▼
       JetStream
          ▼
   projections / consumers
```

## Protobuf Envelope

`contracts/ifuri/v1/envelope.proto` keeps the required core small:

- `envelope_version`,
- `id`,
- `target_uri`, `source_uri`,
- `kind`,
- typed `google.protobuf.Any payload`,
- `created_at`.

Correlation, causation and aggregate metadata are present but empty unless used by that message.

A second typed contract, `DslDocument`, carries `contextdsl`, `sourcedsl` and `intentdsl` without allowing arbitrary natural-language prompt construction in domain code.

## CQRS

Commands and queries share transport infrastructure but are semantically separate in both IFURI and the manifest:

```text
.../commands/... -> MessageKind.COMMAND
.../queries/...  -> MessageKind.QUERY
.../events/...   -> MessageKind.EVENT
```

`IfuriRuntime.call()` refuses event capabilities and `emit()` refuses non-event capabilities.

## Event sourcing / outbox

`PostgresEventStore.append()` locks the stream version, performs optimistic concurrency checking, writes every event and the corresponding outbox item in one transaction, then updates the stream version.

The broker publication happens only after commit. Consumers must remain idempotent by `event_id` because an outbox publisher can crash after a broker acknowledgement but before marking the local row published. This is intentionally **at-least-once**, not a false exactly-once claim.

## Multi-runtime

A consumer calls:

```text
ifuri://hardware/diagnostics/default/commands/run
```

The manifest can move placement from `inproc` to `nats` without changing the consumer or Protobuf contract. A Python handler can therefore be replaced by Node/Rust/PHP/another device as long as the same IFURI and message contract are preserved.

## Artifact placement

Logical identity:

```text
ifuri://artifact/document/spec42/artifacts/content
```

A storage adapter may resolve that to `file://...` locally or later `s3://...`; the physical URI is placement metadata and does not replace IFURI in domain messages.
