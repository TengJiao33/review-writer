from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
DISCOVERY_DIR = REPO / "skills" / "review-topic-paper-discovery" / "scripts"
DISCOVER = DISCOVERY_DIR / "discover.py"
INGEST = DISCOVERY_DIR / "ingest_external_papers.py"
FIGURES = (
    REPO
    / "skills"
    / "review-source-figure-tools"
    / "scripts"
    / "build_paper_figure_inventory.py"
)


def load_module(name: str, path: Path):
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


class RetrievalToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.discovery = load_module("review_discovery_tools", DISCOVER)
        cls.ingest = load_module("review_ingest_tools", INGEST)
        cls.figures = load_module("review_figure_inventory_tools", FIGURES)

    def test_generic_query_plan_does_not_leak_allene_vocabulary(self) -> None:
        rows = self.discovery.infer_keywords(
            "enzymatic PET depolymerization",
            [],
            {
                "manuscript_title": "Enzymatic depolymerization of PET waste",
                "central_question": (
                    "How do feedstock crystallinity and enzyme engineering "
                    "change depolymerization performance?"
                ),
                "important_coverage": [
                    "feedstock crystallinity",
                    "enzyme engineering",
                    "reaction conditions",
                ],
            },
        )
        rendered = json.dumps(rows).lower()
        self.assertIn("feedstock crystallinity", rendered)
        self.assertIn("enzyme engineering", rendered)
        self.assertNotIn("allene", rendered)
        self.assertNotIn("propargyl", rendered)

    def test_markdown_topic_input_accepts_common_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "topic.md"
            path.write_text(
                "# Enzymatic PET recycling\n\n"
                "## Central question\n"
                "How do substrate state and enzyme design interact?\n\n"
                "## Important coverage\n"
                "- substrate crystallinity\n"
                "- enzyme engineering\n\n"
                "## Inclusion criteria\n"
                "- full experimental studies\n"
                "  with reported reaction conditions\n\n"
                "## Exclusion criteria\n"
                "- abstracts without full text\n",
                encoding="utf-8",
            )
            payload = self.discovery.load_topic_contract_file(str(path))
        self.assertEqual(payload["topic"], "Enzymatic PET recycling")
        self.assertEqual(len(payload["important_coverage"]), 2)
        self.assertIn(
            "with reported reaction conditions",
            payload["inclusion_criteria"][0],
        )

    def test_crossref_filter_removes_editorial_and_supplement_records(self) -> None:
        bad = [
            {"type": "peer-review", "title": ["Review report"], "DOI": "10.1/x"},
            {
                "type": "journal-article",
                "title": ["Supporting information"],
                "DOI": "10.1/x.s1",
            },
            {
                "type": "journal-article",
                "title": ["Author response"],
                "DOI": "10.1/x/v2/response1",
            },
        ]
        self.assertTrue(
            all(self.discovery.is_excluded_crossref_record(row) for row in bad)
        )
        self.assertFalse(
            self.discovery.is_excluded_crossref_record(
                {
                    "type": "journal-article",
                    "title": ["A primary research article"],
                    "DOI": "10.1/article",
                }
            )
        )

    def test_provider_status_distinguishes_failure_from_no_results(self) -> None:
        self.assertEqual(
            self.discovery.provider_run_status(
                True,
                {"attempted_queries": 2, "successful_queries": 0},
                ["HTTP 429"],
            ),
            "error",
        )
        self.assertEqual(
            self.discovery.provider_run_status(
                True,
                {
                    "attempted_queries": 2,
                    "successful_queries": 2,
                    "returned_records": 0,
                },
                [],
            ),
            "no_results",
        )

    def test_unpaywall_requires_a_real_contact(self) -> None:
        self.assertFalse(
            self.discovery.valid_unpaywall_email("research@university.edu")
        )
        self.assertFalse(self.discovery.valid_unpaywall_email("not-an-email"))
        self.assertTrue(self.discovery.valid_unpaywall_email("lab@example.org"))

    def test_ingest_target_cannot_escape_managed_download_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            good = self.ingest.safe_target(
                root, "chem_papers/web-imports/paper.pdf"
            )
            self.assertEqual(good.suffix, ".pdf")
            with self.assertRaises(ValueError):
                self.ingest.safe_target(root, "../outside.pdf")
            with self.assertRaises(ValueError):
                self.ingest.safe_target(
                    root, "chem_papers/web-imports/not-a-pdf.txt"
                )

    def test_pdf_link_extraction_handles_metadata_and_relative_links(self) -> None:
        urls = self.ingest.extract_pdf_urls(
            "https://example.org/article/1",
            """
            <html><head>
              <meta name="citation_pdf_url" content="/files/paper.pdf">
            </head><body>
              <a href="/download/secondary">Download PDF</a>
            </body></html>
            """,
        )
        self.assertIn("https://example.org/files/paper.pdf", urls)
        self.assertIn("https://example.org/download/secondary", urls)

    def test_license_inventory_surfaces_hints_without_approving_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "paper.md"
            source.write_text(
                "This article is licensed under CC BY 4.0.\n"
                "https://creativecommons.org/licenses/by/4.0/\n",
                encoding="utf-8",
            )
            hints = self.figures.license_hints(source)
        self.assertEqual(hints["reuse_hint_class"], "open_reuse_candidate")
        self.assertIn("instructions", hints)
        self.assertNotIn("verified", json.dumps(hints).lower())
        self.assertNotIn("passed", json.dumps(hints).lower())

    def test_crop_spec_rejects_missing_or_inverted_geometry(self) -> None:
        self.assertIsNone(
            self.figures.crop_spec("paper.pdf", 3, [100, 100, 50, 150])
        )
        self.assertIsNone(self.figures.crop_spec("paper.pdf", "3", [0, 0, 5, 5]))
        self.assertEqual(
            self.figures.crop_spec("paper.pdf", 3, [0, 1, 100, 101]),
            {
                "source_pdf": "paper.pdf",
                "page_index": 3,
                "bbox": [0.0, 1.0, 100.0, 101.0],
            },
        )


if __name__ == "__main__":
    unittest.main()
