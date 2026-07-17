---
name: review-literature-matrix-outline
description: Read the screened literature, record source-located evidence anchors, and build a coverage-aware outline for an open-form review manuscript.
---

# Literature Matrix and Outline

Create a compact evidence base and one useful manuscript outline.

## Inputs

Read:

```text
00_discovery/topic_contract.json
00_discovery/selected_discovery_results.json
00_discovery/screening_validation.json
review-library/metadata/papers/<paper_id>.metadata.json
the linked Markdown for each included paper
the linked PDF when the Markdown does not resolve the needed detail
```

Assign `role_after_reading` as `core`, `supporting`, `background`, or `excluded`. `intended_use` is optional and belongs here, after reading.

Read toward the review argument: identify what the paper changes in the central question, open the passage or figure that establishes it, and note the boundary of that evidence. Let those paper-specific findings determine the anchors instead of beginning from a repeated method/result/mechanism template.

## Evidence anchors

An evidence anchor keeps the reviewer's concise paraphrase separate from a short verifiable source excerpt. It supplies traceability without prescribing manuscript wording.

```json
{
  "paper_id": "P001",
  "title": "...",
  "role_after_reading": "core",
  "main_content": "Concise notes useful for synthesis",
  "intended_use": "optional",
  "evidence_anchors": [
    {
      "evidence_id": "P001-E01",
      "note": "Source-supported information in review-ready language",
      "source_excerpt": "Short source wording that preserves material qualifiers",
      "source_path": "review-root-relative or absolute path",
      "locator": "page, section, figure, table, or paragraph locator",
      "source_level": "full_text | abstract | metadata",
      "evidence_kind": "result, method, mechanism, limitation, context, or another useful label",
      "certainty": "direct | author_interpretation | review_inference | unclear"
    }
  ]
}
```

Core and supporting papers receive at least one full-text anchor, but that is an integrity floor rather than a target. Give every core/supporting anchor a short verbatim source excerpt from the identified location; retain qualifiers such as `may`, `might`, `suggest`, and `possible`. Put paraphrase and interpretation in `note`, never in `source_excerpt`. The validator permits harmless whitespace, line-break, Unicode, and ellipsis normalization but blocks an excerpt that cannot be found in the recorded text or PDF. Evidence depth follows intended use: when one paper supports separate claims about scope, mechanism, selectivity, or limitation, capture the distinct source locations instead of reusing one generic anchor. Do not create extra anchors merely to reach a count. Keep a proposal or review inference labeled at its actual certainty.

## Outline

Organize the outline around the central question and available evidence. Useful annotations include section question, assigned papers, comparison axes, important coverage, and expected synthesis. Use a single outline unless genuinely different organizations merit a choice.

Validate:

```bash
python skills/review-literature-matrix-outline/scripts/validate_evidence_matrix.py \
  --review-root . \
  --project-id <project_id>
```

The validator checks schema, unique IDs, source existence, source depth, provenance structure, and verbatim excerpt presence. It does not infer whether the excerpt semantically proves the reviewer's claim; that remains a reading and audit judgment.

## Outputs

```text
01_matrix_outline/paper_reading_notes.json
01_matrix_outline/literature_matrix.json
01_matrix_outline/literature_matrix.csv
01_matrix_outline/outline_options.md (optional)
01_matrix_outline/selected_outline.md
01_matrix_outline/matrix_outline_report.md
01_matrix_outline/matrix_validation.json
01_matrix_outline/matrix_validation.md
```
