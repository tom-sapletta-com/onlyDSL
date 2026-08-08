# Test report — IFURI Runtime Lab 0.3

Date: 2026-08-08

## Executed successfully in this environment

### Python/unit architecture suite

Command:

```bash
python3 -m unittest discover -s tests -v
```

Result:

```text
32 tests
OK
```

Covered areas:

- IFURI parse/canonicalization/forbidden placement fields,
- URI → NATS subject mapping,
- explicit capability manifest resolution,
- resolver inspection and ambiguity fail-closed,
- Protobuf Envelope serialization/unpack,
- message kind vs IFURI kind validation,
- inproc fallback when preferred NATS transport is unavailable,
- Core NATS wire request/reply using a protocol-level test broker,
- SQLite reference ES + optimistic concurrency,
- atomic event/outbox commit,
- outbox publication after commit,
- artifact IFURI → safe `file://` placement,
- DSL-native ContextDSL boundary,
- LLM as `ifuri://llm/...` capability,
- proactive IntentDSL runtime,
- no gRPC dependency in requirements/Compose,
- no direct domain/server import of `llm_client`,
- multi-runtime IFURI parity across Python, Node/JavaScript and PHP.

### Python syntax/compile

```text
server.py: OK
contextdsl.py: OK
intentdsl.py: OK
boundary.py: OK
llm_client.py: OK
ifuri_core/*.py: OK
scripts/docker_integration.py: OK
```

### HTTP end-to-end POC

Executed against a locally started `server.py`:

```text
GET /api/health                         200
GET /api/ifuri/route                    200
POST /api/ifuri/analyze-context         200
```

Observed route/runtime result:

```text
selected capability: scenario.status
LLM transport: inproc
IntentDSL valid: true
runtime action: refresh_token
runtime event: auth_error
retry_count: 1
```

### Compose static contract

`docker-compose.yml` parses as YAML and contains:

```text
app
integration
nats
postgres
```

Architecture tests verify that no gRPC dependency or transport URL is used as logical capability identity.

## Docker execution status in this ChatGPT runtime

Actual `docker compose build/run` could not be executed because this execution environment has no Docker CLI/daemon/socket:

```text
docker: command not found
/var/run/docker.sock: unavailable
```

The package nevertheless includes the complete Docker integration test:

```bash
./docker-test.sh
```

which runs:

```text
NATS Core request/reply
Postgres authoritative Event Store
Postgres transactional outbox
JetStream durable publish
JetStream replay
Protobuf decode
IFURI routing
DSL-only LLM capability
```

Docker runtime verification is therefore **prepared but not falsely reported as executed** in this environment.
