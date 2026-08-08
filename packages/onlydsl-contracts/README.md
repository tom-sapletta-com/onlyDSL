# onlydsl-contracts

Pure, independently buildable contracts owned by onlyDSL and safe for use by
doDSL, twin-dsl and other clients. The package contains deterministic DSL
models and parsers, the logical IFURI value object, SSOT data models and their
canonical Proto/GBNF schemas. It has no runtime, transport, LLM or authority
dependencies.

`DevelopmentEvidenceBundleDSL` is the cross-project boundary for deterministic
todo2code evidence. It binds an exact Git revision and tree to immutable graph,
diagnostic and semantic-manifest URNs. Its required `AUTHORITY_EFFECT none` and
`MUTATION_EFFECT none` fields make explicit that evidence never grants AQL
authority and never authorizes execution.
