# onlyDSL documentation

This menu separates current contracts and operating guides from historical
design records. Start with the [project README](../README.md) for installation,
the package map, current runtime modes and the complete HTTP route table.

## Source-of-truth policy

When documents disagree, use this order:

1. executable schemas, parsers and tests;
2. current package and runtime code;
3. current contract and operating guides below;
4. [TEST_REPORT.md](../TEST_REPORT.md) as evidence from a named run;
5. dated audits and historical architecture records as context only.

Generated files under [`project/`](../project/README.md) are analysis evidence.
They can reveal drift, but they do not redefine implemented behavior. A local
`START.md`, when present, describes observed services on one host and is ignored
by Git deliberately.

## Current contracts and architecture

| Document | Scope |
| --- | --- |
| [IFURI specification](IFURI_SPEC.md) | Canonical location-independent capability URI and transport mapping |
| [LLM boundary architecture](LLM_BOUNDARY_ARCHITECTURE.md) | DSL-only provider boundary, validation and repair rules |
| [Project Integrity Closure v2](PROJECT_INTEGRITY_CLOSURE_V2.md) | Integrity contracts, authority projection, RepairPlanDSL and closure evidence |
| [SSOT accepted truth](SSOT_ACCEPTED_TRUTH.md) | Candidate validation, immutable receipts and single-writer promotion |

## Current operation and integration

| Document | Scope |
| --- | --- |
| [Autonomous evolution](AUTONOMOUS_EVOLUTION.md) | Observe/apply modes, AQL, diagnostics, rollback and runtime state |
| [Docker tests](DOCKER_TESTS.md) | Repeatable Compose validation commands |
| [OpenRouter test](OPENROUTER_TEST.md) | Real-provider smoke path and fail-closed expectations |
| [OQL OS integration](OQLOS_INTEGRATION.md) | External OQL OS integration boundary |

The normal HTTP server currently uses the in-process request adapter and a file
store. NATS, JetStream and PostgreSQL are verified by the separate Compose
`integration` service; see the [root README](../README.md#core-architecture).

## Historical records and dated evidence

| Document | Status |
| --- | --- |
| [Architecture v0.3](ARCHITECTURE_V03.md) | Historical architecture decision; retained for design lineage |
| [Architecture v0.4](ARCHITECTURE_V04.md) | Historical digital-twin decision; retained for design lineage |
| [Docker and OpenRouter audit — 2026-08-08](AUDYT_DOCKER_OPENROUTER_2026-08-08.md) | Dated audit snapshot; later fixes and results do not make its original observations current |
| [Documentation intent audit — 2026-08-09](DOCUMENTATION_INTENT_AUDIT_2026-08-09.md) | todo2code findings, applied corrections and interpretation of residual heuristics |

## Package documentation and evidence

- [onlydsl-contracts](../packages/onlydsl-contracts/README.md)
- [onlydsl-core](../packages/onlydsl-core/README.md)
- [onlydsl-ssot](../packages/onlydsl-ssot/README.md)
- [current test report](../TEST_REPORT.md)
- [generated project analysis](../project/README.md)
