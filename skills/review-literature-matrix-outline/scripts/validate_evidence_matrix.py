#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any


LIGHTWEIGHT_ROLES = {"background", "candidate", "excluded"}
KNOWN_ROLES = LIGHTWEIGHT_ROLES | {"core", "supporting"}
ALLOWED_CERTAINTY = {"direct", "author_interpretation", "review_inference", "unclear"}
ALLOWED_SOURCE_LEVEL = {"full_text", "abstract", "metadata"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def matrix_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("papers", "rows", "literature_matrix"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def word_count(value: Any) -> int:
    return len(re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", str(value or "")))


def resolve_source_path(review_root: Path, raw: str) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else review_root / path


def source_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader

            return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        except Exception as exc:
            raise ValueError(f"could not extract PDF text: {exc}") from exc
    return path.read_text(encoding="utf-8", errors="replace")


def normalize_verbatim(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = value.replace("\u00ad", "").replace("\u200b", "")
    value = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", value)
    value = value.translate(
        str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
    )
    return re.sub(r"\s+", " ", value).strip().lower()


def excerpt_matches_source(excerpt: str, text: str) -> bool:
    if excerpt in text:
        return True
    normalized_text = normalize_verbatim(text)
    normalized_excerpt = normalize_verbatim(excerpt)
    if normalized_excerpt and normalized_excerpt in normalized_text:
        return True
    segments = [
        normalize_verbatim(part)
        for part in re.split(r"(?:\.{3,}|…+)", excerpt)
        if len(normalize_verbatim(part)) >= 12
    ]
    if len(segments) < 2:
        return False
    position = 0
    for segment in segments:
        found = normalized_text.find(segment, position)
        if found < 0:
            return False
        position = found + len(segment)
    return True


def validate_anchor(
    anchor: Any,
    index: int,
    review_root: Path,
    require_source_excerpt: bool = False,
) -> tuple[list[str], list[str], bool]:
    if not isinstance(anchor, dict):
        return [f"evidence_anchors[{index}] is not an object"], [], False
    blockers: list[str] = []
    warnings: list[str] = []
    for field in (
        "evidence_id",
        "note",
        "source_path",
        "locator",
        "source_level",
        "evidence_kind",
        "certainty",
    ):
        if not str(anchor.get(field) or "").strip():
            blockers.append(f"evidence_anchors[{index}].{field} is empty")
    note = str(anchor.get("note") or "").strip()
    if note and len(note) < 20:
        warnings.append(f"evidence_anchors[{index}].note is very short")
    source_excerpt = str(anchor.get("source_excerpt") or "").strip()
    if require_source_excerpt and not source_excerpt:
        blockers.append(
            f"evidence_anchors[{index}].source_excerpt is required for core/supporting evidence"
        )
    elif source_excerpt and len(source_excerpt) < 12:
        warnings.append(f"evidence_anchors[{index}].source_excerpt is very short")
    elif len(source_excerpt) > 700:
        warnings.append(
            f"evidence_anchors[{index}].source_excerpt is longer than a compact verification excerpt"
        )
    certainty = str(anchor.get("certainty") or "").strip()
    if certainty and certainty not in ALLOWED_CERTAINTY:
        blockers.append(
            f"evidence_anchors[{index}].certainty must be one of "
            + ", ".join(sorted(ALLOWED_CERTAINTY))
        )
    source_level = str(anchor.get("source_level") or "").strip()
    if source_level and source_level not in ALLOWED_SOURCE_LEVEL:
        blockers.append(
            f"evidence_anchors[{index}].source_level must be one of "
            + ", ".join(sorted(ALLOWED_SOURCE_LEVEL))
        )
    source_path = str(anchor.get("source_path") or "").strip()
    resolved_source = resolve_source_path(review_root, source_path) if source_path else None
    if resolved_source is not None and not resolved_source.exists():
        blockers.append(f"evidence_anchors[{index}].source_path does not exist: {source_path}")
    excerpt_verified = False
    if source_excerpt and resolved_source is not None and resolved_source.exists():
        try:
            excerpt_verified = excerpt_matches_source(source_excerpt, source_text(resolved_source))
        except ValueError as exc:
            blockers.append(f"evidence_anchors[{index}].source_excerpt could not be checked: {exc}")
        if not excerpt_verified and not any("could not be checked" in item for item in blockers):
            blockers.append(
                f"evidence_anchors[{index}].source_excerpt is not found in the recorded source"
            )
    locator = str(anchor.get("locator") or "").strip().lower()
    compact_locator = re.sub(r"[^a-z]+", "", locator)
    if locator in {"title", "metadata"} or "abstract" in compact_locator:
        if source_level == "full_text":
            blockers.append(f"evidence_anchors[{index}] labels a shallow locator as full_text")
        else:
            warnings.append(f"evidence_anchors[{index}] uses a shallow locator: {locator}")
    if source_level == "full_text" and resolved_source is not None:
        if resolved_source.suffix.lower() not in {".md", ".markdown", ".pdf", ".txt"}:
            blockers.append(f"evidence_anchors[{index}] full_text source is not a text or PDF file")
    return blockers, warnings, excerpt_verified


def validate_row(row: dict[str, Any], min_words: int, review_root: Path) -> dict[str, Any]:
    paper_id = str(row.get("paper_id") or "<missing>")
    blockers: list[str] = []
    warnings: list[str] = []
    for field in ("paper_id", "title"):
        if row.get(field) in (None, "", [], {}):
            blockers.append(f"{field} is missing or empty")
    for field in ("authors", "keywords", "abstract"):
        if row.get(field) in (None, "", [], {}):
            warnings.append(f"{field} is missing or empty")

    role = str(row.get("role_after_reading") or row.get("role") or "core").strip().lower()
    if role not in KNOWN_ROLES:
        warnings.append(f"unrecognized role_after_reading: {role}")
    evidence_required = role not in LIGHTWEIGHT_ROLES

    main_words = word_count(row.get("main_content"))
    if main_words == 0:
        warnings.append("main_content is empty; concise notes are recommended")
    elif min_words and main_words < min_words:
        warnings.append(
            f"main_content has {main_words} words; suggested minimum is {min_words}"
        )

    anchors = row.get("evidence_anchors")
    if not isinstance(anchors, list):
        if evidence_required:
            blockers.append("evidence_anchors is required for core/supporting papers")
        elif anchors is not None:
            blockers.append("evidence_anchors must be a list")
        anchors = []
    if evidence_required and not anchors:
        blockers.append("evidence_anchors needs at least one source-grounded item")
    full_text_anchor_count = 0
    verified_excerpt_count = 0
    for index, anchor in enumerate(anchors):
        anchor_blockers, anchor_warnings, excerpt_verified = validate_anchor(
            anchor,
            index,
            review_root,
            require_source_excerpt=evidence_required,
        )
        blockers.extend(anchor_blockers)
        warnings.extend(anchor_warnings)
        verified_excerpt_count += int(excerpt_verified)
        if isinstance(anchor, dict) and str(anchor.get("source_level") or "").strip() == "full_text":
            full_text_anchor_count += 1
    if evidence_required and full_text_anchor_count == 0:
        blockers.append("core/supporting paper needs at least one full_text evidence anchor")

    figure = row.get("most_relevant_figure")
    if not isinstance(figure, dict):
        warnings.append("most_relevant_figure is missing; acceptable only in text-first mode")
    elif str(figure.get("relevance_reason") or "").strip().lower() in {"first figure", "first image"}:
        warnings.append("most_relevant_figure was selected positionally rather than semantically")

    return {
        "paper_id": paper_id,
        "role_after_reading": role,
        "main_content_words": main_words,
        "evidence_anchor_count": len(anchors),
        "full_text_anchor_count": full_text_anchor_count,
        "verified_excerpt_count": verified_excerpt_count,
        "blocking_issues": blockers,
        "warnings": warnings,
    }


def normalize_sentence(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\bP\d{3}\b|\d+", " ", value.lower())).strip()


def repeated_boilerplate(rows: list[dict[str, Any]]) -> list[str]:
    if len(rows) < 5:
        return []
    sentence_papers: dict[str, set[str]] = {}
    for index, row in enumerate(rows, start=1):
        paper_id = str(row.get("paper_id") or f"row-{index}")
        content = str(row.get("main_content") or "")
        for raw in re.split(r"(?<=[.!?])\s+", content):
            sentence = normalize_sentence(raw)
            if word_count(sentence) < 12:
                continue
            sentence_papers.setdefault(sentence, set()).add(paper_id)
    threshold = max(5, math.ceil(len(rows) * 0.2))
    repeated = [
        (sentence, len(papers))
        for sentence, papers in sentence_papers.items()
        if len(papers) >= threshold
    ]
    repeated.sort(key=lambda item: (-item[1], item[0]))
    return [
        f"boilerplate sentence repeated across {count} papers: {sentence[:140]}"
        for sentence, count in repeated[:10]
    ]


def write_report(stage_dir: Path, report: dict[str, Any]) -> None:
    (stage_dir / "matrix_validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Evidence Matrix Validation",
        "",
        f"- Papers: {report['paper_count']}",
        f"- Blocking issues: {report['blocking_issue_count']}",
        f"- Warnings: {report['warning_count']}",
        "",
    ]
    for issue in report.get("global_blocking_issues") or []:
        lines.append(f"- BLOCKER: {issue}")
    for warning in report.get("global_warnings") or []:
        lines.append(f"- WARNING: {warning}")
    if report.get("global_blocking_issues") or report.get("global_warnings"):
        lines.append("")
    for item in report["papers"]:
        if not item["blocking_issues"] and not item["warnings"]:
            continue
        lines.append(f"## {item['paper_id']}")
        lines.append("")
        for issue in item["blocking_issues"]:
            lines.append(f"- BLOCKER: {issue}")
        for warning in item["warnings"]:
            lines.append(f"- WARNING: {warning}")
        lines.append("")
    (stage_dir / "matrix_validation.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate evidence-grounded literature matrix rows.")
    parser.add_argument("--review-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--project-id", required=True)
    parser.add_argument(
        "--min-main-content-words",
        type=int,
        default=80,
        help="Suggested note length; falling below it produces a warning, not a blocker.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    review_root = Path(args.review_root).resolve()
    stage_dir = review_root / "review-projects" / args.project_id / "01_matrix_outline"
    matrix_path = stage_dir / "literature_matrix.json"
    if not matrix_path.exists():
        raise SystemExit(f"Missing literature matrix: {matrix_path}")
    rows = matrix_rows(read_json(matrix_path))
    papers = [validate_row(row, args.min_main_content_words, review_root) for row in rows]
    global_blockers: list[str] = []
    global_warnings: list[str] = []
    paper_ids = [str(row.get("paper_id") or "") for row in rows]
    duplicate_ids = sorted(pid for pid, count in Counter(paper_ids).items() if pid and count > 1)
    if duplicate_ids:
        global_blockers.append("duplicate paper IDs: " + ", ".join(duplicate_ids))
    anchor_ids = [
        str(anchor.get("evidence_id") or "")
        for row in rows
        for anchor in (row.get("evidence_anchors") or [])
        if isinstance(anchor, dict) and anchor.get("evidence_id")
    ]
    duplicate_anchor_ids = sorted(
        evidence_id for evidence_id, count in Counter(anchor_ids).items() if count > 1
    )
    if duplicate_anchor_ids:
        global_blockers.append("duplicate evidence IDs: " + ", ".join(duplicate_anchor_ids))
    global_blockers.extend(repeated_boilerplate(rows))
    if not rows:
        global_blockers.append("literature_matrix contains no paper rows")
    report = {
        "project_id": args.project_id,
        "matrix_path": str(matrix_path),
        "paper_count": len(rows),
        "minimum_main_content_words": args.min_main_content_words,
        "blocking_issue_count": sum(len(item["blocking_issues"]) for item in papers)
        + len(global_blockers),
        "warning_count": sum(len(item["warnings"]) for item in papers)
        + len(global_warnings),
        "global_blocking_issues": global_blockers,
        "global_warnings": global_warnings,
        "papers": papers,
    }
    write_report(stage_dir, report)
    print(f"Wrote matrix validation to {stage_dir}")
    if report["blocking_issue_count"]:
        print(f"BLOCKING ISSUES: {report['blocking_issue_count']}")
        for issue in report.get("global_blocking_issues") or []:
            print(f"- {issue}")
        for item in report["papers"]:
            for issue in item["blocking_issues"]:
                print(f"- {item['paper_id']}: {issue}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
