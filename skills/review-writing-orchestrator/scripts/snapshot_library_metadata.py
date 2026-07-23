#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SHARED = Path(__file__).resolve().parents[2] / "_shared"
sys.path.insert(0, str(SHARED))
from review_integrity import metadata_snapshot_payload  # noqa: E402


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def selected_ids(project: Path) -> list[str]:
    payload = read_json(project / "00_discovery" / "selected_discovery_results.json")
    rows: list[Any] = []
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        for key in ("local_papers", "selected_papers", "papers"):
            if isinstance(payload.get(key), list):
                rows.extend(payload[key])
    return list(
        dict.fromkeys(
            str(row.get("paper_id"))
            for row in rows
            if isinstance(row, dict) and row.get("paper_id") and row.get("keep") is not False
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Snapshot selected shared metadata before evidence authoring begins."
    )
    parser.add_argument("--review-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--project-id", required=True)
    args = parser.parse_args()
    review_root = Path(args.review_root).resolve()
    project = review_root / "review-projects" / args.project_id
    selected = project / "00_discovery" / "selected_discovery_results.json"
    if not selected.is_file():
        raise SystemExit(f"Missing selected discovery results: {selected}")
    out = project / "00_discovery" / "library_metadata_snapshot.json"
    if out.exists():
        raise SystemExit(
            "Metadata snapshot already exists. Do not refresh it during a run; investigate the drift instead."
        )
    payload = metadata_snapshot_payload(review_root, selected_ids(project))
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote immutable project metadata snapshot: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
