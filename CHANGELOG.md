# Changelog

## 2026-08-08 — governed diagnostics

- Added deterministic error-code classification and persisted DiagnosticDSL solutions.
- Split repair outcomes into `patch`, `defer`, and `manual` so transient failures and authority denials do not invoke an unsafe LLM patch.
- Added `/api/evolution/diagnostics` and a syntax-highlighted diagnostics view in the browser.
- Protected the diagnostic catalog as part of the non-evolvable governance kernel.

## Unreleased

- Added TestQL 1.2.66 startup verification for onlyDSL and the live Digital Twin, with hash-bound TestQLDSL artifacts and repair feedback routing.
- Exposed Biofoundry iteration events and current DSL artifacts through `/api/events`, `/api/dsl`, and the port-7444 dashboard.
- Made the development AQL contract permissive by default for all project OQL operations and system-owned workspace/process/health/vault URI routes.
- Aligned live evolution governance with Subactor's Intent/AQL/DOQL/OQL/URI Process/EQL/Process Envelope/SODL layering.
- Added a canonical `aql:contract/v1`, schema-valid process pack, hash-bound envelopes and independent receipts.
- Made dependencies, Docker, runtime and evolution code governable through explicit AQL grants while keeping authority sources and audit history protected.
- Prohibited model-generated commands, URI selection, self-grants and secret disclosure; added opaque secret-rotation authorization pending a vault connector.

## [Unreleased]

### Added

- Guarded autonomous evolution profile with live supervisor and OpenRouter repair agent.
- GuidanceDSL, IncidentDSL, EventDSL and strict PatchDSL persistence.
- IFURI repair proposal capability and DSL-only code context boundary.
- Base-hash/path/size policy, fixed test gate, live health verification and automatic rollback.
- Evolution status, guidance and bug-report APIs plus web controls.

### Changed

- Docker ports are configurable and bound to localhost by default.
- Docker build context excludes local virtual environments and runtime state.
- Integration service receives the required Python module path.

### Fixed

- Controlled supervisor shutdown no longer creates a false crash incident.
- PatchDSL contract now explicitly requires the `patchdsl` fence and accepts the provider's safe block alias.

## [0.0.8] - 2026-08-08

### Docs
- Update README.md
- Update SSOT/README.md
- Update TEST_REPORT.md
- Update docs/AUDYT_DOCKER_OPENROUTER_2026-08-08.md
- Update docs/SSOT_ACCEPTED_TRUTH.md
- Update project/README.md
- Update project/context.md

### Test
- Update testql/digital-twin-startup.testql.toon.yaml
- Update tests/test_architecture_contract.py
- Update tests/test_digital_twin.py
- Update tests/test_ssot.py

### Other
- Update .onlydsl/.gitignore
- Update SSOT/.gitignore
- Update SSOT/current/project.projectdsl
- Update SSOT/manifest.dsl
- Update SSOT/revisions/78d2de9b906d6466c0d72473f5b23285b30093eb2708317e663883c362ae460f.manifest.dsl
- Update onlydsl/cli.py
- Update onlydsl/dsl/claim.py
- Update onlydsl/dsl/trust.py
- Update onlydsl/ssot/__init__.py
- Update onlydsl/ssot/candidate.py
- ... and 27 more files

## [0.0.7] - 2026-08-08

### Docs
- Update README.md
- Update TEST_REPORT.md
- Update docs/AUDYT_DOCKER_OPENROUTER_2026-08-08.md
- Update docs/PROJECT_INTEGRITY_CLOSURE_V2.md

### Test
- Update tests/test_evolution.py
- Update tests/test_project_integrity_closure.py

### Other
- Update config/process-packs/project-integrity-closure/registry.v2.json
- Update diagnostics.py
- Update onlydsl/runtime/repair_controller.py

## [0.0.6] - 2026-08-08

### Docs
- Update README.md
- Update TEST_REPORT.md
- Update docs/AUDYT_DOCKER_OPENROUTER_2026-08-08.md
- Update docs/PROJECT_INTEGRITY_CLOSURE_V2.md

### Test
- Update tests/test_evolution.py
- Update tests/test_openrouter.py
- Update tests/test_project_integrity_closure.py

### Other
- Update config/process-packs/project-integrity-closure/registry.v2.json
- Update diagnostics.py
- Update digital_twin.py
- Update llm_client.py
- Update onlydsl/dsl/assumption.py
- Update onlydsl/dsl/repair_plan.py
- Update onlydsl/dsl/spatial_class.py
- Update onlydsl/runtime/repair_controller.py
- Update server.py
- Update static/index.html

## [0.0.5] - 2026-08-08

### Docs
- Update README.md
- Update TEST_REPORT.md
- Update docs/AUDYT_DOCKER_OPENROUTER_2026-08-08.md
- Update docs/PROJECT_INTEGRITY_CLOSURE_V2.md
- Update project/README.md
- Update project/context.md
- Update state/digital_twin.md

### Test
- Update tests/test_architecture_contract.py
- Update tests/test_evolution.py
- Update tests/test_project_integrity_closure.py

### Other
- Update boundary.py
- Update config/contracts/evolution-agent.contract.aql
- Update config/process-packs/live-evolution/operations.v1.oql.json
- Update config/process-packs/project-integrity-closure/registry.v2.json
- Update digital_twin.py
- Update evolution.py
- Update ifuri_core/llm_gateway.py
- Update llm_client.py
- Update onlydsl/__init__.py
- Update onlydsl/dsl/__init__.py
- ... and 30 more files

## [0.0.4] - 2026-08-08

### Docs
- Update CHANGELOG.md
- Update README.md
- Update TEST_REPORT.md
- Update docs/AUDYT_DOCKER_OPENROUTER_2026-08-08.md
- Update docs/AUTONOMOUS_EVOLUTION.md
- Update state/digital_twin.md
- Update state/history/rev-0001-20260808T133208Z.md
- Update state/history/rev-0002-20260808T133217Z.md
- Update state/history/rev-0003-20260808T144735Z.md

### Test
- Update testql/digital-twin-startup.testql.toon.yaml
- Update testql/onlydsl-startup.testql.toon.yaml
- Update tests/test_architecture_contract.py
- Update tests/test_evolution.py

### Other
- Update .dockerignore
- Update .env.example
- Update .gitignore
- Update .goal_test_report.xml
- Update Dockerfile.testql
- Update aql.py
- Update boundary.py
- Update config/contracts/evolution-agent.contract.aql
- Update config/process-packs/live-evolution/expectations.v1.eql.json
- Update config/process-packs/live-evolution/operations.v1.oql.json
- ... and 14 more files

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
