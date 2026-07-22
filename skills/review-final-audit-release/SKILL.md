---
name: review-final-audit-release
description: Check a complete review for structural integrity, reader utility, semantic support, and release readiness.
---

# Final Audit and Release

Audit the assembled manuscript, revise it, and release the checked final draft.

## Inputs

Read:

```text
00_discovery/topic_contract.json
04_first_draft/first_draft.md
04_first_draft/citations.json
01_matrix_outline/literature_matrix.json
01_matrix_outline/literature_portfolio.json
01_matrix_outline/method_cards.json
01_matrix_outline/coverage_ledger.json
02_section_drafting/section_drafts.json
```

## 1. Preflight

Copy the current `04_first_draft/first_draft.md` to `05_final_audit/final_draft.md`, preserving `figures/<name>` links. Then run:

```bash
python skills/review-final-audit-release/scripts/final_audit_scan.py \
  --review-root . \
  --project-id <project_id> \
  --phase preflight
```

Preflight checks structure, citation and reference numbering, metadata, duplicate prose, internal tokens, asset placement, and release formatting. Each cited reference needs journal and year plus a DOI or a usable volume-and-page/article locator. When the local PDF exposes a DOI, the metadata must match it.

Preflight also writes `semantic_audit_queue.json`. It selects every paragraph
with an explicit risk signal, number, mechanism claim, or missing provenance,
plus one representative evidence-bearing paragraph per section. This separates
whole-draft deterministic provenance checks from selective semantic reading.
Do not narrow a queue item to one convenient sentence. Select the minimum
supporting paper and evidence IDs only after opening the linked source, and
rerun preflight whenever section drafts change so the queue fingerprint remains
current.

Record `manuscript_sha256` in `semantic_audit.json` for the exact `final_draft.md` revision that was checked. Release fails when any required paragraph is missing, the checked span is narrower than the queued paragraph, the queue is stale, or the manuscript changed after review.

## 2. Reader revision

Initialize the review sheet:

```bash
python skills/review-final-audit-release/scripts/init_reader_utility_review.py \
  --review-root . \
  --project-id <project_id>
```

Read the whole manuscript before auditing isolated claims. Revise missing organizing logic, representative method detail, decision-relevant comparison, recurring boundaries, evidentiary distinctions, and places where a figure or table would compress real complexity. Record only findings that lead to a material revision or explain a deliberate scope choice.

Counts of words, references, images, tables, sections, and method cards help locate imbalance; they have no fixed targets.

## 3. Semantic audit

Prioritize claims whose failure would change the review: numerical results, causal or mechanistic explanations, comparisons, broad generalizations, priority claims, recommendations, and central topic judgments. For multi-paper synthesis, check which part of the sentence each source supports and narrow the wording where needed.

Record each queued passage:

```json
{
  "model": "actual model name",
  "checks": [
    {
      "check_id": "sec2-p1-a1",
      "queue_id": "sec2-p1-a1",
      "section_id": "sec2",
      "paragraph_id": "sec2-p1",
      "text_span": "Exact manuscript passage",
      "cited_paper_ids": ["P001", "P002"],
      "evidence_ids": ["P001-E01", "P002-E03"],
      "source_receipts": [
        {
          "paper_id": "P001",
          "evidence_id": "P001-E01",
          "source_path": "exact path recorded by the evidence anchor",
          "source_sha256": "sha256 of the reopened source",
          "locator": "Results, paragraph 3",
          "checked_excerpt": "Verbatim passage reopened for this audit"
        }
      ],
      "source_checked": true,
      "support_scope": "full | partial",
      "epistemic_basis": "directly_observed | consistent_with | author_proposed | review_inference",
      "verdict": "supported | needs_revision | unsupported | removed",
      "comment": "Source fact, qualification, or contradiction that determines the verdict"
    }
  ],
  "changes_made": ["..."],
  "unresolved_blockers": []
}
```

`text_span` must occur in the identified paragraph. Paper and evidence IDs must
already be linked to that paragraph. For every evidence ID, record a source
receipt only after reopening the full text. The scanner verifies the source
path, current file hash, locator, and verbatim checked excerpt; a Boolean
`source_checked` without these receipts is not evidence of review. Semantic fit
cannot be proved by word overlap, so the rationale states the source fact and
qualification that determine the verdict. Use `partial` with `needs_revision`
when the source supports only part of the passage.

Match certainty to the source. Possibility or author-proposed mechanisms do not establish confirmed or universal conclusions. Claims such as `first`, `only`, `general`, `mature`, field-wide absence, and cross-system convergence require appropriate coverage and scope.

Revise `05_final_audit/final_draft.md` until each required high-risk queue item is supported, removed, or replaced by a checked revision. The scanner verifies IDs, ownership, source-check declarations, and issue closure; the semantic decision comes from reading the passage and source context.

## 4. Release

For a declared `comprehensive` review, release has one coarse product floor:
8,000 substantive words, 25 cited references, two real tables, and two real
non-table figures. Figures may be verified lawful source figures or
evidence-linked original syntheses. This floor prevents scale regression; it does not prescribe
section lengths or excuse filler. The topic and evidence should normally drive
a stronger article and additional useful visuals.

Run:

```bash
python skills/review-final-audit-release/scripts/final_audit_scan.py \
  --review-root . \
  --project-id <project_id> \
  --phase release
```

Release when `blocking_issues` is empty.

## Outputs

```text
05_final_audit/format_scan.json
05_final_audit/format_scan.md
05_final_audit/semantic_audit.json
05_final_audit/semantic_audit_queue.json
05_final_audit/reader_utility_review.json
05_final_audit/reader_utility_review.md
05_final_audit/reader_utility_snapshot.json
05_final_audit/content_audit_report.md
05_final_audit/format_audit_report.md
05_final_audit/final_draft.md
05_final_audit/final_remaining_issues.md
05_final_audit/release_report.md
```
