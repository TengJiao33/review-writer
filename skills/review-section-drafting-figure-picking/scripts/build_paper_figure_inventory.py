#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


FIGURE_TYPES = {"image", "chart", "table"}
LICENSE_URL_RE = re.compile(
    r"https?://creativecommons\.org/licenses/[A-Za-z0-9_-]+(?:/[0-9.]+)?/?",
    re.I,
)
LICENSE_LINE_RE = re.compile(
    r"(?:creative commons|\bcc[- ]by\b|open access article|licensed under|copyright|©)",
    re.I,
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean(text: Any) -> str:
    if isinstance(text, list):
        text = " ".join(str(x) for x in text if str(x).strip())
    return re.sub(r"\s+", " ", str(text or "")).strip()


def selected_paper_ids(project: Path) -> list[str]:
    path = project / "00_discovery" / "selected_discovery_results.json"
    data = read_json(path)
    rows = []
    if isinstance(data, dict):
        for key in ["local_papers", "selected_papers", "papers"]:
            value = data.get(key)
            if isinstance(value, list):
                rows.extend(value)
    elif isinstance(data, list):
        rows = data
    ids: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("keep") is False:
            continue
        paper_id = str(row.get("paper_id") or "").strip()
        if paper_id and paper_id not in seen:
            seen.add(paper_id)
            ids.append(paper_id)
    return ids


def metadata(review_root: Path, paper_id: str) -> dict[str, Any] | None:
    path = review_root / "review-library" / "metadata" / "papers" / f"{paper_id}.metadata.json"
    if not path.exists():
        return None
    data = read_json(path)
    return data if isinstance(data, dict) else None


def field_value(meta: dict[str, Any], key: str) -> Any:
    value = meta.get(key)
    if isinstance(value, dict):
        return value.get("value")
    return value


def license_hints(markdown_path: Any) -> dict[str, Any]:
    """Surface possible reuse statements without deciding that reuse is lawful."""
    raw = str(markdown_path or "").strip()
    if not raw:
        return {
            "rights_review_status": "pending",
            "license_statement_candidates": [],
            "license_urls": [],
        }
    path = Path(raw)
    if not path.exists() or not path.is_file():
        return {
            "rights_review_status": "pending",
            "license_statement_candidates": [],
            "license_urls": [],
        }
    text = path.read_text(encoding="utf-8", errors="ignore")
    statements: list[str] = []
    for line in text.splitlines():
        cleaned = clean(line)
        if cleaned and LICENSE_LINE_RE.search(cleaned):
            statements.append(cleaned[:600])
        if len(statements) >= 6:
            break
    urls = list(dict.fromkeys(LICENSE_URL_RE.findall(text)))
    return {
        "rights_review_status": "license_hint_found" if statements or urls else "pending",
        "license_statement_candidates": list(dict.fromkeys(statements)),
        "license_urls": urls[:6],
        "instructions": (
            "These are discovery hints only. Verify the article license, the selected figure's "
            "credit line, any third-party exclusion, and whether adaptation is permitted."
        ),
    }


def block_caption(block: dict[str, Any]) -> str:
    parts = []
    for key in ["image_caption", "table_caption", "caption", "text"]:
        value = block.get(key)
        text = clean(value)
        if text:
            parts.append(text)
    return clean(" ".join(parts))


def infer_source_label(caption: str, index: int, source_type: str) -> str:
    match = re.search(r"\b(Scheme|Figure|Fig\.|Table)\s*[\w.-]+", caption, re.I)
    if match:
        return match.group(0).replace("Fig.", "Figure")
    prefix = "Table" if source_type == "table" else "Figure"
    return f"{prefix} candidate {index}"


def candidate_score(caption: str, source_type: str) -> int:
    low = caption.lower()
    score = 0
    for word, weight in [
        ("scheme", 8),
        ("mechanism", 8),
        ("catalytic cycle", 8),
        ("overview", 7),
        ("workflow", 7),
        ("pathway", 6),
        ("comparison", 5),
        ("microstructure", 5),
        ("degradation", 4),
        ("recycling", 4),
        ("performance", 4),
        ("structure", 3),
        ("process", 3),
        ("proposed", 5),
        ("reaction", 4),
        ("synthesis", 4),
        ("scope", 4),
        ("optimization", 2),
        ("crystal", -4),
        ("nmr", -5),
        ("hrms", -5),
        ("supporting", -3),
    ]:
        if word in low:
            score += weight
    if source_type == "table":
        score += 1
    return score


def split_figure_groups(blocks: list[Any]) -> dict[int, list[int]]:
    figure_indexes = [
        index
        for index, block in enumerate(blocks)
        if isinstance(block, dict) and block.get("type") in FIGURE_TYPES
    ]
    groups: dict[int, list[int]] = {}
    for left, right in zip(figure_indexes, figure_indexes[1:]):
        left_block = blocks[left]
        right_block = blocks[right]
        if left_block.get("page_idx") != right_block.get("page_idx"):
            continue
        continuation = re.match(r"^\(?([A-Z])\)?[.)]\s*", block_caption(right_block))
        if continuation and re.search(
            rf"\({re.escape(continuation.group(1))}\)",
            block_caption(left_block),
            re.I,
        ):
            group = [left, right]
            groups[left] = group
            groups[right] = group
    return groups


def build_inventory(review_root: Path, project_id: str) -> dict[str, Any]:
    project = review_root / "review-projects" / project_id
    ids = selected_paper_ids(project)
    papers = []
    all_candidates: list[dict[str, Any]] = []
    for paper_id in ids:
        meta = metadata(review_root, paper_id)
        if not meta:
            papers.append(
                {
                    "paper_id": paper_id,
                    "status": "missing_metadata",
                    "candidate_count": 0,
                    "candidates": [],
                    "top_candidates": [],
                }
            )
            continue
        source_paths = meta.get("source_paths") or {}
        rights_hints = license_hints(source_paths.get("markdown"))
        raw_content_path = str(source_paths.get("content_list") or "").strip()
        raw_extracted_dir = str(source_paths.get("extracted_dir") or "").strip()
        content_path = Path(raw_content_path) if raw_content_path else None
        extracted_dir = Path(raw_extracted_dir) if raw_extracted_dir else None
        candidates = []
        if content_path and content_path.is_file():
            blocks = read_json(content_path)
            if isinstance(blocks, list):
                split_groups = split_figure_groups(blocks)
                for block_index, block in enumerate(blocks):
                    if not isinstance(block, dict) or block.get("type") not in FIGURE_TYPES:
                        continue
                    idx = block_index + 1
                    img_rel = block.get("img_path") or block.get("image_path") or block.get("path")
                    source_image_path = str((extracted_dir / str(img_rel)).resolve()) if img_rel and extracted_dir and extracted_dir.is_dir() else ""
                    fragment_indexes = split_groups.get(block_index, [])
                    fragment_paths = [
                        str((extracted_dir / str(fragment_rel)).resolve())
                        for fragment_index in fragment_indexes
                        for fragment_rel in [
                            blocks[fragment_index].get("img_path")
                            or blocks[fragment_index].get("image_path")
                            or blocks[fragment_index].get("path")
                        ]
                        if fragment_rel and extracted_dir and (extracted_dir / str(fragment_rel)).exists()
                    ]
                    caption = block_caption(block)
                    source_type = str(block.get("type") or "")
                    candidates.append(
                        {
                            "paper_id": paper_id,
                            "title": field_value(meta, "title"),
                            "source_label": infer_source_label(caption, len(candidates) + 1, source_type),
                            "source_type": source_type,
                            "source_pdf": source_paths.get("pdf"),
                            "source_content_list": str(content_path),
                            "source_image_path": (
                                source_image_path
                                if not fragment_indexes and source_image_path and Path(source_image_path).exists()
                                else ""
                            ),
                            "source_completeness": "mineru_split" if fragment_indexes else "single_block",
                            "source_fragment_paths": fragment_paths,
                            "source_page_hint": f"page {int(block.get('page_idx', 0)) + 1}" if block.get("page_idx") is not None else "",
                            "source_caption_text": caption,
                            "reuse_rights_hints": rights_hints,
                            "inventory_score": candidate_score(caption, source_type),
                            "human_reading_hint": "Prefer when the asset answers a named reader question or compresses a comparison, mechanism, evidence boundary, or process relationship.",
                        }
                    )
        candidates.sort(key=lambda item: item.get("inventory_score", 0), reverse=True)
        all_candidates.extend(candidates)
        papers.append(
            {
                "paper_id": paper_id,
                "title": field_value(meta, "title"),
                "source_pdf": source_paths.get("pdf"),
                "markdown": source_paths.get("markdown"),
                "content_list": source_paths.get("content_list"),
                "reuse_rights_hints": rights_hints,
                "candidate_count": len(candidates),
                "candidates": candidates,
                "top_candidates": candidates[:12],
            }
        )
    all_candidates.sort(key=lambda item: item.get("inventory_score", 0), reverse=True)
    return {
        "project_id": project_id,
        "paper_count": len(ids),
        "candidate_count": len(all_candidates),
        "figure_candidate_count": sum(
            candidate.get("source_type") in {"image", "chart"}
            for candidate in all_candidates
        ),
        "table_candidate_count": sum(
            candidate.get("source_type") == "table" for candidate in all_candidates
        ),
        "license_hint_candidate_count": sum(
            (candidate.get("reuse_rights_hints") or {}).get("rights_review_status")
            == "license_hint_found"
            for candidate in all_candidates
        ),
        # Keep both a flat self-describing view and the per-paper grouping.
        # Consumers can no longer mistake nested candidates for an empty set.
        "candidates": all_candidates,
        "papers": papers,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a MinerU figure/table inventory for selected review papers.")
    parser.add_argument("--review-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--project-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    review_root = Path(args.review_root).resolve()
    project = review_root / "review-projects" / args.project_id
    if not project.exists():
        raise SystemExit(f"Project not found: {project}")
    out = project / "02_section_drafting" / "paper_figure_inventory.json"
    inventory = build_inventory(review_root, args.project_id)
    write_json(out, inventory)
    print(f"Wrote {out}")
    print(f"Papers: {inventory['paper_count']}")
    print(
        "Candidates: "
        f"{inventory['candidate_count']} total; "
        f"{inventory['figure_candidate_count']} figures/charts; "
        f"{inventory['table_candidate_count']} tables; "
        f"{inventory['license_hint_candidate_count']} with licence hints"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
