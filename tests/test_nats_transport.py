import asyncio
import json
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ifuri_core.transport import NatsWireClient, capability_pattern_to_subject  # noqa: E402


class _FakeNatsBroker:
    def __init__(self):
        self.server = None
        self.port = 0

    async def start(self):
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def close(self):
        self.server.close()
        await self.server.wait_closed()

    async def _handle(self, reader, writer):
        writer.write(b'INFO {"server_id":"fake","version":"0.1"}\r\n')
        await writer.drain()
        subs = {}
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                line = line.rstrip(b"\r\n")
                if line.startswith(b"CONNECT "):
                    continue
                if line == b"PING":
                    writer.write(b"PONG\r\n"); await writer.drain(); continue
                if line.startswith(b"SUB "):
                    parts = line.split()
                    subject = parts[1].decode()
                    sid = int(parts[-1])
                    subs[sid] = subject
                    continue
                if line.startswith(b"UNSUB "):
                    continue
                if line.startswith(b"PUB "):
                    parts = line.split()
                    subject = parts[1].decode()
                    if len(parts) == 3:
                        reply = ""; size = int(parts[2])
                    else:
                        reply = parts[2].decode(); size = int(parts[3])
                    data = await reader.readexactly(size)
                    await reader.readexactly(2)
                    # Echo normal pub to exact subscribers (used by connect flush).
                    for sid, sub in list(subs.items()):
                        if sub == subject:
                            writer.write(f"MSG {subject} {sid} {len(data)}\r\n".encode() + data + b"\r\n")
                    # For request/reply, synthesize a response to the inbox.
                    if reply:
                        for sid, sub in list(subs.items()):
                            if sub == reply:
                                response = b"reply:" + data
                                writer.write(f"MSG {reply} {sid} {len(response)}\r\n".encode() + response + b"\r\n")
                    await writer.drain()
                    continue
        finally:
            writer.close()
            await writer.wait_closed()


class NatsWireTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.broker = _FakeNatsBroker()
        await self.broker.start()

    async def asyncTearDown(self):
        await self.broker.close()

    async def test_core_request_reply_wire_protocol(self):
        client = NatsWireClient("127.0.0.1", self.broker.port, "test")
        await client.connect()
        try:
            result = await client.request("svc.echo", b"abc")
            self.assertEqual(result, b"reply:abc")
            self.assertEqual(client.server_info["server_id"], "fake")
        finally:
            await client.close()

    def test_capability_pattern_maps_to_nats_wildcard(self):
        subject = capability_pattern_to_subject(
            "ifuri://scenario/scenario/{scenario_id}/queries/status"
        )
        self.assertEqual(subject, "ifuri.qry.scenario.scenario.*.status")


if __name__ == "__main__":
    unittest.main()
