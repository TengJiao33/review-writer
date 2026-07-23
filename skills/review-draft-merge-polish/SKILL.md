---
name: review-draft-merge-polish
description: Merge review sections, assign global citation numbers, generate references, insert verified assets, and polish the assembled manuscript.
---

# Draft Merge and Polish

Use the merge script for citation numbering, reference generation, and asset insertion.

## Inputs

Read:

```text
01_matrix_outline/literature_matrix.json
01_matrix_outline/section_blueprint.json
02_section_drafting/section_drafts.json
02_section_drafting/figure_candidates.json
02_section_drafting/method_comparison_table_manifest.json (when selected)
03_figure_redraw/redrawn_figure_manifest.json (when available)
03_figure_redraw/review_visual_manifest.json (when available)
```

## Merge

Run:

```bash
python skills/review-draft-merge-polish/scripts/merge_review.py \
  --review-root . \
  --project-id <project_id>
```

The script:

```text
rejects pre-numbered citations and images in the Abstract
checks paragraph citation IDs against cited_paper_ids when supplied
orders references by first appearance
replaces [@Pxxx] with global [n] callouts
generates References and citations.json from the same mapping
removes paragraph markers from manuscript prose
inserts verified selected figures and copies their assets
```

Selected source figures require `source_verified`; original synthesis visuals require `original_verified` and `verification_status: passed`. Figure insertion uses the recorded paragraph or `section_heading` and stops when the target is unresolved. Every inserted figure and table must then be called out in the surrounding prose and used to make an argumentative move; a caption alone does not integrate an asset. A selected comparison table keeps its evidence manifest and visible method labels.

Resolve citation, parsing, and asset blockers in the canonical
`02_section_drafting/manuscript.md`, then recompile and rerun the merge. Keep
stable paper IDs in provenance comments as the source of citation identity;
never repair `first_draft.md` as an independent prose branch.

## Polish

Revise the assembled manuscript for:

```text
argument and section transitions
terminology consistency
redundancy
comparison clarity
mechanistic qualification
```

If a prose revision changes citation order or identity, update the stable
`[@Pxxx]` tokens in `manuscript.md`, recompile, and rerun the merge. Numeric
citations and the reference list remain script-generated.

## Outputs

```text
04_first_draft/first_draft.md
04_first_draft/citations.json
04_first_draft/merge_validation.json
04_first_draft/merge_report.md
04_first_draft/remaining_issues.md
```
