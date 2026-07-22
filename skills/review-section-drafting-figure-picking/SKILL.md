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
instead of creating project-specific draft-generation scripts.

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
or practical comparison clearer than prose. A review may legally reproduce an
unchanged source figure, adapt one when its licence permits adaptation, or
create an original synthesis. Original synthesis visuals cite their supporting
paper and evidence IDs, distinguish corpus coverage from scientific certainty,
and receive an independent content check.

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

Build the inventory when source figures could serve a real reader need, then
inspect the small set of promising candidates:

```bash
python skills/review-section-drafting-figure-picking/scripts/build_paper_figure_inventory.py \
  --review-root . --project-id <project_id>
python skills/review-section-drafting-figure-picking/scripts/select_initial_figure_candidates.py \
  --review-root . --project-id <project_id>
```

Do not disposition every extracted image. Select a source figure only when it
has a specific `reader_job`, `placement_rationale`, and verified `reuse_rights`.
The inventory surfaces licence statements as hints, not permission. Check the
article licence, chosen figure credit line, third-party exclusions, adaptation
rights, and attribution wording. Inspect adjacent MinerU fragments and the
source page when a labeled figure may have been split. If no source figure is
suitable, record the reason in `03_figure_redraw/skip_reason.md`; an original
review visual may still be used.

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
