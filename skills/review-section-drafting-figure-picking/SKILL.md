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
01_matrix_outline/literature_portfolio.json
01_matrix_outline/method_cards.json
01_matrix_outline/coverage_ledger.json
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

Use method cards as a navigation layer, then reopen the linked anchor or source for details. When the material supports it, give readers more than a list of studies: explain representative conditions and scope, contrast decision-relevant variables, preserve limitations, and state what the comparison changes. Suggested lengths and section payloads are editorial prompts, not quotas.

## Structured output

Write `section_drafts.json` with `front_matter` and a list of sections. Each section has `section_id`, `title`, and `paragraphs`; `draft_md` may be included as a preview. Keep internal IDs out of manuscript prose.

## Review visuals and tables

Plan original review assets independently of source figures:

```bash
python skills/review-section-drafting-figure-picking/scripts/init_review_visual_plan.py \
  --review-root . --project-id <project_id>
```

The plan suggests an original overview or taxonomy, a Markdown comparison table, and an evidence-or-boundary map. Select, adapt, combine, or skip whatever genuinely helps; the plan may remain partly unresolved and there is no asset count. A short rationale is useful for material choices but is not a drafting or release gate. Prefer a useful high-density asset when it would let a reader understand structure, method choice, or limitations faster than prose. Original synthesis must name its supporting paper and evidence IDs, distinguish corpus coverage from scientific certainty, and be independently checked. It must not imitate or silently adapt a source figure.

For an evidence-traceable comparison table, select the decision-relevant fields and, optionally, representative paper IDs:

```bash
python skills/review-section-drafting-figure-picking/scripts/build_method_comparison_table.py \
  --review-root . --project-id <project_id> \
  --fields method_family,substrate_class,activation_mode,selectivity,limitations \
  --require-traceable
```

Repeat `--paper-id Pxxx` to choose rows; omit it to use all available cards. The command writes a Markdown table and a cell-level evidence manifest. Unknown values remain an em dash and do not imply failure or absence. Reopen sources for any `source_check_required` cell. Insert the verified Markdown table where it serves the argument; selection does not itself force the table into the manuscript.

Markdown tables belong directly in the section draft. A prepared original image is recorded later in `03_figure_redraw/review_visual_manifest.json` with `status: original_verified`, a passed verification status, and its evidence basis.

## Source figures

Run the deterministic inventory and selection path rather than writing figure artifacts by hand:

```bash
python skills/review-section-drafting-figure-picking/scripts/build_paper_figure_inventory.py \
  --review-root . --project-id <project_id>
python skills/review-section-drafting-figure-picking/scripts/select_initial_figure_candidates.py \
  --review-root . --project-id <project_id>
```

The selection command rebuilds the MinerU inventory and writes suggestions, not manuscript selections. Review the candidates and set `manuscript_selected: true` only for a figure with a specific `reader_job` and `placement_rationale`; source reuse also needs a recorded `reuse_basis`. When MinerU has split one labeled figure across adjacent image blocks, the inventory exposes the fragment paths but keeps that candidate unresolved; select a complete candidate or reconstruct the complete source figure deliberately. An empty source-figure list is valid after inspection and should not fail drafting. When resolvable candidates exist but none is suitable, record the actual editorial reason in `03_figure_redraw/skip_reason.md`. An original review visual remains available even when source reuse is skipped.

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
02_section_drafting/review_visual_plan.json
02_section_drafting/review_visual_plan.md
02_section_drafting/method_comparison_table.md (when selected)
02_section_drafting/method_comparison_table_manifest.json (when selected)
02_section_drafting/paper_figure_inventory.json
02_section_drafting/paper_figure_candidates.json
02_section_drafting/figure_candidates.json
02_section_drafting/section_drafting_report.md
02_section_drafting/section_draft_validation.json
```
