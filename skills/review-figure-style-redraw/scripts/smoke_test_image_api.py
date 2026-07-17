#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import ssl
import urllib.request
import uuid
from pathlib import Path


def guess_mime(path: Path) -> str:
    return mimetypes.guess_type(str(path))[0] or "image/png"


def build_headers(api_key: str, content_type: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": "review-writer-figure-redraw-smoke/1.0",
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def build_multipart_form(fields: dict[str, str], file_fields: list[tuple[str, Path]]) -> tuple[str, bytes]:
    boundary = f"----CodexBoundary{uuid.uuid4().hex}"
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(value.encode("utf-8"))
        body.extend(b"\r\n")
    for name, path in file_fields:
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"; filename="{path.name}"\r\n'.encode("utf-8"))
        body.extend(f"Content-Type: {guess_mime(path)}\r\n\r\n".encode("utf-8"))
        body.extend(path.read_bytes())
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    return f"multipart/form-data; boundary={boundary}", bytes(body)


def save_b64_png(b64: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(b64))


def test_images_generate(base_url: str, api_key: str, out_path: Path) -> None:
    payload = {
        "model": "gpt-image-2",
        "prompt": "Generate a simple flat chemistry-themed icon: an Erlenmeyer flask with a small green liquid fill on a white background.",
        "size": "1024x1024",
        "quality": "low",
        "background": "white",
    }
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/images/generations",
        data=json.dumps(payload).encode("utf-8"),
        headers=build_headers(api_key, "application/json"),
        method="POST",
    )
    with urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    save_b64_png(data["data"][0]["b64_json"], out_path)


def test_images_edit(base_url: str, api_key: str, source_path: Path, out_path: Path) -> None:
    fields = {
        "model": "gpt-image-2",
        "prompt": "Restyle this image into a cleaner publication-ready flat illustration style. Preserve all objects and layout exactly. Change only style.",
        "quality": "low",
        "background": "white",
        "output_format": "png",
    }
    content_type, body = build_multipart_form(fields, [("image[]", source_path)])
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/images/edits",
        data=body,
        headers=build_headers(api_key, content_type),
        method="POST",
    )
    with urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=300) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    save_b64_png(data["data"][0]["b64_json"], out_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test image generation and edit APIs.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parents[3] / "tmp" / "image-smoke-test"))
    parser.add_argument("--edit-only", action="store_true")
    parser.add_argument("--source-image", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    gen_path = output_dir / "generated.png"
    edit_path = output_dir / "edited.png"
    if args.edit_only:
        if not args.source_image:
            raise SystemExit("--edit-only requires --source-image")
        source_path = Path(args.source_image).resolve()
        test_images_edit(args.base_url, args.api_key, source_path, edit_path)
    else:
        test_images_generate(args.base_url, args.api_key, gen_path)
        test_images_edit(args.base_url, args.api_key, gen_path, edit_path)
        print(gen_path)
    print(edit_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
