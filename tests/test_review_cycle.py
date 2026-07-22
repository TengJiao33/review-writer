from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
BLUEPRINT_INIT = REPO / "skills" / "review-section-blueprint" / "scripts" / "init_section_blueprint.py"
REVIEW_CYCLE = REPO / "skills" / "review-writing-orchestrator" / "scripts" / "review_cycle.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class ReviewCycleTests(unittest.TestCase):
    def test_general_blueprint_uses_topic_contract_not_allene_template(self) -> None:
        module = load_module("general_blueprint", BLUEPRINT_INIT)
        coverage = module.build_coverage_contract(
            "enzymatic PET depolymerization",
            [],
            [],
            "comprehensive",
            ["feedstock state", "enzyme engineering"],
            [{"label": "feedstock state", "paper_ids": ["P218"], "status": "mapped"}],
            "general",
        )
        section = module.build_section(
            {"section_id": "sec2", "title": "PET substrate and accessibility"},
            [{"paper_id": "P218", "title": "PET hydrolase", "role_after_reading": "core"}],
            ["feedstock state", "reaction conditions"],
            {},
            {},
            "Introduction",
            "Enzyme engineering",
            "How do feedstock and reaction conditions determine measured PET hydrolysis?",
            "general",
            "comprehensive",
        )
        rendered = json.dumps({"coverage": coverage, "section": section}, ensure_ascii=False).lower()
        self.assertIn("feedstock state", rendered)
        self.assertIn("pet substrate", rendered)
        for leaked in ("allene", "propargyl", "copper catalysis", "precursor class"):
            self.assertNotIn(leaked, rendered)
        self.assertTrue(
            all(claim["status"] == "editorial_prompt_requires_evidence_authoring" for claim in section["review_claims"])
        )

    def test_cycle_returns_to_evidence_and_exposes_cross_stage_failures(self) -> None:
        module = load_module("review_cycle", REVIEW_CYCLE)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_id = "pet-review"
            project = root / "review-projects" / project_id
            write_json(
                project / "00_discovery" / "topic_contract.json",
                {"topic": "enzymatic PET recycling", "review_profile": "comprehensive"},
            )
            write_json(project / "01_matrix_outline" / "literature_matrix.json", {"papers": []})
            write_json(project / "01_matrix_outline" / "matrix_validation.json", {"blocking_issues": []})
            write_json(
                project / "01_matrix_outline" / "section_blueprint.json",
                {
                    "review_topic": "enzymatic PET recycling",
                    "rule_pack": "general",
                    "status": "draft_initialization_needs_semantic_review",
                    "sections": [
                        {
                            "section_id": "sec1",
                            "title": "PET feedstocks",
                            "section_thesis": "Explain propargylic precursors and allene products.",
                            "review_claims": [],
                        }
                    ],
                },
            )
            write_json(
                project / "01_matrix_outline" / "quality_gate_prewrite.json",
                {
                    "risk_signals": [
                        {
                            "risk_id": "evidence_base_depth",
                            "summary": "Evidence is thin.",
                            "details": ["included_paper_count=0"],
                        }
                    ]
                },
            )
            write_json(project / "02_section_drafting" / "section_drafts.json", {"sections": []})
            write_json(
                project / "02_section_drafting" / "section_draft_validation.json",
                {"blocking_issues": ["draft_empty"], "evidence_usage_by_paper": []},
            )
            write_json(project / "05_final_audit" / "final_draft.md", {})
            (project / "05_final_audit" / "final_draft.docx").write_bytes(b"docx")

            state = module.assess(root, project_id)
            debt_ids = {item["debt_id"] for item in state["quality_debts"]}
            self.assertEqual(state["active_loop"], "evidence")
            self.assertFalse(state["release_ready"])
            self.assertIn("evidence_base_depth", debt_ids)
            self.assertIn("blueprint_domain_leakage", debt_ids)
            self.assertIn("draft_not_ready", debt_ids)


if __name__ == "__main__":
    unittest.main()
