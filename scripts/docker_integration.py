from __future__ import annotations

import asyncio
import json
import os
import time
import uuid

from google.protobuf.struct_pb2 import Struct

from boundary import source_text_dsl
from contextdsl import compiler_from_payload
from digital_twin import extract_twindsl, intent_fingerprint, parse_twindsl
from source_ingest import build_source_index
from ifuri_core.dsl_document import make_dsl_document, validate_dsl_document
from ifuri_core.dsl_pb2 import DslDocument
from ifuri_core.envelope import EnvelopeCodec, MessageKind
from ifuri_core.llm_gateway import (
    build_llm_build_plan_handler,
    build_llm_reasoner_handler,
    build_llm_twin_bootstrap_handler,
    build_llm_twin_update_handler,
)
from ifuri_core.manifest import CapabilityRegistry
from ifuri_core.outbox import OutboxPublisher
from ifuri_core.postgres_store import PostgresEventStore
from ifuri_core.runtime import IfuriRuntime
from ifuri_core.transport import InProcessTransport, NatsTransport, NatsWireClient


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


async def connect_nats() -> NatsWireClient:
    host = os.getenv("NATS_HOST", "nats")
    port = int(os.getenv("NATS_PORT", "4222"))
    last = None
    for _ in range(60):
        client = NatsWireClient(host, port, "ifuri-docker-integration")
        try:
            await client.connect()
            return client
        except Exception as exc:
            last = exc
            try:
                await client.close()
            except Exception:
                pass
            await asyncio.sleep(0.5)
    raise RuntimeError(f"NATS unavailable: {last}")


def connect_postgres() -> PostgresEventStore:
    dsn = os.environ["POSTGRES_DSN"]
    last = None
    for _ in range(60):
        try:
            return PostgresEventStore(dsn)
        except Exception as exc:
            last = exc
            time.sleep(0.5)
    raise RuntimeError(f"Postgres unavailable: {last}")


async def main() -> None:
    registry = CapabilityRegistry.from_file(os.path.join(ROOT, "manifests", "capabilities.yaml"))
    nats_client = await connect_nats()
    nats_transport = NatsTransport(nats_client, event_stream=f"IFURI_EVENTS_{uuid.uuid4().hex[:8].upper()}")
    await nats_transport.ensure_event_stream(["ifuri.evt.scenario.>"])

    # Multi-runtime request/reply over NATS using logical IFURI only.
    status_cap = registry.resolve("ifuri://scenario/scenario/probe/queries/status").capability

    def status_handler(resolved, env):
        payload = Struct()
        payload.update({"status": "ready", "scenario_id": resolved.params["scenario_id"]})
        return EnvelopeCodec.create(
            target_uri=env.source_uri,
            source_uri=env.target_uri,
            kind=MessageKind.REPLY,
            payload=payload,
            correlation_id=env.id,
        )

    await nats_transport.serve_capability(status_cap, registry, status_handler, queue_group="scenario-runtime")
    runtime = IfuriRuntime(registry, {"nats": nats_transport})
    request = Struct(); request.update({})
    reply, route = await runtime.call("ifuri://scenario/scenario/docker-42/queries/status", request, timeout=5)
    status = Struct(); EnvelopeCodec.unpack(reply, status)
    assert status["status"] == "ready"
    assert route.selected_transport == "nats"

    # Postgres is authoritative ES. Event + outbox are one transaction.
    store = connect_postgres()
    stream_id = f"docker-{uuid.uuid4().hex}"
    event_payload = Struct(); event_payload.update({"success": True, "source": "docker-integration"})
    event = EnvelopeCodec.create(
        target_uri=f"ifuri://scenario/scenario/{stream_id}/events/executed",
        source_uri="ifuri://scenario/runtime/default/events/domain_event",
        kind=MessageKind.EVENT,
        payload=event_payload,
        aggregate_id=stream_id,
    )
    stored = store.append(stream_id, 0, [event])
    assert stored[0].aggregate_version == 1
    assert store.outbox_stats()["pending"] >= 1

    publish_report = await OutboxPublisher(store, nats_transport.js).publish_once(limit=100)
    assert publish_report.published >= 1
    assert store.outbox_stats()["pending"] == 0

    replay = await nats_transport.js.replay(nats_transport.event_stream)
    replayed = [EnvelopeCodec.parse(row["data_bytes"]) for row in replay]
    assert any(env.id == stored[0].id for env in replayed)

    # LLM is also a URI capability and receives only ContextDSL protobuf payload.
    inproc = InProcessTransport()
    inproc.register("llm.reasoner.analyze", build_llm_reasoner_handler("demo"))
    llm_runtime = IfuriRuntime(registry, {"inproc": inproc})
    context = compiler_from_payload({
        "name": "docker_auth_failure",
        "state": {"api_status": 401, "refresh_status": 401},
        "capabilities": {"actions": ["refresh_token"], "events": ["auth_error"]},
        "events": [
            {"source": "auth", "code": "request_unauthorized", "severity": "error", "fields": {"status": 401}},
            {"source": "auth", "code": "token_refresh_failed", "severity": "error", "fields": {"status": 401}},
        ],
    }).to_markdown()
    dsl_payload = make_dsl_document("contextdsl", context)
    llm_reply, llm_route = await llm_runtime.call(
        "ifuri://llm/reasoner/default/commands/analyze", dsl_payload
    )
    intent = DslDocument(); EnvelopeCodec.unpack(llm_reply, intent); validate_dsl_document(intent)
    assert intent.dsl_type == "intentdsl"
    assert "DO refresh_token" in intent.markdown

    # Digital twin lifecycle uses the same IFURI/Protobuf/DSL-only boundary.
    inproc.register("llm.twin.bootstrap", build_llm_twin_bootstrap_handler("demo"))
    inproc.register("llm.twin.update", build_llm_twin_update_handler("demo"))
    inproc.register("llm.builder.plan", build_llm_build_plan_handler("demo"))
    twin_intent = (
        "Build a source-backed application digital twin from user intent and Markdown documents. "
        "Preserve intent while architecture evolves through IFURI capabilities."
    )
    source_doc = make_dsl_document(
        "sourcedsl",
        source_text_dsl(twin_intent, "en", fingerprint=intent_fingerprint(twin_intent)),
    )
    twin_reply1, twin_route1 = await llm_runtime.call(
        "ifuri://llm/twin/default/commands/bootstrap", source_doc
    )
    twin1 = DslDocument(); EnvelopeCodec.unpack(twin_reply1, twin1); validate_dsl_document(twin1)
    twin_doc1 = parse_twindsl(extract_twindsl(twin1.markdown))
    assert twin_doc1.revision == 1

    source_index = build_source_index(os.getenv("SOURCES_DIR", os.path.join(ROOT, "sources"))).to_markdown()
    twin_bundle = make_dsl_document("dslbundle", twin1.markdown + "\n" + source_index)
    twin_reply2, twin_route2 = await llm_runtime.call(
        "ifuri://llm/twin/default/commands/update", twin_bundle
    )
    twin2 = DslDocument(); EnvelopeCodec.unpack(twin_reply2, twin2); validate_dsl_document(twin2)
    twin_doc2 = parse_twindsl(extract_twindsl(twin2.markdown))
    assert twin_doc2.revision == 2
    assert twin_doc2.intent_fingerprint == twin_doc1.intent_fingerprint

    plan_reply, plan_route = await llm_runtime.call(
        "ifuri://llm/builder/default/commands/plan", make_dsl_document("twindsl", twin2.markdown)
    )
    plan_doc = DslDocument(); EnvelopeCodec.unpack(plan_reply, plan_doc); validate_dsl_document(plan_doc)
    assert plan_doc.dsl_type == "buildplanddsl"

    print(json.dumps({
        "ok": True,
        "nats": {
            "server": nats_client.server_info.get("version"),
            "route": route.to_dict(),
            "jetstream": nats_transport.event_stream,
            "replayed_events": len(replayed),
        },
        "postgres": {
            "stream_id": stream_id,
            "version": store.current_version(stream_id),
            "outbox": store.outbox_stats(),
        },
        "llm": {
            "route": llm_route.to_dict(),
            "dsl_type": intent.dsl_type,
        },
        "digital_twin": {
            "bootstrap_route": twin_route1.to_dict(),
            "update_route": twin_route2.to_dict(),
            "plan_route": plan_route.to_dict(),
            "revision": twin_doc2.revision,
            "sources": len(twin_doc2.sources),
            "plan_dsl_type": plan_doc.dsl_type,
        },
    }, indent=2))

    store.close()
    await nats_transport.stop_services()
    await nats_client.close()


if __name__ == "__main__":
    asyncio.run(main())
