from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


REPO = Path(__file__).resolve().parents[1]
INSPECT = REPO / "skills" / "review-writing-tools" / "scripts" / "inspect_review.py"
SEARCH = REPO / "skills" / "review-writing-tools" / "scripts" / "search_library.py"
MERGE = REPO / "skills" / "review-citation-assets" / "scripts" / "merge_citations.py"
INSERT = REPO / "skills" / "review-citation-assets" / "scripts" / "insert_assets.py"
RENDER = REPO / "skills" / "review-export-docx" / "scripts" / "render_docx.py"
MD2DOCX = REPO / "skills" / "review-export-docx" / "scripts" / "md2docx.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


class ReviewToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.metadata_dir = (
            self.root / "review-library" / "metadata" / "papers"
        )
        self.metadata_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def add_paper(
        self,
        paper_id: str,
        *,
        title: str = "A useful paper",
        authors: object | None = None,
        journal: str = "Journal of Useful Results",
        year: int | None = 2024,
        doi: str | None = "10.1000/example",
        full_text: str = "The method improves selectivity under bounded conditions.",
    ) -> Path:
        source = self.root / "sources" / f"{paper_id}.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(full_text, encoding="utf-8")
        payload = {
            "paper_id": paper_id,
            "title": {"value": title},
            "authors": authors
            if authors is not None
            else [{"given": "Ada", "family": "Lovelace"}],
            "journal": {"value": journal} if journal else {"value": ""},
            "year": {"value": year},
            "doi": {"value": doi},
            "abstract": {"value": full_text},
            "source_paths": {"markdown": str(source)},
        }
        write_json(self.metadata_dir / f"{paper_id}.metadata.json", payload)
        return source

    def test_word_range_is_a_source_count_advisory(self) -> None:
        module = load_module("inspect_review_range", INSPECT)
        few = module.recommended_range("comprehensive", 5)
        many = module.recommended_range("comprehensive", 35)
        self.assertEqual(few["center"], 4000)
        self.assertGreater(many["center"], few["center"])
        self.assertEqual(many["basis"], "cited_papers_with_local_full_text")

    def test_inspector_does_not_gate_a_short_manuscript(self) -> None:
        module = load_module("inspect_review_short", INSPECT)
        self.add_paper("P001")
        manuscript = self.root / "manuscript.md"
        manuscript.write_text(
            "# Review\n\n## Discussion\n\nA bounded result is reported [@P001].\n",
            encoding="utf-8",
        )
        report = module.inspect(self.root, manuscript, "comprehensive")
        self.assertEqual(report["mechanical_errors"], [])
        self.assertEqual(report["length_observation"], "below_advisory_range")
        self.assertEqual(report["report_type"], "advisory_snapshot")
        rendered = json.dumps(report).lower()
        self.assertNotIn('"passed"', rendered)
        self.assertNotIn('"release_ready"', rendered)

    def test_inspector_reports_broken_local_references_only(self) -> None:
        module = load_module("inspect_review_broken", INSPECT)
        manuscript = self.root / "manuscript.md"
        manuscript.write_text(
            "# Review\n\nUnknown evidence [@P999].\n\n![Figure 1](missing.png)\n",
            encoding="utf-8",
        )
        report = module.inspect(self.root, manuscript, "focused")
        self.assertIn("unknown stable citation: P999", report["mechanical_errors"])
        self.assertIn("missing local image: missing.png", report["mechanical_errors"])

    def test_library_search_uses_full_text(self) -> None:
        module = load_module("search_library_fulltext", SEARCH)
        self.add_paper(
            "P010",
            title="General method",
            full_text="A crossover experiment constrains the proposed radical mechanism.",
        )
        rows = module.search(
            self.root,
            "crossover radical mechanism",
            limit=10,
            metadata_only=False,
        )
        self.assertEqual(rows[0]["paper_id"], "P010")
        self.assertIn("full_text", rows[0]["matched_fields"])

    def test_citation_merge_numbers_first_appearance(self) -> None:
        module = load_module("merge_citations_order", MERGE)
        self.add_paper("P001", title="First paper")
        self.add_paper("P002", title="Second paper")
        manuscript = self.root / "manuscript.md"
        manuscript.write_text(
            "# Review\n\nSecond appears first [@P002]. "
            "Then both are compared [@P001; @P002].\n",
            encoding="utf-8",
        )
        output = self.root / "deliverables" / "review.md"
        citations = self.root / "deliverables" / "citations.json"
        report = module.merge(
            self.root,
            manuscript,
            output,
            citations,
            strict_metadata=False,
        )
        rendered = output.read_text(encoding="utf-8")
        self.assertIn("Second appears first [1]", rendered)
        self.assertIn("Then both are compared [2, 1]", rendered)
        self.assertLess(rendered.index("Second paper"), rendered.index("First paper"))
        self.assertEqual(report["unknown_paper_ids"], [])
        self.assertNotIn("{'given'", rendered)

    def test_citation_merge_reuses_a_trailing_references_heading(self) -> None:
        module = load_module("merge_citations_heading", MERGE)
        self.add_paper("P001")
        manuscript = self.root / "manuscript.md"
        manuscript.write_text(
            "# Review\n\nA result [@P001].\n\n## References\n",
            encoding="utf-8",
        )
        output = self.root / "review.md"
        module.merge(
            self.root,
            manuscript,
            output,
            self.root / "citations.json",
            strict_metadata=False,
        )
        rendered = output.read_text(encoding="utf-8")
        self.assertEqual(rendered.count("## References"), 1)

    def test_placeholder_authors_are_exposed_not_disguised(self) -> None:
        module = load_module("merge_citations_placeholder", MERGE)
        self.add_paper(
            "P003",
            authors=[{"given": "A.", "family": "Author"}],
        )
        manuscript = self.root / "manuscript.md"
        manuscript.write_text("A claim [@P003].\n", encoding="utf-8")
        output = self.root / "review.md"
        citations = self.root / "citations.json"
        report = module.merge(
            self.root,
            manuscript,
            output,
            citations,
            strict_metadata=False,
        )
        self.assertIn("[authors unavailable]", output.read_text(encoding="utf-8"))
        self.assertIn(
            "authors_missing_or_placeholder",
            report["metadata_observations"][0]["issues"],
        )

    def test_strict_metadata_is_optional_and_transparent(self) -> None:
        module = load_module("merge_citations_strict", MERGE)
        self.add_paper("P004", journal="", year=None, doi=None)
        manuscript = self.root / "manuscript.md"
        manuscript.write_text("A claim [@P004].\n", encoding="utf-8")
        output = self.root / "review.md"
        citations = self.root / "citations.json"
        report = module.merge(
            self.root,
            manuscript,
            output,
            citations,
            strict_metadata=True,
        )
        self.assertFalse(output.exists())
        self.assertTrue(citations.exists())
        self.assertTrue(report["metadata_observations"])

    def test_reaction_scheme_uses_the_normal_asset_inserter(self) -> None:
        module = load_module("insert_assets_scheme", INSERT)
        source = self.root / "selected" / "scheme.png"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
        manuscript = self.root / "manuscript.md"
        manuscript.write_text(
            "# Review\n\nThe reaction network is summarized below.\n\n"
            "<!-- insert:scheme-1 -->\n",
            encoding="utf-8",
        )
        manifest = self.root / "assets" / "asset_manifest.json"
        write_json(
            manifest,
            {
                "assets": [
                    {
                        "asset_id": "scheme-1",
                        "kind": "scheme",
                        "label": "Scheme 1",
                        "path": str(source),
                        "caption": "Representative reaction pathways.",
                        "origin": "source_paper",
                        "source_paper_id": "P001",
                        "source_locator": "Scheme 2, page 5",
                        "reuse_basis": "CC BY 4.0; credit line checked",
                        "attribution": "Reused under CC BY 4.0.",
                    }
                ]
            },
        )
        output = self.root / "deliverables" / "review.md"
        report = module.insert_assets(
            manuscript,
            manifest,
            output,
            output.parent / "assets",
        )
        rendered = output.read_text(encoding="utf-8")
        self.assertIn("![Scheme 1.", rendered)
        self.assertNotIn("<!-- insert:scheme-1 -->", rendered)
        self.assertEqual(report["inserted"][0]["kind"], "scheme")
        self.assertTrue((output.parent / "assets" / "scheme-1.png").is_file())

    def test_asset_caption_does_not_repeat_its_label(self) -> None:
        module = load_module("insert_assets_label", INSERT)
        source = self.root / "selected" / "figure.png"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"image")
        manuscript = self.root / "manuscript.md"
        manuscript.write_text("<!-- insert:f2 -->\n", encoding="utf-8")
        manifest = self.root / "asset_manifest.json"
        write_json(
            manifest,
            {
                "assets": [
                    {
                        "asset_id": "f2",
                        "kind": "figure",
                        "label": "Fig. 2",
                        "path": str(source),
                        "caption": "Fig. 2. Reaction scope.",
                        "origin": "original",
                    }
                ]
            },
        )
        output = self.root / "review.md"
        report = module.insert_assets(
            manuscript,
            manifest,
            output,
            self.root / "copied",
        )
        rendered = output.read_text(encoding="utf-8")
        self.assertEqual(report["mechanical_errors"], [])
        self.assertIn("![Fig. 2. Reaction scope.]", rendered)
        self.assertNotIn("Fig. 2. Fig. 2.", rendered)

    def test_source_asset_without_provenance_is_not_inserted(self) -> None:
        module = load_module("insert_assets_provenance", INSERT)
        source = self.root / "figure.png"
        source.write_bytes(b"image")
        manuscript = self.root / "manuscript.md"
        manuscript.write_text("<!-- insert:f1 -->\n", encoding="utf-8")
        manifest = self.root / "asset_manifest.json"
        write_json(
            manifest,
            {
                "assets": [
                    {
                        "asset_id": "f1",
                        "path": str(source),
                        "caption": "A figure.",
                        "origin": "source_paper",
                    }
                ]
            },
        )
        output = self.root / "out.md"
        report = module.insert_assets(
            manuscript,
            manifest,
            output,
            self.root / "copied",
        )
        self.assertFalse(output.exists())
        self.assertGreaterEqual(len(report["mechanical_errors"]), 4)

    def test_active_skill_surface_is_small_and_tool_oriented(self) -> None:
        skill_names: set[str] = set()
        for skill_file in (REPO / "skills").glob("*/SKILL.md"):
            text = skill_file.read_text(encoding="utf-8")
            match = __import__("re").search(r"^name:\s*(\S+)", text, __import__("re").M)
            self.assertIsNotNone(match)
            skill_names.add(match.group(1))
        self.assertEqual(
            skill_names,
            {
                "mineru-precise-parse-review-writer",
                "review-citation-assets",
                "review-export-docx",
                "review-metadata-prep",
                "review-source-figure-tools",
                "review-topic-paper-discovery",
                "review-writing-tools",
            },
        )

    def test_legacy_control_plane_is_removed(self) -> None:
        legacy_paths = [
            REPO
            / "skills"
            / "review-writing-orchestrator"
            / "scripts"
            / "project_status.py",
            REPO
            / "skills"
            / "review-writing-orchestrator"
            / "scripts"
            / "review_quality_gate.py",
            REPO
            / "skills"
            / "review-writing-orchestrator"
            / "scripts"
            / "finalize_run.py",
            REPO
            / "skills"
            / "review-final-audit-release"
            / "scripts"
            / "final_audit_scan.py",
        ]
        self.assertTrue(all(not path.exists() for path in legacy_paths))

    def test_docx_scheme_is_compact_and_figures_keep_full_width(self) -> None:
        module = load_module("md2docx_bounds", MD2DOCX)
        self.assertEqual(module._figure_bounds_for_caption("scheme", 6.2), (5.25, 3.6))
        self.assertEqual(module._figure_bounds_for_caption("figure", 6.2), (6.2, 5.9))

    def test_docx_table_uses_white_three_line_borders(self) -> None:
        from docx import Document
        from docx.oxml.ns import qn

        module = load_module("md2docx_table", MD2DOCX)
        template = REPO / "skills" / "review-export-docx" / "review_template.docx"
        document = Document(str(template))
        module._clear_body(document)
        module._configure_academic_document(document)
        module._add_table_single(
            document,
            ["Method", "Yield"],
            [["Route A", "80%"], ["Route B", "75%"]],
        )
        table = document.tables[0]

        def border_value(cell, edge: str) -> str | None:
            borders = cell._tc.get_or_add_tcPr().first_child_found_in("w:tcBorders")
            element = borders.find(qn(f"w:{edge}"))
            return element.get(qn("w:val")) if element is not None else None

        self.assertEqual(border_value(table.cell(0, 0), "top"), "single")
        self.assertEqual(border_value(table.cell(0, 0), "bottom"), "single")
        self.assertEqual(border_value(table.cell(0, 0), "left"), "nil")
        self.assertEqual(border_value(table.cell(1, 0), "top"), "nil")
        self.assertEqual(border_value(table.cell(1, 0), "bottom"), "nil")
        self.assertEqual(border_value(table.cell(2, 0), "bottom"), "single")
        self.assertIsNone(table.cell(0, 0)._tc.get_or_add_tcPr().find(qn("w:shd")))

    def test_docx_ordered_lists_have_explicit_restart(self) -> None:
        from docx import Document
        from docx.oxml.ns import qn

        module = load_module("md2docx_numbering", MD2DOCX)
        template = REPO / "skills" / "review-export-docx" / "review_template.docx"
        document = Document(str(template))
        num_id = module._create_numbering_definition(
            document,
            ordered=True,
            reference=True,
        )
        numbering = document.part.numbering_part.element
        target = next(
            item
            for item in numbering.findall(qn("w:num"))
            if item.get(qn("w:numId")) == str(num_id)
        )
        overrides = target.findall(qn("w:lvlOverride"))
        self.assertEqual(len(overrides), 3)
        self.assertTrue(
            all(
                item.find(qn("w:startOverride")).get(qn("w:val")) == "1"
                for item in overrides
            )
        )

    def test_docx_references_keep_their_explicit_numbers(self) -> None:
        module = load_module("md2docx_references", MD2DOCX)
        blocks = module.tokenize(
            "## Conclusions\n\n1. First point.\n2. Second point.\n\n"
            "## References\n\n1. First paper.\n2. Second paper.\n"
        )
        reference_items = [
            block
            for block in blocks
            if block.kind == "list_item" and block.text.endswith("paper.")
        ]
        self.assertEqual(
            [(block.list_number, block.text) for block in reference_items],
            [(1, "First paper."), (2, "Second paper.")],
        )

    def test_render_report_records_artifacts_without_visual_verdict(self) -> None:
        module = load_module("render_docx_lightweight", RENDER)
        docx = self.root / "review.docx"
        pdf = self.root / "review.pdf"
        pages = self.root / "pages"
        report_path = self.root / "render.json"
        docx.write_bytes(b"docx fixture")

        def fake_render(_docx: Path, output_pdf: Path):
            output_pdf.write_bytes(b"%PDF-1.4 fixture")
            return True, {"renderer": "fixture", "available": True, "exit_code": 0}

        def fake_rasterize(_pdf: Path, pages_dir: Path):
            pages_dir.mkdir(parents=True, exist_ok=True)
            page = pages_dir / "page-1.png"
            page.write_bytes(b"png fixture")
            return [str(page)], {"available": True, "exit_code": 0}

        module.render_with_libreoffice = fake_render
        module.render_with_word = fake_render
        module.rasterize = fake_rasterize
        module.pdf_page_count = lambda _pdf: 1
        module.layout_warnings = lambda _pdf, _pages: []
        code = module.run(
            SimpleNamespace(
                input=docx,
                output_pdf=pdf,
                pages_dir=pages,
                report=report_path,
            )
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertTrue(report["pdf_created"])
        self.assertTrue(report["page_images_created"])
        rendered = json.dumps(report).lower()
        self.assertNotIn('"render_status"', rendered)
        self.assertNotIn('"inspection_status"', rendered)
        self.assertNotIn('"verdict"', rendered)


if __name__ == "__main__":
    unittest.main()
