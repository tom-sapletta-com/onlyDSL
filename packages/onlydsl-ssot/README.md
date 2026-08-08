# onlydsl-ssot

Transport- and domain-neutral storage for the onlyDSL Single Source of Accepted
Truth (SSAT). It owns candidates, deterministic manifests, validation reports,
atomic promotion, immutable receipts, and revision history.

The package deliberately does not import Digital Twin, source ingestion, AQL
policy evaluators, LLMs, Docker, or application runtimes. It only protects the
authority boundary and verifies opaque approval/receipt identifiers.
Applications add domain rules by injecting a `TreeValidator`.
