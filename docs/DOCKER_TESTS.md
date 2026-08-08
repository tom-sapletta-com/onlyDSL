# Docker integration test

The Compose stack contains:

- `nats:2.14-alpine` with JetStream enabled,
- `postgres:17-alpine`,
- the Python POC image,
- an `integration` service.

Run:

```bash
docker compose build
docker compose run --rm integration
```

The integration script verifies in one run:

1. a Core NATS request/reply to a wildcard capability subscription,
2. logical IFURI routing with no host:port in domain code,
3. Protobuf Envelope round-trip,
4. Postgres event stream versioning,
5. atomic Postgres event + outbox creation,
6. outbox publication to JetStream after commit,
7. JetStream replay and Protobuf event decoding,
8. LLM capability invocation through `ifuri://llm/...`,
9. ContextDSL-only input and IntentDSL-only output.

For a clean stack:

```bash
docker compose down -v
docker compose run --rm integration
```

Unit tests inside the same application image:

```bash
docker compose run --rm app python3 -m unittest discover -s tests -v
```
