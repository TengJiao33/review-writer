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
references/rule_packs.json
```

Proceed when `matrix_validation.json` has zero blocking issues. Warnings may remain when they concern optional detail or note length.

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
