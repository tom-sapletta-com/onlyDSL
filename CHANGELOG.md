# Changelog

## [Unreleased]

## [0.0.2] - 2026-08-08

### Docs
- Update CHANGELOG.md
- Update README.md
- Update TEST_REPORT.md
- Update docs/ARCHITECTURE_V03.md
- Update docs/DOCKER_TESTS.md
- Update docs/IFURI_SPEC.md

### Test
- Update tests/test_architecture_contract.py
- Update tests/test_ifuri_core.py
- Update tests/test_multiruntime.py
- Update tests/test_nats_transport.py
- Update tests/test_outbox.py

### Other
- Update .dockerignore
- Update .env.example
- Update contracts/ifuri/v1/dsl.proto
- Update contracts/ifuri/v1/envelope.proto
- Update docker-test.sh
- Update ifuri_core/__init__.py
- Update ifuri_core/artifacts.py
- Update ifuri_core/cqrs.py
- Update ifuri_core/dsl_document.py
- Update ifuri_core/dsl_pb2.py
- ... and 19 more files


## 0.3.0

- Added IFURI canonical grammar and parser.
- Added explicit capability manifest and deterministic/fail-closed resolver.
- Added Protobuf `Envelope` and typed `DslDocument` contracts without gRPC.
- Added InProcess and Core NATS transports.
- Added dependency-free POC NATS wire client and JetStream API adapter.
- Added CQRS aggregate repository primitive.
- Added SQLite reference Event Store and PostgreSQL authoritative Event Store.
- Added transactional outbox and post-commit JetStream publisher.
- Added logical artifact URI → `file://` placement adapter.
- Routed LLM analysis and source semantic compilation through IFURI capabilities.
- Kept DSL-only input/output boundary from 0.2.
- Added Docker Compose NATS + JetStream + PostgreSQL integration scenario.
- Expanded architecture/runtime tests.
