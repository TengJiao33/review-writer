#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STAGE_IDS = (
    "discovery",
    "matrix_outline",
    "section_blueprint",
    "section_drafting",
    "figure_redraw",
    "first_draft",
    "final_audit",
    "docx_export",
    "status",
)

SECRET_FLAGS = {"--api-key", "--token", "--password", "--secret"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def redact_command(command: list[str]) -> list[str]:
    redacted = []
    hide_next = False
    for item in command:
        if hide_next:
            redacted.append("<redacted>")
            hide_next = False
            continue
        lower = item.lower()
        if lower in SECRET_FLAGS:
            redacted.append(item)
            hide_next = True
            continue
        if any(lower.startswith(flag + "=") for flag in SECRET_FLAGS):
            redacted.append(item.split("=", 1)[0] + "=<redacted>")
            continue
        redacted.append(item)
    return redacted


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except Exception:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def write_markdown(path: Path, project_id: str, events: list[dict[str, Any]]) -> None:
    lines = [
        f"# Run Record: {project_id}",
        "",
        "Generated from `run_events.jsonl`. Commands, exit codes, timestamps, and notes below are execution records rather than reconstructed summaries.",
        "",
    ]
    for index, event in enumerate(events, start=1):
        lines.extend(
            [
                f"## {index}. {event.get('stage')}",
                "",
                f"- Started: {event.get('started_at')}",
                f"- Finished: {event.get('finished_at')}",
                f"- Exit code: {event.get('exit_code')}",
                f"- Working directory: `{event.get('cwd')}`",
                f"- Command: `{event.get('command_text')}`",
            ]
        )
        if event.get("note"):
            lines.append(f"- Note: {event['note']}")
        if event.get("artifacts"):
            lines.append("- Artifacts: " + ", ".join(f"`{item}`" for item in event["artifacts"]))
        if event.get("stdout_tail"):
            lines.extend(["", "Output tail:", "", "```text", event["stdout_tail"], "```"])
        if event.get("stderr_tail"):
            lines.extend(["", "Error tail:", "", "```text", event["stderr_tail"], "```"])
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    review_root = Path(args.review_root).resolve()
    project = review_root / "review-projects" / args.project_id
    project.mkdir(parents=True, exist_ok=True)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("A command is required after --")
    started_at = utc_now()
    result = subprocess.run(command, cwd=review_root, text=True, capture_output=True, check=False)
    finished_at = utc_now()
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    public_command = redact_command(command)
    command_text = subprocess.list2cmdline(public_command) if os.name == "nt" else shlex.join(public_command)
    event = {
        "event_version": 1,
        "project_id": args.project_id,
        "stage": args.stage,
        "started_at": started_at,
        "finished_at": finished_at,
        "cwd": str(review_root),
        "command": public_command,
        "command_text": command_text,
        "exit_code": result.returncode,
        "note": args.note.strip(),
        "artifacts": args.artifact,
        "stdout_tail": result.stdout[-4000:].strip(),
        "stderr_tail": result.stderr[-4000:].strip(),
    }
    events_path = project / "run_events.jsonl"
    with events_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    write_markdown(project / "run_record.md", args.project_id, read_events(events_path))
    return result.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one workflow command and append a truthful project-local execution record.")
    parser.add_argument("--review-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--stage", required=True, choices=STAGE_IDS)
    parser.add_argument("--note", default="")
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
