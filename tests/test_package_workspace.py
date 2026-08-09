from __future__ import annotations

import ast
import importlib.util
from importlib.resources import files
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "packages/onlydsl-contracts"
CORE = ROOT / "packages/onlydsl-core"
SSOT = ROOT / "packages/onlydsl-ssot"
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
    assert root["tool"]["uv"]["sources"]["onlydsl-ssot"] == {"workspace": True}
    assert package["project"]["name"] == "onlydsl-contracts"
    assert package["project"]["dependencies"] == []
    assert package["project"]["version"] == expected
    assert root["project"]["dependencies"][:3] == [
        "onlydsl-contracts>=0.0.10,<0.1",
        "onlydsl-core>=0.0.10,<0.1",
        "onlydsl-ssot>=0.0.10,<0.1",
    ]


def test_release_pipeline_covers_every_workspace_distribution():
    script = ROOT / "scripts/workspace_release.py"
    spec = importlib.util.spec_from_file_location("onlydsl_workspace_release", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert [item.name for item in module.DISTRIBUTIONS] == [
        "onlydsl-contracts", "onlydsl-core", "onlydsl-ssot", "onlyDSL",
    ]
    module.verify_versions((ROOT / "VERSION").read_text(encoding="utf-8").strip())


def test_core_package_depends_only_on_contracts_and_protobuf():
    package = tomllib.loads((CORE / "pyproject.toml").read_text(encoding="utf-8"))
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert package["project"]["name"] == "onlydsl-core"
    assert package["project"]["version"] == expected
    assert package["project"]["dependencies"] == [
        "onlydsl-contracts>=0.0.10,<0.1", "protobuf>=6.30,<7",
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


def test_ssot_package_depends_only_on_contracts():
    package = tomllib.loads((SSOT / "pyproject.toml").read_text(encoding="utf-8"))
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert package["project"]["name"] == "onlydsl-ssot"
    assert package["project"]["version"] == expected
    assert package["project"]["dependencies"] == ["onlydsl-contracts>=0.0.10,<0.1"]


def test_ssot_package_has_no_domain_runtime_or_execution_imports():
    failures: list[str] = []
    for path in sorted((SSOT / "src/onlydsl_ssot").rglob("*.py")):
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


def test_extracted_ssot_supports_an_independent_promotion_cycle(tmp_path):
    from onlydsl_contracts.ssot import PromotionApproval
    from onlydsl_ssot import SsotStore

    store = SsotStore(tmp_path)
    before = store.initialize("package-demo")
    candidate = store.create_candidate(
        candidate_id="candidate-package",
        updates={"intent/intent.dsl": b"INTENT package-demo\nEND_INTENT\n"},
    )
    assert store.validate_candidate(candidate.candidate_id).ok
    receipt_hash = "a" * 64
    after = store.promote(candidate.candidate_id, PromotionApproval(
        authority_contract_hash="sha256:" + "b" * 64,
        testql_receipts=("urn:subactor:testql:sha256:" + receipt_hash,),
        eql_receipts=("urn:subactor:eql:sha256:" + receipt_hash,),
    ))
    assert after.parent_hash == before.revision_hash
    assert store.verified_manifest() == after
    assert len(store.history()) == 2


def test_ssot_baseline_validator_rejects_authority_and_leaves_domain_state_unverified(tmp_path):
    from onlydsl_ssot.validation import basic_validate_tree

    tree = tmp_path / "tree"
    (tree / "authority").mkdir(parents=True)
    (tree / "authority/contract.aql").write_text("PROFILE aql:contract/v1\n", encoding="utf-8")
    _, issues, integrity, completeness = basic_validate_tree(tree)
    assert issues == ("AUTHORITY_PATH_FORBIDDEN:authority/contract.aql",)
    assert integrity is None
    assert completeness is None


def test_ssot_store_uses_an_injected_domain_validator(tmp_path):
    from onlydsl_ssot import SsotStore
    from onlydsl_ssot.validation import basic_validate_tree

    calls: list[Path] = []

    def domain_validator(tree: Path):
        calls.append(tree)
        files, issues, _, _ = basic_validate_tree(tree)
        return files, issues, "pass", "incomplete"

    store = SsotStore(tmp_path, validator=domain_validator)
    store.initialize("injected-demo")
    candidate = store.create_candidate(
        candidate_id="candidate-injected",
        updates={"intent/intent.dsl": b"INTENT injected-demo\nEND_INTENT\n"},
    )
    report = store.validate_candidate(candidate.candidate_id)
    assert calls
    assert report.integrity == "pass"
    assert report.completeness == "incomplete"


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


def test_legacy_ssot_imports_use_extracted_storage_with_domain_composition():
    from onlydsl.ssot.reader import SsotReader as LegacyReader
    from onlydsl.ssot.writer import SsotStore as LegacyStore
    from onlydsl_ssot.reader import SsotReader
    from onlydsl_ssot.writer import SsotStore

    assert LegacyReader is SsotReader
    assert issubclass(LegacyStore, SsotStore)
