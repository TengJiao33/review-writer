from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
QUALITY_GATE = (
    REPO
    / "skills"
    / "review-writing-orchestrator"
    / "scripts"
    / "review_quality_gate.py"
)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_gate(root: Path, project_id: str, phase: str = "prewrite") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(QUALITY_GATE),
            "--review-root",
            str(root),
            "--project-id",
            project_id,
            "--phase",
            phase,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class ReviewQualityGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project_id = "thin-comprehensive-review"
        self.project = self.root / "review-projects" / self.project_id
        discovery = self.project / "00_discovery"
        matrix_stage = self.project / "01_matrix_outline"
        write_json(
            discovery / "topic_contract.json",
            {
                "topic": "A broad process-chain review",
                "central_question": "How do materials, methods, and operating conditions interact?",
                "review_profile": "comprehensive",
                "important_coverage": ["materials", "methods", "operating conditions"],
            },
        )
        decisions = []
        matrix = []
        for index in range(1, 11):
            paper_id = f"P{index:03d}"
            study_type = "primary_research" if index <= 6 else "review"
            decisions.append(
                {
                    "paper_id": paper_id,
                    "decision": "include",
                    "study_type": study_type,
                    "relevance_summary": "Directly relevant full-text evidence.",
                    "decision_basis": "The local full text was read.",
                }
            )
            source = self.root / "review-library" / "sources" / f"{paper_id}.md"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(
                "# Results\n\nThe full text reports a study result with methods, conditions, and limitations.\n",
                encoding="utf-8",
            )
            matrix.append(
                {
                    "paper_id": paper_id,
                    "role_after_reading": "core" if index <= 6 else "background",
                    "evidence_anchors": [
                        {
                            "evidence_id": f"{paper_id}-E01",
                            "source_level": "full_text",
                            "source_path": str(source),
                            "source_excerpt": "The full text reports a study result with methods, conditions, and limitations.",
                        }
                    ],
                }
            )
        write_json(
            discovery / "selected_discovery_results.json",
            {
                "screening": {"status": "confirmed", "decided_by": "agent"},
                "candidate_paper_ids": [row["paper_id"] for row in decisions],
                "local_papers": [{"paper_id": row["paper_id"]} for row in decisions],
                "screening_decisions": decisions,
            },
        )
        write_json(matrix_stage / "literature_matrix.json", matrix)
        write_json(matrix_stage / "method_cards.json", {"method_cards": []})
        write_json(
            matrix_stage / "section_blueprint.json",
            {
                "coverage_contract": {
                    "review_profile": "comprehensive",
                    "dimensions": [
                        {
                            "name": "process_chain",
                            "items": [
                                {
                                    "name": "materials and operating conditions",
                                    "required": True,
                                    "covered_by": ["P001", "P002"],
                                }
                            ],
                        }
                    ],
                },
                "sections": [
                    {"section_id": f"S{index}", "target_words": 850}
                    for index in range(1, 7)
                ],
            },
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_depth_signals_are_grouped_advisories_and_cannot_be_self_cleared(self) -> None:
        result = run_gate(self.root, self.project_id)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report_path = self.project / "01_matrix_outline" / "quality_gate_prewrite.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertTrue(report["passed"])
        self.assertEqual(report["blocking_issues"], [])
        risk_ids = {row["risk_id"] for row in report["risk_signals"]}
        self.assertEqual(
            risk_ids,
            {"evidence_base_depth", "comparison_readiness", "blueprint_depth"},
        )
        self.assertLessEqual(len(report["risk_signals"]), 4)

        write_json(
            self.project / "01_matrix_outline" / "evidence_readiness_review.json",
            {
                "status": "completed",
                "decision": "proceed",
                "rationale": "The agent wants to continue despite the thin evidence base.",
                "risk_dispositions": [
                    {
                        "risk_id": risk_id,
                        "disposition": "accepted_by_user",
                        "approved_by": "agent",
                        "rationale": "Agent-created exception.",
                    }
                    for risk_id in sorted(risk_ids)
                ],
            },
        )
        result = run_gate(self.root, self.project_id)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertTrue(any("cannot authorize" in warning for warning in report["warnings"]))
        self.assertEqual(
            {row["risk_id"] for row in report["risk_signals"]},
            risk_ids,
        )

        review = json.loads(
            (
                self.project / "01_matrix_outline" / "evidence_readiness_review.json"
            ).read_text(encoding="utf-8")
        )
        for row in review["risk_dispositions"]:
            row["approved_by"] = "user"
            row["rationale"] = "The user explicitly approved a narrower, shorter deliverable."
        write_json(
            self.project / "01_matrix_outline" / "evidence_readiness_review.json",
            review,
        )
        result = run_gate(self.root, self.project_id)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertTrue(any("cannot authorize" in warning for warning in report["warnings"]))
        self.assertEqual(
            {row["risk_id"] for row in report["risk_signals"]},
            risk_ids,
        )


if __name__ == "__main__":
    unittest.main()
