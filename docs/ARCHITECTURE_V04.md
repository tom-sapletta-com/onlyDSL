# Architecture v0.4 — intent-bounded digital twin

## Decision

The digital twin becomes the authoritative semantic model used by the code-building agent. The LLM is not allowed to reason directly over arbitrary application context or raw Markdown files.

```text
User NL
  -> SourceDSL
  -> LLM semantic capability
  -> TwinDSL r1

Markdown files
  -> SourceIndexDSL
  -> LLM update capability
  -> TwinDSL rN+1

TwinDSL
  -> BuildPlanDSL
  -> code builder / tests / runtime feedback
  -> ContextDSL
  -> Twin update or implementation patch
```

## Layer responsibilities

### Runtime/application

Responsible for:

- computing hashes,
- assigning source IDs,
- parsing Markdown structure,
- compiling raw events/logs/tool results into DSL,
- validating DSL,
- preserving intent fingerprint,
- storing accepted twin revisions,
- IFURI routing and Protobuf envelopes.

### LLM Gateway

Responsible only for transformations between declared DSL contracts. Domain code never imports the provider client.

Current logical capabilities:

```text
ifuri://llm/twin/default/commands/bootstrap
ifuri://llm/twin/default/commands/update
ifuri://llm/builder/default/commands/plan
ifuri://llm/reasoner/default/commands/analyze
```

### Digital twin

The twin is a graph/model of the intended application, not a mirror of source files. It contains user goals, semantic components, capabilities, invariants, evidence and evolution constraints.

## Evolution rule

Let:

```text
I0 = original user intent
F0 = sha256(normalize(I0))
Tn = accepted TwinDSL revision n
Sn = source evidence available at revision n
```

Every accepted revision must satisfy:

```text
Tn.intent_fingerprint == F0
preserve_user_intent in Tn.invariants
sources(Tn) subset_of {user_intent} union Sn
revision(Tn+1) == revision(Tn) + 1
```

This does not prove semantic correctness, but it makes intent drift observable and gives the runtime a fail-closed contract.

## Source handling

`source_ingest.py` converts `.md` into a typed structure. Text still exists as typed DSL literal values because a semantic model must read the information, but raw Markdown syntax is not directly concatenated into the provider request.

Each document gets:

- stable source ID for the current scan,
- path,
- SHA-256,
- headings,
- normalized paragraphs,
- bullets,
- typed code blocks with separate SHA-256.

The twin can cite these source IDs through `EVIDENCE`.

## Next architecture step

The next major layer should be `CodeTwinDSL` / `PatchDSL` generated from the current twin and a repository-derived `CodeIndexDSL`. This would close the loop:

```text
TwinDSL
  -> BuildPlanDSL
  -> CodeIndexDSL
  -> PatchDSL
  -> deterministic patch executor
  -> tests
  -> ContextDSL evidence
  -> TwinDSL / next PatchDSL
```

That is preferable to giving the LLM an unrestricted shell and a repository dump.
