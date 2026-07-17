---
name: review-figure-style-redraw
description: Prepare selected review figures by source-verifying the original extracted image or, when useful, redrawing it into a unified style while preserving chemistry and content. The source-verified path does not require an image API. Use after section drafting has produced figure_candidates.json and before manuscript merge.
---

# Review Figure Preparation

Use this skill when `figure_candidates.json` contains a figure worth including.

This stage uses a script because file resolution, API calls, and manifests must be stable.

## Inputs

Read:

```text
review-projects/<project_id>/02_section_drafting/figure_candidates.json
review-projects/<project_id>/02_section_drafting/section_drafting_report.md
```

Each useful candidate should include:

```text
paper_id
source_label
source_type
source_pdf
source_content_list
source_image_path
source_caption_text
recommended_action
source_completeness: complete | intentionally_partial | uncertain
source_page_review_status: pending | passed
source_verification_note
```

If `source_image_path` is missing, the script attempts to resolve it from metadata and `content_list.json`.

## Default Rule

Prefer the original MinerU-extracted figure when it is legible and materially supports the manuscript. Inspect it against the source PDF at readable zoom, then accept it unchanged with source attribution. This is a complete figure path, not a placeholder, and it requires no image-generation credential. Attribution does not replace permission: record the source's reuse basis or choose a newly synthesized/adapted visual when reuse rights are unclear.

Use generative restyling only when the user or manuscript genuinely benefits from it. Image editing is optional, not a workflow preflight dependency.

## Fidelity Rule

Change visual style only.

Preserve:

```text
chemical structures
bond connectivity
stereochemistry
atom and substituent labels
reagents, catalysts, solvents, temperatures, times, yields
reaction arrows and panel order
table values and figure labels
```

Treat chemical schemes, structures, spectra, and data plots as fidelity-critical. A generative image edit is not release evidence by itself. Prefer deterministic vector redraw, retabling, or an appropriately cited source figure. If a generative edit is used for styling, compare the source and output directly at readable zoom and record `verification_status: passed` only after checking connectivity, stereochemistry, labels, conditions, yields, and numeric values. Do not release a chemistry figure whose fidelity cannot be verified.

## Source-Verified Run

After inspecting the extracted image and its source PDF, update each accepted candidate with `source_page_review_status: passed`, an explicit completeness decision, and a figure-specific verification note. `single_block` is an extraction description, not proof that a labeled multi-panel figure is complete. Treat a panel marker or adjacent same-page visual blocks as a prompt to inspect the PDF, not as an automatic rejection.

For one figure, the note may be passed on the command line:

```bash
python skills/review-figure-style-redraw/scripts/redraw_figures.py \
  --review-root . \
  --project-id <project_id> \
  --use-source \
  --source-verification-note "Checked Scheme 5 on page 6 against the source PDF: label, complete panel set, caption, content, and legibility agree." \
  --require-usable
```

Name the selected source label and page in the note. For multiple figures, store `source_verification_note` on each candidate rather than combining several checks in one CLI note. This copies the unchanged accepted image to `03_figure_redraw/verified/`, records `status: source_verified` plus `verification_status: passed`, and writes one row per figure to `figure_fidelity_review.json`.

## Optional Redraw API

Default recommendation for this project:

```text
base_url: https://naiccc.com
wire_api: images
model: gpt-image-2
endpoint: /v1/images/edits
```

Use `wire_api: images` for real source-image editing. Do not use `responses` for chemistry-preserving redraw unless the relay demonstrably supports image input and image editing through `/v1/responses`; otherwise it can generate a new figure without faithfully editing the source.

## Optional Redraw Run

```bash
python skills/review-figure-style-redraw/scripts/redraw_figures.py \
  --review-root . \
  --project-id <project_id> \
  --base-url https://naiccc.com \
  --wire-api images \
  --api-key <key> \
  --require-usable
```

Useful options:

```text
--figures-file
--model
--quality
--background
--output-format
--style-name
--limit
--dry-run
--use-source
--source-verification-note
--require-usable
```

For optional API redraw only, if `--api-key` is omitted, the script uses `OPENAI_API_KEY`.

Validate source resolution first when needed:

```bash
python skills/review-figure-style-redraw/scripts/redraw_figures.py \
  --review-root . \
  --project-id <project_id> \
  --dry-run
```

## Outputs

Write under:

```text
review-projects/<project_id>/03_figure_redraw/
```

Create:

```text
style_config.json
source_figure_manifest.json
redrawn_figure_manifest.json
figure_fidelity_review.json
figure_redraw_report.md
source/
verified/
redrawn/
```

If a selected figure cannot be resolved or verified faithfully, return to figure selection and reconsider it. When the manuscript does not use figures, create `03_figure_redraw/skip_reason.md` with a one-line record of that decision.
