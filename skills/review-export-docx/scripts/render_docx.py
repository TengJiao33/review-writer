#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def run_command(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    return {
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def render_with_libreoffice(docx: Path, pdf: Path) -> tuple[bool, dict[str, Any]]:
    executable = shutil.which("soffice") or shutil.which("libreoffice")
    if not executable:
        return False, {"renderer": "LibreOffice", "available": False}
    pdf.parent.mkdir(parents=True, exist_ok=True)
    result = run_command(
        [executable, "--headless", "--convert-to", "pdf", "--outdir", str(pdf.parent), str(docx)]
    )
    generated = pdf.parent / f"{docx.stem}.pdf"
    if result["exit_code"] == 0 and generated.exists():
        if generated.resolve() != pdf.resolve():
            generated.replace(pdf)
        return True, {"renderer": "LibreOffice", "available": True, **result}
    return False, {"renderer": "LibreOffice", "available": True, **result}


def ps_literal(value: Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def render_with_word(docx: Path, pdf: Path) -> tuple[bool, dict[str, Any]]:
    if os.name != "nt":
        return False, {"renderer": "Microsoft Word COM", "available": False}
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        return False, {"renderer": "Microsoft Word COM", "available": False}
    pdf.parent.mkdir(parents=True, exist_ok=True)
    script = f"""
$ErrorActionPreference = 'Stop'
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {{
  $document = $word.Documents.Open({ps_literal(docx)}, $false, $true)
  try {{ $document.SaveAs2({ps_literal(pdf)}, 17) }} finally {{ $document.Close($false) }}
}} finally {{
  $word.Quit()
  [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) | Out-Null
}}
""".strip()
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    result = run_command([powershell, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded])
    public_command = [powershell, "-NoProfile", "-NonInteractive", "-EncodedCommand", "<encoded Word export script>"]
    result["command"] = public_command
    return result["exit_code"] == 0 and pdf.exists(), {
        "renderer": "Microsoft Word COM",
        "available": True,
        **result,
    }


def find_pdftoppm() -> str | None:
    local_app_data = os.environ.get("LOCALAPPDATA")
    candidates = []
    if local_app_data:
        candidates.append(Path(local_app_data) / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64" / "pdftoppm.exe")
    candidates.extend(
        [
            Path(sys.executable).resolve().parent.parent / "native" / "poppler" / "Library" / "bin" / "pdftoppm.exe",
            Path(r"C:\Program Files\poppler\Library\bin\pdftoppm.exe"),
            Path(r"C:\Program Files\MiKTeX\miktex\bin\x64\pdftoppm.exe"),
        ]
    )
    direct = next((path for path in candidates if path.exists()), None)
    if direct:
        return str(direct)
    return shutil.which("pdftoppm")


def pdf_page_count(pdf: Path) -> int | None:
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(pdf)).pages)
    except Exception:
        return None


def rasterize(pdf: Path, pages_dir: Path) -> tuple[list[str], dict[str, Any]]:
    executable = find_pdftoppm()
    if not executable:
        return [], {"available": False, "error": "pdftoppm not found"}
    pages_dir.mkdir(parents=True, exist_ok=True)
    for stale_page in pages_dir.glob("page-*.png"):
        stale_page.unlink()
    prefix = pages_dir / "page"
    result = run_command([executable, "-png", "-r", "150", str(pdf), str(prefix)])
    images = sorted(str(path) for path in pages_dir.glob("page-*.png"))
    return images, {"available": True, **result}


def parse_inspected_pages(value: str, page_count: int | None) -> list[int]:
    value = value.strip().lower()
    if not value:
        return []
    if value == "all":
        return list(range(1, (page_count or 0) + 1))
    pages = sorted({int(item.strip()) for item in value.split(",") if item.strip().isdigit()})
    return pages


def load_page_inspections(
    path: Path | None,
    page_images: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    if path is None:
        return [], []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [], [f"inspection file is invalid: {exc}"]
    rows = payload.get("pages") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return [], ["inspection file must contain a pages list"]
    expected = {
        index: file_sha256(Path(image_path))
        for index, image_path in enumerate(page_images, start=1)
    }
    issues: list[str] = []
    seen: set[int] = set()
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("page_number"), int):
            issues.append("inspection row has no integer page_number")
            continue
        page_number = int(row["page_number"])
        if page_number in seen:
            issues.append(f"duplicate inspection for page {page_number}")
        seen.add(page_number)
        expected_hash = expected.get(page_number)
        recorded_hash = str(row.get("page_sha256") or "").lower()
        if not expected_hash or recorded_hash != expected_hash:
            issues.append(f"inspection image hash mismatch for page {page_number}")
        observation = str(row.get("observation") or "").strip()
        if len(observation) < 30 or len(set(observation.casefold().split())) < 5:
            issues.append(f"page {page_number} has no page-specific visual observation")
        verdict = str(row.get("verdict") or "").lower()
        if verdict not in {"passed", "needs_revision"}:
            issues.append(f"page {page_number} has an invalid inspection verdict")
        normalized.append(
            {
                "page_number": page_number,
                "page_sha256": recorded_hash,
                "verdict": verdict,
                "observation": observation,
            }
        )
    missing = sorted(set(expected) - seen)
    if missing:
        issues.append("uninspected pages: " + ", ".join(map(str, missing)))
    return sorted(normalized, key=lambda row: row["page_number"]), issues


def layout_warnings(pdf: Path, page_images: list[str]) -> list[dict[str, Any]]:
    """Cheap warning signals; visual judgment remains with the page reviewer."""
    warnings: list[dict[str, Any]] = []
    try:
        from pypdf import PdfReader

        pages = PdfReader(str(pdf)).pages
        for index, page in enumerate(pages, start=1):
            text = re.sub(r"\s+", " ", page.extract_text() or "").strip()
            if 1 < index < len(pages) and len(text) < 120:
                warnings.append(
                    {"page": index, "signal": "very_little_extracted_text", "characters": len(text)}
                )
    except Exception:
        pass
    return warnings


def run(args: argparse.Namespace) -> int:
    docx = args.input.resolve()
    pdf = args.output_pdf.resolve()
    report_path = args.report.resolve()
    pages_dir = args.pages_dir.resolve()
    if not docx.exists():
        raise SystemExit(f"DOCX not found: {docx}")
    if pdf.suffix.lower() != ".pdf":
        raise SystemExit("--output-pdf must name a .pdf file")
    if pdf.exists():
        pdf.unlink()
    attempts = []
    rendered = False
    renderer = None
    for function in (render_with_libreoffice, render_with_word):
        rendered, attempt = function(docx, pdf)
        attempts.append(attempt)
        if rendered:
            renderer = attempt["renderer"]
            break
    page_images: list[str] = []
    raster_report: dict[str, Any] = {"available": False, "error": "render failed"}
    if rendered:
        page_images, raster_report = rasterize(pdf, pages_dir)
    page_count = pdf_page_count(pdf) if rendered else None
    if args.inspection_status == "passed" or args.inspected_pages.strip().lower() == "all":
        raise SystemExit(
            "Inline 'all/passed' inspection is no longer accepted. View every rendered page, "
            "then provide --inspection-file with one hash-bound observation per page."
        )
    inspection_file = args.inspection_file.resolve() if args.inspection_file else None
    page_inspections, inspection_errors = load_page_inspections(inspection_file, page_images)
    if inspection_file is None:
        inspection_status = "pending"
    elif inspection_errors or any(row["verdict"] != "passed" for row in page_inspections):
        inspection_status = "failed"
    else:
        inspection_status = "passed"
    page_hashes = [
        {"page_number": index, "path": image_path, "sha256": file_sha256(Path(image_path))}
        for index, image_path in enumerate(page_images, start=1)
    ]
    report = {
        "input_docx": str(docx),
        "output_pdf": str(pdf),
        "pages_dir": str(pages_dir),
        "created_at": utc_now(),
        "renderer": renderer,
        "input_docx_sha256": file_sha256(docx),
        "output_pdf_sha256": file_sha256(pdf),
        "render_status": "passed" if rendered and raster_report.get("exit_code") == 0 and page_images else "failed",
        "renderer_attempts": attempts,
        "rasterization": raster_report,
        "page_count": page_count,
        "page_images": page_images,
        "page_artifacts": page_hashes,
        "layout_warnings": layout_warnings(pdf, page_images) if rendered else [],
        "inspection_status": inspection_status,
        "inspection_file": str(inspection_file) if inspection_file else None,
        "page_inspections": page_inspections,
        "inspection_errors": inspection_errors,
        "inspected_pages": [row["page_number"] for row in page_inspections],
        "inspection_note": args.inspection_note.strip(),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["render_status"] == "passed" and not inspection_errors else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a review DOCX with LibreOffice or Microsoft Word, then rasterize every page.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-pdf", required=True, type=Path)
    parser.add_argument("--pages-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--inspection-status", choices=("pending", "passed", "failed"), default="pending")
    parser.add_argument("--inspected-pages", default="")
    parser.add_argument("--inspection-note", default="")
    parser.add_argument(
        "--inspection-file",
        type=Path,
        help="JSON file containing one page_number, page_sha256, verdict, and observation per rendered page.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
