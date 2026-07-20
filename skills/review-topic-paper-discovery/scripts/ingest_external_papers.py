#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def field_value(value: Any) -> Any:
    return value.get("value") if isinstance(value, dict) and "value" in value else value


def normalized_doi(value: Any) -> str:
    return re.sub(r"^https?://(?:dx\.)?doi\.org/", "", str(value or "").strip(), flags=re.I).lower()


def normalized_title(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def load_managed_metadata(review_root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted((review_root / "review-library" / "metadata" / "papers").glob("*.metadata.json")):
        try:
            payload = read_json(path)
        except Exception:
            continue
        if isinstance(payload, dict) and payload.get("paper_id"):
            result[str(payload["paper_id"])] = payload
    return result


def match_managed_paper(
    item: dict[str, Any],
    metadata: dict[str, dict[str, Any]],
    preferred_ids: set[str],
) -> tuple[str | None, dict[str, Any] | None]:
    target_name = Path(str(item.get("target_pdf_path") or "")).name.lower()
    wanted_doi = normalized_doi(item.get("doi"))
    wanted_title = normalized_title(item.get("title"))
    ranked_ids = sorted(metadata, key=lambda paper_id: paper_id not in preferred_ids)
    for paper_id in ranked_ids:
        row = metadata[paper_id]
        source_paths = row.get("source_paths") or {}
        source_file = row.get("source_file") or {}
        pdf_names = {
            Path(str(source_paths.get("pdf") or "")).name.lower(),
            Path(str(source_file.get("relative_pdf_path") or "")).name.lower(),
            Path(str(source_file.get("pdf_name") or "")).name.lower(),
        }
        if target_name and target_name in pdf_names:
            return paper_id, row
        if wanted_doi and normalized_doi(field_value(row.get("doi"))) == wanted_doi:
            return paper_id, row
        if wanted_title and normalized_title(field_value(row.get("title"))) == wanted_title:
            return paper_id, row
    return None, None


def screening_candidate(
    paper_id: str,
    metadata: dict[str, Any],
    item: dict[str, Any],
) -> dict[str, Any]:
    return {
        "paper_id": paper_id,
        "title": field_value(metadata.get("title")) or item.get("title"),
        "year": field_value(metadata.get("year")) or item.get("year"),
        "journal": field_value(metadata.get("journal")),
        "abstract": field_value(metadata.get("abstract")) or "",
        "structured_tags": field_value(metadata.get("structured_tags")) or {},
        "source_paths": metadata.get("source_paths") or {},
        "role": "uncertain",
        "matched_keywords": [str(value) for value in item.get("matched_keywords") or [] if value],
        "best_score": 0,
        "ranking_score": 0,
        "keep": True,
        "discovery_source": "external_promoted",
        "external_paper_key": item.get("paper_key"),
    }


def reopen_screening_for_promotions(
    discovery_dir: Path,
    promotions: list[tuple[dict[str, Any], str, dict[str, Any]]],
) -> list[str]:
    selected_path = discovery_dir / "selected_discovery_results.json"
    if not selected_path.exists() or not promotions:
        return []
    selected = read_json(selected_path)
    if not isinstance(selected, dict):
        raise ValueError("selected_discovery_results.json must contain an object")
    local_papers = selected.setdefault("local_papers", [])
    decisions = selected.setdefault("screening_decisions", [])
    if not isinstance(local_papers, list) or not isinstance(decisions, list):
        raise ValueError("selected discovery candidate and screening rows must be lists")
    existing_ids = {
        str(row.get("paper_id"))
        for row in local_papers
        if isinstance(row, dict) and row.get("paper_id")
    }
    decision_ids = {
        str(row.get("paper_id"))
        for row in decisions
        if isinstance(row, dict) and row.get("paper_id")
    }
    promoted_ids: list[str] = []
    for item, paper_id, metadata in promotions:
        if paper_id not in existing_ids:
            local_papers.append(screening_candidate(paper_id, metadata, item))
            existing_ids.add(paper_id)
        if paper_id not in decision_ids:
            decisions.append(
                {
                    "paper_id": paper_id,
                    "decision": "uncertain",
                    "relevance_summary": "",
                    "decision_basis": "Promoted from external coverage; topic screening required.",
                    "portfolio_intent_hint": "needs_reading",
                    "citation_role_hints": ["coverage_candidate"],
                    "coverage_tags": [],
                }
            )
            decision_ids.add(paper_id)
        promoted_ids.append(paper_id)
    candidate_ids = [str(row.get("paper_id")) for row in local_papers if isinstance(row, dict) and row.get("paper_id")]
    selected["candidate_paper_ids"] = list(dict.fromkeys(candidate_ids))
    screening = selected.setdefault("screening", {})
    if not isinstance(screening, dict):
        screening = {}
        selected["screening"] = screening
    screening.update(
        {
            "status": "pending",
            "decided_by": "unreviewed",
            "external_promotions_pending": list(dict.fromkeys(promoted_ids)),
        }
    )
    selected["human_confirmed"] = False
    write_json(selected_path, selected)
    write_json(
        discovery_dir / "human_check_state.json",
        {
            "project_id": selected.get("project_id") or discovery_dir.parent.name,
            "status": "pending",
            "confirmed_at": None,
            "reason": "external_papers_promoted_for_screening",
            "promoted_paper_ids": list(dict.fromkeys(promoted_ids)),
        },
    )
    return list(dict.fromkeys(promoted_ids))


def safe_target(review_root: Path, relative_path: str) -> Path:
    import_root = (review_root / "chem_papers" / "web-imports").resolve()
    target = (review_root / relative_path).resolve()
    try:
        target.relative_to(import_root)
    except ValueError as exc:
        raise ValueError(f"target_pdf_path escapes chem_papers/web-imports: {relative_path}") from exc
    if target.suffix.lower() != ".pdf":
        raise ValueError(f"target_pdf_path must end in .pdf: {relative_path}")
    return target


def download_pdf(url: str, target: Path, timeout: int) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"unsupported PDF URL: {url}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "review-writer-ingest/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, temp.open("wb") as handle:
            first = response.read(8192)
            if not first.startswith(b"%PDF-"):
                raise ValueError("downloaded content is not a PDF")
            handle.write(first)
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    temp.replace(target)
    return str(target)


def select_items(plan: dict[str, Any], paper_keys: list[str], limit: int) -> list[dict[str, Any]]:
    requested = set(paper_keys)
    rows = [
        row
        for row in plan.get("items") or []
        if isinstance(row, dict)
        and row.get("action") == "download_then_mineru"
        and (not requested or str(row.get("paper_key")) in requested)
    ]
    return rows[:limit] if limit > 0 else rows


def run_command(command: list[str]) -> tuple[int, str]:
    result = subprocess.run(command, text=True, encoding="utf-8", errors="replace")
    return result.returncode, " ".join(command)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download selected OA discovery papers, parse them with MinerU, and append metadata."
    )
    parser.add_argument("--review-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--paper-key", action="append", default=[])
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Stop after PDF download; do not call MinerU or metadata preparation.",
    )
    parser.add_argument(
        "--skip-metadata",
        action="store_true",
        help="Run MinerU but do not append the parsed papers to managed metadata yet.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    review_root = Path(args.review_root).resolve()
    discovery_dir = review_root / "review-projects" / args.project_id / "00_discovery"
    plan_path = discovery_dir / "external_ingest_plan.json"
    if not plan_path.exists():
        raise SystemExit(f"Missing external ingest plan: {plan_path}")
    plan = read_json(plan_path)
    items = select_items(plan, args.paper_key, args.limit)
    if not items:
        raise SystemExit("No downloadable external papers matched the selection.")

    metadata_before = load_managed_metadata(review_root)
    mineru_script = (
        review_root
        / "skills"
        / "mineru-precise-parse-review-writer"
        / "scripts"
        / "parse_review_writer_pdfs.py"
    )
    metadata_script = review_root / "skills" / "review-metadata-prep" / "scripts" / "prepare_metadata.py"
    receipt: dict[str, Any] = {
        "project_id": args.project_id,
        "started_at": utc_now(),
        "download_only": args.download_only,
        "items": [],
        "metadata_status": "not_run",
        "screening_promotion_status": "not_run",
    }
    parsed_any = False
    failures = 0
    for item in items:
        record = {
            "paper_key": item.get("paper_key"),
            "title": item.get("title"),
            "source_url": item.get("open_access_pdf_url"),
            "target_pdf_path": item.get("target_pdf_path"),
            "download_status": "pending",
            "mineru_status": "not_run",
            "promotion_status": "not_run",
        }
        try:
            target = safe_target(review_root, str(item.get("target_pdf_path") or ""))
            if target.exists() and not args.force_download:
                record["download_status"] = "existing"
            else:
                download_pdf(str(item.get("open_access_pdf_url") or ""), target, args.timeout)
                record["download_status"] = "downloaded"
            if not args.download_only:
                code, command = run_command(
                    [
                        sys.executable,
                        str(mineru_script),
                        "--input-dir",
                        str(review_root / "chem_papers"),
                        "--output-dir",
                        str(review_root / "mineru-outputs"),
                        "--pdf",
                        str(target),
                    ]
                )
                record["mineru_command"] = command
                record["mineru_status"] = "completed" if code == 0 else f"failed:{code}"
                parsed_any = parsed_any or code == 0
                failures += int(code != 0)
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
            record["download_status"] = "failed"
            failures += 1
        receipt["items"].append(record)

    if parsed_any and not args.skip_metadata and not args.download_only:
        code, command = run_command(
            [
                sys.executable,
                str(metadata_script),
                "--review-root",
                str(review_root),
                "--mineru-output",
                str(review_root / "mineru-outputs"),
                "--pdf-root",
                str(review_root / "chem_papers"),
                "--discover-from-pdf-root",
                "--append-registry",
            ]
        )
        receipt["metadata_command"] = command
        receipt["metadata_status"] = "completed" if code == 0 else f"failed:{code}"
        failures += int(code != 0)
        if code == 0:
            metadata_after = load_managed_metadata(review_root)
            new_ids = set(metadata_after) - set(metadata_before)
            plan_by_key = {
                str(row.get("paper_key")): row
                for row in plan.get("items") or []
                if isinstance(row, dict) and row.get("paper_key")
            }
            receipt_by_key = {
                str(row.get("paper_key")): row
                for row in receipt["items"]
                if isinstance(row, dict) and row.get("paper_key")
            }
            promotions: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
            for item in items:
                record = receipt_by_key.get(str(item.get("paper_key")))
                if not record or record.get("mineru_status") != "completed":
                    continue
                paper_id, metadata_row = match_managed_paper(item, metadata_after, new_ids)
                if not paper_id or not metadata_row:
                    record["promotion_status"] = "unresolved_metadata_identity"
                    failures += 1
                    continue
                record["local_paper_id"] = paper_id
                record["promotion_status"] = "ready_for_screening"
                plan_item = plan_by_key.get(str(item.get("paper_key")))
                if plan_item is not None:
                    plan_item.update(
                        {
                            "local_paper_id": paper_id,
                            "action": "use_local",
                            "next_step": f"Screen managed paper {paper_id} against topic_contract.json.",
                        }
                    )
                promotions.append((item, paper_id, metadata_row))
            try:
                promoted_ids = reopen_screening_for_promotions(discovery_dir, promotions)
                receipt["promoted_paper_ids"] = promoted_ids
                receipt["screening_promotion_status"] = (
                    "completed" if len(promoted_ids) == len(promotions) else "partial"
                )
            except Exception as exc:
                receipt["screening_promotion_status"] = f"failed:{type(exc).__name__}"
                receipt["screening_promotion_error"] = str(exc)
                failures += 1
            remaining_downloads = sum(
                isinstance(row, dict) and row.get("action") == "download_then_mineru"
                for row in plan.get("items") or []
            )
            plan["downloadable_count"] = remaining_downloads
            plan["status"] = "ready" if remaining_downloads else "screening_update_required"
            write_json(plan_path, plan)
    elif args.download_only:
        receipt["metadata_status"] = "download_only"
    elif args.skip_metadata:
        receipt["metadata_status"] = "skipped"

    receipt["finished_at"] = utc_now()
    receipt["failure_count"] = failures
    write_json(discovery_dir / "external_ingest_receipt.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
