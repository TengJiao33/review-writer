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

Preflight checks structure, citation and reference numbering, metadata, duplicate prose, internal tokens, asset placement, and release formatting. Each cited reference needs journal and year plus a DOI or a usable volume-and-page/article locator. For a comprehensive review, title, leading authors, year, and DOI are checked against the linked PDF front matter; an unresolved record does not count toward the 25-reference floor.

Preflight also writes `semantic_audit_queue.json`. It selects critical scope and
certainty claims, stratified samples of operational, causal, practical, and
numerical risks, plus one representative evidence-bearing paragraph per
section. A full review normally yields about 15-24 passages; missing provenance
remains mandatory. This separates whole-draft deterministic checks from
selective semantic reading.
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

Counts of words, references, images, tables, sections, and method cards help
locate imbalance. The reader-utility and visual-plan sheets are diagnostic
working views, not approval forms: do not fill pending fields merely to release.

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

For numerical conditions and results, the quantities in a supported passage
must occur in the reopened checked excerpts. `removed` is a factual disposition:
the complete queued span must no longer occur in the audited manuscript, and
the removal rationale must identify the unsupported or overbroad point. Do not
use `removed` to skip source receipts while leaving the prose unchanged.

Revise the canonical `02_section_drafting/manuscript.md`, then recompile, merge,
and refresh `05_final_audit/final_draft.md` until each required high-risk queue
item is supported, removed, or replaced by a checked revision. The scanner
verifies IDs, ownership, source-check declarations, and issue closure; the
semantic decision comes from reading the passage and source context.

## 4. Release

For a declared `comprehensive` review, release has one coarse product floor:
8,000 substantive article-body words, 25 references actually called from that
body, two argument-bearing tables, and three useful unchanged non-table figures from cited
source papers with verified reuse rights. Original syntheses may be additional
figures, not substitutes. The body stops at the first canonical or disguised
backmatter heading, so duplicated reference blocks and figure descriptions
cannot inflate the result. This floor prevents scale regression; it does not
prescribe section lengths or excuse filler. The topic and evidence should
normally drive a stronger article and additional useful visuals.

Release also requires trustworthy reference metadata. Do not infer authors,
titles, journal details, years, DOIs, pages, or article numbers merely to fill a
record. Reopen the source or use a reliable bibliographic record; otherwise the
reference remains unresolved.

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
