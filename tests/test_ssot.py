from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from onlydsl.dsl.claim import parse_claims, render_claims
from onlydsl.dsl.trust import parse_trust_policy, render_trust_policy
from onlydsl.ssot.cli import main as ssot_cli
from onlydsl.ssot.manifest import create_manifest, parse_manifest, render_manifest
from onlydsl.ssot.model import PromotionApproval, SsotConflict, SsotValidationError
from onlydsl.ssot.registry import ProjectRegistry, parse_registry, render_registry
from onlydsl.ssot.writer import SsotStore


AUTHORITY_HASH = "sha256:" + "a" * 64
TESTQL_RECEIPT = "urn:subactor:testql:sha256:" + "b" * 64
EQL_RECEIPT = "urn:subactor:eql:sha256:" + "c" * 64


def approval(*, incomplete: bool = False, integrity: str = "pass") -> PromotionApproval:
    return PromotionApproval(
        AUTHORITY_HASH, (TESTQL_RECEIPT,), (EQL_RECEIPT,), integrity,
        "incomplete" if incomplete else "complete", incomplete,
    )


def integrity_dsl(result: str = "PASS", completeness: str = "INCOMPLETE") -> bytes:
    return f"""```projectintegritydsl
PROJECT_INTEGRITY demo
METHOD deterministic-cross-layer
COVERAGE LAYERS 1/1 DEPENDENCIES 1/1 PARAMETERS 1/1 ASSUMPTIONS 0/0
COMPLETENESS {completeness}
RESULT {result}
END_PROJECT_INTEGRITY
```
""".encode()


class SsotTests(unittest.TestCase):
    CLAIM_DSL = """```claimdsl
CLAIM_SET laboratory
CLAIM lid-width
  SUBJECT twin://laboratory/component/lid
  PREDICATE width
  VALUE 0.0765
  UNIT m
  SOURCE_URI urn:subactor:resource:sha256:abc
  SOURCE_HASH sha256:1111111111111111111111111111111111111111111111111111111111111111
  SOURCE_REVISION "cad-r3"
  SOURCE_ANCHOR "body:1/bbox:x"
  EVIDENCE_KIND cad
  QUALITY 0.98
  TRUST customer-certified
  GENERATED_BY deterministic:cad-extractor/v2
  VALIDATED_BY deterministic:geometry-validation/v1
  STATUS accepted
  ACCEPTED_AT "2026-08-08T18:30:00Z"
  SUPERSEDES ["lid-width-conceptual"]
END_CLAIM
END_CLAIM_SET
```"""

    TRUST_DSL = """```trustdsl
TRUST_POLICY laboratory
ROLE measured
  PRIORITY 95
  CAN_DEFINE ["physical-state", "geometry"]
END_ROLE
ROLE web-research
  PRIORITY 40
  CAN_DEFINE ["research"]
END_ROLE
END_TRUST_POLICY
```"""

    def test_claim_is_first_class_versioned_evidence(self):
        document = parse_claims(self.CLAIM_DSL)
        claim = document.claims[0]
        self.assertEqual(claim.status, "accepted")
        self.assertEqual(str(claim.quality), "0.98")
        self.assertEqual(claim.supersedes, ("lid-width-conceptual",))
        self.assertEqual(parse_claims(render_claims(document)), document)

    def test_accepted_claim_cannot_use_model_as_its_only_validator(self):
        invalid = self.CLAIM_DSL.replace(
            "VALIDATED_BY deterministic:geometry-validation/v1", "VALIDATED_BY llm:openrouter",
        )
        with self.assertRaisesRegex(ValueError, "requires deterministic validation"):
            parse_claims(invalid)

    def test_trust_policy_ranks_domains_without_resolving_conflicts_itself(self):
        policy = parse_trust_policy(self.TRUST_DSL)
        self.assertEqual(policy.priority_for("measured", "geometry"), 95)
        self.assertIsNone(policy.priority_for("web-research", "geometry"))
        self.assertEqual(parse_trust_policy(render_trust_policy(policy)), policy)

    def test_manifest_is_merkle_like_and_timestamp_does_not_change_revision(self):
        files = {"intent/intent.dsl": "sha256:" + "1" * 64, "twin/twin.dsl": "sha256:" + "2" * 64}
        first = create_manifest("demo", files, created_at="2026-01-01T00:00:00Z")
        second = create_manifest("demo", files, created_at="2027-01-01T00:00:00Z")
        self.assertEqual(first.revision_hash, second.revision_hash)
        self.assertNotEqual(first.created_at, second.created_at)
        parsed = parse_manifest(render_manifest(first))
        self.assertEqual(parsed, first)
        self.assertEqual(set(parsed.sections), {"intent", "twin"})

    def test_init_separates_accepted_truth_from_authority_and_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            store = SsotStore(td)
            manifest = store.initialize("demo")
            self.assertTrue((Path(td) / "SSOT/current/project.projectdsl").is_file())
            self.assertTrue((Path(td) / ".onlydsl/authority/grants").is_dir())
            self.assertFalse((Path(td) / "SSOT/current/authority").exists())
            self.assertEqual(store.verified_manifest().revision_hash, manifest.revision_hash)
            self.assertEqual(len(store.history()), 1)

    def test_candidate_diff_validation_and_authorized_promotion(self):
        with tempfile.TemporaryDirectory() as td:
            store = SsotStore(td)
            before = store.initialize("demo")
            candidate = store.create_candidate(
                candidate_id="candidate-intent",
                updates={"intent/intent.dsl": b"INTENT demo\nGOAL accepted\nEND_INTENT\n"},
                evidence_uris=("urn:subactor:git:sha256:" + "d" * 64,),
            )
            report = store.validate_candidate(candidate.candidate_id)
            self.assertTrue(report.ok, report.issues)
            diff = store.candidate_diff(candidate.candidate_id)
            self.assertIn('CHANGE "intent/intent.dsl" OPERATION add', diff)
            after = store.promote(candidate.candidate_id, approval())
            self.assertEqual(after.parent_hash, before.revision_hash)
            self.assertEqual(after.integrity, "pass")
            self.assertEqual((Path(td) / "SSOT/current/intent/intent.dsl").read_text(), "INTENT demo\nGOAL accepted\nEND_INTENT\n")
            self.assertEqual(len(store.history()), 2)
            self.assertTrue((Path(td) / "SSOT/receipts/mutation" / (after.revision_hash.split(":")[1] + ".json")).is_file())

    def test_candidate_can_remove_an_accepted_file_and_initial_diff_is_exact(self):
        with tempfile.TemporaryDirectory() as td:
            store = SsotStore(td)
            store.initialize("demo")
            added = store.create_candidate(
                candidate_id="candidate-add-removable",
                updates={"intent/removable.dsl": b"INTENT removable\nEND_INTENT\n"},
            )
            store.promote(added.candidate_id, approval())
            removed = store.create_candidate(
                candidate_id="candidate-remove-accepted",
                removals=("intent/removable.dsl",),
            )
            initial_diff = (
                Path(td) / "SSOT/candidate/candidate-remove-accepted/semantic.diff.dsl"
            ).read_text(encoding="utf-8")
            self.assertIn('CHANGE "intent/removable.dsl" OPERATION remove', initial_diff)
            self.assertNotIn('CHANGE "project.projectdsl"', initial_diff)
            self.assertTrue(store.validate_candidate(removed.candidate_id).ok)

    def test_candidate_evidence_must_be_an_immutable_urn(self):
        with tempfile.TemporaryDirectory() as td:
            store = SsotStore(td)
            store.initialize("demo")
            with self.assertRaisesRegex(SsotValidationError, "immutable urn"):
                store.create_candidate(
                    updates={"intent/a.dsl": b"A\n"},
                    evidence_uris=("file:///tmp/mutable-result.json",),
                )
            with self.assertRaisesRegex(SsotValidationError, "immutable urn"):
                store.create_candidate(
                    updates={"intent/b.dsl": b"B\n"},
                    evidence_uris=("urn:subactor:todo2code:latest",),
                )

    def test_incomplete_integrity_requires_explicit_grant_but_may_be_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            store = SsotStore(td)
            store.initialize("demo")
            candidate = store.create_candidate(
                candidate_id="candidate-incomplete",
                updates={"integrity/project-integrity.dsl": integrity_dsl()},
            )
            with self.assertRaisesRegex(SsotValidationError, "INCOMPLETE_REQUIRES_EXPLICIT_GRANT"):
                store.promote(candidate.candidate_id, approval())
            manifest = store.promote(candidate.candidate_id, approval(incomplete=True))
            self.assertEqual(manifest.integrity, "pass")
            self.assertEqual(manifest.completeness, "incomplete")

    def test_failed_integrity_can_never_be_promoted_by_declared_approval(self):
        with tempfile.TemporaryDirectory() as td:
            store = SsotStore(td)
            store.initialize("demo")
            candidate = store.create_candidate(
                candidate_id="candidate-failed",
                updates={"integrity/project-integrity.dsl": integrity_dsl("FAIL")},
            )
            with self.assertRaisesRegex(SsotValidationError, "REQUIRES_INTEGRITY_PASS"):
                store.promote(candidate.candidate_id, approval(incomplete=True))

    def test_stale_candidate_is_rejected_after_another_promotion(self):
        with tempfile.TemporaryDirectory() as td:
            store = SsotStore(td)
            store.initialize("demo")
            first = store.create_candidate(candidate_id="candidate-first", updates={"intent/a.dsl": b"A\n"})
            stale = store.create_candidate(candidate_id="candidate-stale", updates={"intent/b.dsl": b"B\n"})
            store.promote(first.candidate_id, approval())
            with self.assertRaisesRegex(SsotConflict, "STALE_BASE_REVISION"):
                store.promote(stale.candidate_id, approval())

    def test_candidate_cannot_contain_authority_or_aql_contract(self):
        with tempfile.TemporaryDirectory() as td:
            store = SsotStore(td)
            store.initialize("demo")
            with self.assertRaisesRegex(SsotValidationError, "AUTHORITY_PATH_FORBIDDEN"):
                store.create_candidate(updates={"authority/contract.aql": b"PROFILE aql:contract/v1\n"})
            with self.assertRaisesRegex(SsotValidationError, "AUTHORITY_CONTENT_FORBIDDEN"):
                store.create_candidate(updates={"contracts/fake.dsl": b"PROFILE aql:contract/v1\nALLOW URI_PROCESS repo://workspace/*\n"})

    def test_promotion_lock_enforces_one_writer(self):
        with tempfile.TemporaryDirectory() as td:
            store = SsotStore(td)
            store.initialize("demo")
            candidate = store.create_candidate(candidate_id="candidate-locked", updates={"intent/a.dsl": b"A\n"})
            store.lock_path.mkdir()
            with self.assertRaisesRegex(SsotConflict, "WRITER_ALREADY_ACTIVE"):
                store.promote(candidate.candidate_id, approval())

    def test_dead_stale_writer_lock_is_recovered(self):
        with tempfile.TemporaryDirectory() as td:
            store = SsotStore(td)
            store.initialize("demo")
            candidate = store.create_candidate(candidate_id="candidate-recovery", updates={"intent/a.dsl": b"A\n"})
            store.lock_path.mkdir()
            (store.lock_path / "owner.json").write_text(json.dumps({"pid": 2_000_000_000, "created_at": 0}), encoding="utf-8")
            manifest = store.promote(candidate.candidate_id, approval())
            self.assertEqual(manifest.integrity, "pass")
            self.assertFalse(store.lock_path.exists())

    def test_registry_federates_only_verified_project_revisions(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as registry_td:
            store = SsotStore(td)
            manifest = store.initialize("demo")
            registry = ProjectRegistry(Path(registry_td) / "registry.dsl")
            entry = registry.register(td)
            self.assertEqual(entry.revision, manifest.revision_hash)
            parsed = parse_registry(render_registry(registry.entries()))
            self.assertEqual(parsed[0].project_id, "demo")
            self.assertTrue(parsed[0].path_uri.startswith("file://"))

    def test_cli_init_status_reconcile_and_validate(self):
        with tempfile.TemporaryDirectory() as td, tempfile.NamedTemporaryFile() as update:
            update.write(b"INTENT cli\nEND_INTENT\n")
            update.flush()
            self.assertEqual(ssot_cli(["init", td, "--project-id", "cli-demo"]), 0)
            self.assertEqual(ssot_cli(["status", td]), 0)
            self.assertEqual(ssot_cli([
                "reconcile", td, "--id", "candidate-cli",
                "--section", f"intent/intent.dsl={update.name}",
            ]), 0)
            self.assertEqual(ssot_cli(["candidate", "validate", "candidate-cli", td]), 0)

    def test_cli_scan_compiles_deterministic_source_index_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "sources").mkdir()
            (root / "sources/design.md").write_text("# Design\n\nStable source.\n", encoding="utf-8")
            self.assertEqual(ssot_cli(["init", td, "--project-id", "scan-demo"]), 0)
            self.assertEqual(ssot_cli(["scan", td, "--id", "candidate-scan"]), 0)
            source_index = root / "SSOT/candidate/candidate-scan/tree/sources/source-index.dsl"
            self.assertTrue(source_index.is_file())
            self.assertNotIn("GENERATED_AT", source_index.read_text(encoding="utf-8"))
            self.assertTrue(SsotStore(td).validate_candidate("candidate-scan").ok)


if __name__ == "__main__":
    unittest.main()
