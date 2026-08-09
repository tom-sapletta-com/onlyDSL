# Documentation intent audit — 2026-08-09

This is a dated verification record, not a runtime specification. The current
navigation and behavior summary live in the [project README](../README.md) and
the [documentation menu](README.md).

## Intent

The audit asked whether README and project documentation describe implemented
packages, interfaces, LLM boundaries, runtime modes and tests; whether important
project files are discoverable; and whether plans or historical decisions are
presented as current functionality.

## todo2code runs

The local todo2code 0.5.0 pipeline analyzed the repository task, Git history,
AST and Markdown documentation. Natural-language extraction, documentation
extraction and summary used the configured structured LLM boundary; source-code
planning stayed deterministic.

The first broad pass found actionable drift:

- the README advertised Python 3.9 while every package requires Python 3.10;
- the README reported 73 tests while the current suite contains 114;
- the route documentation covered only a subset of the HTTP handlers;
- current HTTP persistence and the separate NATS/PostgreSQL integration
  contract were described as if they were one execution path;
- architecture v0.3/v0.4 and the dated Docker audit lacked an explicit
  historical status;
- no categorized menu covered all files under `docs/`.

The broad documentation pass was partial because its configured budget covered
12 of 17 chunks. A second focused pass analyzed `README.md`, `docs/README.md`
and `TEST_REPORT.md` with a 24-chunk budget. It completed with pipeline status
`succeeded`, no stage warnings and non-degraded structured LLM stages.

## Applied corrections

- Added the project map and complete documentation menu.
- Corrected the supported Python version and test count.
- Matched all 23 documented API routes to the handlers in `server.py`.
- Separated the in-process/file HTTP path from the Compose integration path.
- Marked old architecture documents and the 2026-08-08 audit as historical.
- Split current test evidence from retained HTTP/Docker evidence for 0.0.7.
- Added `intent_codegen.py` to the built distribution because `intentdsl.py`
  imports it.

## Interpretation of residual diagnostics

todo2code still produced broad `IMPLEMENTED_NOT_PLANNED` and
`IMPLEMENTED_NOT_DOCUMENTED` records for individual AST symbols. The focused
run intentionally disabled TODO/CHANGELOG ingestion and analyzed navigation
documents rather than per-symbol API reference material, so those diagnostics
do not by themselves prove a documentation defect.

Two blocking polarity diagnostics were also extraction artifacts: one treated
the control-plane role and the exclusion of CAD execution as opposites; another
assigned opposite polarity to duplicate descriptions of the missing-key smoke
guard. Both pairs describe compatible behavior. They were reviewed rather than
applied as source patches. Deterministic code-change suggestions targeting
`.env` were rejected because a secret-bearing local file must never be created
or committed by documentation automation.

One useful model conclusion was retained and clarified: PostgreSQL is
authoritative in the integration contract, while the current HTTP health
endpoint truthfully reports a file store and `cqrs_es=false`.

## Independent checks

```text
uv run pytest -q                         -> 114 passed
local Markdown targets                  -> all resolved
README route table vs server handlers   -> 23/23 match
wheel import: intent_codegen, intentdsl  -> PASS
GET 127.0.0.1:18787/api/health          -> version 0.0.10, demo/inproc/file
```
