---
name: review-figure-style-redraw
description: Verify selected source figures, prepare evidence-linked original review visuals, or redraw useful figures while preserving scientific content.
---

# Review Figure Preparation

Prepare only figures selected for a defined reader need. The extraction inventory
is not a checklist: inspect promising candidates, and fully verify only assets
selected for the manuscript. Available paths are unchanged source reuse,
original review synthesis, and verified redraw.

## Inputs

Read:

```text
02_section_drafting/figure_candidates.json
02_section_drafting/review_visual_plan.json
02_section_drafting/section_drafting_report.md
```

A selected source candidate records:

```text
paper_id
source_label
source_type
source_pdf
source_content_list
source_image_path
source_caption_text
source_completeness: complete | intentionally_partial | uncertain
source_page_review_status: pending | passed
source_verification_note
reader_job
placement_rationale
reuse_basis
reuse_rights:
  status: verified
  basis: CC BY 4.0 | CC BY-NC 4.0 | public domain | publisher permission | other verified basis
  license_url_or_permission_record
  source_locator
  third_party_material_checked: true
  adaptation: unchanged | adapted
  attribution_text
```

The script processes rows marked `manuscript_selected: true` or with editorial status `selected`, `adapted`, or `combined`. It resolves a missing `source_image_path` from paper metadata and `content_list.json` when possible.

## Source reuse

Prefer the MinerU-extracted source figure when it is complete, legible, relevant, and legally reusable. Compare it with the source PDF at readable zoom. Record the source label, page, completeness, content check, and structured reuse rights. A general article licence is not enough when the figure credit line excludes third-party material. Attribution and reuse permission are separate requirements. Use `adaptation: adapted` only when the verified licence or permission allows derivatives.

Run:

```bash
python skills/review-figure-style-redraw/scripts/redraw_figures.py \
  --review-root . \
  --project-id <project_id> \
  --use-source \
  --source-verification-note "Checked Scheme 5 on page 6: label, panel set, caption, content, and legibility agree." \
  --require-usable
```

For multiple figures, store `source_verification_note` on each candidate. Accepted files are copied to `03_figure_redraw/verified/` and recorded as `source_verified` with `verification_status: passed`.

## Original review synthesis

An overview, taxonomy, comparison landscape, decision map, or evidence-boundary figure may be built from verified method cards and anchors. Check every relationship, label, structure, condition, and inference against the recorded evidence.

Record a completed visual in `review_visual_manifest.json`:

```json
{
  "visuals": [
    {
      "visual_id": "RV-01",
      "status": "original_verified",
      "verification_status": "passed",
      "original_image": "absolute or project-relative path",
      "section_id": "sec1",
      "section_heading": "Introduction",
      "title": "Field map and organizing logic",
      "caption": "Original synthesis of ...",
      "reader_job": "What becomes clearer for the reader",
      "placement_rationale": "Why it belongs here",
      "source_paper_ids": ["P001", "P014"],
      "evidence_ids": ["P001-E01", "P014-E02"],
      "verification_note": "Sources and scientific content checked"
    }
  ]
}
```

Keep `status: draft` until the rendered asset has been inspected at readable zoom.

## Fidelity

Styling may change; scientific content may not. Preserve:

```text
chemical structures, connectivity, stereochemistry, atoms and substituents
reagents, catalysts, solvents, temperatures, times, yields
reaction arrows, panel order, table values, plot values, and labels
```

Use deterministic vector redraw or retabling for fidelity-critical chemistry, spectra, and data plots when practical. Compare every generative edit directly with the source before setting `verification_status: passed`.

MinerU's `single_block` describes extraction, not figure completeness. Panel labels or adjacent visual blocks require inspection of the source page.

## Optional redraw API

Project default:

```text
base_url: https://naiccc.com
wire_api: images
model: gpt-image-2
endpoint: /v1/images/edits
```

Use the image-editing endpoint for source-image restyling:

```bash
python skills/review-figure-style-redraw/scripts/redraw_figures.py \
  --review-root . \
  --project-id <project_id> \
  --base-url https://naiccc.com \
  --wire-api images \
  --api-key <key> \
  --require-usable
```

Validate source resolution first with `--dry-run`. Other options include:

```text
--figures-file
--model
--quality
--background
--output-format
--style-name
--limit
--use-source
--source-verification-note
```

If `--api-key` is omitted, the optional redraw path reads `OPENAI_API_KEY`.

## Outputs

Write under `review-projects/<project_id>/03_figure_redraw/`:

```text
style_config.json
source_figure_manifest.json
redrawn_figure_manifest.json
review_visual_manifest.json
figure_fidelity_review.json
figure_redraw_report.md
source/
verified/
redrawn/
```

When a selected figure cannot be resolved or verified, return it to selection. When the manuscript uses no image, create `skip_reason.md` with the editorial reason.
