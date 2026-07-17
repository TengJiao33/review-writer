#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_available_figures(project: Path) -> tuple[str, list[dict[str, Any]]]:
    redrawn_path = project / "03_figure_redraw" / "redrawn_figure_manifest.json"
    if redrawn_path.exists():
        data = read_json(redrawn_path)
        figures = data.get("figures") if isinstance(data, dict) else None
        if isinstance(figures, list):
            usable = [
                f
                for f in figures
                if isinstance(f, dict)
                and (
                    (f.get("status") == "redrawn" and f.get("redrawn_image"))
                    or (
                        f.get("status") == "source_verified"
                        and f.get("verification_status") == "passed"
                        and (f.get("verified_image") or f.get("source_image"))
                    )
                )
            ]
            if usable:
                statuses = {str(f.get("status")) for f in usable}
                mode = statuses.pop() if len(statuses) == 1 else "prepared"
                return mode, usable
    candidates_path = project / "02_section_drafting" / "figure_candidates.json"
    data = read_json(candidates_path)
    figures = data.get("figures") if isinstance(data, dict) else data
    source = [f for f in figures if isinstance(f, dict) and f.get("source_image_path")]
    return "source_candidates", source


def section_number(section_id: str) -> str:
    match = re.search(r"(\d+)", str(section_id or ""))
    return match.group(1) if match else ""


def copy_figure(project: Path, figure: dict[str, Any], index: int, mode: str) -> str | None:
    status = figure.get("status")
    if status == "redrawn":
        src = figure.get("redrawn_image")
    elif status == "source_verified":
        src = figure.get("verified_image") or figure.get("source_image")
    else:
        src = figure.get("source_image_path")
    if not src:
        return None
    src_path = Path(str(src))
    if not src_path.exists():
        return None
    suffix = src_path.suffix.lower() or ".png"
    name = f"figure_{index:02d}{suffix}"
    # Keep the same relative Markdown path valid in both the merged draft and
    # the final-audit copy.  The latter directory may not contain Markdown yet.
    for stage_name in ("04_first_draft", "05_final_audit"):
        out_dir = project / stage_name / "figures"
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, out_dir / name)
    return (Path("figures") / name).as_posix()


def figure_markdown(figure: dict[str, Any], rel_path: str, index: int, mode: str) -> str:
    label = figure.get("source_label") or f"Figure {index}"
    caption = figure.get("source_caption_text") or figure.get("what_it_shows") or ""
    source_title = figure.get("title") or "the cited source paper"
    status = figure.get("status")
    if status == "redrawn":
        note = "Redrawn figure verified against the source"
    elif status == "source_verified":
        note = "Source figure reproduced unchanged with attribution"
    else:
        note = "Unverified source figure candidate"
    return (
        f"\n\n![{label}]({rel_path})\n\n"
        f"**Figure {index}.** {caption} Source: {source_title}, {label}. {note}.\n\n"
    )


def heading_aliases(section_id: str, section_heading: str) -> list[str]:
    aliases = [str(section_heading or "").strip()]
    fallback = {
        "sec1": ["Introduction"],
        "sec2": ["Foundational methods", "activated propargylic", "Copper-catalyzed substitution"],
        "sec3": ["Carbonates", "esters"],
        "sec4": ["Radical", "one-electron", "photoredox"],
        "sec5": ["Direct transformations", "free propargylic alcohols"],
        "sec6": ["Organoboron", "organosilicon", "Stereochemical control", "mechanistic comparison"],
    }
    aliases.extend(fallback.get(str(section_id or ""), []))
    return [a for a in aliases if a]


PARAGRAPH_ID_RE = re.compile(r"<!--\s*paragraph_id:\s*([A-Za-z0-9_\-:.]+)\s*-->")

def insert_after_paragraph(text: str, paragraph_id: str, block: str) -> tuple[str, bool]:
    if not paragraph_id:
        return text, False
    for match in PARAGRAPH_ID_RE.finditer(text):
        if match.group(1) == paragraph_id:
            insert_at = match.end()
            return text[:insert_at] + block + text[insert_at:], True
    return text, False

def insert_after_section(text: str, section_id: str, section_heading: str, block: str) -> tuple[str, bool]:
    for alias in heading_aliases(section_id, section_heading):
        escaped = re.escape(alias)
        pattern = rf"(^#{{2,3}}\s+.*{escaped}.*$)"
        match = re.search(pattern, text, re.M | re.I)
        if match:
            insert_at = match.end()
            return text[:insert_at] + block + text[insert_at:], True
    normalized_heading = str(section_heading or "").strip()
    if not normalized_heading:
        return text, False
    heading = re.escape(normalized_heading)
    patterns = [
        rf"(^##\s+\d+\.?\s*{heading}.*$)",
        rf"(^##\s+{heading}.*$)",
        rf"(^#{{2,3}}\s+.*{heading}.*$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.M | re.I)
        if match:
            insert_at = match.end()
            return text[:insert_at] + block + text[insert_at:], True
    return text, False


def insert_figures(project: Path, max_per_section: int = 1) -> dict[str, Any]:
    first_draft = project / "04_first_draft" / "first_draft.md"
    if not first_draft.exists():
        raise ValueError(f"Missing first draft: {first_draft}")
    mode, figures = load_available_figures(project)
    if not figures:
        raise ValueError("No available figures to insert.")
    selected: list[dict[str, Any]] = []
    section_counts: dict[str, int] = {}
    for figure in figures:
        section_id = str(figure.get("section_id") or "")
        if section_counts.get(section_id, 0) >= max_per_section:
            continue
        section_counts[section_id] = section_counts.get(section_id, 0) + 1
        selected.append(figure)

    draft_paths = [first_draft]
    final_draft = project / "05_final_audit" / "final_draft.md"
    if final_draft.exists():
        draft_paths.append(final_draft)
    texts = {path: read_text(path) for path in draft_paths}
    inserted: list[dict[str, Any]] = []
    for index, figure in enumerate(selected, start=1):
        rel = copy_figure(project, figure, index, mode)
        if not rel:
            continue
        heading = figure.get("section_heading") or ""
        block = figure_markdown(figure, rel, index, mode)
        target_pid = str(figure.get("target_paragraph_id") or "")
        matches: dict[str, bool] = {}
        anchor_mode = "existing"
        for draft_path in draft_paths:
            text = texts[draft_path]
            if f"]({rel})" in text:
                matches[draft_path.parent.name] = True
                continue
            text, matched = insert_after_paragraph(text, target_pid, block)
            anchor_mode = "paragraph" if matched else "section"
            if not matched:
                text, matched = insert_after_section(
                    text,
                    str(figure.get("section_id") or ""),
                    heading,
                    block,
                )
            texts[draft_path] = text
            matches[draft_path.parent.name] = matched
        if not all(matches.values()):
            raise ValueError(
                f"Could not place {figure.get('source_label') or rel} under "
                f"section {figure.get('section_id') or '<missing>'}: "
                f"section_heading={heading!r}"
            )
        inserted.append(
            {
                "figure_number": index,
                "section_id": figure.get("section_id"),
                "paper_id": figure.get("paper_id"),
                "source_label": figure.get("source_label"),
                "inserted_path": rel,
                "mode": figure.get("status") or mode,
                "anchor_mode": anchor_mode,
                "target_paragraph_id": target_pid,
                "matched_heading_by_stage": matches,
            }
        )
    for draft_path, text in texts.items():
        write_text(draft_path, text)
    report = {
        "project_id": project.name,
        "mode": mode,
        "selected_count": len(selected),
        "inserted_count": len(inserted),
        "target_drafts": [path.parent.name for path in draft_paths],
        "inserted": inserted,
        "note": (
            "source_verified figures are unchanged, source-checked figures. "
            "source_candidates mode remains unverified and is blocked from final release."
        ),
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (project / "04_first_draft" / "figure_insertion_report.json").write_text(
        rendered,
        encoding="utf-8",
    )
    if final_draft.exists():
        (project / "05_final_audit" / "figure_insertion_report.json").write_text(
            rendered,
            encoding="utf-8",
        )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Insert available figures into the first draft.")
    parser.add_argument("--review-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--max-per-section", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project = Path(args.review_root).resolve() / "review-projects" / args.project_id
    try:
        report = insert_figures(project, max_per_section=args.max_per_section)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(
        f"Inserted {report['inserted_count']} figures into "
        f"{', '.join(report['target_drafts'])} using mode={report['mode']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
