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

Assign `role_after_reading` as `core`, `supporting`, `background`, or `excluded`. This is the paper's evidence-depth role, not a one-dimensional quality ranking. Add one or more flexible `citation_roles` when useful, such as `landmark`, `method_example`, `comparative_support`, `mechanistic_support`, `limitation`, `context`, or `historical_bridge`. A paper may serve several of these purposes. `chronology_role`, `coverage_tags`, and `intended_use` are optional and belong here, after reading.

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

Background papers may supply bounded definitions, historical transitions, or context from an abstract when the claim stays at that level. Promote a paper to supporting and reopen full text when it becomes material to scope, mechanism, selectivity, limitations, priority, or a cross-method judgment. This keeps the corpus broad enough to orient readers without weakening key claims.

## Portfolio, method cards, and coverage ledger

After the matrix validator passes its integrity checks, build the editorial views:

```bash
python skills/review-literature-matrix-outline/scripts/build_review_portfolio.py \
  --review-root . \
  --project-id <project_id>
```

`literature_portfolio.json` separates evidence-depth roles from citation uses. `method_cards.json` extracts comparison-ready fields such as substrate class, leaving group, coupling partner, catalyst, activation, conditions, product topology, scope, selectivity, limitations, operational notes, and mechanistic basis. Populate only what was actually read; keep unknown fields `null` instead of filling them from generic chemistry knowledge. Each populated field records the evidence IDs that support it. Deepen the fields that matter to the manuscript rather than forcing every paper into an identical card.

`coverage_ledger.json` maps declared topic priorities to candidate papers and labels thin or unmapped areas. Its token mapping is a navigation aid, not semantic proof. Reopen sources before writing, and respond to a gap by adding evidence, narrowing the title, or explaining the omission. Counts and gaps in `portfolio_report.md` are editorial prompts, never progression gates.

`portfolio_editorial_review.json` turns material observations into a small set of optional editorial prompts. Record a decision or rationale when it helps the manuscript; unresolved rows remain visible but do not block later stages or release. It is valid to keep a bounded corpus, accept a sparse comparison field, or narrow the scope when that best serves the review. The point is to prevent an accidental thin manuscript, not to impose paper, citation, or method-card quotas. Rerunning the builder preserves decisions for issues that still apply.

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
01_matrix_outline/literature_portfolio.json
01_matrix_outline/method_cards.json
01_matrix_outline/coverage_ledger.json
01_matrix_outline/portfolio_editorial_review.json
01_matrix_outline/portfolio_report.md
```
