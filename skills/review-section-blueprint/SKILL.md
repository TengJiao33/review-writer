---
name: review-section-blueprint
description: Convert the selected outline and evidence matrix into a concise writing map for the review manuscript.
---

# Section Blueprint

Turn the selected outline into one executable `section_blueprint.json`. Keep it concise enough to guide drafting without reproducing the manuscript.

`init_section_blueprint.py` creates a topic-bound scaffold, not scientific
content. For the general rule pack its generated `review_claims` are explicitly
marked `editorial_prompt_requires_evidence_authoring`. Reopen the assigned
sources, replace every prompt with a bounded evidence-backed argument unit, and
set the root status to `ready_for_drafting` only after this semantic authoring is
complete. Never draft from initializer prose.

## Inputs

Read:

```text
01_matrix_outline/selected_outline.md
01_matrix_outline/literature_matrix.json
01_matrix_outline/paper_reading_notes.json
01_matrix_outline/matrix_validation.json
01_matrix_outline/literature_portfolio.json
01_matrix_outline/method_cards.json
01_matrix_outline/coverage_ledger.json
01_matrix_outline/portfolio_editorial_review.json
references/rule_packs.json
```

Start after matrix validation has no blockers. Resolve material portfolio findings by adding evidence, using existing sources more effectively, narrowing scope, or accepting a bounded omission.

Run the whole-review coordinator after authoring or revising the blueprint. A
topic mismatch, rule-pack leakage, or un-authored initializer prompt keeps work
in the manuscript loop even when the blueprint file exists.

## Coverage contract

Keep title-defining topics and declared priorities visible:

```json
{
  "coverage_contract": {
    "suggested_manuscript_words": 5000,
    "dimensions": [
      {
        "name": "major_evidence_dimension",
        "items": [
          {
            "name": "topic-defining comparison or coverage item",
            "required": true,
            "covered_by": ["P001", "P052"]
          }
        ]
      }
    ]
  }
}
```

When evidence cannot support a title-defining topic, record the scope decision and update the title if needed:

```json
{
  "scope_decision": "exclude_with_title_scope_update",
  "reason": "..."
}
```

## Section map

Each substantive section needs:

```text
section_id
title
section_thesis
review_problem
major_papers
```

Add claims, comparison axes, evidence, transitions, figures, tables, paragraph modes, or approximate length only when they guide a real writing choice. Common paragraph modes include:

```text
comparison
mechanism
landmark_example
limitation_or_gap
context
synthesis
outlook
```

`review_claims` is optional. If it is used and the blueprint is marked
`ready_for_drafting`, each claim must name the evidence anchors that support it,
and those anchors must belong to its supporting papers. Do not mark initializer
prompts or `needs verification` claims as ready. A shorter map with genuine
claim—evidence links is better than a long list of plausible headings.

Use the portfolio and method cards to expose the representative methods, useful comparisons, practical boundaries, and section-level takeaway. Match structure and length to the evidence instead of a fixed paragraph pattern.

Select a domain rule pack only when it fits the topic. The allene rule pack applies to the registered allene and propargylic-chemistry scope, not to general chemistry reviews.

## Validation

Run:

```bash
python skills/review-section-blueprint/scripts/validate_blueprint.py \
  --review-root . \
  --project-id <project_id>
```

Fix structural blockers and unknown paper references. Coverage and length warnings inform editorial revision.

## Outputs

```text
01_matrix_outline/section_blueprint.json
01_matrix_outline/section_writing_plan.md
01_matrix_outline/blueprint_validation.json
01_matrix_outline/blueprint_validation.md
```

`section_writing_plan.md` is generated directly from the blueprint as its readable view.
