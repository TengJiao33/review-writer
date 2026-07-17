from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from docx import Document


REPO = Path(__file__).resolve().parents[1]
MERGE = REPO / "skills" / "review-draft-merge-polish" / "scripts" / "merge_review.py"
AUDIT = REPO / "skills" / "review-final-audit-release" / "scripts" / "final_audit_scan.py"
MD2DOCX = REPO / "skills" / "review-export-docx" / "scripts" / "md2docx.py"
DOCX_AUDIT = REPO / "skills" / "review-export-docx" / "scripts" / "audit_docx.py"
MATRIX_VALIDATOR = REPO / "skills" / "review-literature-matrix-outline" / "scripts" / "validate_evidence_matrix.py"
BLUEPRINT_VALIDATOR = REPO / "skills" / "review-section-blueprint" / "scripts" / "validate_blueprint.py"
DRAFT_VALIDATOR = REPO / "skills" / "review-section-drafting-figure-picking" / "scripts" / "validate_section_drafts.py"
SCREENING_VALIDATOR = REPO / "skills" / "review-topic-paper-discovery" / "scripts" / "validate_screening.py"
METADATA_PREP = REPO / "skills" / "review-metadata-prep" / "scripts" / "prepare_metadata.py"
DISCOVER = REPO / "skills" / "review-topic-paper-discovery" / "scripts" / "discover.py"
FIGURE_SELECTOR = REPO / "skills" / "review-section-drafting-figure-picking" / "scripts" / "select_initial_figure_candidates.py"
FIGURE_REDRAW = REPO / "skills" / "review-figure-style-redraw" / "scripts" / "redraw_figures.py"
PROJECT_STATUS = REPO / "skills" / "review-writing-orchestrator" / "scripts" / "project_status.py"
EXTERNAL_INGEST = REPO / "skills" / "review-topic-paper-discovery" / "scripts" / "ingest_external_papers.py"


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class ReviewWorkflowContractsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project_id = "fixture-review"
        self.project = self.root / "review-projects" / self.project_id
        self._write_matrix_and_metadata()
        write_json(self.project / "02_section_drafting" / "figure_candidates.json", [])
        write_json(
            self.project / "00_discovery" / "screening_validation.json",
            {"blocking_issues": [], "warnings": []},
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_matrix_and_metadata(self) -> None:
        rows = []
        for paper_id, title, year in (
            ("P001", "Palladium Carbonylation of Propargylic Carbonates", 2020),
            ("P002", "Nickel Electrocarboxylation of Propargylic Carbonates", 2022),
        ):
            rows.append(
                {
                    "paper_id": paper_id,
                    "title": title,
                    "authors": ["Ada Chemist", "Ben Researcher"],
                    "keywords": {"substrate": "propargylic carbonates"},
                    "abstract": "Evidence-grounded abstract.",
                    "main_content": "Evidence " * 360,
                    "most_relevant_figure": {},
                    "evidence_anchors": [
                        {
                            "evidence_id": f"{paper_id}-E01",
                            "note": "The full text reports the transformation and representative scope.",
                            "source_excerpt": "The transformation and representative scope are reported.",
                            "source_path": f"review-library/sources/{paper_id}.md",
                            "locator": "Results, paragraph 1",
                            "source_level": "full_text",
                            "evidence_kind": "result",
                            "certainty": "direct",
                        },
                        {
                            "evidence_id": f"{paper_id}-E02",
                            "note": "The authors describe the pathway as a mechanistic proposal.",
                            "source_excerpt": "The pathway is presented as a mechanistic proposal.",
                            "source_path": f"review-library/sources/{paper_id}.md",
                            "locator": "Mechanism, paragraph 1",
                            "source_level": "full_text",
                            "evidence_kind": "mechanism",
                            "certainty": "author_interpretation",
                        },
                    ],
                }
            )
            source = self.root / "review-library" / "sources" / f"{paper_id}.md"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(
                "# Results\n\nThe transformation and representative scope are reported.\n\n"
                "# Mechanism\n\nThe pathway is presented as a mechanistic proposal.\n",
                encoding="utf-8",
            )
            write_json(
                self.root / "review-library" / "metadata" / "papers" / f"{paper_id}.metadata.json",
                {
                    "paper_id": paper_id,
                    "title": {"value": title},
                    "authors": {"value": ["Ada Chemist", "Ben Researcher"]},
                    "journal": {"value": "Journal of Allene Chemistry"},
                    "year": {"value": year},
                    "doi": {"value": f"10.1000/{paper_id.lower()}"},
                },
            )
        write_json(self.project / "01_matrix_outline" / "literature_matrix.json", {"papers": rows})

    def _front_matter(self) -> dict:
        abstract = (
            "This review compares catalytic strategies for converting propargylic carbonates into allenes. "
            "It evaluates activation mode, selectivity control, mechanistic evidence, substrate scope, and practical limitations. "
        ) * 12
        return {
            "title": "Catalytic Allene Synthesis from Propargylic Carbonates",
            "abstract": abstract,
            "keywords": ["allenes", "propargylic carbonates", "palladium", "nickel", "selectivity"],
        }

    def test_legacy_numeric_citations_are_rejected(self) -> None:
        payload = {
            "front_matter": self._front_matter(),
            "sections": [
                {
                    "section_id": "sec1",
                    "title": "1. Introduction",
                    "paragraphs": [
                        {
                            "paragraph_id": "sec1-p1",
                            "paragraph_type": "comparison",
                            "markdown": "Palladium and nickel systems differ [1].",
                            "cited_paper_ids": ["P001", "P002"],
                        }
                    ],
                }
            ],
        }
        write_json(self.project / "02_section_drafting" / "section_drafts.json", payload)
        result = run(MERGE, "--review-root", self.root, "--project-id", self.project_id)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("numeric citations are forbidden", result.stdout)

    def test_abstract_image_embed_is_rejected(self) -> None:
        front = self._front_matter()
        front["abstract"] += "\n\n![A misplaced scheme](figures/scheme.png)"
        write_json(
            self.project / "02_section_drafting" / "section_drafts.json",
            {
                "front_matter": front,
                "sections": [
                    {
                        "section_id": "sec1",
                        "title": "1. Introduction",
                        "paragraphs": [
                            {
                                "paragraph_id": "sec1-p1",
                                "markdown": "The focal transformation is reported [@P001].",
                                "evidence_ids": ["P001-E01"],
                            }
                        ],
                    }
                ],
            },
        )
        result = run(MERGE, "--review-root", self.root, "--project-id", self.project_id)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("front_matter.abstract must not contain embedded images", result.stdout)

    def test_delegated_screening_uses_generic_topic_contract(self) -> None:
        write_json(
            self.project / "00_discovery" / "topic_contract.json",
            {
                "topic": "Interventions and long-term retention",
                "central_question": "Which interventions improve long-term retention?",
                "important_coverage": ["follow-up duration", "population"],
                "inclusion_criteria": ["reports a retention outcome"],
                "exclusion_criteria": ["no longitudinal measurement"],
            },
        )
        write_json(
            self.project / "00_discovery" / "selected_discovery_results.json",
            {
                "screening": {"status": "confirmed", "decided_by": "agent"},
                "candidate_paper_ids": ["P001", "P002"],
                "local_papers": [{"paper_id": "P001"}],
                "screening_decisions": [
                    {
                        "paper_id": "P001",
                        "decision": "include",
                        "relevance_summary": "Reports the outcome named in the central question.",
                        "decision_basis": "Full-text results and the inclusion criterion.",
                    },
                    {
                        "paper_id": "P002",
                        "decision": "exclude",
                        "relevance_summary": "Measures only immediate performance.",
                        "decision_basis": "No longitudinal measurement.",
                    },
                ],
            },
        )
        result = run(
            SCREENING_VALIDATOR,
            "--review-root",
            self.root,
            "--project-id",
            self.project_id,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_journal_hint_does_not_match_affiliation_text(self) -> None:
        spec = importlib.util.spec_from_file_location("review_metadata_prep", METADATA_PREP)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        extracted = module.extract_journal(
            "Shanghai Key Laboratory of Green Chemistry and Chemical Processes",
            "article.pdf",
        )
        self.assertIsNone(extracted["value"])
        filename_extracted = module.extract_journal("", "Green Chemistry - article.pdf")
        self.assertEqual(filename_extracted["value"], "Green Chemistry")
        abbreviated = module.extract_journal(
            "",
            "46-Angew Chem Int Ed - 2012 - Wan - Enantioselective Amination.pdf",
        )
        self.assertEqual(abbreviated["value"], "Angew. Chem. Int. Ed.")

    def test_discovery_selection_keeps_compact_screening_context(self) -> None:
        sys.path.insert(0, str(DISCOVER.parent))
        try:
            spec = importlib.util.spec_from_file_location("review_discover", DISCOVER)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        selected = module.selected_from_combined(
            [
                {
                    "keyword": "nickel catalysis",
                    "category": "catalyst_or_method",
                    "keep": True,
                    "local_results": [
                        {
                            "paper_id": "P001",
                            "title": "A paper",
                            "year": 2025,
                            "journal": "A Journal",
                            "abstract": "Enough context for screening.",
                            "structured_tags": {"catalyst_or_method": "nickel catalysis"},
                            "source_paths": {"markdown": "paper.md", "pdf": "paper.pdf"},
                            "role": "core_candidate",
                            "score": 0.8,
                            "keep": True,
                        }
                    ],
                    "web_results": [],
                }
            ]
        )
        paper = selected["local_papers"][0]
        self.assertEqual(paper["abstract"], "Enough context for screening.")
        self.assertEqual(paper["structured_tags"]["catalyst_or_method"], "nickel catalysis")
        self.assertEqual(paper["source_paths"]["markdown"], "paper.md")

    def test_discovery_reads_structured_markdown_topic_contract(self) -> None:
        sys.path.insert(0, str(DISCOVER.parent))
        try:
            spec = importlib.util.spec_from_file_location("review_discover_contract", DISCOVER)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        contract = self.root / "topic_input.md"
        contract.write_text(
            "# Review Topic\n\n"
            "## Manuscript Title\n\nA concise title\n\n"
            "## Retrieval Query\n\nNickel catalysis with propargylic electrophiles\n\n"
            "## Central Question\n\nWhich factors control product topology?\n\n"
            "## Important Coverage\n\n- activation mode\n- ligand effects\n\n"
            "## Inclusion Criteria\n\n- nickel is part of the transformation\n\n"
            "## Exclusion Criteria\n\n- nickel is not part of the transformation\n\n"
            "## Suggested Retrieval Keywords\n\n- nickel catalysis\n- propargylic electrophiles\n",
            encoding="utf-8",
        )
        parsed = module.load_topic_contract_file(str(contract))
        self.assertEqual(parsed["manuscript_title"], "A concise title")
        self.assertEqual(parsed["retrieval_query"], "Nickel catalysis with propargylic electrophiles")
        self.assertEqual(parsed["important_coverage"], ["activation mode", "ligand effects"])
        self.assertEqual(parsed["suggested_keywords"], ["nickel catalysis", "propargylic electrophiles"])

    def test_provider_status_distinguishes_irrelevance_from_failure(self) -> None:
        sys.path.insert(0, str(DISCOVER.parent))
        try:
            spec = importlib.util.spec_from_file_location("review_discover_provider", DISCOVER)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        records, errors = module.split_provider_rows(
            [
                {
                    "title": "A valid but irrelevant record",
                    "keep": False,
                    "reason": "low topic overlap",
                },
                {
                    "title": "WEB_SEARCH_FAILED: TimeoutError",
                    "keep": False,
                    "reason": "timed out",
                },
            ]
        )
        self.assertEqual([row["title"] for row in records], ["A valid but irrelevant record"])
        self.assertEqual(errors, ["timed out"])
        self.assertEqual(
            module.provider_run_status(
                True,
                {
                    "attempted_queries": 1,
                    "successful_queries": 1,
                    "returned_records": 1,
                    "retained_records": 0,
                },
                [],
            ),
            "no_retained_results",
        )

    def test_external_discovery_builds_deduplicated_mineru_ingest_plan(self) -> None:
        sys.path.insert(0, str(DISCOVER.parent))
        try:
            spec = importlib.util.spec_from_file_location("review_discover_ingest", DISCOVER)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        local = {
            "P001": {
                "paper_id": "P001",
                "title": {"value": "Known Allene Paper"},
                "doi": {"value": "10.1000/known"},
            }
        }
        rows = module.annotate_external_results(
            [
                {
                    "external_id": "s2-known",
                    "title": "Known Allene Paper",
                    "doi": "https://doi.org/10.1000/KNOWN",
                    "source": "semantic_scholar",
                    "keep": True,
                    "score": 0.8,
                },
                {
                    "external_id": "s2-new",
                    "title": "New Open Allene Paper",
                    "doi": "10.1000/new",
                    "year": 2026,
                    "open_access_pdf_url": "https://example.org/new.pdf",
                    "source": "semantic_scholar",
                    "keep": True,
                    "score": 0.7,
                },
            ],
            local,
        )
        selected = module.selected_from_combined(
            [
                {
                    "keyword": "allene synthesis",
                    "category": "reaction_type",
                    "keep": True,
                    "local_results": [],
                    "web_results": rows,
                },
                {
                    "keyword": "nickel catalysis",
                    "category": "catalyst_or_method",
                    "keep": True,
                    "local_results": [],
                    "web_results": [rows[1]],
                },
            ]
        )
        self.assertEqual(len(selected["web_papers"]), 2)
        new_row = next(row for row in selected["web_papers"] if row["external_id"] == "s2-new")
        self.assertEqual(new_row["matched_keywords"], ["allene synthesis", "nickel catalysis"])
        plan = module.build_external_ingest_plan("fixture-review", selected["web_papers"], True)
        actions = {item["paper_key"]: item["action"] for item in plan["items"]}
        self.assertEqual(actions["s2-known"], "use_local")
        self.assertEqual(actions["s2-new"], "download_then_mineru")
        self.assertEqual(plan["downloadable_count"], 1)

        spec = importlib.util.spec_from_file_location("review_external_ingest", EXTERNAL_INGEST)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        ingest = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ingest)
        chosen = ingest.select_items(plan, ["s2-new"], 3)
        self.assertEqual([row["paper_key"] for row in chosen], ["s2-new"])
        with self.assertRaises(ValueError):
            ingest.safe_target(self.root, "../outside.pdf")

    def test_matrix_blocks_missing_source_and_draft_blocks_wrong_evidence_owner(self) -> None:
        matrix_path = self.project / "01_matrix_outline" / "literature_matrix.json"
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        matrix["papers"][0]["evidence_anchors"][0]["source_path"] = "missing-source.md"
        write_json(matrix_path, matrix)
        result = run(
            MATRIX_VALIDATOR,
            "--review-root",
            self.root,
            "--project-id",
            self.project_id,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source_path does not exist", result.stdout)

        self._write_matrix_and_metadata()
        write_json(
            self.project / "01_matrix_outline" / "section_blueprint.json",
            {"coverage_contract": {"dimensions": []}, "sections": [{"section_id": "sec1"}]},
        )
        write_json(
            self.project / "02_section_drafting" / "section_drafts.json",
            {
                "front_matter": self._front_matter(),
                "sections": [
                    {
                        "section_id": "sec1",
                        "title": "Evidence ownership",
                        "paragraphs": [
                            {
                                "paragraph_id": "sec1-p1",
                                "markdown": "The first paper reports the focal result [@P001].",
                                "evidence_ids": ["P002-E01"],
                            }
                        ],
                    }
                ],
            },
        )
        result = run(
            DRAFT_VALIDATOR,
            "--review-root",
            self.root,
            "--project-id",
            self.project_id,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("evidence belongs to uncited papers P002", result.stdout)

    def test_matrix_blocks_source_excerpt_that_is_only_a_paraphrase(self) -> None:
        matrix_path = self.project / "01_matrix_outline" / "literature_matrix.json"
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        matrix["papers"][0]["evidence_anchors"][0]["source_excerpt"] = (
            "A broad transformation with useful scope was established by the authors."
        )
        write_json(matrix_path, matrix)
        result = run(
            MATRIX_VALIDATOR,
            "--review-root",
            self.root,
            "--project-id",
            self.project_id,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source_excerpt is not found in the recorded source", result.stdout)

    def test_draft_validator_rejects_invalid_figure_candidates_shape(self) -> None:
        write_json(
            self.project / "01_matrix_outline" / "section_blueprint.json",
            {"coverage_contract": {"dimensions": []}, "sections": [{"section_id": "sec1"}]},
        )
        write_json(
            self.project / "02_section_drafting" / "section_drafts.json",
            {
                "front_matter": self._front_matter(),
                "sections": [
                    {
                        "section_id": "sec1",
                        "title": "Evidence",
                        "paragraphs": [
                            {
                                "paragraph_id": "sec1-p1",
                                "markdown": "The paper reports the focal result [@P001].",
                                "evidence_ids": ["P001-E01"],
                            }
                        ],
                    }
                ],
            },
        )
        write_json(
            self.project / "02_section_drafting" / "figure_candidates.json",
            {"candidates": [], "skip_reason": "not a supported structure"},
        )
        result = run(DRAFT_VALIDATOR, "--review-root", self.root, "--project-id", self.project_id)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("figure_candidates.json must be a list", result.stdout)

    def test_figure_selector_accepts_object_section_tasks_and_uses_blueprint(self) -> None:
        write_json(
            self.project / "00_discovery" / "selected_discovery_results.json",
            {"local_papers": [{"paper_id": "P001"}]},
        )
        write_json(
            self.project / "01_matrix_outline" / "section_blueprint.json",
            {
                "sections": [
                    {
                        "section_id": "sec1",
                        "title": "1. Mechanistic Pathways",
                        "section_thesis": "Compare palladium and nickel catalytic pathways.",
                        "major_papers": ["P001"],
                    }
                ]
            },
        )
        write_json(
            self.project / "02_section_drafting" / "section_tasks.json",
            {
                "project_id": self.project_id,
                "sections": [{"section_id": "sec1", "title": "1. Mechanistic Pathways"}],
            },
        )
        image_path = self.root / "review-library" / "figures" / "P001-scheme.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(b"fixture")
        content_path = image_path.parent / "P001_content_list.json"
        write_json(
            content_path,
            [
                {
                    "type": "image",
                    "img_path": image_path.name,
                    "image_caption": "Scheme 1. Proposed catalytic mechanism",
                    "page_idx": 3,
                }
            ],
        )
        metadata_path = self.root / "review-library" / "metadata" / "papers" / "P001.metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["source_paths"] = {
            "content_list": str(content_path),
            "extracted_dir": str(image_path.parent),
        }
        write_json(metadata_path, metadata)
        write_json(
            self.project / "02_section_drafting" / "paper_figure_inventory.json",
            {
                "papers": [
                    {
                        "paper_id": "P001",
                        "title": "Palladium Carbonylation",
                        "top_candidates": [
                            {
                                "paper_id": "P001",
                                "source_label": "Scheme 1",
                                "source_type": "image",
                                "source_caption_text": "Proposed catalytic mechanism",
                                "source_image_path": str(image_path),
                                "inventory_score": 20,
                            }
                        ],
                    }
                ]
            },
        )
        result = run(
            FIGURE_SELECTOR,
            "--review-root",
            self.root,
            "--project-id",
            self.project_id,
            "--max-total",
            "1",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        selected = json.loads(
            (self.project / "02_section_drafting" / "figure_candidates.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["section_id"], "sec1")
        self.assertEqual(selected[0]["source_page_review_status"], "pending")

    def test_source_figure_requires_and_records_page_completeness_review(self) -> None:
        image_path = self.root / "review-library" / "figures" / "P001-scheme.png"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(b"fixture image bytes")
        candidate = {
            "paper_id": "P001",
            "section_id": "sec1",
            "source_label": "Scheme 1",
            "source_page_hint": "page 4",
            "source_caption_text": "(A) Proposed pathway",
            "source_image_path": str(image_path),
            "source_verification_note": "Checked Scheme 1 on page 4 against the source PDF.",
        }
        figures_path = self.project / "02_section_drafting" / "figure_candidates.json"
        write_json(figures_path, [candidate])
        result = run(
            FIGURE_REDRAW,
            "--review-root",
            self.root,
            "--project-id",
            self.project_id,
            "--use-source",
            "--require-usable",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No usable figure", result.stdout + result.stderr)

        candidate["source_page_review_status"] = "passed"
        candidate["source_completeness"] = "complete"
        write_json(figures_path, [candidate])
        result = run(
            FIGURE_REDRAW,
            "--review-root",
            self.root,
            "--project-id",
            self.project_id,
            "--use-source",
            "--require-usable",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        fidelity_path = self.project / "03_figure_redraw" / "figure_fidelity_review.json"
        fidelity = json.loads(fidelity_path.read_text(encoding="utf-8"))
        self.assertEqual(fidelity["figures"][0]["verdict"], "passed")
        self.assertTrue(
            fidelity["figures"][0]["completeness_signals"]["panel_marker_detected"]
        )

        spec = importlib.util.spec_from_file_location("review_project_status", PROJECT_STATUS)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        figure_stage = next(stage for stage in module.STAGES if stage["id"] == "figure_redraw")
        self.assertTrue(module.stage_status(self.project, figure_stage)["complete"])
        fidelity["figures"][0]["verdict"] = "pending"
        write_json(fidelity_path, fidelity)
        status = module.stage_status(self.project, figure_stage)
        self.assertFalse(status["complete"])
        self.assertIn("figure_fidelity_not_passed:F001", status["semantic_issues"])

        skip_path = self.project / "03_figure_redraw" / "skip_reason.md"
        skip_path.write_text("", encoding="utf-8")
        self.assertFalse(module.stage_status(self.project, figure_stage)["skipped_by_user"])

        result = run(
            PROJECT_STATUS,
            "--review-root",
            self.root,
            "--project-id",
            self.project_id,
            "--require-complete",
        )
        self.assertNotEqual(result.returncode, 0)

    def test_reference_metadata_requires_doi_or_journal_locator(self) -> None:
        spec = importlib.util.spec_from_file_location("review_final_audit", AUDIT)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        rows = {"P001": {"paper_id": "P001"}}
        self.assertEqual(module.actual_incomplete_references(self.root, ["P001"], rows), [])

        metadata_path = self.root / "review-library" / "metadata" / "papers" / "P001.metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["doi"] = {"value": ""}
        write_json(metadata_path, metadata)
        issues = module.actual_incomplete_references(self.root, ["P001"], rows)
        self.assertEqual(issues[0]["missing"], ["doi_or_volume_and_page_locator"])

        metadata["volume"] = {"value": "12"}
        metadata["article_number"] = {"value": "104321"}
        write_json(metadata_path, metadata)
        self.assertEqual(module.actual_incomplete_references(self.root, ["P001"], rows), [])

    def test_stable_citations_audit_and_docx_chemistry(self) -> None:
        payload = {
            "front_matter": self._front_matter(),
            "sections": [
                {
                    "section_id": "sec1",
                    "title": "1. Introduction",
                    "paragraphs": [
                        {
                            "paragraph_id": "sec1-p1",
                            "paragraph_type": "comparison",
                            "markdown": "Palladium carbonylation and nickel electrocarboxylation provide distinct entry points to allenes [@P001; @P002].",
                            "cited_paper_ids": ["P001", "P002"],
                            "evidence_ids": ["P001-E01", "P002-E01"],
                        },
                        {
                            "paragraph_id": "sec1-p2",
                            "paragraph_type": "mechanism",
                            "markdown": "The proposed pathways should remain qualified because their evidentiary bases differ [@P001; @P002]. CO_2_ incorporation, sp^2^ rehybridization, η1-allenyl binding, and η3-propargyl binding are discussed without converting locants such as C1.\n\n| Method | Distinction |\n|---|---|\n| Palladium | Carbonylation |\n| Nickel | Electrocarboxylation |",
                            "cited_paper_ids": ["P001", "P002"],
                            "evidence_ids": ["P001-E02", "P002-E02"],
                        },
                    ],
                },
                {
                    "section_id": "sec2",
                    "title": "2. Conclusion and Outlook",
                    "paragraphs": [
                        {
                            "paragraph_id": "sec2-p1",
                            "paragraph_type": "limitation_or_gap",
                            "markdown": "Both approaches retain limitations in scope and direct mechanistic verification today [@P001; @P002]. H_2_O and S_N2_ notation exercise explicit subscripts.",
                            "cited_paper_ids": ["P001", "P002"],
                            "evidence_ids": ["P001-E01", "P001-E02", "P002-E01", "P002-E02"],
                        }
                    ],
                },
            ],
        }
        write_json(self.project / "02_section_drafting" / "section_drafts.json", payload)
        p001_metadata_path = (
            self.root / "review-library" / "metadata" / "papers" / "P001.metadata.json"
        )
        p001_metadata = json.loads(p001_metadata_path.read_text(encoding="utf-8"))
        p001_metadata["journal"] = {"value": "46-Journal of Allene Chemistry 2020"}
        write_json(p001_metadata_path, p001_metadata)
        write_json(
            self.project / "01_matrix_outline" / "section_blueprint.json",
            {
                "coverage_contract": {
                    "minimum_manuscript_words": 60,
                    "dimensions": [
                        {
                            "name": "substrate_class",
                            "items": [
                                {
                                    "name": "propargylic carbonates",
                                    "required": True,
                                    "covered_by": ["P001", "P002"],
                                }
                            ],
                        }
                    ],
                },
                "sections": [
                    {
                        "section_id": "sec1",
                        "title": "1. Introduction",
                        "target_words": 41,
                        "paragraph_types_required": ["comparison", "mechanism"],
                        "review_claims": [
                            {"claim_type": "comparison", "supporting_papers": ["P001", "P002"]}
                        ],
                    },
                    {
                        "section_id": "sec2",
                        "title": "2. Conclusion and Outlook",
                        "target_words": 19,
                        "paragraph_types_required": ["limitation_or_gap"],
                        "review_claims": [
                            {"claim_type": "limitation", "supporting_papers": ["P001", "P002"]}
                        ],
                    },
                ],
            },
        )
        for validator in (MATRIX_VALIDATOR, BLUEPRINT_VALIDATOR, DRAFT_VALIDATOR):
            result = run(validator, "--review-root", self.root, "--project-id", self.project_id)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = run(MERGE, "--review-root", self.root, "--project-id", self.project_id)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        first = self.project / "04_first_draft" / "first_draft.md"
        text = first.read_text(encoding="utf-8")
        self.assertIn("[1,2]", text)
        self.assertNotIn("[@P", text)
        self.assertNotIn("[P001]", text)
        self.assertIn("*Journal of Allene Chemistry* 2020.", text)
        self.assertNotIn("46-Journal", text)
        self.assertNotIn("2020* 2020", text)

        skip = self.project / "03_figure_redraw" / "skip_reason.md"
        skip.parent.mkdir(parents=True, exist_ok=True)
        skip.write_text("Text-first regression fixture.\n", encoding="utf-8")
        final_dir = self.project / "05_final_audit"
        final_dir.mkdir(parents=True, exist_ok=True)
        final = final_dir / "final_draft.md"
        final.write_text(text, encoding="utf-8")
        result = run(AUDIT, "--review-root", self.root, "--project-id", self.project_id, "--phase", "preflight")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        write_json(
            final_dir / "semantic_audit.json",
            {
                "model": "fixture-model",
                "checks": [
                    {
                        "check_id": "A001",
                        "section_id": "sec1",
                        "paragraph_id": "sec1-p1",
                        "text_span": "Palladium carbonylation and nickel electrocarboxylation provide distinct entry points to allenes [@P001; @P002].",
                        "cited_paper_ids": ["P001", "P002"],
                        "evidence_ids": ["P001-E01", "P002-E01"],
                        "source_checked": True,
                        "support_scope": "full",
                        "verdict": "supported",
                        "comment": "Fixture claim is supported.",
                    },
                    {
                        "check_id": "A002",
                        "section_id": "sec2",
                        "paragraph_id": "sec2-p1",
                        "text_span": "Both approaches retain limitations in scope and direct mechanistic verification today [@P001; @P002].",
                        "cited_paper_ids": ["P001", "P002"],
                        "evidence_ids": ["P001-E01", "P002-E01"],
                        "source_checked": True,
                        "support_scope": "full",
                        "verdict": "supported",
                        "comment": "Fixture claim is supported.",
                    },
                ],
                "section_checks": [
                    {"section_id": "sec1", "coverage_complete": True, "comment": "checked"},
                    {"section_id": "sec2", "coverage_complete": True, "comment": "checked"},
                ],
                "changes_made": [],
                "unresolved_blockers": [],
            },
        )
        result = run(AUDIT, "--review-root", self.root, "--project-id", self.project_id, "--phase", "release")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        docx = final_dir / "final_draft.docx"
        result = run(MD2DOCX, "--input", final, "--output", docx)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = run(DOCX_AUDIT, "--input", docx, "--markdown", final)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        document = Document(docx)
        self.assertEqual(len(document.tables), 1)
        self.assertGreater(sum(bool(run.font.subscript) for p in document.paragraphs for run in p.runs), 0)
        self.assertGreater(sum(bool(run.font.superscript) for p in document.paragraphs for run in p.runs), 0)
        c1_runs = [run for p in document.paragraphs for run in p.runs if "C1" in run.text]
        self.assertTrue(c1_runs)
        self.assertTrue(all(not run.font.subscript and not run.font.superscript for run in c1_runs))
        eta_paragraphs = [p for p in document.paragraphs if "η1" in p.text and "η3" in p.text]
        self.assertTrue(eta_paragraphs)
        eta_superscripts = [
            run.text
            for paragraph in eta_paragraphs
            for run in paragraph.runs
            if run.font.superscript
        ]
        self.assertIn("1", eta_superscripts)
        self.assertIn("3", eta_superscripts)

        write_json(
            final_dir / "semantic_audit.json",
            {
                "model": "fixture-model",
                "checks": [
                    {
                        "check_id": "A001",
                        "section_id": "sec1",
                        "paragraph_id": "sec1-p1",
                        "text_span": "Representative claim from Introduction section reviewed against evidence",
                        "cited_paper_ids": ["P001", "P002"],
                        "evidence_ids": ["P001-E01", "P002-E01"],
                        "verdict": "supported",
                        "comment": "Fixture placeholder must fail.",
                    },
                    {
                        "check_id": "A002",
                        "section_id": "sec2",
                        "paragraph_id": "sec2-p1",
                        "text_span": "Both approaches retain limitations in scope and direct mechanistic verification today [@P001; @P002].",
                        "cited_paper_ids": ["P001", "P002"],
                        "evidence_ids": ["P001-E01", "P002-E01"],
                        "verdict": "supported",
                        "comment": "Fixture claim is supported.",
                    },
                ],
                "section_checks": [
                    {"section_id": "sec1", "coverage_complete": True, "comment": "checked"},
                    {"section_id": "sec2", "coverage_complete": True, "comment": "checked"},
                ],
                "changes_made": [],
                "unresolved_blockers": [],
            },
        )
        result = run(AUDIT, "--review-root", self.root, "--project-id", self.project_id, "--phase", "release")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("placeholder text_span", result.stdout)

        semantic_payload = json.loads(
            (final_dir / "semantic_audit.json").read_text(encoding="utf-8")
        )
        semantic_payload["checks"][0]["text_span"] = (
            "A plausible but fabricated mechanistic statement that is absent from the linked paragraph."
        )
        write_json(final_dir / "semantic_audit.json", semantic_payload)
        result = run(AUDIT, "--review-root", self.root, "--project-id", self.project_id, "--phase", "release")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("text_span is not found in paragraph", result.stdout)

        write_json(
            final_dir / "semantic_audit.json",
            {
                "model": "fixture-model",
                "checks": [
                    {
                        "check_id": "A001",
                        "section_id": "sec1",
                        "paragraph_id": "sec1-p1",
                        "text_span": "Palladium carbonylation and nickel electrocarboxylation provide distinct entry points to allenes [@P001; @P002].",
                        "cited_paper_ids": ["P001", "P002"],
                        "evidence_ids": ["P001-E01", "P002-E01"],
                        "verdict": "supported",
                        "comment": "Fixture claim is supported.",
                    },
                    {
                        "check_id": "A002",
                        "section_id": "sec2",
                        "paragraph_id": "sec2-p1",
                        "text_span": "Both approaches retain limitations in scope and direct mechanistic verification today [@P001; @P002].",
                        "cited_paper_ids": ["P001", "P002"],
                        "evidence_ids": ["P001-E01", "P002-E01"],
                        "verdict": "supported",
                        "comment": "Fixture claim is supported.",
                    },
                ],
                "section_checks": [
                    {"section_id": "sec1", "coverage_complete": True, "comment": "checked"},
                    {"section_id": "sec2", "coverage_complete": True, "comment": "checked"},
                ],
                "changes_made": [],
                "unresolved_blockers": [],
            },
        )
        metadata_path = (
            self.root / "review-library" / "metadata" / "papers" / "P002.metadata.json"
        )
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["journal"] = {"value": ""}
        write_json(metadata_path, metadata)
        citations_path = self.project / "04_first_draft" / "citations.json"
        citations = json.loads(citations_path.read_text(encoding="utf-8"))
        citations["incomplete_reference_metadata"] = []
        write_json(citations_path, citations)
        result = run(AUDIT, "--review-root", self.root, "--project-id", self.project_id, "--phase", "release")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("incomplete_reference_metadata", result.stdout)

        metadata["journal"] = {"value": "Journal of Allene Chemistry"}
        write_json(metadata_path, metadata)
        (self.project / "00_discovery" / "screening_validation.json").unlink()
        result = run(AUDIT, "--review-root", self.root, "--project-id", self.project_id, "--phase", "release")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing_upstream_validation:screening", result.stdout)

    def test_free_form_length_and_paragraph_mix_are_warnings(self) -> None:
        write_json(
            self.project / "01_matrix_outline" / "section_blueprint.json",
            {
                "coverage_contract": {"suggested_manuscript_words": 5000, "dimensions": []},
                "sections": [
                    {
                        "section_id": "sec1",
                        "title": "A focused narrative",
                        "target_words": 2000,
                        "paragraph_types_required": ["comparison", "limitation_or_gap"],
                    }
                ],
            },
        )
        write_json(
            self.project / "02_section_drafting" / "section_drafts.json",
            {
                "front_matter": self._front_matter(),
                "sections": [
                    {
                        "section_id": "sec1",
                        "title": "A focused narrative",
                        "paragraphs": [
                            {
                                "markdown": "A concise evidence-led discussion may choose its own paragraph pattern [@P001].",
                                "evidence_ids": ["P001-E01"],
                            }
                        ],
                    }
                ],
            },
        )
        result = run(BLUEPRINT_VALIDATOR, "--review-root", self.root, "--project-id", self.project_id)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = run(DRAFT_VALIDATOR, "--review-root", self.root, "--project-id", self.project_id)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(
            (self.project / "02_section_drafting" / "section_draft_validation.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(any("planning estimate" in warning for warning in report["warnings"]))

    def test_duplicate_template_paragraphs_are_blocked(self) -> None:
        write_json(
            self.project / "01_matrix_outline" / "section_blueprint.json",
            {
                "coverage_contract": {"dimensions": []},
                "sections": [{"section_id": "sec1", "title": "Review"}],
            },
        )
        repeated = (
            "This deliberately repeated review paragraph contains enough words to represent template padding. "
            "It makes a broad comparison without adding paper-specific chemical evidence, scope boundaries, "
            "reaction conditions, selectivity values, mechanistic distinctions, or meaningful interpretation "
            "for the reader, and therefore should never be counted twice in a finished manuscript"
        )
        write_json(
            self.project / "02_section_drafting" / "section_drafts.json",
            {
                "front_matter": self._front_matter(),
                "sections": [
                    {
                        "section_id": "sec1",
                        "title": "Review",
                        "paragraphs": [
                            {"paragraph_id": "sec1-p1", "markdown": repeated + " [@P001].", "evidence_ids": ["P001-E01"]},
                            {"paragraph_id": "sec1-p2", "markdown": repeated + " [@P002].", "evidence_ids": ["P002-E01"]},
                        ],
                    }
                ],
            },
        )
        result = run(DRAFT_VALIDATOR, "--review-root", self.root, "--project-id", self.project_id)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicated long paragraph", result.stdout)

    def test_matrix_boilerplate_across_papers_is_blocked(self) -> None:
        repeated = (
            "The experimental procedures and characterization data fully support the proposed pathway, "
            "while systematic optimization establishes broad scope and practical utility for this method."
        )
        rows = [
            {
                "paper_id": f"P{i:03d}",
                "title": f"Distinct paper {i}",
                "role_after_reading": "background",
                "main_content": repeated,
            }
            for i in range(1, 6)
        ]
        write_json(
            self.project / "01_matrix_outline" / "literature_matrix.json", {"papers": rows}
        )
        result = run(MATRIX_VALIDATOR, "--review-root", self.root, "--project-id", self.project_id)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("boilerplate sentence repeated", result.stdout)


if __name__ == "__main__":
    unittest.main()
