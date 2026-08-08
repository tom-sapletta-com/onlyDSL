# Changelog

## [Unreleased]

## [0.0.3] - 2026-08-08

### Docs
- Update CHANGELOG.md
- Update README.md
- Update TEST_REPORT.md
- Update docs/ARCHITECTURE_V04.md
- Update docs/OPENROUTER_TEST.md
- Update sources/01-product-intent.md
- Update sources/02-architecture.md

### Test
- Update tests/test_digital_twin.py
- Update tests/test_openrouter.py

### Other
- Update .dockerignore
- Update .env.example
- Update boundary.py
- Update digital_twin.py
- Update ifuri_core/dsl_document.py
- Update ifuri_core/llm_gateway.py
- Update llm_client.py
- Update manifests/capabilities.yaml
- Update server.py
- Update source_ingest.py
- ... and 3 more files


## 0.4.0 — 2026-08-08

- Added first-class OpenRouter provider configuration with `OPENROUTER_API_KEY`.
- Added OpenRouter endpoint/model/attribution settings and provider status API.
- Added IFURI capabilities for DigitalTwinDSL bootstrap, source-driven update and BuildPlanDSL generation.
- Added deterministic `sources/*.md -> SourceIndexDSL` compiler with SHA-256 provenance.
- Added immutable `INTENT_FINGERPRINT` and revision validation.
- Added TwinDSL source evidence, invariants, evolution rules and Mermaid graph output.
- Added persistent twin revision store under `state/`.
- Added fail-closed LLM repair loop using `ValidationDSL`; rejected raw output is not re-fed to the model.
- Added `openrouter-smoke` Docker profile for a real provider test.
- Extended Docker integration scenario with DigitalTwinDSL lifecycle.
- Test suite increased to 44 tests.

## 0.3.0

- Added IFURI kernel, capability manifests, Protobuf envelope, CQRS/ES, transactional outbox and NATS/JetStream adapters.
- Added DSL-only LLM capability boundary and multi-runtime URI parity tests.
