# SSOT — Single Source of Accepted Truth

`SSOT/` is a materialized, versioned projection of the DSL contracts already
owned by onlyDSL. It does not replace code, Git history, documentation, CAD,
telemetry or todo2code. Those remain primary evidence sources.

```text
primary sources
  -> system-owned extractor / todo2code / CAD compiler / LLM semantic proposal
  -> SSOT/candidate/<id>/tree
  -> deterministic DSL validation
  -> ProjectIntegrityDSL
  -> AQL contract hash + TestQL receipt + EQL receipt
  -> single-writer promotion
  -> SSOT/current
```

The LLM may help create semantic candidate sections. It cannot write
`SSOT/current`, issue receipts, choose an executable process URI or modify
`.onlydsl/authority`.

`ClaimDSL` makes individual accepted assertions addressable. It requires subject,
predicate, JSON value, exact unit, immutable source URI/hash/revision/anchor,
evidence kind, quality, trust role, generator, independent validator, lifecycle
status and supersession links. A claim cannot become `accepted` when an LLM is
its only validator. `TrustDSL` declares which source roles may define which
domains and their priority; it exposes conflicts but does not silently resolve
them.

## Layout

```text
project/
├── SSOT/
│   ├── manifest.dsl
│   ├── current/
│   │   ├── project.projectdsl
│   │   ├── sources/
│   │   ├── intent/
│   │   ├── contracts/
│   │   ├── development/
│   │   ├── twin/
│   │   ├── runtime/
│   │   └── integrity/
│   ├── candidate/<candidate-id>/
│   │   ├── tree/
│   │   ├── manifest.json
│   │   ├── semantic.diff.dsl
│   │   └── validation.dsl
│   ├── receipts/{testql,eql,geometry,development,mutation}/
│   └── revisions/<revision-hash>.manifest.dsl
└── .onlydsl/
    ├── authority/{contract.aql,grants/}
    ├── process-packs/
    ├── cache/
    ├── locks/
    ├── queue/
    └── runtime/
```

`SSOT/current` contains accepted project state. `.onlydsl` contains the
mechanism and authority controlling changes to that state. Authority paths and
AQL contract contents are rejected if found in a candidate.

## Merkle-like manifest

The root manifest records file hashes and derived hashes for each top-level
section. The root revision is calculated from the project identity and sorted
section hashes:

```text
file hash       = sha256(file bytes)
section hash    = hash(sorted(relative path -> file hash))
SSOT revision   = hash(schema, project id, sorted section hashes)
```

`CREATED_AT`, parent lineage and execution duration are not part of the semantic
revision. Two equivalent accepted states therefore have the same revision even
when analyzed at different times.

The manifest URI is:

```text
urn:subactor:ssot:sha256:<digest>
```

Revision history stores manifests, not another full copy of every source. Git or
a content-addressed artifact store remains responsible for recovering historical
file bodies and large CAD/media artifacts.

## Promotion contract

Promotion requires all of the following:

- the candidate is based on the exact current revision;
- every candidate file still matches its staged hash;
- known onlyDSL documents pass their existing parsers;
- ProjectIntegrityDSL is `PASS`, if supplied;
- incomplete evidence has an explicit `allow_incomplete` grant;
- the authority contract is bound by an exact SHA-256 hash;
- at least one immutable TestQL receipt and EQL receipt is supplied;
- the per-project promotion lock proves one writer.

An `Integrity=FAIL` candidate cannot be promoted by claiming `pass` in the CLI.
The parsed integrity document takes precedence over declared approval metadata.

The filesystem promotion uses a staged tree, a writer lock, directory swap,
manifest replacement, append-only history and rollback on failure. Readers load
the manifest before and after hashing `current/`; if the manifest changed during
the read, they retry instead of accepting a partial transition.

## CLI

```bash
onlydsl ssot init . --project-id my-project
onlydsl ssot status .
onlydsl ssot verify .
onlydsl ssot scan . --source-root sources

onlydsl ssot candidate create . \
  --id candidate-001 \
  --section development/todo2code.dsl=/tmp/todo2code.dsl \
  --remove development/superseded.dsl \
  --evidence urn:subactor:todo2code:sha256:...

onlydsl ssot candidate validate candidate-001 .
onlydsl ssot diff candidate-001 .

onlydsl ssot promote candidate-001 . \
  --authority-hash sha256:... \
  --testql urn:subactor:testql:sha256:... \
  --eql urn:subactor:eql:sha256:... \
  --integrity pass \
  --completeness incomplete \
  --allow-incomplete

onlydsl ssot history .
onlydsl ssot registry add .
onlydsl ssot registry list
```

`reconcile` is a propose-only convenience operation. System-owned producers
first materialize section files, then pass them to the command:

```bash
onlydsl ssot reconcile . \
  --section development/todo2code.dsl=/run/todo2code/accepted.dsl \
  --section sources/source-index.dsl=/run/index/source-index.dsl \
  --evidence urn:subactor:todo2code:sha256:...
```

It creates and validates a candidate and prints SemanticDiffDSL. It never
promotes automatically.

## todo2code and generated feedback

todo2code is a candidate producer, not an SSOT writer:

```text
Git + AST + TODO + CHANGELOG
  -> todo2code intent/evidence graph
  -> development candidate DSL
  -> onlyDSL validation and ProjectIntegrity
  -> promotion receipt
```

Execution timestamps, run IDs and provider-declared execution hashes must stay
outside semantic fingerprints. Generated feedback may enter the next iteration,
but unchanged semantic feedback must converge to `NO CHANGE`.

## Git and artifact storage

Recommended for Git:

- `SSOT/manifest.dsl`;
- stable files under `SSOT/current`;
- small revision manifests and relevant immutable receipts.

Not recommended for automatic commits:

- `SSOT/candidate` and `.staging`;
- `.onlydsl/cache`, locks, queue and runtime state;
- high-volume telemetry;
- GLB, USD, video, PDF and binary CAD bodies.

Large bodies remain in CAS/artifact storage. SSOT contains immutable URI, hash,
unit, provenance and acceptance metadata.

## Federated projects

Each project owns its SSOT. The optional registry stores only verified project
pointers:

```text
PROJECT nanobionic-laboratory
  SSOT_URI urn:subactor:ssot:sha256:...
  PATH file:///.../SSOT
  REVISION sha256:...
  INTEGRITY pass
  COMPLETENESS incomplete
END_PROJECT
```

Cross-project dependencies should bind an exact SSOT revision rather than a
random path in another repository. A changed dependency revision can then become
a typed compatibility finding and RepairPlanDSL input.

## Current boundary

This release implements accepted-state storage and promotion. It deliberately
does not invoke todo2code, CAD tools, Git commands or LLM commands from the SSOT
writer. Those operations remain behind system-owned process packs and provide
files plus immutable receipts to `candidate/`.
