from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
COMPILER = (
    REPO
    / "skills"
    / "review-section-drafting-figure-picking"
    / "scripts"
    / "compile_review_draft.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("compile_review_draft", COMPILER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CompileReviewDraftTests(unittest.TestCase):
    def test_readable_manuscript_compiles_provenance_without_prose_templates(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blueprint = root / "section_blueprint.json"
            manuscript = root / "manuscript.md"
            blueprint.write_text(
                json.dumps(
                    {
                        "sections": [
                            {"section_id": "sec1", "title": "What the evidence establishes"}
                        ]
                    }
                ),
                encoding="utf-8",
            )
            manuscript.write_text(
                "# A usable review\n\n"
                "## Abstract\n\nThis review asks a bounded question and follows the available evidence.\n\n"
                "**Keywords:** evidence; synthesis; review\n\n"
                "## What the evidence establishes\n\n"
                "<!-- section_id: sec1 -->\n\n"
                "<!-- evidence: P001-E01, P002-E03 | type: comparison -->\n\n"
                "The two studies reach different conclusions under different conditions [@P001; @P002].\n\n"
                "The distinction matters for how the field frames the remaining problem.\n",
                encoding="utf-8",
            )

            payload = module.compile_manuscript(manuscript, blueprint)

            self.assertEqual(payload["front_matter"]["title"], "A usable review")
            self.assertEqual(payload["front_matter"]["keywords"], ["evidence", "synthesis", "review"])
            section = payload["sections"][0]
            self.assertEqual(section["section_id"], "sec1")
            self.assertEqual(section["paragraphs"][0]["evidence_ids"], ["P001-E01", "P002-E03"])
            self.assertEqual(section["paragraphs"][0]["cited_paper_ids"], ["P001", "P002"])
            self.assertEqual(section["paragraphs"][0]["paragraph_type"], "comparison")
            self.assertNotIn("<!--", section["paragraphs"][0]["markdown"])
            self.assertEqual(section["paragraphs"][1]["paragraph_type"], "transition")


if __name__ == "__main__":
    unittest.main()
