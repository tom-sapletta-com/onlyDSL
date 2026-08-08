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
`FROM_TWIN_HASH`; its tasks use the same strict fields as RepairPlanDSL.

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

The E2E regression injects a controlled executor and proves:

```text
CONCEPTUAL_GEOMETRY_ASSUMPTION
  -> cad://openscad/scad/geometry/compile
  -> physical-evidence receipt
  -> TestQL green
  -> EQL green
  -> next ProjectIntegrityDSL no longer contains the finding
```

The local web service currently exposes `ONLYDSL_PROFILE=demo` with `InProcessTransport` and a
file store. `/api/health` therefore reports `cqrs_es: false`. Setting
`ONLYDSL_PROFILE=production` fails closed until the HTTP request path itself is wired to NATS,
PostgreSQL Event Store and the transactional outbox. `scripts/docker_integration.py` remains
the real infrastructure contract test; it is not misreported as the web application's path.
