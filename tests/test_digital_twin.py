import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from boundary import assert_dsl_only, build_twin_bootstrap_bundle, build_twin_update_bundle  # noqa: E402
from digital_twin import (  # noqa: E402
    demo_bootstrap_twin,
    extract_twindsl,
    intent_fingerprint,
    parse_twindsl,
    twin_to_mermaid,
    twindsl_schema,
    validate_twin_markdown,
    validate_twin_update,
)
from llm_client import bootstrap_twin, plan_build, update_twin  # noqa: E402
from source_ingest import build_source_index, extract_source_refs, validate_sourceindex_markdown  # noqa: E402
from twin_store import TwinStore  # noqa: E402


class DigitalTwinTests(unittest.TestCase):
    def intent(self):
        return (
            "Build an application that turns a few user sentences into a source-backed digital twin. "
            "Markdown sources may refine implementation but cannot replace the original intent."
        )

    def test_bootstrap_bundle_is_dsl_only_and_contains_runtime_fingerprint(self):
        fp = intent_fingerprint(self.intent())
        bundle = build_twin_bootstrap_bundle(self.intent(), fp, twindsl_schema())
        assert_dsl_only(bundle.markdown, {"contractdsl", "taskdsl", "schemadsl", "sourcedsl"})
        self.assertIn(fp, bundle.markdown)
        self.assertIn("CONTENT_HASH sha256:", bundle.markdown)

    def test_demo_bootstrap_creates_valid_twin(self):
        result = bootstrap_twin(self.intent(), "demo")
        self.assertTrue(result["validation"]["valid"], result["validation"]["errors"])
        doc = parse_twindsl(extract_twindsl(result["markdown"]))
        self.assertEqual(doc.revision, 1)
        self.assertEqual(doc.intent_fingerprint, intent_fingerprint(self.intent()))
        self.assertIn("preserve_user_intent", doc.invariants)
        self.assertIn("user_intent", doc.sources)
        self.assertIn("flowchart LR", twin_to_mermaid(doc))

    def test_markdown_sources_compile_to_sourceindexdsl(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.md").write_text("# API\n\n- Retry twice\n\n```python\nprint('x')\n```\n", encoding="utf-8")
            index = build_source_index(root)
            md = index.to_markdown()
            self.assertTrue(validate_sourceindex_markdown(md)["valid"])
            self.assertIn("HEADING 1 \"API\"", md)
            self.assertIn("BULLET \"Retry twice\"", md)
            self.assertIn("CODE python HASH sha256:", md)
            refs = extract_source_refs(md)
            self.assertEqual(len(refs), 1)

    def test_demo_update_preserves_intent_and_adds_source_provenance(self):
        first = bootstrap_twin(self.intent(), "demo")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "architecture.md").write_text("# Architecture\n\nUse PostgreSQL event store.\n", encoding="utf-8")
            source_md = build_source_index(root).to_markdown()
            bundle = build_twin_update_bundle(first["markdown"], source_md, twindsl_schema())
            assert_dsl_only(bundle.markdown, {"contractdsl", "taskdsl", "schemadsl", "twindsl", "sourceindexdsl"})
            second = update_twin(first["markdown"], source_md, "demo")
        old = parse_twindsl(extract_twindsl(first["markdown"]))
        new = parse_twindsl(extract_twindsl(second["markdown"]))
        self.assertEqual(validate_twin_update(old, new), [])
        self.assertEqual(new.revision, 2)
        self.assertEqual(new.intent_fingerprint, old.intent_fingerprint)
        self.assertGreater(len(new.sources), len(old.sources))

    def test_build_plan_is_derived_from_current_twin(self):
        first = bootstrap_twin(self.intent(), "demo")
        plan = plan_build(first["markdown"], "demo")
        self.assertTrue(plan["validation"]["valid"], plan["validation"]["errors"])
        self.assertIn("FROM_REVISION 1", plan["markdown"])
        self.assertIn("TARGET_URI ifuri://", plan["markdown"])

    def test_store_persists_revision_history(self):
        with tempfile.TemporaryDirectory() as td:
            store = TwinStore(td)
            first = demo_bootstrap_twin(self.intent())
            store.save(first)
            self.assertTrue(store.exists())
            self.assertEqual(store.load().revision, 1)
            self.assertTrue(any((Path(td) / "history").glob("rev-0001-*.md")))


    def test_source_ids_are_stable_when_new_files_are_added(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "b.md").write_text("# B\n", encoding="utf-8")
            first = build_source_index(root)
            first_id = first.documents[0].source_id
            (root / "a.md").write_text("# A\n", encoding="utf-8")
            second = build_source_index(root)
            second_b = next(d for d in second.documents if d.path.endswith("b.md"))
            self.assertEqual(first_id, second_b.source_id)

    def test_source_index_semantic_document_excludes_execution_timestamp(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.md").write_text("# Stable\n\nSame content.\n", encoding="utf-8")
            first = build_source_index(root)
            second = build_source_index(root)
            first.generated_at = "2026-01-01T00:00:00Z"
            second.generated_at = "2027-01-01T00:00:00Z"
            self.assertEqual(first.to_markdown(), second.to_markdown())
            self.assertNotIn("GENERATED_AT", first.to_markdown())
            self.assertEqual(first.envelope()["contentHash"], second.envelope()["contentHash"])
            self.assertNotEqual(first.envelope()["generatedAt"], second.envelope()["generatedAt"])

    def test_existing_source_document_may_advance_to_new_digest(self):
        first = bootstrap_twin(self.intent(), "demo")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "architecture.md"
            path.write_text("# Architecture\n\nVersion one.\n", encoding="utf-8")
            source1 = build_source_index(root).to_markdown()
            second = update_twin(first["markdown"], source1, "demo")
            doc2 = parse_twindsl(extract_twindsl(second["markdown"]))
            ext_id = next(sid for sid in doc2.sources if sid != "user_intent")
            digest1 = doc2.sources[ext_id].digest
            path.write_text("# Architecture\n\nVersion two with a changed constraint.\n", encoding="utf-8")
            source2 = build_source_index(root).to_markdown()
            third = update_twin(second["markdown"], source2, "demo")
            doc3 = parse_twindsl(extract_twindsl(third["markdown"]))
            self.assertIn(ext_id, doc3.sources)
            self.assertNotEqual(digest1, doc3.sources[ext_id].digest)
            self.assertEqual(doc3.revision, 3)



if __name__ == "__main__":
    unittest.main()
