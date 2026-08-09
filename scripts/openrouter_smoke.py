from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from boundary import source_text_dsl  # noqa: E402
from digital_twin import extract_twindsl, intent_fingerprint, parse_twindsl  # noqa: E402
from source_ingest import build_source_index  # noqa: E402
from ifuri_core.dsl_document import make_dsl_document  # noqa: E402
from ifuri_core.dsl_pb2 import DslDocument  # noqa: E402
from ifuri_core.envelope import EnvelopeCodec  # noqa: E402
from ifuri_core.llm_gateway import (  # noqa: E402
    build_llm_build_plan_handler,
    build_llm_twin_bootstrap_handler,
    build_llm_twin_update_handler,
    gateway_provider_status,
)
from ifuri_core.manifest import CapabilityRegistry  # noqa: E402
from ifuri_core.runtime import IfuriRuntime  # noqa: E402
from ifuri_core.transport import InProcessTransport  # noqa: E402


def unpack(reply) -> DslDocument:
    out = DslDocument()
    EnvelopeCodec.unpack(reply, out)
    return out


def main() -> int:
    if not os.getenv("OPENROUTER_API_KEY"):
        print("OPENROUTER_SMOKE_SKIPPED: OPENROUTER_API_KEY is not set")
        return 2

    backend = "openrouter"
    print("PROVIDER", gateway_provider_status(backend))
    registry = CapabilityRegistry.from_file(ROOT / "manifests" / "capabilities.yaml")
    inproc = InProcessTransport()
    inproc.register("llm.twin.bootstrap", build_llm_twin_bootstrap_handler(backend))
    inproc.register("llm.twin.update", build_llm_twin_update_handler(backend))
    inproc.register("llm.builder.plan", build_llm_build_plan_handler(backend))
    runtime = IfuriRuntime(registry, {"inproc": inproc})

    intent = (
        "Build a web application that converts a few sentences of user intent into a durable "
        "digital twin of the application. The twin must evolve from Markdown documents in sources/ "
        "without violating the original intent. Use IFURI, Protobuf, CQRS/Event Sourcing and a DSL-only LLM boundary."
    )
    source = make_dsl_document("sourcedsl", source_text_dsl(intent, "en", fingerprint=intent_fingerprint(intent)))
    reply1, route1 = asyncio.run(runtime.call("ifuri://llm/twin/default/commands/bootstrap", source))
    twin1 = unpack(reply1).markdown
    doc1 = parse_twindsl(extract_twindsl(twin1))
    print("BOOTSTRAP_OK", {"revision": doc1.revision, "nodes": len(doc1.nodes), "transport": route1.selected_transport})

    index = build_source_index(os.getenv("SOURCES_DIR", str(ROOT / "sources")))
    bundle = make_dsl_document("dslbundle", twin1 + "\n" + index.to_markdown())
    reply2, route2 = asyncio.run(runtime.call("ifuri://llm/twin/default/commands/update", bundle))
    twin2 = unpack(reply2).markdown
    doc2 = parse_twindsl(extract_twindsl(twin2))
    print("UPDATE_OK", {"revision": doc2.revision, "sources": len(doc2.sources), "transport": route2.selected_transport})

    reply3, route3 = asyncio.run(
        runtime.call("ifuri://llm/builder/default/commands/plan", make_dsl_document("twindsl", twin2))
    )
    plan = unpack(reply3)
    print("PLAN_OK", {"dsl_type": plan.dsl_type, "transport": route3.selected_transport})
    print("OPENROUTER_SMOKE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
