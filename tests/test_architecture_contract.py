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
        self.assertEqual(metadata["project"]["requires-python"], ">=3.10")
        self.assertIn("version", metadata["project"]["dynamic"])
        self.assertIn("server", metadata["tool"]["setuptools"]["py-modules"])
        self.assertEqual(metadata["project"]["scripts"]["onlydsl"], "onlydsl.cli:main")

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertFalse(metadata["tool"]["costs"]["badge"])
        self.assertFalse(metadata["tool"]["costs"]["update_readme"])
        self.assertIn(f"version-{expected}-blue", readme)
        self.assertIn("python-3.10+-blue", readme)

    def test_goal_preserves_the_atomic_workspace_release_strategy(self):
        config = yaml.safe_load((ROOT / "goal.yaml").read_text(encoding="utf-8"))
        strategy = config["strategies"]["python"]
        self.assertEqual(
            strategy["build"],
            "python scripts/workspace_release.py build",
        )
        self.assertEqual(
            strategy["publish"],
            "ONLYDSL_DISTRIBUTION=onlyDSL python scripts/workspace_release.py publish",
        )
        self.assertEqual(config["strategies"]["nodejs"]["publish"], "npm publish")
        self.assertEqual(config["strategies"]["rust"]["publish"], "cargo publish")

    def test_no_grpc_foundation_dependency(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
        self.assertNotIn("grpc", requirements)
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8").lower()
        self.assertNotIn("grpc", compose)

    def test_docker_image_installs_onlydsl_cli_entrypoint(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("./packages/onlydsl-contracts", dockerfile)
        self.assertIn("./packages/onlydsl-core", dockerfile)
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

    def test_compose_command_scripts_exist_in_the_source_tree(self):
        raw = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
        referenced: set[Path] = set()
        for service in raw["services"].values():
            command = service.get("command", [])
            if isinstance(command, list):
                referenced.update(
                    ROOT / item for item in command if str(item).startswith("scripts/")
                )
        self.assertTrue(referenced)
        missing = [str(path.relative_to(ROOT)) for path in sorted(referenced) if not path.is_file()]
        self.assertEqual(missing, [])

    def test_generated_analysis_uses_clone_independent_project_identity(self):
        calls = (ROOT / "project/calls.yaml").read_text(encoding="utf-8")
        context = (ROOT / "project/context.md").read_text(encoding="utf-8")
        tickets = (ROOT / "project/planfile-tickets.yaml").read_text(encoding="utf-8")
        prompt = (ROOT / "project/prompt.txt").read_text(encoding="utf-8")
        self.assertTrue(calls.startswith("project: .\n"))
        self.assertIn("- **Project**: .", context)
        self.assertIn("project_root: .", tickets)
        self.assertIn("project path: onlyDSL", prompt)
        for content in (calls, context, tickets, prompt):
            self.assertNotIn(str(ROOT), content)
            self.assertNotIn("/tmp/onlydsl-clean-tree.", content)

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
        excluded_directories = {".git", ".venv", "build", "dist", "project", "runtime"}
        offenders = []
        for path in ROOT.rglob("*.py"):
            if (
                excluded_directories.intersection(path.relative_to(ROOT).parts)
                or "tests" in path.parts
                or path.name in allowed
            ):
                continue
            text = path.read_text(encoding="utf-8")
            if "from llm_client import" in text or "import llm_client" in text:
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
