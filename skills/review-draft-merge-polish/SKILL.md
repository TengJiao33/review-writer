---
name: review-draft-merge-polish
description: Deterministically merge review sections, assign global citation numbers from stable paper IDs, generate references, and polish prose without changing citation identity.
---

# Draft Merge and Polish

Use a script for fragile assembly. Do not manually concatenate sections or renumber references.

## Inputs

Read:

```text
01_matrix_outline/literature_matrix.json
01_matrix_outline/section_blueprint.json
02_section_drafting/section_drafts.json
02_section_drafting/figure_candidates.json
03_figure_redraw/redrawn_figure_manifest.json (when available)
```

## Required Merge

Run:

```bash
python skills/review-draft-merge-polish/scripts/merge_review.py \
  --review-root . \
  --project-id <project_id>
```

The script treats section and paragraph metadata as a lightweight envelope. It:

```text
rejects pre-numbered citations
rejects Markdown or HTML image embeds in Abstract
validates paragraph citation IDs against cited_paper_ids when that optional field is present
orders references by first appearance
replaces [@Pxxx] with global [n] callouts
generates References and citations.json from the same mapping
removes paragraph markers from manuscript prose
inserts selected prepared figures (`source_verified` or `redrawn`) and copies figure assets into both draft-stage directories
```

Do not run a separate hand-written figure insertion step. When `figure_candidates.json` is non-empty, merge fails if no selected image can be inserted. Unverified source candidates remain visible to the final release check; an unchanged MinerU image becomes a formal figure after the figure stage records it as `source_verified`.

Prepared figure rows retain `section_heading`. Figure insertion stops when its target heading is unresolved instead of falling back to Abstract or another convenient heading.

Resolve citation or parse blockers in the structured draft and rerun. Abstract length, keyword count, uncited transitional prose, and paragraph labels are editorial warnings; an image embedded in Abstract is an asset-placement error. Do not write an ad hoc replacement script.

## Polish Pass

After deterministic merge, polish prose, structure, and transitions while preserving citation identity. Typical targets include:

```text
section transitions
terminology consistency
redundant sentences
comparison clarity
mechanism qualification
```

Do not manually edit citation numbers or reorder References. If prose changes citation order or identity, restore stable `[@Pxxx]` tokens in the structured section data and rerun `merge_review.py`.

## Outputs

Write:

```text
04_first_draft/first_draft.md
04_first_draft/citations.json
04_first_draft/merge_validation.json
04_first_draft/merge_report.md
04_first_draft/remaining_issues.md
```
