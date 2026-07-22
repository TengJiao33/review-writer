---
name: review-literature-matrix-outline
description: Read screened literature, record source-located evidence, assess coverage, and build one useful review outline.
---

# Literature Matrix and Outline

Build a compact evidence base and organize it around the review question.

## Inputs

Read:

```text
00_discovery/topic_contract.json
00_discovery/selected_discovery_results.json
00_discovery/screening_validation.json
review-library/metadata/papers/<paper_id>.metadata.json
the linked Markdown for each included paper
the linked PDF when Markdown is insufficient
```

After reading, assign each paper `core`, `supporting`, `background`, or `excluded`. Add useful citation roles such as `landmark`, `method_example`, `comparative_support`, `mechanistic_support`, `limitation`, `context`, and `historical_bridge`. Optional fields include `chronology_role`, `coverage_tags`, and `intended_use`.

Read for the argument: identify what the paper changes, locate the passage or figure that establishes it, and note the evidence boundary.

## Evidence anchors

Keep the reviewer note separate from the source wording:

```json
{
  "paper_id": "P001",
  "title": "...",
  "role_after_reading": "core",
  "main_content": "Concise synthesis notes",
  "intended_use": "optional",
  "evidence_anchors": [
    {
      "evidence_id": "P001-E01",
      "note": "Source-supported information in review-ready language",
      "source_excerpt": "Short source wording with material qualifiers",
      "source_path": "review-root-relative or absolute path",
      "locator": "page, section, figure, table, or paragraph",
      "source_level": "full_text | abstract | metadata",
      "evidence_kind": "result | method | mechanism | limitation | context",
      "certainty": "direct | author_interpretation | review_inference | unclear"
    }
  ]
}
```

Every core or supporting paper needs a full-text anchor with a short verbatim excerpt. Preserve qualifiers such as `may`, `might`, `suggest`, and `possible`. Put paraphrase in `note`. Add separate anchors when the paper supports materially different claims about scope, mechanism, selectivity, or limitations.

Background papers may support bounded definitions, history, and orientation at the source level available. Reclassify and read the full text when such a paper becomes material to a mechanism, comparison, limitation, priority, or broad judgment.

## Portfolio and coverage

After matrix validation, run:

```bash
python skills/review-literature-matrix-outline/scripts/build_review_portfolio.py \
  --review-root . \
  --project-id <project_id>
```

The builder creates:

- `literature_portfolio.json`: evidence roles and citation uses.
- `method_cards.json`: evidence-linked fields for comparison, including materials, conditions, scope, selectivity, limitations, operational details, and mechanistic basis.
- `coverage_ledger.json`: the topic contract mapped to candidate papers, with thin and missing areas exposed.
- `portfolio_editorial_review.json`: material choices that need a writing or scope decision.

Populate method-card fields only from checked sources and leave unknown values `null`. When coverage is weak, add evidence, narrow the scope or title, or state the omission. These editorial views have no fixed paper, citation, or method-card quotas.

## Outline

Choose one organization that best answers the central question with the available evidence. Annotate section questions, assigned papers, comparison axes, coverage, and expected synthesis where useful. Create alternatives only when the topic genuinely supports different organizing logics.

Validate:

```bash
python skills/review-literature-matrix-outline/scripts/validate_evidence_matrix.py \
  --review-root . \
  --project-id <project_id>
```

The validator checks schema, IDs, sources, provenance, source depth, and excerpt presence. Semantic support is reviewed during reading and final audit.

## Outputs

```text
01_matrix_outline/paper_reading_notes.json
01_matrix_outline/literature_matrix.json
01_matrix_outline/literature_matrix.csv
01_matrix_outline/outline_options.md (when useful)
01_matrix_outline/selected_outline.md
01_matrix_outline/matrix_outline_report.md
01_matrix_outline/matrix_validation.json
01_matrix_outline/matrix_validation.md
01_matrix_outline/literature_portfolio.json
01_matrix_outline/method_cards.json
01_matrix_outline/coverage_ledger.json
01_matrix_outline/portfolio_editorial_review.json
01_matrix_outline/portfolio_report.md
```
