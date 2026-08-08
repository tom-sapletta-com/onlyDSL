import unittest
from pathlib import Path
import sys
import tomllib
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ifuri_core.manifest import CapabilityRegistry  # noqa: E402


class ArchitectureContractTests(unittest.TestCase):
    def test_runtime_release_version_comes_from_version_file(self):
        from server import _application_version

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "VERSION").write_text("9.8.7\n", encoding="utf-8")
            self.assertEqual(_application_version(root), "9.8.7")

    def test_python_project_has_installable_package_metadata(self):
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(metadata["build-system"]["build-backend"], "setuptools.build_meta")
        self.assertEqual(metadata["project"]["name"], "onlyDSL")
        self.assertIn("version", metadata["project"]["dynamic"])
        self.assertIn("server", metadata["tool"]["setuptools"]["py-modules"])
        self.assertEqual(metadata["project"]["scripts"]["onlydsl"], "onlydsl.cli:main")

    def test_no_grpc_foundation_dependency(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
        self.assertNotIn("grpc", requirements)
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8").lower()
        self.assertNotIn("grpc", compose)

    def test_docker_image_installs_onlydsl_cli_entrypoint(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("pip install --no-cache-dir --no-deps ./packages/onlydsl-contracts .", dockerfile)
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(metadata["project"]["scripts"]["onlydsl"], "onlydsl.cli:main")

    def test_compose_contains_real_fabric_and_authoritative_store(self):
        raw = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
        services = raw["services"]
        self.assertIn("nats", services)
        self.assertIn("postgres", services)
        self.assertIn("integration", services)
        self.assertTrue(str(services["nats"]["image"]).startswith("nats:"))
        self.assertTrue(str(services["postgres"]["image"]).startswith("postgres:"))

    def test_all_manifest_routes_are_logical_ifuri_not_transport_uris(self):
        registry = CapabilityRegistry.from_file(ROOT / "manifests" / "capabilities.yaml")
        for row in registry.dump():
            uri = row["uri_pattern"]
            self.assertTrue(uri.startswith("ifuri://"), uri)
            self.assertNotIn(":4222", uri)
            self.assertNotIn("http://", uri)
            self.assertNotIn("nats://", uri)

    def test_domain_code_does_not_call_llm_client_directly(self):
        allowed = {"llm_client.py", "llm_gateway.py"}
        offenders = []
        for path in ROOT.rglob("*.py"):
            if "tests" in path.parts or path.name in allowed:
                continue
            text = path.read_text(encoding="utf-8")
            if "from llm_client import" in text or "import llm_client" in text:
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
