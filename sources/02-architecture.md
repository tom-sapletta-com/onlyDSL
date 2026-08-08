# Runtime architecture

Use location-independent IFURI capability addressing. Domain code should address logical capabilities rather than host and port pairs.

- Protobuf is the shared wire contract and is not tied to gRPC.
- CQRS commands and queries are routed through capability manifests.
- PostgreSQL remains the authoritative event store.
- Transactional outbox publishes committed domain events to NATS JetStream.
- Core NATS is appropriate for request/reply paths that do not require durable storage.
- LLM access is exposed as an IFURI capability through one gateway.

## LLM boundary

Raw logs, exceptions, tool results, source files, and runtime state must not be concatenated directly into LLM prompts. The application first creates typed DSL documents. LLM output is parsed and rejected if it contains prose outside the expected DSL fence.
