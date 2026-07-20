#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
TABLE_ROW_RE = re.compile(r"^\s*\|.+\|\s*$", re.M)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)
REF_HEADING_RE = re.compile(r"^#{1,6}\s+(references|bibliography|reference list)\s*$", re.I | re.M)

QUESTIONS = [
    ("RU-01", "Can a reader explain the field's organizing logic after the opening sections?"),
    ("RU-02", "Can a reader compare representative methods by the variables that affect method choice?"),
    ("RU-03", "Are scope, selectivity, operational limits, and evidence limits visible rather than buried in praise?"),
    ("RU-04", "Do tables or visuals compress a relationship that prose makes hard to see?"),
    ("RU-05", "Are historical/context sources broad enough for orientation while key claims remain deeply anchored?"),
    ("RU-06", "Does each substantive section end with a synthesis, decision implication, boundary, or unresolved question?"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def manuscript_body(text: str) -> str:
    match = REF_HEADING_RE.search(text)
    return text[: match.start()] if match else text


def word_count(text: str) -> int:
    latin = re.findall(r"\b[A-Za-z0-9][A-Za-z0-9'’.-]*\b", text)
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    return len(latin) + len(cjk)


def metrics(project: Path, text: str) -> dict[str, Any]:
    body = manuscript_body(text)
    citations = read_json(project / "04_first_draft" / "citations.json", {})
    entries = citations.get("reference_list") if isinstance(citations, dict) else None
    if not isinstance(entries, list):
        entries = citations.get("references") if isinstance(citations, dict) else []
    portfolio = read_json(project / "01_matrix_outline" / "literature_portfolio.json", {})
    cards = read_json(project / "01_matrix_outline" / "method_cards.json", {})
    card_rows = cards.get("method_cards") if isinstance(cards, dict) else []
    return {
        "manuscript_words": word_count(re.sub(r"<!--.*?-->", "", body, flags=re.S)),
        "section_headings": len([match for match in HEADING_RE.finditer(body) if len(match.group(1)) <= 3]),
        "reference_count": len(entries) if isinstance(entries, list) else 0,
        "image_count": len(IMAGE_RE.findall(body)),
        "markdown_table_rows": len(TABLE_ROW_RE.findall(body)),
        "portfolio_role_counts": portfolio.get("role_counts") if isinstance(portfolio, dict) else {},
        "method_card_count": len(card_rows) if isinstance(card_rows, list) else 0,
    }


def merge_review(path: Path, project_id: str, snapshot: dict[str, Any], source_path: Path) -> dict[str, Any]:
    existing = read_json(path, {})
    old_rows = existing.get("questions") if isinstance(existing, dict) else []
    old_by_id = {
        str(row.get("question_id")): row
        for row in old_rows or []
        if isinstance(row, dict) and row.get("question_id")
    }
    questions = []
    for question_id, prompt in QUESTIONS:
        old = old_by_id.get(question_id, {})
        questions.append(
            {
                "question_id": question_id,
                "prompt": prompt,
                "finding": str(old.get("finding") or ""),
                "decision": str(old.get("decision") or "pending"),
                "rationale": str(old.get("rationale") or ""),
                "revision_actions": old.get("revision_actions") if isinstance(old.get("revision_actions"), list) else [],
            }
        )
    pending = [row["question_id"] for row in questions if row["decision"] == "pending"]
    prior_status = str(existing.get("status") or "") if isinstance(existing, dict) else ""
    return {
        "project_id": project_id,
        "updated_at": utc_now(),
        "manuscript_path": str(source_path),
        "status": "pending" if pending else (prior_status if prior_status == "completed" else "ready_for_completion"),
        "allowed_decisions": ["revise", "accept_as_is", "narrow_scope", "not_applicable"],
        "pending_question_ids": pending,
        "snapshot": snapshot,
        "questions": questions,
        "overall_decision": str(existing.get("overall_decision") or "") if isinstance(existing, dict) else "",
        "summary": str(existing.get("summary") or "") if isinstance(existing, dict) else "",
    }


def review_markdown(project_id: str, snapshot: dict[str, Any], review: dict[str, Any]) -> str:
    lines = [
        "# Reader Utility Review",
        "",
        f"- Project: `{project_id}`",
        f"- Updated: {utc_now()}",
        f"- Status: `{review['status']}`",
        "- Use the structured findings when helpful; unanswered prompts remain editorial observations, not quotas or release gates.",
        "",
        "## Snapshot",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in snapshot.items())
    lines.extend(["", "## Read the manuscript as a reader", ""])
    by_id = {
        str(row.get("question_id")): row
        for row in review.get("questions") or []
        if isinstance(row, dict)
    }
    for index, (question_id, prompt) in enumerate(QUESTIONS, start=1):
        row = by_id.get(question_id, {})
        lines.extend(
            [
                f"### {index}. {prompt} (`{question_id}`)",
                "",
                f"Finding: {row.get('finding') or ''}",
                "",
                f"Decision: {row.get('decision') or ''}",
                "",
                f"Rationale or revision: {row.get('rationale') or ''}",
                "",
            ]
        )
    lines.extend(
        [
            "## Editorial decision",
            "",
            f"- Overall decision: {review.get('overall_decision') or ''}",
            f"- Summary: {review.get('summary') or ''}",
            "",
            "It is valid to accept the manuscript as-is on a question when the rationale explains why the evidence, scope, or manuscript form is already sufficient.",
            "",
        ]
    )
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    review_root = Path(args.review_root).resolve()
    project = review_root / "review-projects" / args.project_id
    final_draft = project / "05_final_audit" / "final_draft.md"
    first_draft = project / "04_first_draft" / "first_draft.md"
    draft_path = final_draft if final_draft.exists() else first_draft
    if not draft_path.exists():
        raise SystemExit("No first_draft.md or final_draft.md found")
    text = draft_path.read_text(encoding="utf-8", errors="ignore")
    snapshot = metrics(project, text)
    stage = project / "05_final_audit"
    stage.mkdir(parents=True, exist_ok=True)
    review_path = stage / "reader_utility_review.json"
    review = merge_review(review_path, args.project_id, snapshot, draft_path)
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (stage / "reader_utility_review.md").write_text(
        review_markdown(args.project_id, snapshot, review), encoding="utf-8"
    )
    (stage / "reader_utility_snapshot.json").write_text(
        json.dumps(
            {
                "project_id": args.project_id,
                "created_at": utc_now(),
                "status": "observational_snapshot_not_a_quota",
                "metrics": snapshot,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Initialized reader utility decision record from {draft_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize a reader-utility decision record without content quotas.")
    parser.add_argument("--review-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--project-id", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
