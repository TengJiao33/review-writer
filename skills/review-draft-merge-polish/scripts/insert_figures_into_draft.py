#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
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


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def load_available_figures(project: Path) -> tuple[str, list[dict[str, Any]]]:
    prepared: list[dict[str, Any]] = []
    redrawn_path = project / "03_figure_redraw" / "redrawn_figure_manifest.json"
    if redrawn_path.exists():
        data = read_json(redrawn_path)
        figures = data.get("figures") if isinstance(data, dict) else None
        if isinstance(figures, list):
            prepared.extend(
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
            )
    original_path = project / "03_figure_redraw" / "review_visual_manifest.json"
    if original_path.exists():
        data = read_json(original_path)
        visuals = data.get("visuals") if isinstance(data, dict) else None
        if isinstance(visuals, list):
            prepared.extend(
                visual
                for visual in visuals
                if isinstance(visual, dict)
                and visual.get("status") == "original_verified"
                and visual.get("verification_status") == "passed"
                and visual.get("original_image")
            )
    if prepared:
        statuses = {str(figure.get("status")) for figure in prepared}
        mode = statuses.pop() if len(statuses) == 1 else "prepared_mixed"
        return mode, prepared
    candidates_path = project / "02_section_drafting" / "figure_candidates.json"
    if not candidates_path.exists():
        return "none", []
    data = read_json(candidates_path)
    figures = data.get("figures") if isinstance(data, dict) else data
    source = [f for f in figures or [] if isinstance(f, dict) and f.get("source_image_path")]
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
    elif status == "original_verified":
        src = figure.get("original_image")
    else:
        src = figure.get("source_image_path")
    if not src:
        return None
    src_path = Path(str(src))
    if not src_path.exists():
        src_path = project / src_path
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
    label = figure.get("source_label") or figure.get("visual_id") or f"Figure {index}"
    caption = figure.get("caption") or figure.get("source_caption_text") or figure.get("what_it_shows") or ""
    source_title = figure.get("title") or "the cited source paper"
    status = figure.get("status")
    reuse_rights = figure.get("reuse_rights") if isinstance(figure.get("reuse_rights"), dict) else {}
    attribution = str(reuse_rights.get("attribution_text") or "").strip()
    if status == "redrawn":
        note = "Redrawn figure verified against the source"
    elif status == "source_verified":
        note = "Source figure reproduced unchanged with attribution"
    elif status == "original_verified":
        basis = ", ".join(str(pid) for pid in figure.get("source_paper_ids") or [] if pid)
        note = f"Original review synthesis based on the cited studies{f' ({basis})' if basis else ''}"
        source_title = ""
    else:
        note = "Unverified source figure candidate"
    source_clause = f" Source: {source_title}, {label}." if source_title else ""
    rights_clause = f" {attribution}" if attribution else ""
    return (
        f"\n\n![{label}]({rel_path})\n\n"
        f"**Figure {index}.** {caption}{source_clause} {note}.{rights_clause}\n\n"
    )


def heading_aliases(section_id: str, section_heading: str) -> list[str]:
    heading = str(section_heading or "").strip()
    if not heading:
        return []
    # Derive placement aliases only from the project's own blueprint.  The old
    # fallback silently carried allene-specific headings into every review.
    without_number = re.sub(r"^\d+[.)]?\s*", "", heading).strip()
    return list(dict.fromkeys(value for value in (heading, without_number) if value))


def blueprint_headings(project: Path) -> dict[str, str]:
    payload = read_json(project / "01_matrix_outline" / "section_blueprint.json")
    if not isinstance(payload, dict):
        return {}
    return {
        str(section.get("section_id")): str(section.get("title") or "").strip()
        for section in payload.get("sections") or []
        if isinstance(section, dict) and section.get("section_id") and section.get("title")
    }


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
    section_headings = blueprint_headings(project)
    section_order = {section_id: index for index, section_id in enumerate(section_headings)}
    section_counts: dict[str, int] = {}
    for figure in figures:
        section_id = str(figure.get("section_id") or "")
        if section_counts.get(section_id, 0) >= max_per_section:
            continue
        section_counts[section_id] = section_counts.get(section_id, 0) + 1
        selected.append(figure)
    selected.sort(key=lambda row: section_order.get(str(row.get("section_id") or ""), 10**6))

    draft_paths = [first_draft]
    final_draft = project / "05_final_audit" / "final_draft.md"
    if final_draft.exists():
        draft_paths.append(final_draft)
    texts = {path: read_text(path) for path in draft_paths}
    inserted: list[dict[str, Any]] = []
    for index, figure in enumerate(selected, start=1):
        manuscript_callout = str(figure.get("manuscript_callout") or "").strip()
        if manuscript_callout and manuscript_callout not in texts[first_draft]:
            raise ValueError(
                f"The authored manuscript_callout for {figure.get('source_label') or index} "
                "is not present in the first draft. Integrate the figure into the prose before insertion."
            )
        rel = copy_figure(project, figure, index, mode)
        if not rel:
            continue
        section_id = str(figure.get("section_id") or "")
        heading = figure.get("section_heading") or section_headings.get(section_id, "")
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
                "figure_id": figure.get("figure_id"),
                "inventory_candidate_id": figure.get("inventory_candidate_id"),
                "section_id": figure.get("section_id"),
                "paper_id": figure.get("paper_id"),
                "source_label": figure.get("source_label") or figure.get("visual_id"),
                "inserted_path": rel,
                "inserted_sha256": file_sha256(project / "04_first_draft" / rel),
                "accepted_image_sha256": figure.get("accepted_image_sha256"),
                "reader_job": figure.get("reader_job"),
                "placement_rationale": figure.get("placement_rationale"),
                "manuscript_callout": manuscript_callout,
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
            "source_verified figures are unchanged, source-checked figures; original_verified assets are independently checked review syntheses. "
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
