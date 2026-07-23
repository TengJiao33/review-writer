#!/usr/bin/env python3
"""Small, shared integrity contracts for the review workflow.

These helpers deliberately verify relationships between artifacts.  They do
not try to judge prose quality or replace source reading.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def file_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_relative(project: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def input_artifacts(project: Path, paths: Iterable[Path]) -> list[dict[str, Any]]:
    rows = []
    for path in paths:
        resolved = path.resolve()
        rows.append(
            {
                "path": project_relative(project, resolved),
                "sha256": file_sha256(resolved),
                "size": resolved.stat().st_size if resolved.is_file() else None,
            }
        )
    return rows


def attach_input_artifacts(
    report: dict[str, Any], project: Path, paths: Iterable[Path]
) -> dict[str, Any]:
    report["contract_version"] = 2
    report["validated_at"] = utc_now()
    report["input_artifacts"] = input_artifacts(project, paths)
    return report


def resolve_project_path(project: Path, raw: Any) -> Path:
    path = Path(str(raw or ""))
    return path.resolve() if path.is_absolute() else (project / path).resolve()


def input_artifact_issues(
    report: Any,
    project: Path,
    required_paths: Iterable[Path],
    *,
    require_receipts: bool,
) -> list[str]:
    """Verify that a report was produced from the current required inputs."""
    if not isinstance(report, dict):
        return ["validation_report_invalid"]
    rows = report.get("input_artifacts")
    if not isinstance(rows, list):
        return ["validation_input_receipts_missing"] if require_receipts else []
    by_path: dict[Path, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and row.get("path"):
            by_path[resolve_project_path(project, row["path"])] = row
    issues: list[str] = []
    for required in required_paths:
        resolved = required.resolve()
        receipt = by_path.get(resolved)
        label = project_relative(project, resolved)
        if not isinstance(receipt, dict):
            issues.append(f"validation_input_unrecorded:{label}")
            continue
        recorded = str(receipt.get("sha256") or "").lower()
        actual = file_sha256(resolved)
        if not actual:
            issues.append(f"validation_input_missing:{label}")
        elif recorded != actual:
            issues.append(f"validation_input_stale:{label}")
    return issues

def metadata_snapshot_payload(review_root: Path, paper_ids: Iterable[str]) -> dict[str, Any]:
    papers: dict[str, Any] = {}
    for paper_id in sorted(set(str(item) for item in paper_ids if str(item).strip())):
        path = review_root / "review-library" / "metadata" / "papers" / f"{paper_id}.metadata.json"
        papers[paper_id] = {
            "path": path.resolve().relative_to(review_root.resolve()).as_posix(),
            "sha256": file_sha256(path),
            "size": path.stat().st_size if path.is_file() else None,
        }
    return {
        "snapshot_version": 1,
        "created_at": utc_now(),
        "policy": "shared_library_metadata_is_read_only_during_project_execution",
        "papers": papers,
    }


def metadata_snapshot_issues(
    review_root: Path, project: Path, paper_ids: Iterable[str]
) -> list[str]:
    path = project / "00_discovery" / "library_metadata_snapshot.json"
    if not path.is_file():
        return ["library_metadata_snapshot_missing"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ["library_metadata_snapshot_invalid"]
    papers = payload.get("papers") if isinstance(payload, dict) else None
    if not isinstance(papers, dict):
        return ["library_metadata_snapshot_invalid"]
    issues: list[str] = []
    for paper_id in sorted(set(str(item) for item in paper_ids if str(item).strip())):
        receipt = papers.get(paper_id)
        metadata_path = review_root / "review-library" / "metadata" / "papers" / f"{paper_id}.metadata.json"
        if not isinstance(receipt, dict):
            issues.append(f"library_metadata_not_snapshotted:{paper_id}")
            continue
        if str(receipt.get("sha256") or "").lower() != file_sha256(metadata_path):
            issues.append(f"shared_library_metadata_changed:{paper_id}")
    authored_outputs = [
        project / "01_matrix_outline" / "literature_matrix.json",
        project / "02_section_drafting" / "manuscript.md",
        project / "04_first_draft" / "first_draft.md",
    ]
    snapshot_time = path.stat().st_mtime
    if any(output.is_file() and output.stat().st_mtime < snapshot_time for output in authored_outputs):
        issues.append("library_metadata_snapshot_created_after_authored_outputs")
    return issues
