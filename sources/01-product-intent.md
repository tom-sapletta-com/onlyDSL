# Digital twin application

The application should maintain a durable digital representation of the software product being built. The initial model is derived from user intent and later revisions may be refined by trusted documentation.

- User intent is the product anchor and must remain immutable as an intent fingerprint.
- New documentation may refine architecture and implementation details but must not silently replace the requested outcome.
- Unsupported assumptions should remain explicit open questions.
- Every source-derived capability should carry provenance to the source document.

## Required workflow

1. Accept a short user request.
2. Compile it into a validated digital twin model.
3. Scan Markdown files from `sources/`.
4. Convert Markdown into an application-generated DSL before LLM analysis.
5. Update the digital twin only if the revision passes semantic validation.
6. Produce a build plan from the current twin revision.
