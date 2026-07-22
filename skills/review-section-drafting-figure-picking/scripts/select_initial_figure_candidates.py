#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from build_paper_figure_inventory import build_inventory


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def lower(text: Any) -> str:
    return norm(text).lower()


GENERIC_STOPWORDS = {
    "and", "the", "for", "from", "with", "into", "that", "this", "these", "those",
    "review", "section", "study", "studies", "using", "based", "between", "through",
}


def content_terms(text: Any) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z][a-z0-9-]{3,}", lower(text))
        if token not in GENERIC_STOPWORDS
    }


def figure_score(candidate: dict[str, Any], section: dict[str, Any] | None = None) -> int:
    caption = lower(candidate.get("source_caption_text"))
    label = lower(candidate.get("source_label"))
    score = int(candidate.get("inventory_score") or 0)
    if "scheme" in label or "scheme" in caption:
        score += 8
    if "mechanism" in caption or "catalytic cycle" in caption:
        score += 10
    if "scope" in caption:
        score += 4
    if "optimization" in caption:
        score -= 5
    if "gram-scale" in caption or "control experiment" in caption:
        score -= 2
    for term, weight in (
        ("overview", 6),
        ("workflow", 6),
        ("pathway", 6),
        ("comparison", 5),
        ("structure", 4),
        ("performance", 4),
        ("degradation", 4),
        ("recycling", 4),
        ("process", 3),
        ("design", 3),
    ):
        if term in caption:
            score += weight
    if section:
        section_text = lower(" ".join([section.get("heading", ""), section.get("core_argument", "")]))
        if "radical" in section_text and ("radical" in caption or "photoredox" in caption):
            score += 6
        if "stereo" in section_text and ("stereo" in caption or "enantio" in caption or "chiral" in caption):
            score += 5
        if "carbonates" in section_text and "carbonate" in caption:
            score += 4
        if "mechan" in section_text and "mechanism" in caption:
            score += 4
        overlap = content_terms(section_text) & content_terms(caption)
        score += min(12, len(overlap) * 3)
    if candidate.get("source_image_path"):
        score += 4
    return score


def inventory_by_paper(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(paper.get("paper_id")): paper
        for paper in inventory.get("papers", [])
        if isinstance(paper, dict) and paper.get("paper_id")
    }


def section_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("sections", "tasks"):
            if isinstance(payload.get(key), list):
                return [row for row in payload[key] if isinstance(row, dict)]
    raise ValueError(
        "section_tasks.json must be a list or an object with a sections/tasks list"
    )


def inferred_figure_need(section: dict[str, Any]) -> str:
    explicit = lower(section.get("figure_need"))
    if explicit:
        return explicit
    text = lower(
        " ".join(
            [
                section.get("heading", ""),
                section.get("title", ""),
                section.get("core_argument", ""),
            ]
        )
    )
    if any(word in text for word in ("introduction", "conclusion", "outlook")):
        return "none"
    if any(word in text for word in ("mechanism", "mechanistic", "pathway", "catalytic cycle")):
        return "mechanism"
    if any(word in text for word in ("selectivity", "stereocontrol", "regiocontrol")):
        return "selectivity comparison"
    if any(word in text for word in ("substrate scope", "leaving-group", "catalyst")):
        return "scope comparison"
    if any(
        word in text
        for word in (
            "structure", "microstructure", "design", "engineering", "condition", "kinetic",
            "interface", "process", "pretreatment", "performance", "evidence", "comparison",
            "taxonomy", "classification", "workflow", "recycling", "degradation",
        )
    ):
        return "editorial review for a source figure, comparison table, or synthesis visual"
    return "editorial review"


def normalized_sections(project: Path, tasks: Any) -> list[dict[str, Any]]:
    blueprint_path = project / "01_matrix_outline" / "section_blueprint.json"
    blueprint = read_json(blueprint_path) if blueprint_path.exists() else {}
    blueprint_by_id = {
        str(row.get("section_id")): row
        for row in blueprint.get("sections", [])
        if isinstance(row, dict) and row.get("section_id")
    }
    normalized: list[dict[str, Any]] = []
    for raw in section_rows(tasks):
        row = dict(raw)
        section_id = str(row.get("section_id") or "")
        source = blueprint_by_id.get(section_id, {})
        row["heading"] = row.get("heading") or row.get("title") or source.get("title") or section_id
        row["core_argument"] = (
            row.get("core_argument")
            or source.get("section_thesis")
            or source.get("review_problem")
            or ""
        )
        allowed = list(
            row.get("allowed_papers")
            or row.get("assigned_papers")
            or source.get("major_papers")
            or []
        )
        for subsection in source.get("subsections", []):
            if isinstance(subsection, dict):
                allowed.extend(subsection.get("major_papers") or [])
        row["allowed_papers"] = list(dict.fromkeys(str(pid) for pid in allowed if pid))
        if not row.get("figure_need"):
            planned = source.get("figure_or_table_needs") or []
            planned_types = [
                norm(item.get("type"))
                for item in planned
                if isinstance(item, dict) and item.get("type")
            ]
            row["figure_need"] = ", ".join(planned_types) or inferred_figure_need(row)
        normalized.append(row)
    return normalized


def best_candidate_for_paper(paper: dict[str, Any]) -> dict[str, Any]:
    candidates = [c for c in paper.get("top_candidates", []) if isinstance(c, dict)]
    resolved = [candidate for candidate in candidates if candidate.get("source_image_path")]
    if resolved:
        candidates = resolved
    candidates.sort(key=lambda c: figure_score(c), reverse=True)
    if not candidates:
        return {
            "paper_id": paper.get("paper_id"),
            "title": paper.get("title"),
            "status": "no_useful_figure",
            "no_useful_figure_reason": "No image/table candidates were found in MinerU content_list.",
        }
    best = dict(candidates[0])
    best.update(
        {
            "status": "selected_best_paper_level_candidate",
            "why_selected": "Highest-ranked candidate whose caption and section assignment may answer the section's reader need; editorial and rights review are still required.",
            "manuscript_selected": False,
            "resolution_status": "ready" if best.get("source_image_path") else "needs_source_resolution",
        }
    )
    return best


def build_outputs(
    project: Path,
    *,
    max_total: int = 4,
    max_per_section: int = 1,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    inventory = read_json(project / "02_section_drafting" / "paper_figure_inventory.json")
    tasks = read_json(project / "02_section_drafting" / "section_tasks.json")
    by_paper = inventory_by_paper(inventory)

    paper_level: list[dict[str, Any]] = []
    for paper in inventory.get("papers", []):
        if isinstance(paper, dict):
            paper_level.append(best_candidate_for_paper(paper))

    manuscript: list[dict[str, Any]] = []
    used_keys: set[tuple[str, str]] = set()
    for section in normalized_sections(project, tasks):
        figure_need = lower(section.get("figure_need"))
        if figure_need in {"no", "none", "optional"}:
            continue
        allowed = [str(pid) for pid in section.get("allowed_papers", [])]
        pool: list[dict[str, Any]] = []
        for paper_id in allowed:
            paper = by_paper.get(paper_id)
            if not paper:
                continue
            for candidate in paper.get("top_candidates", []):
                if isinstance(candidate, dict) and candidate.get("source_image_path"):
                    row = dict(candidate)
                    row["_score"] = figure_score(row, section)
                    pool.append(row)
        pool.sort(key=lambda c: c.get("_score", 0), reverse=True)
        section_selected = 0
        for candidate in pool:
            key = (str(candidate.get("paper_id")), str(candidate.get("source_image_path") or candidate.get("source_label")))
            if key in used_keys:
                continue
            used_keys.add(key)
            section_selected += 1
            candidate.pop("_score", None)
            candidate.update(
                {
                    "section_id": section.get("section_id"),
                    "section_heading": section.get("heading"),
                    "why_selected": (
                        "Suggested for editorial review because its caption and paper assignment may support this "
                        "section and the MinerU source image is resolvable."
                    ),
                    "what_it_shows": candidate.get("source_caption_text") or candidate.get("source_label"),
                    "fits_paragraph_or_claim": section.get("core_argument"),
                    "recommended_action": "redraw" if candidate.get("source_type") != "table" else "retable",
                    "editorial_status": "suggested",
                    "manuscript_selected": False,
                    "reader_job": "",
                    "placement_rationale": "",
                    "reuse_basis": "",
                    "reuse_rights": {
                        "status": "pending",
                        "basis": "",
                        "license_url_or_permission_record": "",
                        "source_locator": "",
                        "third_party_material_checked": False,
                        "adaptation": "unchanged",
                        "attribution_text": "",
                    },
                    "resolution_status": "ready" if candidate.get("source_image_path") else "needs_source_resolution",
                    "source_page_review_status": "pending",
                }
            )
            manuscript.append(candidate)
            if section_selected >= max(1, max_per_section):
                break
        if max_total > 0 and len(manuscript) >= max_total:
            manuscript = manuscript[:max_total]
            break
    return paper_level, manuscript


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select initial paper-level and manuscript figure candidates.")
    parser.add_argument("--review-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--max-total", type=int, default=4)
    parser.add_argument("--max-per-section", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project = Path(args.review_root).resolve() / "review-projects" / args.project_id
    if not project.exists():
        raise SystemExit(f"Project not found: {project}")
    # Inventory is a deterministic prerequisite, not an agent-authored
    # artifact. Rebuild it on every selection run so stale `[]` files or an
    # invented "MinerU has no images" explanation cannot bypass source data.
    inventory_path = project / "02_section_drafting" / "paper_figure_inventory.json"
    inventory = build_inventory(Path(args.review_root).resolve(), args.project_id)
    write_json(inventory_path, inventory)
    try:
        paper_level, manuscript = build_outputs(
            project,
            max_total=args.max_total,
            max_per_section=args.max_per_section,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    out_dir = project / "02_section_drafting"
    paper_level_manifest = {
        "project_id": args.project_id,
        "inventory_candidate_count": int(inventory.get("candidate_count") or 0),
        "reviewed_paper_count": len(paper_level),
        "candidates": paper_level,
    }
    write_json(out_dir / "paper_figure_candidates.json", paper_level_manifest)
    write_json(out_dir / "figure_candidates.json", manuscript)
    print(
        f"Wrote {out_dir / 'paper_figure_candidates.json'} "
        f"({paper_level_manifest['inventory_candidate_count']} inventory candidates; "
        f"{len(paper_level)} paper-level decisions)"
    )
    print(
        f"Wrote {out_dir / 'figure_candidates.json'} ({len(manuscript)} editorial suggestions; "
        "none are manuscript-selected until explicitly reviewed)"
    )
    if not manuscript:
        source_candidate_count = sum(
            int(row.get("candidate_count") or 0)
            for row in inventory.get("papers") or []
            if isinstance(row, dict)
        )
        resolved_candidate_count = sum(
            bool(candidate.get("source_image_path"))
            for row in inventory.get("papers") or []
            if isinstance(row, dict)
            for candidate in row.get("top_candidates") or []
            if isinstance(candidate, dict)
        )
        print(
            "No manuscript source-figure candidates were selected after rebuilding the MinerU inventory "
            f"({source_candidate_count} candidates; {resolved_candidate_count} resolved top images). "
            "This is an editorial observation, not a drafting failure; consider the independent review visual plan "
            "or record a source-reuse skip reason."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
