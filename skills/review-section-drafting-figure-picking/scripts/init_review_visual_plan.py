#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rows(value: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get(key)
    return [item for item in value or [] if isinstance(item, dict)] if isinstance(value, list) else []


def first_substantive_section(sections: list[dict[str, Any]]) -> dict[str, Any]:
    for section in sections:
        title = str(section.get("title") or "").lower()
        if not any(word in title for word in ("introduction", "abstract", "conclusion", "outlook")):
            return section
    return sections[0] if sections else {}


def visual_rows(
    sections: list[dict[str, Any]],
    cards: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    usable_cards = [card for card in cards if card.get("paper_id")]
    paper_ids = [str(card["paper_id"]) for card in usable_cards]
    evidence_ids = [
        str(eid)
        for card in usable_cards
        for eid in card.get("evidence_ids") or []
        if eid
    ]
    first = first_substantive_section(sections)
    first_id = str(first.get("section_id") or "sec1")
    first_title = str(first.get("title") or "Introduction")
    comparison_section = next(
        (
            section
            for section in sections
            if str(section.get("dominant_logic") or "") in {"reaction_type", "precursor_class", "mechanistic_pathway"}
        ),
        first,
    )
    return [
        {
            "visual_id": "RT-01",
            "kind": "markdown_comparison_table",
            "status": "suggested",
            "decision_rationale": "",
            "result_path": "",
            "verification_note": "",
            "required": False,
            "section_id": str(comparison_section.get("section_id") or first_id),
            "section_heading": str(comparison_section.get("title") or first_title),
            "working_title": "Method choice and boundary table",
            "reader_job": "Compare representative methods by substrate, activation, partner, selectivity, scope, limitations, and practical conditions.",
            "source_paper_ids": paper_ids,
            "evidence_ids": evidence_ids,
            "design_prompt": "Build the table from method_cards.json, retaining nulls where the source was not read deeply enough.",
            "verification_requirements": [
                "Each populated cell is traceable to an evidence anchor or directly reopened source location.",
                "Do not turn missing information into a negative result.",
                "Keep the table selective enough to remain readable.",
            ],
        },
    ]


def write_markdown(path: Path, project_id: str, visuals: list[dict[str, Any]]) -> None:
    lines = [
        "# Review Visual Plan",
        "",
        f"Project: `{project_id}`",
        "",
        "This is one evidence-derived starting opportunity, not a ready-made visual quota. The author must identify any other structured display from the manuscript's real comparison needs. Source-paper figures are selected separately and are not replaceable by an automatically generated diagram.",
        "",
    ]
    for visual in visuals:
        lines.extend(
            [
                f"## {visual['visual_id']}: {visual['working_title']}",
                "",
                f"- Kind: `{visual['kind']}`",
                f"- Decision: `{visual['status']}`",
                f"- Decision rationale: {visual.get('decision_rationale') or ''}",
                f"- Suggested placement: `{visual['section_id']}` {visual['section_heading']}",
                f"- Reader job: {visual['reader_job']}",
                f"- Evidence base: {', '.join(visual['source_paper_ids']) or 'to be selected'}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    review_root = Path(args.review_root).resolve()
    project = review_root / "review-projects" / args.project_id
    blueprint = read_json(project / "01_matrix_outline" / "section_blueprint.json", {})
    method_cards = read_json(project / "01_matrix_outline" / "method_cards.json", {})
    sections = rows(blueprint, "sections")
    if not sections:
        raise SystemExit("section_blueprint.json contains no sections")
    plan_path = project / "02_section_drafting" / "review_visual_plan.json"
    existing = read_json(plan_path, {})
    prior_rows = rows(existing, "visuals")
    prior_by_id = {str(row.get("visual_id")): row for row in prior_rows if row.get("visual_id")}
    visuals = visual_rows(sections, rows(method_cards, "method_cards"))
    for visual in visuals:
        prior = prior_by_id.get(str(visual.get("visual_id")), {})
        for key in ("status", "decision_rationale", "result_path", "verification_note"):
            if prior.get(key) not in (None, ""):
                visual[key] = prior[key]
    pending = [row["visual_id"] for row in visuals if row.get("status") == "suggested"]
    payload = {
        "project_id": args.project_id,
        "updated_at": utc_now(),
        "status": "pending" if pending else "resolved",
        "allowed_decisions": ["selected", "adapted", "combined", "skipped"],
        "pending_visual_ids": pending,
        "instructions": "Use this table only when it supports a meaningful comparison. Find any additional table or structured display by reading the whole manuscript and naming a distinct reader job; do not duplicate this template or create an original diagram merely to satisfy a count. The comprehensive source-figure portfolio is handled through figure_candidates.json.",
        "visuals": visuals,
    }
    stage = project / "02_section_drafting"
    write_json(plan_path, payload)
    write_markdown(stage / "review_visual_plan.md", args.project_id, visuals)
    print(f"Wrote {len(visuals)} review visual decisions ({len(pending)} pending) to {stage}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize an advisory plan for evidence-linked structured displays.")
    parser.add_argument("--review-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--project-id", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
