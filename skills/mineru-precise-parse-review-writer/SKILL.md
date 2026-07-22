---
name: mineru-precise-parse-review-writer
description: Parse local literature PDFs under the current review-writer root into Markdown with the MinerU precise parsing batch API. Use when Codex needs to batch-convert a review paper library, preserve full MinerU zip sidecars, keep extracted images and JSON outputs, and skip files that were already parsed unless a force rerun is explicitly requested.
---

# MinerU Precise Parse For Review Writer

Use this skill when the task is to convert a local PDF library into review-ready Markdown with the MinerU precise parsing API.

This skill is for batch parsing only. It uploads local PDFs to MinerU, waits for batch completion, downloads the result zip for each PDF, extracts `full.md`, rewrites image paths, and writes a local manifest.

## Default Paths

- input root: `<review-root>/chem_papers`
- skill root: `<review-root>/skills/mineru-precise-parse-review-writer`
- output root: `<review-root>/mineru-outputs`

The parser scans the input root recursively for `*.pdf` files and ignores the skill directory and output directory.

## Auth

Token resolution order:

1. `--token <token>`
2. `MINERU_API_TOKEN`
3. `config/mineru_api_token.txt`

This skill already includes a local token file. Rotate it by editing `config/mineru_api_token.txt`.

## Default Behavior

Parsing is incremental by default:

- if `mineru-outputs/markdown/<slug>.md` already exists, skip that PDF
- reparse only when the user explicitly wants a rerun and `--force` is passed

## Commands

Parse the whole local library:

```bash
python3 scripts/parse_review_writer_pdfs.py
```

Parse only one or two files as a smoke test:

```bash
python3 scripts/parse_review_writer_pdfs.py --limit 2
```

Force a full rerun:

```bash
python3 scripts/parse_review_writer_pdfs.py --force
```

Parse a specific subtree:

```bash
python3 skills/mineru-precise-parse-review-writer/scripts/parse_review_writer_pdfs.py --input-dir chem_papers
```

Parse one specific PDF:

```bash
python3 skills/mineru-precise-parse-review-writer/scripts/parse_review_writer_pdfs.py --pdf chem_papers/1-s2.0-S004040202400526X-main.pdf
```

Parse an explicit batch without scanning unrelated PDFs:

```bash
python3 skills/mineru-precise-parse-review-writer/scripts/parse_review_writer_pdfs.py \
  --pdf chem_papers/web-imports/paper-1.pdf \
  --pdf chem_papers/web-imports/paper-2.pdf \
  --batch-size 10
```

## Outputs

The skill writes:

- `mineru-outputs/markdown/*.md`
- `mineru-outputs/extracted/<slug>/`
- `mineru-outputs/raw_zips/*.zip`
- `mineru-outputs/manifest.json`

The Markdown copies are the main deliverable.
The extracted directories keep `full.md`, images, and MinerU sidecar JSON for downstream chunking, provenance, and figure extraction.

## Boundary

Use this skill only for PDF-to-Markdown conversion.

Do not use it to:

- clean or rewrite the parsed Markdown
- synthesize the review itself
- treat MinerU output as already validated evidence
- replace later chunking, indexing, or citation-grounding stages
