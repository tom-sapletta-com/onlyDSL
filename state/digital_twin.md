```twindsl
TWIN application
VERSION 1
REVISION 3
INTENT_FINGERPRINT sha256:d8c547f880d17d20243c52b0f2511342a70c6b2354ee4426d38d5c90c3f905f7
INTENT_SUMMARY "Build a web application that takes user intent, maintains a source-backed digital twin of the application, and evolves the implementation only when new Markdown documentation supports the change. Use IFURI capabilities, Protobuf contracts, CQRS/Event Sourcing and a DSL-only LLM boundary. The user intent must remain the invariant that constrains future evolution."
GOAL "Build a correct application whose evolution remains bounded by the user intent and source-backed evidence."
NODE user KIND actor
  RESPONSIBILITY "Provides intent, desired outcome, constraints and acceptance direction."
  EVIDENCE user_intent
END
NODE intent_compiler KIND service
  RESPONSIBILITY "Compiles user natural-language intent into validated DSL before downstream reasoning."
  EVIDENCE user_intent
END
NODE source_ingest KIND service
  RESPONSIBILITY "Transforms Markdown documents from sources/ into deterministic SourceIndexDSL before LLM analysis."
  EVIDENCE source_doc-01-product-intent_d67b5f2d79
  EVIDENCE source_doc-02-architecture_158e273228
END
NODE digital_twin KIND model
  RESPONSIBILITY "Maintains the current source-backed application model, capabilities, invariants and evolution limits."
  EVIDENCE user_intent
END
NODE builder_agent KIND service
  RESPONSIBILITY "Derives implementation plans and code changes from the validated digital twin, never from raw context."
  EVIDENCE user_intent
END
CAPABILITY compile_user_intent
  URI ifuri://llm/twin/default/commands/bootstrap
  OWNER intent_compiler
  INPUT ifuri.v1.DslDocument
  OUTPUT ifuri.v1.DslDocument
  RESPONSIBILITY "Create revision 1 of the DigitalTwinDSL from runtime-generated SourceDSL."
  EVIDENCE user_intent
END
CAPABILITY update_from_sources
  URI ifuri://llm/twin/default/commands/update
  OWNER digital_twin
  INPUT ifuri.v1.DslDocument
  OUTPUT ifuri.v1.DslDocument
  RESPONSIBILITY "Refine the twin only with evidence present in SourceIndexDSL while preserving the immutable intent fingerprint."
END
CAPABILITY plan_build
  URI ifuri://llm/builder/default/commands/plan
  OWNER builder_agent
  INPUT ifuri.v1.DslDocument
  OUTPUT ifuri.v1.DslDocument
  RESPONSIBILITY "Generate a source-backed build plan from the current twin revision."
  EVIDENCE user_intent
END
EDGE user -> compile_user_intent REL invokes
EDGE compile_user_intent -> digital_twin REL creates
EDGE source_ingest -> update_from_sources REL supplies
EDGE update_from_sources -> digital_twin REL revises
EDGE digital_twin -> plan_build REL constrains
INVARIANT preserve_user_intent
  ASSERT "Every revision must keep the original INTENT_FINGERPRINT and must not contradict explicit user intent."
  EVIDENCE user_intent
END
INVARIANT evidence_before_evolution
  ASSERT "New requirements or capabilities require evidence from user_intent or a source document; unsupported assumptions remain OPEN_QUESTION."
  EVIDENCE user_intent
  EVIDENCE source_doc-01-product-intent_d67b5f2d79
  EVIDENCE source_doc-02-architecture_158e273228
END
EVOLUTION
  ALLOW "Refine architecture, implementation details, capabilities and acceptance criteria when supported by sources."
  ALLOW "Add implementation-specific nodes without changing the original product outcome."
  REQUIRE "Preserve user intent and the immutable INTENT_FINGERPRINT across revisions."
  REQUIRE "Attach source evidence to source-derived changes."
  FORBID "Invent product requirements that are unsupported by user intent or sources."
  FORBID "Remove invariants solely to make an implementation easier."
END
SOURCE user_intent HASH sha256:d8c547f880d17d20243c52b0f2511342a70c6b2354ee4426d38d5c90c3f905f7
SOURCE source_doc-01-product-intent_d67b5f2d79 HASH sha256:424b9e0513f662eace4c7c60b45174fc883769fb299da251f36e6a2b72034ab3 PATH "sources/01-product-intent.md"
SOURCE source_doc-02-architecture_158e273228 HASH sha256:53923b2918b2b0456c31efe85009f124af3566e78684f7ea53f5f29ddaedc0f2 PATH "sources/02-architecture.md"
OPEN_QUESTION "Which source-backed capabilities should be promoted from evidence into implementation tasks first?"
OPEN_QUESTION "Which source-backed capabilities should be promoted from evidence into implementation tasks first?"
END_TWIN
```