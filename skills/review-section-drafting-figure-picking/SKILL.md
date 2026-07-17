---
name: review-section-drafting-figure-picking
description: Write an open-form review manuscript using stable paper citations and paragraph-level evidence links, with figures selected only when useful.
---

# Section Drafting and Figure Picking

Write coherent review prose in the form best suited to the central question. Evidence links preserve traceability without supplying sentence templates.

## Inputs

Read:

```text
00_discovery/topic_contract.json
01_matrix_outline/literature_matrix.json
01_matrix_outline/section_blueprint.json
01_matrix_outline/section_writing_plan.md
01_matrix_outline/matrix_validation.json
01_matrix_outline/blueprint_validation.json
```

## Citations and evidence links

Use stable paper IDs in prose; merge assigns numeric references later:

```markdown
The two approaches differ in their evidentiary basis [@P107; @P022].
```

Each cited paragraph lists the evidence anchors used to write it:

```json
{
  "paragraph_id": "sec2-p1",
  "markdown": "Complete, freely written paragraph with [@Pxxx] citations.",
  "cited_paper_ids": ["P001", "P002"],
  "evidence_ids": ["P001-E01", "P002-E03"],
  "paragraph_type": "comparison",
  "figure_candidate_id": null
}
```

`paragraph_id`, `paragraph_type`, and `figure_candidate_id` are lightweight editorial metadata. `markdown`, inline citations, and `evidence_ids` form the provenance contract. The paragraph may synthesize, compare, narrate, explain one paper deeply, or use another structure appropriate to the section.

## Structured output

Write `section_drafts.json` with `front_matter` and a list of sections. Each section has `section_id`, `title`, and `paragraphs`; `draft_md` may be included as a preview. Keep internal IDs out of manuscript prose.

## Figures

Run the deterministic inventory and selection path rather than writing figure artifacts by hand:

```bash
python skills/review-section-drafting-figure-picking/scripts/build_paper_figure_inventory.py \
  --review-root . --project-id <project_id>
python skills/review-section-drafting-figure-picking/scripts/select_initial_figure_candidates.py \
  --review-root . --project-id <project_id>
```

The selection command rebuilds the MinerU inventory again before choosing candidates. Write `figure_candidates.json` as a JSON list. When MinerU has split one labeled figure across adjacent image blocks, the inventory exposes the fragment paths but keeps that candidate unresolved; select a complete candidate or reconstruct the complete source figure deliberately. Use `[]` only after inspecting the generated inventory. When resolvable candidates exist but none is suitable, record the actual editorial reason in `03_figure_redraw/skip_reason.md`. Choose figures whose visual content and source context improve the manuscript.

Validate:

```bash
python skills/review-section-drafting-figure-picking/scripts/validate_section_drafts.py \
  --review-root . \
  --project-id <project_id>
```

The validator checks citation IDs, evidence ownership, paragraph provenance, duplicates, and required structure. It also reports `evidence_usage_by_paper` without turning it into a quota: use the profile to notice when many materially different paragraphs rely on one anchor, then deepen only those sources. It does not compare manuscript wording with evidence wording.

## Outputs

```text
02_section_drafting/section_tasks.json
02_section_drafting/sections/<section_id>.md
02_section_drafting/section_drafts.json
02_section_drafting/section_drafts.md
02_section_drafting/paper_figure_inventory.json
02_section_drafting/paper_figure_candidates.json
02_section_drafting/figure_candidates.json
02_section_drafting/section_drafting_report.md
02_section_drafting/section_draft_validation.json
```
