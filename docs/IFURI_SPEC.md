# IFURI v0.1 — logical capability addressing

## Goal

IFURI is a location-independent identifier for a capability/process/resource. It deliberately does **not** encode a host, port or transport.

## Canonical grammar

```ebnf
ifuri          = "ifuri://", bounded_context, "/", entity, "/", identity, "/", kind, "/", operation ;
bounded_context = segment ;
entity         = segment ;
identity       = segment ;
operation      = segment ;
kind           = "commands" | "queries" | "events" | "artifacts" | "streams" ;
segment        = alnum, { alnum | "_" | "-" } ;
```

Forbidden in canonical logical addresses:

- userinfo,
- port,
- query string,
- fragment,
- transport names such as `nats://`, `http://` or `grpc://`.

Examples:

```text
ifuri://scenario/scenario/9f7/commands/execute
ifuri://scenario/scenario/9f7/queries/status
ifuri://scenario/scenario/9f7/events/executed
ifuri://artifact/document/spec42/artifacts/content
ifuri://llm/reasoner/default/commands/analyze
```

## Transport mapping

The NATS adapter maps the logical identity deterministically:

```text
ifuri://scenario/scenario/9f7/commands/execute
→ ifuri.cmd.scenario.scenario.9f7.execute

ifuri://scenario/scenario/9f7/events/executed
→ ifuri.evt.scenario.scenario.9f7.executed
```

This subject is transport placement. It is not persisted as domain identity in place of the IFURI.

## Manifest matching

A capability can declare a single-segment parameter:

```yaml
uri_pattern: ifuri://scenario/scenario/{scenario_id}/commands/execute
```

The resolver:

1. validates the requested IFURI,
2. evaluates every manifest route,
3. ranks by literal-segment specificity,
4. fails closed if two best routes have the same specificity,
5. exposes an `explain()` result with all candidates and transport order.

The `kind` segment must be literal in the manifest to avoid accidental cross-kind routing.
