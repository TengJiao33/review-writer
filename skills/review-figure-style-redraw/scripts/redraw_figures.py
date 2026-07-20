#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import shutil
import ssl
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize_label(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", normalize_space(text).lower()).strip()


def missing_source_note_identifiers(note: str, figure: dict[str, Any]) -> list[str]:
    normalized_note = normalize_label(note)
    expected = [
        normalize_label(figure.get("source_label")),
        normalize_label(figure.get("source_page_hint")),
    ]
    return [item for item in expected if item and item not in normalized_note]


def ensure_project_dir(review_root: Path, project_id: str) -> Path:
    project = review_root / "review-projects" / project_id
    if not project.exists():
        raise SystemExit(f"Project not found: {project}")
    return project


def load_candidate_file(review_root: Path, project_id: str, path_arg: str) -> Path:
    if path_arg:
        path = Path(path_arg).resolve()
    else:
        path = review_root / "review-projects" / project_id / "02_section_drafting" / "figure_candidates.json"
    if not path.exists():
        raise SystemExit(f"figure_candidates.json not found: {path}")
    return path


def load_metadata(review_root: Path, paper_id: str) -> dict[str, Any] | None:
    path = review_root / "review-library" / "metadata" / "papers" / f"{paper_id}.metadata.json"
    if not path.exists():
        return None
    try:
        data = read_json(path)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def completeness_signals(
    review_root: Path,
    figure: dict[str, Any],
    source_image: Path,
) -> dict[str, Any]:
    paper_id = str(figure.get("paper_id") or "")
    meta = load_metadata(review_root, paper_id) if paper_id else None
    raw_content_list = figure.get("source_content_list") or (
        ((meta or {}).get("source_paths") or {}).get("content_list")
    )
    signals = {
        "matched_block_index": None,
        "same_page_visual_cluster_size": None,
        "panel_marker_detected": bool(
            re.match(r"^\s*\(?[A-Ha-h]\)\s*", str(figure.get("source_caption_text") or ""))
        ),
        "completeness_review_recommended": False,
    }
    if not raw_content_list:
        return signals
    content_path = Path(str(raw_content_list)).expanduser()
    if not content_path.is_absolute():
        content_path = review_root / content_path
    if not content_path.exists():
        return signals
    try:
        blocks = read_json(content_path)
    except Exception:
        return signals
    if not isinstance(blocks, list):
        return signals
    visual_types = {"image", "chart", "table"}
    matched_index = None
    for index, block in enumerate(blocks):
        if not isinstance(block, dict) or block.get("type") not in visual_types:
            continue
        raw_image = str(block.get("img_path") or block.get("image_path") or block.get("path") or "")
        if raw_image and Path(raw_image).name == source_image.name:
            matched_index = index
            break
    if matched_index is None:
        return signals
    signals["matched_block_index"] = matched_index
    page = blocks[matched_index].get("page_idx")
    start = matched_index
    while start > 0:
        previous = blocks[start - 1]
        if not isinstance(previous, dict) or previous.get("type") not in visual_types:
            break
        if previous.get("page_idx") != page:
            break
        start -= 1
    end = matched_index
    while end + 1 < len(blocks):
        following = blocks[end + 1]
        if not isinstance(following, dict) or following.get("type") not in visual_types:
            break
        if following.get("page_idx") != page:
            break
        end += 1
    cluster_size = end - start + 1
    signals["same_page_visual_cluster_size"] = cluster_size
    signals["completeness_review_recommended"] = bool(
        cluster_size > 1 or signals["panel_marker_detected"]
    )
    return signals


def resolve_source_image(review_root: Path, figure: dict[str, Any]) -> tuple[Path | None, dict[str, Any]]:
    notes: dict[str, Any] = {
        "resolution_method": None,
        "matched_block_page_idx": None,
        "matched_caption": None,
        "matched_img_relpath": None,
    }
    if figure.get("source_completeness") == "mineru_split":
        notes["resolution_method"] = "split_mineru_candidate"
        notes["fragment_paths"] = figure.get("source_fragment_paths") or []
        return None, notes
    image_path = figure.get("source_image_path")
    if image_path:
        path = Path(str(image_path)).expanduser()
        if not path.is_absolute():
            path = review_root / path
        path = path.resolve()
        if path.exists():
            notes["resolution_method"] = "candidate_source_image_path"
            notes.update(completeness_signals(review_root, figure, path))
            return path, notes
    paper_id = figure.get("paper_id")
    meta = load_metadata(review_root, str(paper_id)) if paper_id else None
    content_list_path = figure.get("source_content_list") or (((meta or {}).get("source_paths") or {}).get("content_list"))
    extracted_dir = (((meta or {}).get("source_paths") or {}).get("extracted_dir"))
    if not content_list_path or not extracted_dir:
        return None, notes
    cpath = Path(str(content_list_path)).resolve()
    edir = Path(str(extracted_dir)).resolve()
    if not cpath.exists() or not edir.exists():
        return None, notes
    try:
        blocks = read_json(cpath)
    except Exception:
        return None, notes
    if not isinstance(blocks, list):
        return None, notes
    wanted_label = normalize_label(figure.get("source_label"))
    wanted_caption = normalize_label(figure.get("source_caption_text"))
    wanted_page = normalize_label(figure.get("source_page_hint"))
    best: tuple[int, dict[str, Any]] | None = None
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") not in {"image", "chart", "table"}:
            continue
        img_rel = block.get("img_path") or block.get("image_path") or block.get("path")
        if not img_rel:
            continue
        captions = []
        for key in ["image_caption", "table_caption", "caption"]:
            value = block.get(key)
            if isinstance(value, list):
                captions.extend(str(x) for x in value if str(x).strip())
            elif isinstance(value, str) and value.strip():
                captions.append(value)
        norm_text = normalize_label(" ".join(captions))
        score = 0
        if wanted_label and wanted_label in norm_text:
            score += 8
        if wanted_caption and wanted_caption[:48] and wanted_caption[:48] in norm_text:
            score += 6
        if wanted_page:
            page_idx = block.get("page_idx")
            if page_idx is not None and str(page_idx + 1) in wanted_page:
                score += 2
        if figure.get("source_type") == block.get("type"):
            score += 1
        if best is None or score > best[0]:
            best = (score, block)
    if best is None or best[0] <= 0:
        return None, notes
    block = best[1]
    img_rel = str(block.get("img_path") or block.get("image_path") or block.get("path"))
    resolved = (edir / img_rel).resolve()
    if not resolved.exists():
        return None, notes
    captions = []
    for key in ["image_caption", "table_caption", "caption"]:
        value = block.get(key)
        if isinstance(value, list):
            captions.extend(str(x) for x in value if str(x).strip())
        elif isinstance(value, str) and value.strip():
            captions.append(value)
    notes["resolution_method"] = "content_list_caption_match"
    notes["matched_block_page_idx"] = block.get("page_idx")
    notes["matched_caption"] = " ".join(captions)
    notes["matched_img_relpath"] = img_rel
    notes.update(completeness_signals(review_root, figure, resolved))
    return resolved, notes


def guess_mime(path: Path) -> str:
    return mimetypes.guess_type(str(path))[0] or "image/png"


def resolve_api_key(cli_value: str) -> str:
    return cli_value or os.environ.get("OPENAI_API_KEY", "")


def default_base_url() -> str:
    return os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")


def build_headers(api_key: str, content_type: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": "review-writer-figure-redraw/1.0",
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def build_multipart_form(fields: dict[str, Any], file_fields: list[tuple[str, Path]]) -> tuple[str, bytes]:
    boundary = f"----CodexBoundary{uuid.uuid4().hex}"
    body = bytearray()
    for name, value in fields.items():
        if value is None:
            continue
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")
    for name, path in file_fields:
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="{name}"; filename="{path.name}"\r\n'.encode("utf-8")
        )
        body.extend(f"Content-Type: {guess_mime(path)}\r\n\r\n".encode("utf-8"))
        body.extend(path.read_bytes())
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    return f"multipart/form-data; boundary={boundary}", bytes(body)


def build_prompt(style_name: str, figure: dict[str, Any]) -> str:
    label = figure.get("source_label") or "source figure"
    caption = normalize_space(figure.get("source_caption_text") or "")
    what = normalize_space(figure.get("what_it_shows") or "")
    claim = normalize_space(figure.get("fits_paragraph_or_claim") or "")
    extra = " ".join(
        x for x in [
            f"Label: {label}.",
            f"Caption: {caption}." if caption else "",
            f"It shows: {what}." if what else "",
            f"Used for: {claim}." if claim else "",
        ] if x
    )
    return (
        "Restyle the input image into a unified high-quality organic chemistry review figure style. "
        "Preserve every chemical structure, bond connectivity, stereochemistry, atom label, substituent label, "
        "reaction arrow direction, reagent, catalyst, solvent, stoichiometry, temperature, time, yield, "
        "footnote marker, panel layout, numbering, and relative placement exactly as in the source. "
        "Do not add, remove, rename, reorder, summarize, or reinterpret any chemistry or text. "
        "If any source text is hard to read, preserve it faithfully rather than inventing new text. "
        "Change only visual style: use consistent dark ink lines, a restrained publication palette, a clean white or off-white background, "
        "consistent typography, crisp arrows, balanced spacing, and a publication-ready organic review aesthetic. "
        "Keep the figure scientifically identical to the source. "
        f"Style preset: {style_name}. {extra}"
    )


def call_images_edit(
    api_key: str,
    base_url: str,
    image_path: Path,
    prompt: str,
    model: str,
    quality: str,
    background: str,
    output_format: str,
) -> dict[str, Any]:
    fields = {
        "model": model,
        "prompt": prompt,
        "quality": quality,
        "background": background,
        "output_format": output_format,
    }
    content_type, body = build_multipart_form(fields, [("image[]", image_path)])
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/images/edits",
        data=body,
        headers=build_headers(api_key, content_type),
        method="POST",
    )
    with urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))


def call_responses_image_edit(
    api_key: str,
    base_url: str,
    image_path: Path,
    prompt: str,
    model: str,
    quality: str,
    background: str,
    output_format: str,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "input": prompt,
        "tools": [
            {
                "type": "image_generation",
                "quality": quality,
                "background": background,
                "output_format": output_format,
            }
        ],
    }
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers=build_headers(api_key, "application/json"),
        method="POST",
    )
    with urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_response_image_base64(response: dict[str, Any]) -> str | None:
    for item in response.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "image_generation_call":
            continue
        result = item.get("result")
        if isinstance(result, str) and result.strip():
            return result
    return None


def save_redrawn_image(response: dict[str, Any], out_path: Path) -> None:
    items = response.get("data") or []
    if not items:
        raise RuntimeError("image edit response missing data")
    b64 = items[0].get("b64_json")
    if not b64:
        raise RuntimeError("image edit response missing b64_json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(base64.b64decode(b64))


def save_response_redrawn_image(response: dict[str, Any], out_path: Path) -> None:
    b64 = extract_response_image_base64(response)
    if not b64:
        raise RuntimeError("responses image edit response missing image_generation result")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(base64.b64decode(b64))


def write_report(path: Path, style: dict[str, Any], source_rows: list[dict[str, Any]], redraw_rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Figure Preparation Report",
        "",
        f"- Preparation mode: {style['preparation_mode']}",
        f"- Style preset: {style['style_name']}",
        f"- Model: {style['model']}",
        f"- Quality: {style['quality']}",
        f"- Background: {style['background']}",
        f"- Output format: {style['output_format']}",
        "",
        f"- Source candidates processed: {len(source_rows)}",
        f"- Source candidates resolved: {sum(1 for r in source_rows if r['status'] == 'resolved')}",
        f"- Source figures verified: {sum(1 for r in redraw_rows if r['status'] == 'source_verified')}",
        f"- Redraw success: {sum(1 for r in redraw_rows if r['status'] == 'redrawn')}",
        f"- Unusable or incomplete: {sum(1 for r in redraw_rows if r['status'] not in {'source_verified', 'redrawn'})}",
        "",
        "## Required Source Check",
        "",
        "Every accepted figure must be checked against its source PDF at readable zoom. "
        "An unchanged source figure does not require an image-generation API.",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    review_root = Path(args.review_root).resolve()
    project = ensure_project_dir(review_root, args.project_id)
    figures_file = load_candidate_file(review_root, args.project_id, args.figures_file)
    out_dir = project / "03_figure_redraw"
    source_dir = out_dir / "source"
    verified_dir = out_dir / "verified"
    redrawn_dir = out_dir / "redrawn"
    source_dir.mkdir(parents=True, exist_ok=True)
    verified_dir.mkdir(parents=True, exist_ok=True)
    redrawn_dir.mkdir(parents=True, exist_ok=True)
    data = read_json(figures_file)
    figures = data.get("figures") if isinstance(data, dict) else data
    if not isinstance(figures, list):
        raise SystemExit(f"Invalid figure candidates structure: {figures_file}")
    style = {
        "preparation_mode": "source_verified" if args.use_source else "api_redraw",
        "style_name": args.style_name,
        "model": args.model,
        "quality": args.quality,
        "background": args.background,
        "output_format": args.output_format,
        "base_url": args.base_url,
        "wire_api": args.wire_api,
        "dry_run": bool(args.dry_run),
    }
    write_json(out_dir / "style_config.json", style)
    api_key = "" if args.use_source else resolve_api_key(args.api_key)
    source_rows: list[dict[str, Any]] = []
    redraw_rows: list[dict[str, Any]] = []
    selected_figures = [
        figure
        for figure in figures
        if isinstance(figure, dict)
        and (
            figure.get("manuscript_selected") is True
            or str(figure.get("editorial_status") or "").lower() in {"selected", "adapted", "combined"}
        )
    ]
    limit = args.limit if args.limit and args.limit > 0 else len(selected_figures)
    processed_figures = selected_figures[:limit]
    selection_issues = []
    for figure in processed_figures:
        label = str(figure.get("source_label") or figure.get("paper_id") or "figure")
        if not str(figure.get("reader_job") or "").strip():
            selection_issues.append(f"{label}: reader_job is missing")
        if not str(figure.get("placement_rationale") or "").strip():
            selection_issues.append(f"{label}: placement_rationale is missing")
        if args.use_source and not str(figure.get("reuse_basis") or "").strip():
            selection_issues.append(f"{label}: reuse_basis is missing")
    if selection_issues:
        raise SystemExit(
            "Selected figures need an explicit reader job, placement decision, and reuse basis:\n- "
            + "\n- ".join(selection_issues)
        )
    for index, figure in enumerate(processed_figures, start=1):
        if not isinstance(figure, dict):
            continue
        if figure.get("recommended_action") == "retable":
            continue
        figure_id = f"F{index:03d}"
        source_image, notes = resolve_source_image(review_root, figure)
        src_row = {
            "figure_id": figure_id,
            "section_id": figure.get("section_id"),
            "section_heading": figure.get("section_heading"),
            "paper_id": figure.get("paper_id"),
            "source_label": figure.get("source_label"),
            "source_type": figure.get("source_type"),
            "resolved_source_image": str(source_image) if source_image else None,
            "source_pdf": figure.get("source_pdf"),
            "source_page_hint": figure.get("source_page_hint"),
            "source_caption_text": figure.get("source_caption_text") or notes.get("matched_caption"),
            "source_completeness": figure.get("source_completeness"),
            "source_page_review_status": figure.get("source_page_review_status"),
            "recommended_action": figure.get("recommended_action"),
            "reader_job": figure.get("reader_job"),
            "placement_rationale": figure.get("placement_rationale"),
            "reuse_basis": figure.get("reuse_basis"),
            "status": "resolved" if source_image else "unresolved",
            "notes": notes,
        }
        source_rows.append(src_row)
        redraw_row = {
            "figure_id": figure_id,
            "section_id": figure.get("section_id"),
            "section_heading": figure.get("section_heading"),
            "paper_id": figure.get("paper_id"),
            "source_label": figure.get("source_label"),
            "source_type": figure.get("source_type"),
            "source_image": str(source_image) if source_image else None,
            "verified_image": None,
            "redrawn_image": None,
            "source_pdf": figure.get("source_pdf"),
            "source_page_hint": figure.get("source_page_hint"),
            "source_caption_text": figure.get("source_caption_text") or notes.get("matched_caption"),
            "source_completeness": figure.get("source_completeness"),
            "source_page_review_status": figure.get("source_page_review_status"),
            "title": figure.get("title"),
            "reader_job": figure.get("reader_job"),
            "placement_rationale": figure.get("placement_rationale"),
            "reuse_basis": figure.get("reuse_basis"),
            "prompt": None,
            "model": None if args.use_source else args.model,
            "quality": args.quality,
            "background": args.background,
            "output_format": args.output_format,
            "status": "skipped",
            "notes": "",
        }
        if not source_image:
            redraw_row["status"] = "source_unresolved"
            redraw_row["notes"] = "Could not resolve source image from figure candidate or content_list."
            redraw_rows.append(redraw_row)
            continue
        copied_source = source_dir / f"{figure_id}{source_image.suffix.lower() or '.png'}"
        shutil.copy2(source_image, copied_source)
        if args.use_source:
            figure_note = str(figure.get("source_verification_note") or "").strip()
            if not figure_note and len(processed_figures) == 1:
                figure_note = args.source_verification_note.strip()
            page_review_status = str(figure.get("source_page_review_status") or "").strip().lower()
            completeness = str(figure.get("source_completeness") or "").strip().lower()
            review_issues = []
            if not figure_note:
                review_issues.append("a per-figure source_verification_note")
            if page_review_status not in {"passed", "verified"}:
                review_issues.append("source_page_review_status=passed")
            if completeness not in {"complete", "intentionally_partial"}:
                review_issues.append("source_completeness=complete or intentionally_partial")
            if review_issues:
                redraw_row["status"] = "source_review_incomplete"
                redraw_row["verification_status"] = "failed"
                redraw_row["notes"] = "Source review is missing " + ", ".join(review_issues)
                redraw_rows.append(redraw_row)
                continue
            missing_identifiers = missing_source_note_identifiers(
                figure_note,
                figure,
            )
            if missing_identifiers:
                redraw_row["status"] = "source_review_incomplete"
                redraw_row["verification_status"] = "failed"
                redraw_row["notes"] = (
                    "Source verification note does not identify the selected source: "
                    + ", ".join(missing_identifiers)
                )
                redraw_rows.append(redraw_row)
                continue
            verified_path = verified_dir / copied_source.name
            shutil.copy2(copied_source, verified_path)
            redraw_row["verified_image"] = str(verified_path)
            redraw_row["status"] = "source_verified"
            redraw_row["verification_status"] = "passed"
            redraw_row["notes"] = figure_note
            redraw_rows.append(redraw_row)
            continue
        prompt = build_prompt(args.style_name, figure)
        redraw_row["prompt"] = prompt
        if args.dry_run:
            redraw_row["status"] = "dry_run"
            redraw_row["notes"] = "API call skipped by --dry-run."
            redraw_rows.append(redraw_row)
            continue
        if not api_key:
            redraw_row["status"] = "missing_api_key"
            redraw_row["notes"] = "API key is not set. Pass --api-key or set OPENAI_API_KEY."
            redraw_rows.append(redraw_row)
            continue
        out_path = redrawn_dir / f"{figure_id}.{args.output_format}"
        try:
            if args.wire_api == "responses":
                response = call_responses_image_edit(
                    api_key,
                    args.base_url,
                    copied_source,
                    prompt,
                    args.model,
                    args.quality,
                    args.background,
                    args.output_format,
                )
                save_response_redrawn_image(response, out_path)
            else:
                response = call_images_edit(
                    api_key,
                    args.base_url,
                    copied_source,
                    prompt,
                    args.model,
                    args.quality,
                    args.background,
                    args.output_format,
                )
                save_redrawn_image(response, out_path)
            redraw_row["redrawn_image"] = str(out_path)
            redraw_row["status"] = "redrawn"
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
            redraw_row["status"] = "failed"
            redraw_row["notes"] = f"{type(exc).__name__}: {exc}"
        redraw_rows.append(redraw_row)
    write_json(out_dir / "source_figure_manifest.json", {"project_id": args.project_id, "figures": source_rows})
    write_json(out_dir / "redrawn_figure_manifest.json", {"project_id": args.project_id, "figures": redraw_rows})
    source_by_id = {row["figure_id"]: row for row in source_rows}
    figure_by_id = {
        f"F{index:03d}": figure
        for index, figure in enumerate(processed_figures, start=1)
        if isinstance(figure, dict)
    }
    fidelity_rows = []
    for row in redraw_rows:
        figure = figure_by_id.get(row["figure_id"], {})
        source_row = source_by_id.get(row["figure_id"], {})
        fidelity_rows.append(
            {
                "figure_id": row["figure_id"],
                "source_image": row.get("source_image"),
                "accepted_output": row.get("verified_image") or row.get("redrawn_image"),
                "source_pdf": row.get("source_pdf"),
                "source_page": row.get("source_page_hint"),
                "source_completeness": figure.get("source_completeness"),
                "source_page_review_status": figure.get("source_page_review_status"),
                "completeness_signals": {
                    key: (source_row.get("notes") or {}).get(key)
                    for key in (
                        "matched_block_index",
                        "same_page_visual_cluster_size",
                        "panel_marker_detected",
                        "completeness_review_recommended",
                    )
                },
                "applicable_checks": figure.get("fidelity_checks")
                or [
                    "source label and page",
                    "complete intended panel set",
                    "caption",
                    "chemistry and arrows",
                    "reported values",
                    "legibility",
                ],
                "verdict": (
                    "passed"
                    if row.get("verification_status") == "passed"
                    else "pending"
                    if row.get("status") == "redrawn"
                    else "failed"
                ),
                "notes": row.get("notes") or "",
            }
        )
    write_json(
        out_dir / "figure_fidelity_review.json",
        {"project_id": args.project_id, "figures": fidelity_rows},
    )
    write_report(out_dir / "figure_redraw_report.md", style, source_rows, redraw_rows)
    usable_count = sum(1 for row in redraw_rows if row.get("status") in {"source_verified", "redrawn"})
    if (args.require_usable or args.require_redrawn) and usable_count == 0:
        raise SystemExit(
            "No usable figures were prepared. Fix figure_candidates.json/source_image_path or explicitly document a figure skip."
        )
    print(f"Wrote figure preparation outputs to {out_dir}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare verified source figures or redraw candidates into a unified style.")
    parser.add_argument("--review-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--figures-file", default="")
    parser.add_argument("--base-url", default=default_base_url())
    parser.add_argument("--wire-api", choices=["images", "responses"], default="images")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--model", default="gpt-image-2")
    parser.add_argument("--quality", default="high")
    parser.add_argument("--background", default="opaque")
    parser.add_argument("--output-format", default="png")
    parser.add_argument("--style-name", default="organic-review-clean-v1")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--use-source",
        action="store_true",
        help="Use the resolved source image unchanged after source/PDF inspection; no image API key is needed.",
    )
    parser.add_argument(
        "--source-verification-note",
        default="",
        help="Concise source/PDF comparison for a single figure. Multi-figure runs require source_verification_note on each candidate.",
    )
    parser.add_argument("--require-usable", action="store_true", help="Fail when neither a verified source nor a redrawn figure is prepared.")
    parser.add_argument("--require-redrawn", action="store_true", help="Deprecated alias for --require-usable.")
    args = parser.parse_args()
    if args.use_source and args.dry_run:
        parser.error("--use-source and --dry-run cannot be combined")
    return args


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
