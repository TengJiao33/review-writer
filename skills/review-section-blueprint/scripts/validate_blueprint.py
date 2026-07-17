#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def matrix_ids(matrix: Any) -> set[str]:
    if isinstance(matrix, list):
        rows = matrix
    elif isinstance(matrix, dict):
        rows = matrix.get("papers") or matrix.get("rows") or matrix.get("literature_matrix") or []
    else:
        rows = []
    return {str(row.get("paper_id")) for row in rows if isinstance(row, dict) and row.get("paper_id")}


def supporting_ids(claim: dict[str, Any]) -> list[str]:
    raw = claim.get("supporting_papers") or claim.get("papers") or []
    result = []
    for item in raw:
        if isinstance(item, dict) and item.get("paper_id"):
            result.append(str(item["paper_id"]))
        elif isinstance(item, str):
            result.append(item)
    return result


def validate(project: Path) -> dict[str, Any]:
    stage = project / "01_matrix_outline"
    blueprint_path = stage / "section_blueprint.json"
    matrix_path = stage / "literature_matrix.json"
    blueprint = read_json(blueprint_path)
    known_ids = matrix_ids(read_json(matrix_path))
    blockers: list[str] = []
    warnings: list[str] = []

    contract = blueprint.get("coverage_contract") if isinstance(blueprint, dict) else None
    if not isinstance(contract, dict):
        warnings.append("coverage_contract is missing; title/coverage should be reviewed before drafting")
        contract = {}
    minimum_words = int(
        contract.get("suggested_manuscript_words")
        or contract.get("minimum_manuscript_words")
        or 0
    )
    dimensions = contract.get("dimensions") or []
    if not isinstance(dimensions, list) or not dimensions:
        warnings.append("coverage_contract.dimensions is missing or empty")
        dimensions = []
    for dimension in dimensions:
        if not isinstance(dimension, dict):
            warnings.append("coverage dimension is not an object")
            continue
        name = str(dimension.get("name") or "unnamed")
        items = dimension.get("items") or []
        if not isinstance(items, list) or not items:
            warnings.append(f"coverage dimension {name} has no items")
            continue
        for item in items:
            if not isinstance(item, dict):
                warnings.append(f"coverage dimension {name} contains a non-object item")
                continue
            label = str(item.get("name") or "unnamed")
            if not item.get("required", False):
                continue
            covered = [str(pid) for pid in item.get("covered_by") or []]
            decision = item.get("scope_decision")
            if not covered:
                if decision == "exclude_with_title_scope_update" and str(item.get("reason") or "").strip():
                    warnings.append(f"required coverage item excluded with scope update: {name}/{label}")
                else:
                    warnings.append(f"important coverage item is uncovered: {name}/{label}")
            for pid in covered:
                if pid not in known_ids:
                    blockers.append(f"coverage item {name}/{label} references unknown paper {pid}")

    sections = blueprint.get("sections") if isinstance(blueprint, dict) else None
    if not isinstance(sections, list) or not sections:
        blockers.append("sections is missing or empty")
        sections = []
    total_target_words = 0
    seen_section_ids: set[str] = set()
    for section in sections:
        if not isinstance(section, dict):
            blockers.append("section entry is not an object")
            continue
        sid = str(section.get("section_id") or "<missing>")
        if sid == "<missing>":
            blockers.append("section_id is missing")
        elif sid in seen_section_ids:
            blockers.append(f"duplicate section_id: {sid}")
        else:
            seen_section_ids.add(sid)
        if not str(section.get("title") or "").strip():
            blockers.append(f"{sid}: title is missing")
        words = int(section.get("target_words") or 0)
        total_target_words += words
        claims = section.get("review_claims") or []
        if not isinstance(claims, list) or not claims:
            warnings.append(f"{sid}: review_claims is missing or empty")
            continue
        for index, claim in enumerate(claims, start=1):
            if not isinstance(claim, dict):
                blockers.append(f"{sid}: claim {index} is not an object")
                continue
            pids = supporting_ids(claim)
            if not pids:
                warnings.append(f"{sid}: suggested claim {index} has no supporting papers")
            for pid in pids:
                if pid not in known_ids:
                    blockers.append(f"{sid}: claim {index} references unknown paper {pid}")
            claim_type = str(claim.get("claim_type") or "")
            if claim_type in {"comparison", "contrast", "limitation", "mechanism"} and len(set(pids)) < 2:
                warnings.append(f"{sid}: {claim_type} claim {index} uses fewer than two papers")

    if minimum_words and total_target_words and total_target_words < minimum_words:
        warnings.append(
            f"total target words {total_target_words} is below the suggested {minimum_words}"
        )
    return {
        "project_id": project.name,
        "blueprint_path": str(blueprint_path),
        "minimum_manuscript_words": minimum_words,
        "total_target_words": total_target_words,
        "blocking_issues": blockers,
        "warnings": warnings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate review coverage and blueprint depth.")
    parser.add_argument("--review-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--project-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project = Path(args.review_root).resolve() / "review-projects" / args.project_id
    stage = project / "01_matrix_outline"
    for required in (stage / "section_blueprint.json", stage / "literature_matrix.json"):
        if not required.exists():
            raise SystemExit(f"Missing required input: {required}")
    report = validate(project)
    (stage / "blueprint_validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Blueprint Validation",
        "",
        f"- Target words: {report['total_target_words']}",
        f"- Minimum words: {report['minimum_manuscript_words']}",
        f"- Blocking issues: {len(report['blocking_issues'])}",
        f"- Warnings: {len(report['warnings'])}",
        "",
    ]
    lines.extend(f"- BLOCKER: {item}" for item in report["blocking_issues"])
    lines.extend(f"- WARNING: {item}" for item in report["warnings"])
    (stage / "blueprint_validation.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Wrote blueprint validation to {stage}")
    if report["blocking_issues"]:
        print(f"BLOCKING ISSUES: {len(report['blocking_issues'])}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
