---
name: review-section-blueprint
description: Convert a selected review outline and evidence matrix into a lightweight writing map for a complete review manuscript.
---

# Section Blueprint

Create a lightweight writing map. Do not write manuscript prose.

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

Proceed when `matrix_validation.json` has zero blocking issues. Use `portfolio_editorial_review.json` as optional context: its prompts may suggest adding evidence, reusing current sources more effectively, narrowing scope, or accepting the observed condition. Unresolved prompts do not prevent drafting and do not prescribe a corpus size or section structure.

## Coverage Map

Add this top-level object to `section_blueprint.json`:

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

Derive important items from the manuscript title, retrieval query, central question, and explicitly prioritized scope. If evidence is weak or a topic is intentionally excluded, record the decision and update the title when necessary:

```json
{
  "scope_decision": "exclude_with_title_scope_update",
  "reason": "..."
}
```

Keep title-defining topics visible in the coverage map. Coverage warnings guide revision without dictating section architecture.

## Editorial brief

Use the portfolio, method cards, and coverage ledger to add an `editorial_brief`. It may include a broad content range, reader questions, thin coverage items, and promising original review assets. These are planning signals, not acceptance thresholds. Do not pad to a number, require every method-card field, or force the same internal pattern on every section.

For substantive sections, make enough material visible for the writer to choose among orientation, representative method depth, cross-method comparison, practical or scope boundaries, and a section-level takeaway. This is a menu, not a paragraph template. A short section can still be right when the evidence or argument warrants it.

## Writing Map

Use only fields that help the manuscript. A minimal section contains:

```text
section_id
title
section_thesis
review_problem
major_papers
```

Optional fields may include suggested claims, comparison axes, figures/tables, transitions, approximate length, or paragraph modes.

Possible paragraph modes include:

```text
comparison
mechanism
landmark_example
limitation_or_gap
context
synthesis
outlook
```

Select paragraph modes and approximate length only when they help plan a section.

## Required Validation

Run:

```bash
python skills/review-section-blueprint/scripts/validate_blueprint.py \
  --review-root . \
  --project-id <project_id>
```

Resolve structural blockers and unknown paper references, then rerun. Treat missing optional planning detail, uncovered secondary topics, and length estimates as warnings.

## Outputs

Write:

```text
01_matrix_outline/section_blueprint.json
01_matrix_outline/section_writing_plan.md
01_matrix_outline/blueprint_validation.json
01_matrix_outline/blueprint_validation.md
```
