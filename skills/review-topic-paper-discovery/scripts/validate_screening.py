#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ALLOWED_DECISIONS = {"include", "exclude", "uncertain"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(project: Path) -> dict[str, Any]:
    discovery = project / "00_discovery"
    contract = read_json(discovery / "topic_contract.json")
    selected = read_json(discovery / "selected_discovery_results.json")
    blockers: list[str] = []
    warnings: list[str] = []

    if not isinstance(contract, dict) or not str(contract.get("central_question") or "").strip():
        blockers.append("topic_contract.central_question is missing")
    elif not any(contract.get(field) for field in ("important_coverage", "inclusion_criteria", "exclusion_criteria")):
        warnings.append("topic contract contains a central question but no project-specific criteria")

    screening = selected.get("screening") if isinstance(selected, dict) else None
    if not isinstance(screening, dict):
        blockers.append("screening metadata is missing")
        screening = {}
    status = str(screening.get("status") or "").strip().lower()
    decided_by = str(screening.get("decided_by") or "").strip().lower()
    if status != "confirmed":
        blockers.append("screening.status must be confirmed")
    if decided_by not in {"user", "agent"}:
        blockers.append("screening.decided_by must be user or agent")

    rows = selected.get("screening_decisions") if isinstance(selected, dict) else None
    if not isinstance(rows, list) or not rows:
        blockers.append("screening_decisions is missing or empty")
        rows = []

    decisions: dict[str, str] = {}
    intent_by_paper: dict[str, str] = {}
    citation_hints_by_paper: dict[str, list[str]] = {}
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            blockers.append(f"screening_decisions[{index}] is not an object")
            continue
        paper_id = str(row.get("paper_id") or "").strip()
        decision = str(row.get("decision") or "").strip().lower()
        if not paper_id:
            blockers.append(f"screening_decisions[{index}].paper_id is missing")
            continue
        if paper_id in decisions:
            blockers.append(f"duplicate screening decision for {paper_id}")
        decisions[paper_id] = decision
        intent_by_paper[paper_id] = str(row.get("portfolio_intent_hint") or "unrecorded")
        raw_hints = row.get("citation_role_hints")
        citation_hints_by_paper[paper_id] = (
            [str(value) for value in raw_hints if str(value).strip()]
            if isinstance(raw_hints, list)
            else []
        )
        if decision not in ALLOWED_DECISIONS:
            blockers.append(f"{paper_id}: decision must be include, exclude, or uncertain")
        if not str(row.get("relevance_summary") or "").strip():
            blockers.append(f"{paper_id}: relevance_summary is missing")
        if not str(row.get("decision_basis") or "").strip():
            blockers.append(f"{paper_id}: decision_basis is missing")
        if status == "confirmed" and decision == "uncertain":
            blockers.append(f"{paper_id}: uncertain decision remains after confirmation")

    candidate_ids = {
        str(item) for item in (selected.get("candidate_paper_ids") or []) if str(item).strip()
    }
    if not candidate_ids:
        blockers.append("candidate_paper_ids is missing or empty")
    elif set(decisions) != candidate_ids:
        blockers.append("screening_decisions must cover every candidate_paper_id exactly once")

    retained = {
        str(row.get("paper_id"))
        for row in (selected.get("local_papers") or [])
        if isinstance(row, dict) and row.get("paper_id")
    }
    included = {paper_id for paper_id, decision in decisions.items() if decision == "include"}
    if retained != included:
        blockers.append("local_papers must contain exactly the papers marked include")

    counts = {decision: sum(value == decision for value in decisions.values()) for decision in sorted(ALLOWED_DECISIONS)}
    portfolio_counts = Counter(intent_by_paper.get(paper_id, "unrecorded") for paper_id in included)
    citation_role_counts = Counter(
        role for paper_id in included for role in citation_hints_by_paper.get(paper_id, [])
    )
    if status == "confirmed" and not included:
        warnings.append("screening confirmed with no included papers")
    if included and not any(role in portfolio_counts for role in ("supporting", "background")):
        warnings.append(
            "retained portfolio has no supporting/background intent recorded; inspect whether readers still have enough comparison and orientation material"
        )
    return {
        "project_id": project.name,
        "screening_status": status,
        "decided_by": decided_by,
        "decision_counts": counts,
        "portfolio_intent_counts": dict(portfolio_counts),
        "citation_role_hint_counts": dict(citation_role_counts),
        "blocking_issues": sorted(set(blockers)),
        "warnings": warnings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate topic-driven paper screening decisions.")
    parser.add_argument("--review-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--project-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project = Path(args.review_root).resolve() / "review-projects" / args.project_id
    for required in (
        project / "00_discovery" / "topic_contract.json",
        project / "00_discovery" / "selected_discovery_results.json",
    ):
        if not required.exists():
            raise SystemExit(f"Missing required input: {required}")
    report = validate(project)
    out = project / "00_discovery" / "screening_validation.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote screening validation to {out}")
    if report["blocking_issues"]:
        print(f"BLOCKING ISSUES: {len(report['blocking_issues'])}")
        for issue in report["blocking_issues"]:
            print(f"- {issue}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
