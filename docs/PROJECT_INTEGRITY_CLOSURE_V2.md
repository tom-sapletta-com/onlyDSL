# onlyDSL Project Integrity Closure v2

onlyDSL is the authority and repair control plane. It does not render Digital Twins and does
not implement OpenSCAD, IFC or geometry algorithms. Those remain behind exact, system-owned
process URIs such as `cad://openscad/scad/geometry/compile`.

## Contracts

The release introduces six typed contracts:

| Contract | Authority-owned purpose |
| --- | --- |
| `SpatialClassDSL` | Classify components as `physical`, `hybrid`, `cyber` or `logical` and declare type-specific requirements/forbidden properties. |
| `AssumptionDSL` | Make provisional claims addressable and move them from `open` to `superseded` only when their replacement condition and exact evidence are present. |
| `ParameterContractDSL` | Bind subject type, scalar type, unit, quality and range/allowed values. `UNIT mixed` is forbidden. |
| `EvidenceSetDSL` | Replace long evidence lists with an immutable query, count, members hash and evidence-set URI. |
| `AuthorityProjectionDSL` | Project a pre-existing AQL contract onto an exact Twin revision and system process list. It is never model output. |
| `RepairPlanDSL` | Bind findings to exact target, evidence, operation, process URI, expected result, acceptance, rollback, dependencies and authority class. |

TwinDSL `NODE` now requires `SPATIAL_CLASS`. BuildPlanDSL additionally requires
`FROM_TWIN_HASH`; its tasks use the same strict fields as RepairPlanDSL. Both
`FROM_REVISION` and `FROM_TWIN_HASH` are deterministic bindings copied from the
current canonical Twin by the runtime. They are not accepted as facts authored by
the LLM. The LLM supplies semantic task intent; the runtime binds identity,
revision, authority and executable process selection.

The contracts deliberately separate three different kinds of truth:

```text
semantic claim      model may propose; validators check the DSL and invariants
physical claim      must carry measured/released CAD or equivalent evidence
authority claim     must originate in AQL and the system process registry
```

This prevents a syntactically valid model response from becoming either physical
evidence or permission.

## Four independent outcomes

The onlyDSL ProjectIntegrity reader converts the upstream result into:

```text
Integrity          PASS | FAIL
Evidence           COMPLETE | INCOMPLETE
OperationalReady   READY | PARTIAL | BLOCKED
AutonomyReady      PASS | BLOCKED
```

Missing evidence and open assumptions make a project incomplete without inventing a
contradiction. Invalid parameters, broken dependencies and inconsistencies block autonomy.

## Closure loop

```text
ProjectIntegrityDSL from live 7444
  -> exact append-only streamVersion
  -> system repair-process registry
  -> RepairPlanDSL
  -> AQL preflight
  -> AuthorityProjectionDSL
  -> exact URI Process
  -> TestQL + EQL
  -> closure receipt
  -> next ProjectIntegrityDSL
```

`POST /api/integrity/repair-plan` re-reads the live report before planning. A supplied stale
document or revision is rejected. Plans are stored below
`runtime/evolution/repair-plans/`. The model cannot supply or replace the selected process URI.
Plan identity includes both the exact Twin revision and the integrity hash. The
same unresolved physical contradiction therefore creates an append-only plan per
revision instead of overwriting an earlier authority projection.

`GET /api/integrity/current` also projects the live downstream Twin into SpatialClassDSL,
converts every `ungrounded-assumption` finding into an addressable AssumptionDSL record, exposes
the upstream EvidenceSetDSL and returns the four independent outcomes plus requirement-based
geometry coverage. Visual markers for `cyber` and `logical` components remain renderable but no
longer count as physical geometry claims.

The E2E regression injects a controlled executor and proves the controller
contract:

```text
CONCEPTUAL_GEOMETRY_ASSUMPTION
  -> cad://openscad/scad/geometry/compile
  -> physical-evidence receipt
  -> TestQL green
  -> EQL green
  -> next ProjectIntegrityDSL no longer contains the finding
```

This test does not claim that a real CAD conflict was repaired. A real executor
must preserve fail-closed behavior whenever the physical evidence is ambiguous.
The control loop is complete as software; an individual physical closure remains
blocked until an authoritative source or measurement exists.

The local web service currently exposes `ONLYDSL_PROFILE=demo` with `InProcessTransport` and a
file store. `/api/health` therefore reports `cqrs_es: false`. Setting
`ONLYDSL_PROFILE=production` fails closed until the HTTP request path itself is wired to NATS,
PostgreSQL Event Store and the transactional outbox. `scripts/docker_integration.py` remains
the real infrastructure contract test; it is not misreported as the web application's path.

## Deterministic diagnostics

The system-owned catalog recognizes the closure boundary directly:

- `GEOMETRY_OPENSCAD_BACKEND_REQUIRED` stays `manual`: a model cannot install or replace runtime tooling;
- `GEOMETRY_VALIDATION_INCOMPLETE` requests grounded evidence and forbids synthesizing a passing pose;
- `CONCEPTUAL_GEOMETRY_ASSUMPTION` selects the registered CAD compile process;
- `GEOMETRY_REFERENCE_EXTENT_DRIFT` selects system reconciliation, remains `manual`, and explicitly forbids widening tolerance to manufacture a pass;
- `DEVELOPMENT_EVIDENCE_NOT_ACCEPTED` requires accepted Git/AST/ticket-to-symbol implementation evidence and never permits weakening the acceptance rules;
- `DEVELOPMENT_EXECUTION_METADATA_DRIFT` detects a changed todo2code execution hash when semantic records and the resource diff are unchanged;
- `DUPLICATE_TWIN_ITERATION_WRITER` requires one elected writer per `.living-runtime` and keeps secondary dashboards read-only;
- `OBSERVATION_UNIT_MIXED_FORBIDDEN` requires exact per-metric units;
- `SPATIAL_CLASS_INVALID` repairs the ontology contract while preserving identity;
- `SEMANTIC_MATH_AUTHORITY_FIELD_FORBIDDEN` keeps the audited deterministic fallback.

These diagnostics are solution templates, not grants. AQL preflight and the system process registry
remain mandatory before any operation can execute.

## Multi-layer analysis

ProjectIntegrityDSL is a dependency proof, not a flat checklist. Each finding is
bound to a layer, subjects, exact evidence and a registered repair process. The
current graph evaluates:

```text
requirements -> design -> development -> Twin -> Scene -> validation
                    ^          ^           ^
research -----------+     runtime ----------+
```

The evaluator distinguishes:

- a missing edge (`INCOMPLETE`) from a contradictory edge (`FAIL`);
- an open assumption from a grounded physical fact;
- a logical/cyber visualization from physical geometry;
- a valid parameter value from a complete domain contract;
- a current published artifact from an unpublishable candidate.

### 3D conformance is an evidence proof

Text does not become trustworthy 3D merely because a renderer can draw it. The
pipeline uses distinct contracts:

```text
TwinDSL component + SpatialClassDSL type requirements
  -> ParameterContractDSL units and ranges
  -> hierarchy/assembly relations (PART_OF, MOUNTED_ON, CONNECTED_TO)
  -> grounded CAD/IFC/measurement evidence in one coordinate frame
  -> SceneDSL binding with stable component and scene identity
  -> GeometryValidationDSL pose, extent, orientation and constraint checks
  -> renderer/OpenUSD artifact
  -> TestQL comparison against the exact validation receipt
```

Position and extent are valid only when their unit and coordinate system match.
Orientation is a normalized quaternion with an explicit tolerance, not a label
such as "front". Constraints such as containment, clearance, mounting and
collision are evaluated only when the component type requires them. Cyber and
logical components are forbidden from manufacturing physical completeness just
because the dashboard draws an overlay for them.

This proves that the displayed artifact conforms to supplied evidence and rules;
it cannot prove that an unmeasured laboratory object is physically correct. That
last step requires a released CAD/IFC revision, survey or measurement. The 14 mm
versus 18 mm lid conflict is intentionally blocked for exactly this reason.

This makes hidden assumptions addressable. An error cannot disappear merely
because another layer has a green result: its replacement condition must be met,
evidence hashes must change consistently, dependent tasks must be accepted and a
new TestQL/EQL receipt must be appended.

Iteration identity is semantic. todo2code timestamps, run IDs, durations and its
declared graph hash are excluded because some provider versions derive that hash
from execution metadata. The control plane recalculates a stable hash from
records, relations, diagnostics, stable configuration and acceptance. A changed
record still creates a new revision; repeating the same analysis does not.

The same rule applies to process topology: several read-only dashboards are
allowed, but only one controller may write a given `.living-runtime`. A duplicate
writer is a concurrency diagnostic, not permission for an LLM-generated process
command.

The embedded dashboard on port 7444 now enforces this rule: its state declares
`control.mode=read-only`, while mutation endpoints return
`403 DASHBOARD_READ_ONLY` with `DUPLICATE_TWIN_ITERATION_WRITER`. The elected
controller on 7445 carries the todo2code configuration. This prevents an
inspection replica without `T2C_BIN` from alternating the development layer
between real evidence and a fixture.

Development acceptance is evaluated in the same way. Iteration 51 exposed a
`PLANNED_NOT_IMPLEMENTED` diagnostic for a claim marked complete without Git or
AST proof, producing `DEVELOPMENT_EVIDENCE_NOT_ACCEPTED`. A subsequent input
revision supplied accepted evidence and the finding disappeared. The diagnostic
is nevertheless retained in the system catalog and process registry so a repeat
routes to `process://twin/development-evidence/repair`; it cannot be "repaired"
by changing an acceptance threshold or by relabeling planned work as complete.

## Live verification on 2026-08-08

At stream revision 56 the running nanobionic laboratory candidate reports:

```text
Integrity          FAIL
Evidence           INCOMPLETE
OperationalReady   BLOCKED
AutonomyReady      BLOCKED

layers             8/8 evidenced
dependencies       5/6 complete
parameters         183/183 valid
assumptions         0/16 grounded
spatial bindings   19 physical|hybrid
geometry checks    16/57 required checks passed
```

The decisive contradiction is not an anonymous geometry failure. OpenSCAD
compiled 130,216 triangles, then the reference comparison found:

```text
compiled SCAD extent       76.499 x 76.499 x 14 mm
reference STEP/GLB extent  76.500 x 76.476 x 18 mm
maximum drift              4 mm
diagnostic                 GEOMETRY_REFERENCE_EXTENT_DRIFT
```

The candidate is retained for diagnostics, while the previously published Twin
and scene remain current. The system-owned repair URI is
`process://twin/geometry/reconcile-source-evidence`; execution cannot decide
whether 14 mm or 18 mm is physically authoritative. A released CAD revision or a
measurement must make that decision, after which the normal compile, TestQL, EQL
and ProjectIntegrity cycle can publish a new iteration.

An unchanged replay after revision 56 produced `BLOCKED / NO CHANGE` and did not
append event 57. This proves that a stable todo2code graph plus generated feedback
does not self-excite the loop; the existing physical blocker remains visible
without manufacturing another revision.
