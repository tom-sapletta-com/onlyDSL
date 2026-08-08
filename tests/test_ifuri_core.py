import asyncio
import unittest
from pathlib import Path
import sys

from google.protobuf.struct_pb2 import Struct

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from boundary import LlmBoundaryError  # noqa: E402
from contextdsl import compiler_from_payload  # noqa: E402
from ifuri_core.dsl_document import make_dsl_document, validate_dsl_document  # noqa: E402
from ifuri_core.dsl_pb2 import DslDocument  # noqa: E402
from ifuri_core.envelope import EnvelopeCodec, EnvelopeError, MessageKind  # noqa: E402
from ifuri_core.event_store import ConcurrencyError, SqliteEventStore  # noqa: E402
from ifuri_core.llm_gateway import build_llm_reasoner_handler  # noqa: E402
from ifuri_core.manifest import Capability, CapabilityRegistry, ManifestError, TransportPolicy  # noqa: E402
from ifuri_core.runtime import IfuriRuntime  # noqa: E402
from ifuri_core.transport import InProcessTransport  # noqa: E402
from ifuri_core.uri import IfUri, IfUriError  # noqa: E402


class IfUriTests(unittest.TestCase):
    def test_canonical_uri_and_nats_subject(self):
        uri = IfUri.parse("ifuri://hardware/motor/tic249/commands/start")
        self.assertEqual(str(uri), "ifuri://hardware/motor/tic249/commands/start")
        self.assertEqual(uri.to_subject(), "ifuri.cmd.hardware.motor.tic249.start")

    def test_uri_forbids_transport_location_features(self):
        for raw in (
            "ifuri://hardware:4222/motor/tic249/commands/start",
            "ifuri://hardware/motor/tic249/commands/start?transport=nats",
            "http://hardware/motor/tic249/commands/start",
        ):
            with self.assertRaises(IfUriError, msg=raw):
                IfUri.parse(raw)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.registry = CapabilityRegistry.from_file(ROOT / "manifests" / "capabilities.yaml")

    def test_resolver_is_deterministic_and_inspectable(self):
        resolved = self.registry.resolve("ifuri://scenario/scenario/abc123/queries/status")
        self.assertEqual(resolved.capability.id, "scenario.status")
        self.assertEqual(resolved.params, {"scenario_id": "abc123"})
        explain = self.registry.explain(str(resolved.uri))
        self.assertEqual(explain["selected"], "scenario.status")
        self.assertTrue(any(row["matched"] for row in explain["candidates"]))

    def test_ambiguous_patterns_fail_closed(self):
        caps = [
            Capability("demo.one", "ifuri://demo/item/{id}/queries/read", message_kind="query"),
            Capability("demo.two", "ifuri://demo/item/{x}/queries/read", message_kind="query"),
        ]
        registry = CapabilityRegistry(caps)
        with self.assertRaises(ManifestError):
            registry.resolve("ifuri://demo/item/42/queries/read")


class EnvelopeTests(unittest.TestCase):
    def test_protobuf_roundtrip_with_typed_payload(self):
        payload = Struct()
        payload.update({"scenario_id": "s1", "dry_run": True})
        env = EnvelopeCodec.create(
            target_uri="ifuri://scenario/scenario/s1/commands/execute",
            source_uri="ifuri://client/ui/default/commands/request",
            kind=MessageKind.COMMAND,
            payload=payload,
            correlation_id="corr-1",
        )
        parsed = EnvelopeCodec.parse(EnvelopeCodec.serialize(env))
        out = Struct()
        EnvelopeCodec.unpack(parsed, out)
        self.assertEqual(out["scenario_id"], "s1")
        self.assertEqual(parsed.correlation_id, "corr-1")
        self.assertIn("google.protobuf.Struct", parsed.payload.type_url)

    def test_kind_must_match_target_uri(self):
        with self.assertRaises(EnvelopeError):
            EnvelopeCodec.create(
                target_uri="ifuri://scenario/scenario/s1/events/executed",
                source_uri="ifuri://client/ui/default/commands/request",
                kind=MessageKind.COMMAND,
            )


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.registry = CapabilityRegistry.from_file(ROOT / "manifests" / "capabilities.yaml")
        self.inproc = InProcessTransport()
        self.runtime = IfuriRuntime(self.registry, {"inproc": self.inproc})

    async def test_manifest_transport_fallback(self):
        def handler(resolved, env):
            out = Struct(); out.update({"status": "ready", "id": resolved.params["scenario_id"]})
            return EnvelopeCodec.create(
                target_uri=env.source_uri,
                source_uri=env.target_uri,
                kind=MessageKind.REPLY,
                payload=out,
                correlation_id=env.id,
            )

        self.inproc.register("scenario.status", handler)
        payload = Struct(); payload.update({})
        reply, decision = await self.runtime.call(
            "ifuri://scenario/scenario/s9/queries/status", payload
        )
        out = Struct(); EnvelopeCodec.unpack(reply, out)
        self.assertEqual(out["status"], "ready")
        self.assertEqual(decision.selected_transport, "inproc")
        self.assertEqual(decision.attempted[0]["transport"], "nats")
        self.assertEqual(decision.attempted[0]["result"], "unavailable")

    async def test_llm_is_only_reachable_as_dsl_capability(self):
        self.inproc.register("llm.reasoner.analyze", build_llm_reasoner_handler("demo"))
        context = compiler_from_payload({
            "name": "auth_failure",
            "state": {"api_status": 401, "refresh_status": 401},
            "capabilities": {"actions": ["refresh_token"], "events": ["auth_error"]},
            "events": [
                {"source": "auth", "code": "request_unauthorized", "severity": "error", "fields": {"status": 401}},
                {"source": "auth", "code": "token_refresh_failed", "severity": "error", "fields": {"status": 401}},
            ],
        }).to_markdown()
        doc = make_dsl_document("contextdsl", context)
        reply, decision = await self.runtime.call(
            "ifuri://llm/reasoner/default/commands/analyze", doc
        )
        out = DslDocument(); EnvelopeCodec.unpack(reply, out); validate_dsl_document(out)
        self.assertEqual(out.dsl_type, "intentdsl")
        self.assertIn("```intentdsl", out.markdown)
        self.assertEqual(decision.selected_transport, "inproc")

        bad = make_dsl_document("contextdsl", "raw prose\n```contextdsl\nCONTEXT x\nEND_CONTEXT\n```")
        with self.assertRaises(LlmBoundaryError):
            await self.runtime.call("ifuri://llm/reasoner/default/commands/analyze", bad)


class EventStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = SqliteEventStore(":memory:")

    def tearDown(self):
        self.store.close()

    def _event(self, event_id=None):
        payload = Struct(); payload.update({"success": True})
        return EnvelopeCodec.create(
            target_uri="ifuri://scenario/scenario/s1/events/executed",
            source_uri="ifuri://scenario/runtime/default/events/domain_event",
            kind=MessageKind.EVENT,
            payload=payload,
            message_id=event_id,
            aggregate_id="s1",
        )

    def test_event_and_outbox_commit_atomically(self):
        stored = self.store.append("s1", 0, [self._event()])
        self.assertEqual(stored[0].aggregate_version, 1)
        self.assertEqual(self.store.current_version("s1"), 1)
        self.assertEqual(self.store.outbox_stats(), {"total": 1, "pending": 1})
        self.assertEqual(len(self.store.load_stream("s1")), 1)

    def test_optimistic_concurrency(self):
        self.store.append("s1", 0, [self._event()])
        with self.assertRaises(ConcurrencyError):
            self.store.append("s1", 0, [self._event()])
        self.assertEqual(self.store.outbox_stats(), {"total": 1, "pending": 1})


if __name__ == "__main__":
    unittest.main()

class ArtifactTests(unittest.TestCase):
    def test_logical_artifact_uri_maps_to_file_placement(self):
        import tempfile
        from ifuri_core.artifacts import LocalFileArtifactStore
        with tempfile.TemporaryDirectory() as td:
            store = LocalFileArtifactStore(td)
            logical = "ifuri://artifact/document/spec42/artifacts/content"
            physical = store.put(logical, b"abc")
            self.assertTrue(physical.startswith("file://"))
            self.assertEqual(store.get(logical), b"abc")
