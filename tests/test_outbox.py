import unittest
from pathlib import Path
import sys

from google.protobuf.struct_pb2 import Struct

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ifuri_core.envelope import EnvelopeCodec, MessageKind  # noqa: E402
from ifuri_core.event_store import SqliteEventStore  # noqa: E402
from ifuri_core.outbox import OutboxPublisher  # noqa: E402


class _FakeJetStream:
    def __init__(self):
        self.items = []

    async def publish(self, subject, data):
        self.items.append((subject, data))
        return {"stream": "TEST", "seq": len(self.items)}


class OutboxTests(unittest.IsolatedAsyncioTestCase):
    async def test_outbox_publishes_only_after_authoritative_commit(self):
        store = SqliteEventStore(":memory:")
        payload = Struct(); payload.update({"success": True})
        event = EnvelopeCodec.create(
            target_uri="ifuri://scenario/scenario/s1/events/executed",
            source_uri="ifuri://scenario/runtime/default/events/domain_event",
            kind=MessageKind.EVENT,
            payload=payload,
            aggregate_id="s1",
        )
        store.append("s1", 0, [event])
        self.assertEqual(store.outbox_stats()["pending"], 1)
        js = _FakeJetStream()
        report = await OutboxPublisher(store, js).publish_once()
        self.assertEqual(report.published, 1)
        self.assertEqual(store.outbox_stats()["pending"], 0)
        self.assertEqual(len(store.load_stream("s1")), 1)
        self.assertEqual(js.items[0][0], "ifuri.evt.scenario.scenario.s1.executed")
        store.close()


if __name__ == "__main__":
    unittest.main()
