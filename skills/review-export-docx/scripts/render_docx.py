#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    inspected_pages = parse_inspected_pages(args.inspected_pages, page_count)
    inspection_status = args.inspection_status
    if inspection_status == "passed":
        if not args.inspection_note.strip():
            raise SystemExit("--inspection-note is required when inspection status is passed")
        if page_count is None or inspected_pages != list(range(1, page_count + 1)):
            raise SystemExit("A passed inspection must record every rendered page with --inspected-pages all")
    if inspection_status == "failed" and not args.inspection_note.strip():
        raise SystemExit("--inspection-note is required when inspection status is failed")
    report = {
        "input_docx": str(docx),
        "output_pdf": str(pdf),
        "pages_dir": str(pages_dir),
        "created_at": utc_now(),
        "renderer": renderer,
        "render_status": "passed" if rendered and raster_report.get("exit_code") == 0 and page_images else "failed",
        "renderer_attempts": attempts,
        "rasterization": raster_report,
        "page_count": page_count,
        "page_images": page_images,
        "inspection_status": inspection_status,
        "inspected_pages": inspected_pages,
        "inspection_note": args.inspection_note.strip(),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["render_status"] == "passed" else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a review DOCX with LibreOffice or Microsoft Word, then rasterize every page.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-pdf", required=True, type=Path)
    parser.add_argument("--pages-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--inspection-status", choices=("pending", "passed", "failed"), default="pending")
    parser.add_argument("--inspected-pages", default="")
    parser.add_argument("--inspection-note", default="")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
