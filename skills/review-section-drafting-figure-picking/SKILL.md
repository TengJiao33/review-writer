---
name: review-section-drafting-figure-picking
description: Draft coherent review sections with stable paper citations, paragraph-level evidence links, and useful verified assets.
---

# Section Drafting and Figure Picking

Write the review in the form best suited to its central question. Use structured metadata for provenance, not as a sentence template.

## Inputs

Read the topic contract, validated literature matrix, method cards, section
blueprint, and their current diagnostics. Portfolio and coverage views are
useful when present, but they are generated aids rather than authoring gates.

## Citations and evidence

Use stable paper IDs; merge assigns numbers later:

```markdown
The two approaches differ in their evidentiary basis [@P107; @P022].
```

Write in `02_section_drafting/manuscript.md`. Put one compact provenance comment
before each cited paragraph; it stays out of the published prose:

```markdown
## Evidence boundary
<!-- section_id: sec2 -->

<!-- evidence: P001-E01, P002-E03 | type: comparison -->
The two approaches differ in their evidentiary basis [@P001; @P002].
```

Compile the readable manuscript into the structured contract:

```bash
python skills/review-section-drafting-figure-picking/scripts/compile_review_draft.py \
  --review-root . --project-id <project_id>
```

The compiler produces paragraph records with stable paragraph IDs,
`cited_paper_ids`, `evidence_ids`, and `paragraph_type`. Use the shared compiler
instead of creating project-specific draft-generation scripts. It binds the
compiled structure to the current manuscript and blueprint hashes. Never edit
`section_drafts.json` as a second prose source.

Lead with the point a reader needs, use concrete subjects and verbs, and let each
paragraph make one main move. Remove repeated previews, defensive disclaimers,
and abstract label piles. Reopen the linked source before using method-card
details. Give representative conditions and scope where they matter, compare
decision-relevant variables, preserve limitations, and state the consequence of
the comparison. Clear writing must not strengthen a claim beyond its evidence.

## Review visuals and tables

Generate candidate review assets:

```bash
python skills/review-section-drafting-figure-picking/scripts/init_review_visual_plan.py \
  --review-root . --project-id <project_id>
```

Choose assets that make the field structure, method choice, evidence boundary,
or practical comparison clearer than prose. A comprehensive review uses at
least three useful, unchanged figures from cited source papers when their reuse
rights are verified. Original synthesis visuals may add value, but they do not
replace that source-figure portfolio; they cite their supporting paper and
evidence IDs, distinguish corpus coverage from scientific certainty, and
receive an independent content check.

Build an evidence-linked comparison table when method cards support one:

```bash
python skills/review-section-drafting-figure-picking/scripts/build_method_comparison_table.py \
  --review-root . --project-id <project_id> \
  --fields study_design,subject_or_substrate,intervention_or_method,conditions_or_context,outcome_or_metric,main_result,limitations \
  --require-traceable
```

Repeat `--paper-id Pxxx` to select rows; omit it to use all available cards.
Unknown cells remain an em dash. Check cells marked `source_check_required`,
then place the verified table where it advances the argument.

## Source figures

Build the inventory and select a small source-figure portfolio before sustained
drafting. This makes visual evidence part of the editorial argument instead of
an ornament added after the prose:

```bash
python skills/review-section-drafting-figure-picking/scripts/build_paper_figure_inventory.py \
  --review-root . --project-id <project_id>
python skills/review-section-drafting-figure-picking/scripts/select_initial_figure_candidates.py \
  --review-root . --project-id <project_id>
```

Do not disposition every extracted image. Select a source figure only when it
has a specific `reader_job`, `placement_rationale`, exact
`manuscript_callout`, and verified `reuse_rights`. Keep its deterministic
`inventory_candidate_id`, source-PDF hash, page index, bounding box, true source
label, and full caption unchanged. Three copies of the same reader job do not
form a useful visual portfolio.
The inventory surfaces licence statements as hints, not permission. Check the
article licence, chosen figure credit line, third-party exclusions, adaptation
rights, and attribution wording. Inspect adjacent MinerU fragments and the
source page when a labeled figure may have been split. A crop materialized from
the recorded PDF page and bounding box is only a candidate: inspect the whole
page, caption, panel set, and legibility before selection. If the current corpus
cannot support three lawful and useful source figures for a comprehensive
review, return to source acquisition or revise scope. A skip note or an original
diagram is not a substitute for that missing evidence portfolio.

## Validation

Run:

```bash
python skills/review-section-drafting-figure-picking/scripts/validate_section_drafts.py \
  --review-root . --project-id <project_id>
```

The validator blocks broken citation IDs, evidence ownership, paragraph
provenance, duplicate prose, and invalid structure. Word-plan shortfalls and
heavy reuse of one evidence anchor are warnings for editorial inspection, not
completion gates. Expand through additional supported comparison, conditions,
mechanisms, contradictions, limitations, and implications—never through
repetition or filler. Semantic support is checked by reading and in final audit.

## Outputs

Core authoring outputs:

```text
02_section_drafting/manuscript.md
02_section_drafting/section_drafts.json
02_section_drafting/figure_candidates.json
02_section_drafting/section_draft_validation.json
```

Visual plans, inventories, comparison tables, Markdown previews, and reports are
generated or optional working views. Only selected visual entries proceed to
preparation.
