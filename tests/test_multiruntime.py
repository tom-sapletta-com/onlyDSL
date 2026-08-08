import json
import shutil
import subprocess
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ifuri_core.uri import IfUri  # noqa: E402


class MultiRuntimeParityTests(unittest.TestCase):
    def test_python_node_php_subject_parity(self):
        uri = "ifuri://scenario/scenario/abc-42/queries/status"
        expected = {"canonical": str(IfUri.parse(uri)), "subject": IfUri.parse(uri).to_subject()}
        if shutil.which("node"):
            raw = subprocess.check_output(["node", str(ROOT/"multiruntime/javascript/ifuri.mjs"), uri], text=True)
            self.assertEqual(json.loads(raw), expected)
        if shutil.which("php"):
            raw = subprocess.check_output(["php", str(ROOT/"multiruntime/php/ifuri.php"), uri], text=True)
            self.assertEqual(json.loads(raw), expected)


if __name__ == "__main__":
    unittest.main()
