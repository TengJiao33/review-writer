#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def unresolved_from(summary: dict[str, Any]) -> list[str]:
    issues = [str(item) for item in summary.get("workflow_issues") or []]
    next_stage = summary.get("next_stage")
    if isinstance(next_stage, dict):
        issues.extend(str(item) for item in next_stage.get("missing") or [])
        issues.extend(str(item) for item in next_stage.get("semantic_issues") or [])
    return list(dict.fromkeys(issues))


def run(args: argparse.Namespace) -> int:
    review_root = Path(args.review_root).resolve()
    manifest_path = args.manifest.resolve()
    status_script = Path(__file__).resolve().with_name("project_status.py")
    command = [
        sys.executable,
        str(status_script),
        "--review-root",
        str(review_root),
        "--project-id",
        args.project_id,
        "--json",
        "--require-complete",
    ]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    try:
        summary = json.loads(result.stdout)
    except Exception:
        summary = {"workflow_issues": ["strict_status_output_invalid"], "raw_output": result.stdout[-4000:]}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    if not isinstance(manifest, dict):
        raise SystemExit("Experiment manifest must contain a JSON object")
    manifest["finished_at"] = utc_now()
    manifest["status"] = "completed" if result.returncode == 0 else "blocked"
    manifest["unresolved_conditions"] = [] if result.returncode == 0 else unresolved_from(summary)
    manifest["status_evidence"] = {
        "strict_status_command": command,
        "strict_status_exit_code": result.returncode,
        "recorded_at": utc_now(),
        "summary": summary,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    print(f"Manifest status set to {manifest['status']} from strict status exit {result.returncode}")
    return result.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Finalize an experiment manifest from the actual strict project status.")
    parser.add_argument("--review-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--manifest", required=True, type=Path)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
