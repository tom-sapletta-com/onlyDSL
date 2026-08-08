from __future__ import annotations

import ast
from importlib.resources import files
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "packages/onlydsl-contracts"
CORE = ROOT / "packages/onlydsl-core"
FORBIDDEN_INTERNAL = {
    "aql", "boundary", "contextdsl", "diagnostics", "digital_twin",
    "evolution", "governance", "ifuri_core", "intentdsl", "llm_client",
    "onlydsl", "patchdsl", "server", "source_ingest", "twin_store",
}
FORBIDDEN_EXECUTION = {
    "asyncio", "http.client", "psycopg", "requests", "socket", "subprocess",
    "urllib.request",
}


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            result.add(node.module)
    return result


def test_contract_package_has_no_runtime_or_application_imports():
    failures: list[str] = []
    for path in sorted((CONTRACTS / "src/onlydsl_contracts").rglob("*.py")):
        imported = imports(path)
        roots = {name.split(".", 1)[0] for name in imported}
        invalid = roots & FORBIDDEN_INTERNAL
        execution = imported & FORBIDDEN_EXECUTION
        if invalid or execution:
            failures.append(
                f"{path.relative_to(ROOT)}: internal={sorted(invalid)}, "
                f"execution={sorted(execution)}"
            )
    assert not failures, "\n".join(failures)


def test_contract_package_is_dependency_free_and_versioned_with_runtime():
    root = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package = tomllib.loads((CONTRACTS / "pyproject.toml").read_text(encoding="utf-8"))
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert root["tool"]["uv"]["workspace"]["members"] == ["packages/*"]
    assert root["tool"]["uv"]["sources"]["onlydsl-contracts"] == {"workspace": True}
    assert root["tool"]["uv"]["sources"]["onlydsl-core"] == {"workspace": True}
    assert package["project"]["name"] == "onlydsl-contracts"
    assert package["project"]["dependencies"] == []
    assert package["project"]["version"] == expected


def test_core_package_depends_only_on_contracts_and_protobuf():
    package = tomllib.loads((CORE / "pyproject.toml").read_text(encoding="utf-8"))
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert package["project"]["name"] == "onlydsl-core"
    assert package["project"]["version"] == expected
    assert package["project"]["dependencies"] == [
        "onlydsl-contracts==0.0.8", "protobuf>=6.30,<7",
    ]


def test_core_has_no_adapter_or_application_imports():
    forbidden = FORBIDDEN_INTERNAL | {
        "asyncio", "pathlib", "psycopg", "socket", "sqlite3", "subprocess", "yaml",
    }
    failures: list[str] = []
    for path in sorted((CORE / "src/onlydsl_core").rglob("*.py")):
        imported = imports(path)
        roots = {name.split(".", 1)[0] for name in imported}
        invalid = roots & forbidden
        if invalid:
            failures.append(f"{path.relative_to(ROOT)} imports {sorted(invalid)}")
    assert not failures, "\n".join(failures)


def test_canonical_schemas_are_distributed_as_package_data():
    root = files("onlydsl_contracts").joinpath("schemas")
    assert root.joinpath("intentdsl.gbnf").read_text(encoding="utf-8").startswith(
        "# Canonical grammar"
    )
    assert "message DslDocument" in root.joinpath("ifuri/v1/dsl.proto").read_text(encoding="utf-8")
    assert "message Envelope" in root.joinpath("ifuri/v1/envelope.proto").read_text(encoding="utf-8")


def test_legacy_imports_resolve_to_the_same_contract_types():
    from ifuri_core.uri import IfUri as LegacyIfUri
    from onlydsl.dsl.assumption import AssumptionDocument as LegacyAssumption
    from onlydsl.ssot.model import SsotManifest as LegacySsotManifest
    from onlydsl_contracts.dsl.assumption import AssumptionDocument
    from onlydsl_contracts.ifuri import IfUri
    from onlydsl_contracts.ssot import SsotManifest

    assert LegacyIfUri is IfUri
    assert LegacyAssumption is AssumptionDocument
    assert LegacySsotManifest is SsotManifest


def test_legacy_ifuri_core_imports_resolve_to_extracted_core():
    from ifuri_core.cqrs import AggregateRoot as LegacyAggregateRoot
    from ifuri_core.dsl_document import make_dsl_document as legacy_make_dsl_document
    from ifuri_core.envelope import EnvelopeCodec as LegacyEnvelopeCodec
    from ifuri_core.manifest import CapabilityRegistry as FileCapabilityRegistry
    from ifuri_core.runtime import IfuriRuntime as LegacyIfuriRuntime
    from onlydsl_core.capabilities import CapabilityRegistry
    from onlydsl_core.cqrs import AggregateRoot
    from onlydsl_core.dsl_document import make_dsl_document
    from onlydsl_core.envelope import EnvelopeCodec
    from onlydsl_core.runtime import IfuriRuntime

    assert LegacyAggregateRoot is AggregateRoot
    assert legacy_make_dsl_document is make_dsl_document
    assert LegacyEnvelopeCodec is EnvelopeCodec
    assert LegacyIfuriRuntime is IfuriRuntime
    assert issubclass(FileCapabilityRegistry, CapabilityRegistry)
