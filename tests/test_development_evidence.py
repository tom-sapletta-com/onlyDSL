from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from onlydsl.dsl.development_evidence import (
    create_development_evidence,
    parse_development_evidence,
    render_development_evidence,
)
from onlydsl.ssot.writer import SsotStore


class DevelopmentEvidenceTests(unittest.TestCase):
    def bundle(self):
        return create_development_evidence(
            bundle_id="dev-main-a1b2c3d4", project_id="controller", repository_id="firmware",
            repository_revision="a" * 40, repository_tree="b" * 40,
            producer_version="0.5.1",
            graph_uri="urn:dodsl:todo2code-graph:sha256:" + "c" * 64,
            diagnostics_uri="urn:dodsl:todo2code-diagnostics:sha256:" + "d" * 64,
            manifest_uri="urn:dodsl:todo2code-manifest:sha256:" + "e" * 64,
            graph_fingerprint="sha256:" + "f" * 64,
            assessment="accepted", blocking_diagnostics=0, warning_diagnostics=2,
        )

    def test_bundle_roundtrip_is_content_addressed_and_non_authoritative(self):
        bundle = self.bundle()
        markdown = render_development_evidence(bundle)
        self.assertEqual(parse_development_evidence(markdown), bundle)
        self.assertEqual(bundle.evidence_uri, "urn:onlydsl:development-evidence:" + bundle.semantic_hash)
        self.assertIn("AUTHORITY_EFFECT none", markdown)
        self.assertIn("MUTATION_EFFECT none", markdown)

    def test_bundle_rejects_tampering_and_false_acceptance(self):
        markdown = render_development_evidence(self.bundle())
        with self.assertRaisesRegex(ValueError, "semantic identity"):
            parse_development_evidence(markdown.replace("WARNING_DIAGNOSTICS 2", "WARNING_DIAGNOSTICS 3"))
        with self.assertRaisesRegex(ValueError, "cannot contain blocking"):
            create_development_evidence(
                bundle_id="dev-main-a1b2c3d4", project_id="controller", repository_id="firmware",
                repository_revision="a" * 40, repository_tree="b" * 40,
                producer_version="0.5.1",
                graph_uri="urn:dodsl:todo2code-graph:sha256:" + "c" * 64,
                diagnostics_uri="urn:dodsl:todo2code-diagnostics:sha256:" + "d" * 64,
                manifest_uri="urn:dodsl:todo2code-manifest:sha256:" + "e" * 64,
                graph_fingerprint="sha256:" + "f" * 64,
                assessment="accepted", blocking_diagnostics=1, warning_diagnostics=0,
            )

    def test_domain_ssot_validator_rejects_malformed_development_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            store = SsotStore(td)
            store.initialize("controller")
            valid = render_development_evidence(self.bundle()).encode()
            candidate = store.create_candidate(
                candidate_id="candidate-valid-development",
                updates={"development/todo2code/firmware/development-evidence.dsl": valid},
                evidence_uris=(self.bundle().evidence_uri,),
            )
            self.assertTrue(store.validate_candidate(candidate.candidate_id).ok)
            invalid = store.create_candidate(
                candidate_id="candidate-invalid-development",
                updates={"development/todo2code/firmware/development-evidence.dsl": valid.replace(b"AUTHORITY_EFFECT none", b"AUTHORITY_EFFECT granted")},
            )
            report = store.validate_candidate(invalid.candidate_id)
            self.assertFalse(report.ok)
            self.assertTrue(any("development evidence cannot grant authority" in issue for issue in report.issues))


if __name__ == "__main__":
    unittest.main()
