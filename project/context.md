# System Architecture Analysis
<!-- generated in 0.00s -->

## Overview

- **Project**: /home/tom/github/tom-sapletta-com/onlyDSL
- **Primary Language**: python
- **Languages**: python: 43, json: 5, shell: 4, yaml: 4, txt: 2
- **Analysis Mode**: static
- **Total Functions**: 331
- **Total Classes**: 90
- **Modules**: 67
- **Entry Points**: 190

## Architecture by Module

### ifuri_core.transport
- **Functions**: 32
- **Classes**: 7
- **File**: `transport.py`

### contextdsl
- **Functions**: 28
- **Classes**: 5
- **File**: `contextdsl.py`

### server
- **Functions**: 21
- **Classes**: 1
- **File**: `server.py`

### evolution
- **Functions**: 18
- **Classes**: 1
- **File**: `evolution.py`

### intentdsl
- **Functions**: 18
- **Classes**: 4
- **File**: `intentdsl.py`

### digital_twin
- **Functions**: 17
- **Classes**: 9
- **File**: `digital_twin.py`

### boundary
- **Functions**: 16
- **Classes**: 2
- **File**: `boundary.py`

### llm_client
- **Functions**: 13
- **Classes**: 1
- **File**: `llm_client.py`

### ifuri_core.manifest
- **Functions**: 11
- **Classes**: 5
- **File**: `manifest.py`

### ifuri_core.event_store
- **Functions**: 10
- **Classes**: 4
- **File**: `event_store.py`

### ifuri_core.llm_gateway
- **Functions**: 10
- **Classes**: 1
- **File**: `llm_gateway.py`

### aql
- **Functions**: 9
- **Classes**: 3
- **File**: `aql.py`

### source_ingest
- **Functions**: 9
- **Classes**: 3
- **File**: `source_ingest.py`

### ifuri_core.postgres_store
- **Functions**: 9
- **Classes**: 1
- **File**: `postgres_store.py`

### multiruntime.javascript.ifuri
- **Functions**: 9
- **File**: `ifuri.mjs`

### ifuri_core.cqrs
- **Functions**: 8
- **Classes**: 2
- **File**: `cqrs.py`

### ifuri_core.runtime
- **Functions**: 7
- **Classes**: 3
- **File**: `runtime.py`

### ifuri_core.envelope
- **Functions**: 7
- **Classes**: 4
- **File**: `envelope.py`

### governance
- **Functions**: 6
- **File**: `governance.py`

### twin_store
- **Functions**: 6
- **Classes**: 2
- **File**: `twin_store.py`

## Key Entry Points

Main execution flows into the system:

### server.Handler.do_POST
- **Calls**: self._body, self._send, urlparse, contextdsl.compiler_from_payload, compiler.to_markdown, self._send, self._send, self._send

### ifuri_core.manifest.CapabilityRegistry.from_mapping
- **Calls**: cls, int, ManifestError, raw.get, isinstance, caps.append, raw.get, isinstance

### onlydsl.dsl.spatial_class.parse_spatial_class
- **Calls**: sorted, SpatialClassDocument, line.strip, ControlDslError, None.split, line.startswith, ControlDslError, None.splitlines

### server.Handler.do_GET
- **Calls**: urlparse, self._send, self._send, self._send, EVOLUTION.status, server._application_version, server._twin_status, server.evolution_authority_status

### onlydsl.dsl.repair_plan.parse_repair_plan
- **Calls**: RepairPlan, onlydsl.dsl.repair_plan.validate_repair_plan, line.strip, ControlDslError, None.startswith, set, ControlDslError, int

### evolution.EvolutionStore.status
- **Calls**: sorted, next, sum, self.events.glob, evolution._parse_event, str, str, None.lower

### onlydsl.dsl.parameter_contract.parse_parameter_contracts
- **Calls**: ParameterContractDocument, line.strip, ControlDslError, ParameterContract, None.splitlines, line.strip, None.startswith, None.split

### onlydsl.dsl.assumption.parse_assumptions
- **Calls**: AssumptionDocument, line.strip, ControlDslError, Assumption, None.splitlines, line.strip, None.startswith, None.split

### evolution.EvolutionStore.add_incident
- **Calls**: sorted, rows.extend, None.join, self._write, self.add_event, self.add_diagnostic, Path, uuid.uuid4

### ifuri_core.llm_gateway.build_llm_patch_handler
- **Calls**: DslDocument, EnvelopeCodec.unpack, ifuri_core.dsl_document.validate_dsl_document, boundary.assert_dsl_only, _FENCE.finditer, llm_client.propose_code_patch, ifuri_core.llm_gateway._reply, LlmGatewayError

### ifuri_core.transport.NatsWireClient._reader_loop
- **Calls**: line.rstrip, line.startswith, line.startswith, line.startswith, TransportError, self._subs.values, self.reader.readline, line.startswith

### aql.AqlContract.parse
- **Calls**: enumerate, sorted, cls, text.splitlines, raw.strip, line.split, AqlError, AqlError

### ifuri_core.envelope.EnvelopeCodec.create
- **Calls**: IfUri.parse, IfUri.parse, EnvelopeCodec._validate_kind_uri, envelope_pb2.Envelope, Timestamp, now.FromMilliseconds, env.created_at.CopyFrom, EnvelopeCodec.validate

### ifuri_core.event_store.SqliteEventStore.append
- **Calls**: list, self.conn.cursor, cur.execute, cur.execute, None.fetchone, int, cur.execute, cur.execute

### ifuri_core.postgres_store.PostgresEventStore.append
- **Calls**: list, self.conn.transaction, self.conn.cursor, cur.execute, cur.execute, int, cur.execute, int

### contextdsl.ContextCompiler.legacy_log
> Lossy adapter for old text logs. Prefer `event()` at log emission time.
- **Calls**: line.strip, LEGACY_LOG_RE.match, self.record, match.groupdict, KV_RE.sub, contextdsl._event_code_from_text, groups.get, self.record

### onlydsl.dsl.parameter_contract.ParameterContractDocument.validate
- **Calls**: self.parameters.get, ParameterValidation, ParameterValidation, ParameterValidation, ParameterValidation, ParameterValidation, ParameterValidation, ParameterValidation

### ifuri_core.transport.NatsTransport.serve_capability
- **Calls**: ifuri_core.transport.capability_pattern_to_subject, self._service_sids.append, self._service_tasks.append, self.client.subscribe, asyncio.create_task, loop, q.get, EnvelopeCodec.parse

### onlydsl.dsl.evidence_set.parse_evidence_set
- **Calls**: dict, int, EvidenceSet, line.strip, ControlDslError, set, ControlDslError, ControlDslError

### ifuri_core.runtime.IfuriRuntime.emit
- **Calls**: self.registry.resolve, EnvelopeCodec.create, self._validate_payload_contract, list, RouteDecision, RuntimeErrorIfuri, RuntimeErrorIfuri, resolved.capability.transport.ordered

### evolution.EvolutionStore.add_guidance
- **Calls**: None.join, self._write, self.add_event, None.strip, ValueError, uuid.uuid4, str, str

### twin_store.TwinStore.save
- **Calls**: digital_twin.validate_twin_markdown, digital_twin.parse_twindsl, self.exists, None.strftime, hist.write_text, tmp.replace, TwinStoreError, digital_twin.extract_twindsl

### source_ingest.SourceIndex.to_markdown
- **Calls**: lines.append, lines.extend, lines.append, lines.append, lines.append, lines.append, lines.append, None.join

### ifuri_core.uri.IfUri.parse
- **Calls**: urlsplit, cls, IfUriError, IfUriError, IfUriError, IfUriError, IfUriError, len

### ifuri_core.runtime.IfuriRuntime.call_envelope
- **Calls**: list, RouteDecision, RuntimeErrorIfuri, resolved.capability.transport.ordered, self.transports.get, dict, decision.attempted.append, errors.append

### ifuri_core.transport.NatsWireClient.connect
- **Calls**: asyncio.create_task, asyncio.open_connection, asyncio.wait_for, info_line.startswith, TransportError, json.loads, self._write, self._reader_loop

### ifuri_core.llm_gateway.build_llm_build_plan_handler
- **Calls**: DslDocument, EnvelopeCodec.unpack, ifuri_core.dsl_document.validate_dsl_document, llm_client.plan_build, None.parse_twindsl, ifuri_core.llm_gateway._reply, LlmGatewayError, LlmGatewayError

### evolution.EvolutionStore.add_event
- **Calls**: sorted, rows.extend, self._write, uuid.uuid4, None.items, rows.append, None.join, evolution._q

### ifuri_core.transport.NatsJetStream.get_message
- **Calls**: json.loads, msg.get, self.client.request, raw.decode, TransportError, body.get, base64.b64decode, None.encode

### server.Handler._send
- **Calls**: self.send_response, self.send_header, self.send_header, self.end_headers, self.wfile.write, isinstance, server._json_bytes, str

## Process Flows

Key execution flows identified:

### Flow 1: do_POST
```
do_POST [server.Handler]
  └─ →> compiler_from_payload
```

### Flow 2: from_mapping
```
from_mapping [ifuri_core.manifest.CapabilityRegistry]
```

### Flow 3: parse_spatial_class
```
parse_spatial_class [onlydsl.dsl.spatial_class]
```

### Flow 4: do_GET
```
do_GET [server.Handler]
```

### Flow 5: parse_repair_plan
```
parse_repair_plan [onlydsl.dsl.repair_plan]
  └─> validate_repair_plan
```

### Flow 6: status
```
status [evolution.EvolutionStore]
  └─ →> _parse_event
```

### Flow 7: parse_parameter_contracts
```
parse_parameter_contracts [onlydsl.dsl.parameter_contract]
```

### Flow 8: parse_assumptions
```
parse_assumptions [onlydsl.dsl.assumption]
```

### Flow 9: add_incident
```
add_incident [evolution.EvolutionStore]
```

### Flow 10: build_llm_patch_handler
```
build_llm_patch_handler [ifuri_core.llm_gateway]
  └─ →> validate_dsl_document
  └─ →> assert_dsl_only
```

## Key Classes

### contextdsl.ContextCompiler
> Deterministic application-side compiler. No LLM is called here.
- **Methods**: 15
- **Key Methods**: contextdsl.ContextCompiler.__init__, contextdsl.ContextCompiler.policy, contextdsl.ContextCompiler.capability, contextdsl.ContextCompiler.state, contextdsl.ContextCompiler.metric, contextdsl.ContextCompiler.record, contextdsl.ContextCompiler.event, contextdsl.ContextCompiler.exception, contextdsl.ContextCompiler.tool_result, contextdsl.ContextCompiler.retrieval

### evolution.EvolutionStore
> Filesystem queue whose persisted records are complete, typed DSL documents.
- **Methods**: 14
- **Key Methods**: evolution.EvolutionStore.__init__, evolution.EvolutionStore._write, evolution.EvolutionStore.add_guidance, evolution.EvolutionStore.add_incident, evolution.EvolutionStore.add_diagnostic, evolution.EvolutionStore.add_event, evolution.EvolutionStore.add_json_record, evolution.EvolutionStore.latest_guidance, evolution.EvolutionStore.claim_incident, evolution.EvolutionStore.finish_incident

### ifuri_core.transport.NatsWireClient
> Small dependency-free NATS protocol client used by the POC.

It intentionally implements only the pr
- **Methods**: 10
- **Key Methods**: ifuri_core.transport.NatsWireClient.__init__, ifuri_core.transport.NatsWireClient.connect, ifuri_core.transport.NatsWireClient._write, ifuri_core.transport.NatsWireClient.flush, ifuri_core.transport.NatsWireClient.subscribe, ifuri_core.transport.NatsWireClient.unsubscribe, ifuri_core.transport.NatsWireClient.publish, ifuri_core.transport.NatsWireClient.request, ifuri_core.transport.NatsWireClient.close, ifuri_core.transport.NatsWireClient._reader_loop

### ifuri_core.event_store.SqliteEventStore
> Reference authoritative ES adapter for tests/local POC.

PostgresEventStore implements the same sema
- **Methods**: 10
- **Key Methods**: ifuri_core.event_store.SqliteEventStore.__init__, ifuri_core.event_store.SqliteEventStore._init_schema, ifuri_core.event_store.SqliteEventStore.current_version, ifuri_core.event_store.SqliteEventStore.append, ifuri_core.event_store.SqliteEventStore.load_stream, ifuri_core.event_store.SqliteEventStore.pending_outbox, ifuri_core.event_store.SqliteEventStore.mark_outbox_published, ifuri_core.event_store.SqliteEventStore.mark_outbox_failed, ifuri_core.event_store.SqliteEventStore.outbox_stats, ifuri_core.event_store.SqliteEventStore.close

### ifuri_core.postgres_store.PostgresEventStore
> PostgreSQL authoritative event store + transactional outbox.

`psycopg[binary]` is an optional runti
- **Methods**: 9
- **Key Methods**: ifuri_core.postgres_store.PostgresEventStore.__init__, ifuri_core.postgres_store.PostgresEventStore.current_version, ifuri_core.postgres_store.PostgresEventStore.append, ifuri_core.postgres_store.PostgresEventStore.load_stream, ifuri_core.postgres_store.PostgresEventStore.pending_outbox, ifuri_core.postgres_store.PostgresEventStore.mark_outbox_published, ifuri_core.postgres_store.PostgresEventStore.mark_outbox_failed, ifuri_core.postgres_store.PostgresEventStore.outbox_stats, ifuri_core.postgres_store.PostgresEventStore.close

### aql.AqlContract
> Small compatible reader for Subactor's canonical aql:contract/v1 profile.
- **Methods**: 8
- **Key Methods**: aql.AqlContract.__init__, aql.AqlContract.parse, aql.AqlContract.from_file, aql.AqlContract._matches, aql.AqlContract.decide, aql.AqlContract.require, aql.AqlContract.require_secret_rotation, aql.AqlContract.public_status

### ifuri_core.manifest.CapabilityRegistry
- **Methods**: 7
- **Key Methods**: ifuri_core.manifest.CapabilityRegistry.__init__, ifuri_core.manifest.CapabilityRegistry.register, ifuri_core.manifest.CapabilityRegistry.from_mapping, ifuri_core.manifest.CapabilityRegistry.from_file, ifuri_core.manifest.CapabilityRegistry.resolve, ifuri_core.manifest.CapabilityRegistry.explain, ifuri_core.manifest.CapabilityRegistry.dump

### ifuri_core.envelope.EnvelopeCodec
- **Methods**: 7
- **Key Methods**: ifuri_core.envelope.EnvelopeCodec.create, ifuri_core.envelope.EnvelopeCodec.validate, ifuri_core.envelope.EnvelopeCodec._validate_kind_uri, ifuri_core.envelope.EnvelopeCodec.serialize, ifuri_core.envelope.EnvelopeCodec.parse, ifuri_core.envelope.EnvelopeCodec.unpack, ifuri_core.envelope.EnvelopeCodec.view

### twin_store.TwinStore
- **Methods**: 6
- **Key Methods**: twin_store.TwinStore.__init__, twin_store.TwinStore.exists, twin_store.TwinStore.reset_current, twin_store.TwinStore.load_markdown, twin_store.TwinStore.load, twin_store.TwinStore.save

### ifuri_core.runtime.IfuriRuntime
> Deterministic URI resolver + transport dispatcher.

Domain code sees only logical URI + protobuf pay
- **Methods**: 6
- **Key Methods**: ifuri_core.runtime.IfuriRuntime.__init__, ifuri_core.runtime.IfuriRuntime.inspect_route, ifuri_core.runtime.IfuriRuntime.call, ifuri_core.runtime.IfuriRuntime.call_envelope, ifuri_core.runtime.IfuriRuntime.emit, ifuri_core.runtime.IfuriRuntime._validate_payload_contract

### ifuri_core.transport.NatsJetStream
- **Methods**: 6
- **Key Methods**: ifuri_core.transport.NatsJetStream.__init__, ifuri_core.transport.NatsJetStream.create_stream, ifuri_core.transport.NatsJetStream.stream_info, ifuri_core.transport.NatsJetStream.publish, ifuri_core.transport.NatsJetStream.get_message, ifuri_core.transport.NatsJetStream.replay

### ifuri_core.transport.NatsTransport
- **Methods**: 6
- **Key Methods**: ifuri_core.transport.NatsTransport.__init__, ifuri_core.transport.NatsTransport.call, ifuri_core.transport.NatsTransport.publish, ifuri_core.transport.NatsTransport.ensure_event_stream, ifuri_core.transport.NatsTransport.serve_capability, ifuri_core.transport.NatsTransport.stop_services

### ifuri_core.artifacts.LocalFileArtifactStore
> Maps logical IFURI artifact identity to a safe local file placement.

The returned file:// URI is ph
- **Methods**: 5
- **Key Methods**: ifuri_core.artifacts.LocalFileArtifactStore.__init__, ifuri_core.artifacts.LocalFileArtifactStore._path, ifuri_core.artifacts.LocalFileArtifactStore.put, ifuri_core.artifacts.LocalFileArtifactStore.get, ifuri_core.artifacts.LocalFileArtifactStore.exists

### ifuri_core.cqrs.AggregateRoot
> Minimal event-sourced aggregate base; domain state changes only by events.
- **Methods**: 5
- **Key Methods**: ifuri_core.cqrs.AggregateRoot.__init__, ifuri_core.cqrs.AggregateRoot.apply, ifuri_core.cqrs.AggregateRoot.load_from_history, ifuri_core.cqrs.AggregateRoot.raise_event, ifuri_core.cqrs.AggregateRoot.pull_uncommitted
- **Inherits**: ABC

### ifuri_core.uri.IfUri
> Location-independent capability URI.

Canonical shape:
  ifuri://<bounded-context>/<entity>/<identit
- **Methods**: 5
- **Key Methods**: ifuri_core.uri.IfUri.parse, ifuri_core.uri.IfUri.__str__, ifuri_core.uri.IfUri.to_subject, ifuri_core.uri.IfUri.is_request_reply, ifuri_core.uri.IfUri.is_event

### ifuri_core.transport.InProcessTransport
- **Methods**: 5
- **Key Methods**: ifuri_core.transport.InProcessTransport.__init__, ifuri_core.transport.InProcessTransport.register, ifuri_core.transport.InProcessTransport.has_handler, ifuri_core.transport.InProcessTransport.call, ifuri_core.transport.InProcessTransport.publish

### server.Handler
- **Methods**: 5
- **Key Methods**: server.Handler.log_message, server.Handler._send, server.Handler._body, server.Handler.do_GET, server.Handler.do_POST
- **Inherits**: BaseHTTPRequestHandler

### ifuri_core.outbox.OutboxStore
- **Methods**: 3
- **Key Methods**: ifuri_core.outbox.OutboxStore.pending_outbox, ifuri_core.outbox.OutboxStore.mark_outbox_published, ifuri_core.outbox.OutboxStore.mark_outbox_failed
- **Inherits**: Protocol

### ifuri_core.cqrs.AggregateRepository
- **Methods**: 3
- **Key Methods**: ifuri_core.cqrs.AggregateRepository.__init__, ifuri_core.cqrs.AggregateRepository.load, ifuri_core.cqrs.AggregateRepository.save
- **Inherits**: <ast.Subscript object at 0x7739c5333b10>

### onlydsl.dsl.spatial_class.SpatialClassDocument
- **Methods**: 3
- **Key Methods**: onlydsl.dsl.spatial_class.SpatialClassDocument.classify, onlydsl.dsl.spatial_class.SpatialClassDocument.geometry_subjects, onlydsl.dsl.spatial_class.SpatialClassDocument.required_checks

## Data Transformation Functions

Key functions that process and transform data:

### contextdsl._parse_literal
- **Output to**: raw.strip, re.fullmatch, re.fullmatch, raw.startswith, ContextDslError

### contextdsl._parse_legacy_scalar
- **Output to**: None.strip, raw.lower, re.fullmatch, re.fullmatch, raw.strip

### contextdsl.parse_context_dsl
- **Output to**: dsl.splitlines, enumerate, raw.strip, stripped.startswith, stripped.startswith

### contextdsl.validate_context_markdown
- **Output to**: contextdsl.parse_context_dsl, errors.append, doc.policies.get, errors.append, doc.policies.get

### evolution._parse_event
- **Output to**: path.read_text, re.search, re.search, re.search, re.findall

### aql.AqlContract.parse
- **Output to**: enumerate, sorted, cls, text.splitlines, raw.strip

### intentdsl._parse_literal
- **Output to**: raw.strip, re.fullmatch, re.fullmatch, IntentDslError, int

### intentdsl._parse_call
- **Output to**: raw.strip, re.fullmatch, re.fullmatch, match.groups, arg_src.strip

### intentdsl.parse_dsl
- **Output to**: dsl.splitlines, enumerate, raw.strip, stripped.startswith, stripped.startswith

### intentdsl.validate_program
- **Output to**: program.states.items, set, set, set, set

### intentdsl.validate_markdown
- **Output to**: intentdsl.extract_intentdsl, intentdsl.parse_dsl, intentdsl.validate_program, str

### patchdsl.parse_patchdsl
- **Output to**: _FENCE_RE.fullmatch, patchdsl._json_string, PatchDocument, markdown.strip, PatchDslError

### patchdsl.validate_patch_policy
- **Output to**: None.resolve, PurePosixPath, None.resolve, change.diff.splitlines, errors.append

### patchdsl.validate_patch_markdown
- **Output to**: patchdsl.parse_patchdsl, patchdsl.validate_patch_policy, str

### governance.load_process_pack
- **Output to**: Path, json.loads, None.read_text

### governance.build_process_envelope
- **Output to**: governance.canonical_hash, governance.canonical_hash, sorted, sorted, asdict

### source_ingest.parse_markdown
- **Output to**: path.read_text, None.as_posix, MarkdownDocument, re.compile, code_re.finditer

### source_ingest.validate_sourceindex_markdown
- **Output to**: SourceIngestError, None.rsplit, x.strip, SourceIngestError, len

### ifuri_core.runtime.IfuriRuntime._validate_payload_contract
- **Output to**: resolved.capability.input_type.strip, expected.startswith, RuntimeErrorIfuri, envelope.payload.type_url.rsplit

### ifuri_core.manifest._parse_pattern
- **Output to**: urlsplit, set, enumerate, tuple, ManifestError

### ifuri_core.manifest._validate_capability
- **Output to**: ifuri_core.manifest._parse_pattern, None.get, capability.transport.ordered, re.fullmatch, ManifestError

### ifuri_core.uri.IfUri.parse
- **Output to**: urlsplit, cls, IfUriError, IfUriError, IfUriError

### ifuri_core.envelope.EnvelopeCodec.validate
- **Output to**: IfUri.parse, IfUri.parse, EnvelopeCodec._validate_kind_uri, EnvelopeError, EnvelopeError

### ifuri_core.envelope.EnvelopeCodec._validate_kind_uri
- **Output to**: None.get, EnvelopeError

### ifuri_core.envelope.EnvelopeCodec.serialize
- **Output to**: EnvelopeCodec.validate, env.SerializeToString

## Public API Surface

Functions exposed as public API (no underscore prefix):

- `digital_twin.parse_twindsl` - 149 calls
- `intentdsl.codegen` - 88 calls
- `server.Handler.do_POST` - 83 calls
- `contextdsl.parse_context_dsl` - 73 calls
- `intentdsl.parse_dsl` - 71 calls
- `onlydsl.dsl.build_plan.parse_bound_build_plan` - 60 calls
- `source_ingest.parse_markdown` - 59 calls
- `contextdsl.compiler_from_payload` - 52 calls
- `patchdsl.parse_patchdsl` - 49 calls
- `digital_twin.render_twin` - 42 calls
- `ifuri_core.manifest.CapabilityRegistry.from_mapping` - 39 calls
- `llm_client.update_twin` - 39 calls
- `onlydsl.dsl.spatial_class.parse_spatial_class` - 39 calls
- `server.Handler.do_GET` - 37 calls
- `onlydsl.dsl.repair_plan.parse_repair_plan` - 36 calls
- `contextdsl.render_context_dsl` - 35 calls
- `evolution.EvolutionStore.status` - 35 calls
- `source_ingest.build_source_index` - 35 calls
- `onlydsl.dsl.spatial_class.spatial_class_from_twin` - 35 calls
- `intentdsl.validate_program` - 34 calls
- `onlydsl.dsl.parameter_contract.parse_parameter_contracts` - 34 calls
- `digital_twin.validate_twin` - 34 calls
- `onlydsl.runtime.integrity.parse_project_integrity` - 34 calls
- `intentdsl.run_program` - 29 calls
- `onlydsl.dsl.assumption.parse_assumptions` - 29 calls
- `onlydsl.dsl.assumption.assumptions_from_integrity` - 29 calls
- `evolution.EvolutionStore.add_incident` - 28 calls
- `llm_client.bootstrap_twin` - 28 calls
- `ifuri_core.llm_gateway.build_llm_patch_handler` - 28 calls
- `patchdsl.validate_patch_policy` - 26 calls
- `digital_twin.demo_bootstrap_twin` - 25 calls
- `aql.AqlContract.parse` - 24 calls
- `ifuri_core.envelope.EnvelopeCodec.create` - 23 calls
- `ifuri_core.event_store.SqliteEventStore.append` - 23 calls
- `llm_client.plan_build` - 22 calls
- `ifuri_core.postgres_store.PostgresEventStore.append` - 21 calls
- `contextdsl.ContextCompiler.legacy_log` - 20 calls
- `onlydsl.dsl.parameter_contract.ParameterContractDocument.validate` - 20 calls
- `ifuri_core.transport.NatsTransport.serve_capability` - 19 calls
- `onlydsl.dsl.evidence_set.parse_evidence_set` - 19 calls

## System Interactions

How components interact:

```mermaid
graph TD
    do_POST --> _body
    do_POST --> _send
    do_POST --> urlparse
    do_POST --> compiler_from_payloa
    do_POST --> to_markdown
    from_mapping --> cls
    from_mapping --> int
    from_mapping --> ManifestError
    from_mapping --> get
    from_mapping --> isinstance
    parse_spatial_class --> sorted
    parse_spatial_class --> SpatialClassDocument
    parse_spatial_class --> strip
    parse_spatial_class --> ControlDslError
    parse_spatial_class --> split
    do_GET --> urlparse
    do_GET --> _send
    do_GET --> status
    parse_repair_plan --> RepairPlan
    parse_repair_plan --> validate_repair_plan
    parse_repair_plan --> strip
    parse_repair_plan --> ControlDslError
    parse_repair_plan --> startswith
    status --> sorted
    status --> next
    status --> sum
    status --> glob
    status --> _parse_event
    parse_parameter_cont --> ParameterContractDoc
    parse_parameter_cont --> strip
```

## Reverse Engineering Guidelines

1. **Entry Points**: Start analysis from the entry points listed above
2. **Core Logic**: Focus on classes with many methods
3. **Data Flow**: Follow data transformation functions
4. **Process Flows**: Use the flow diagrams for execution paths
5. **API Surface**: Public API functions reveal the interface

## Context for LLM

Maintain the identified architectural patterns and public API surface when suggesting changes.