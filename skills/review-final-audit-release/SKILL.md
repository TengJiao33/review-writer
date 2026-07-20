---
name: review-final-audit-release
description: Run deterministic release checks and a topic-driven semantic evidence audit over a complete review manuscript.
---

# Final Audit and Release

Complete a deterministic preflight, a reader-utility revision, a semantic evidence review, and a final release scan.

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

Initialize `05_final_audit/final_draft.md` from the current `04_first_draft/first_draft.md` before substantive audit edits. Preserve the `figures/<name>` links; merge has already copied the same assets into `05_final_audit/figures/`. Do not reconstruct the manuscript or its figures by hand.

```bash
python skills/review-final-audit-release/scripts/final_audit_scan.py \
  --review-root . \
  --project-id <project_id> \
  --phase preflight
```

This checks manuscript structure, citation/reference numbering, metadata alignment, duplicate prose, internal-token leakage, and release formatting. A cited reference needs journal and year plus either a DOI or a usable volume-and-page/article locator; a title-only provider record is not release-ready metadata. Do not clear this blocker by guessing or bulk-patching shared library metadata. When a linked local PDF exposes a DOI in its front matter, the recorded DOI must match it.

Preflight also writes `semantic_audit_queue.json`. It includes every passage detected as high-risk, then adds a small advisory sample of other cited passages. It supplies paragraph-linked papers and anchors as candidates but deliberately leaves the selected `cited_paper_ids` and `evidence_ids` empty: choose the minimum supporting subset only after opening the linked source. Detection is a prompt to read, not a verdict that the claim is wrong.

## 2. Reader-utility revision

Read the assembled manuscript as a reader before narrowing attention to claim-level audit. Initialize a compact review sheet:

```bash
python skills/review-final-audit-release/scripts/init_reader_utility_review.py \
  --review-root . \
  --project-id <project_id>
```

Use `reader_utility_review.json` or its Markdown view as a lightweight reading aid. Record only the findings and revision actions that materially help; unanswered questions and an unfinished review status remain advisory warnings rather than release blockers. Free-form notes are acceptable when they capture the useful editorial judgment more naturally.

Ask whether the manuscript exposes its organizing logic, representative method details, decision-relevant comparisons, recurring boundaries, evidentiary distinctions, and useful visual or tabular compression. Revise only where the manuscript and evidence benefit. The snapshot counts words, references, images, tables, sections, and available method cards to aid inspection; none is a quota. A concise, well-bounded review may stay concise, and an asset should be added only when it performs a real reader job.

This pass is where content volume should grow through missing explanation, comparison, or boundary analysis—not filler—and where underused supporting/background literature can be brought in for orientation without weakening key-claim standards.

## 3. Semantic audit

Build the audit from the current topic and manuscript. Concentrate on statements where an error would materially change the review, such as numerical results, causal or mechanistic explanations, comparisons, broad generalizations, priority statements, recommendations, and topic-specific focal points. For a multi-paper synthesis, check whether each cited source supports the whole statement or only part of it, and narrow the wording when needed.

For each selected passage, compare its meaning with the linked evidence anchor and source. `text_span` must be an actual passage from the identified structured paragraph, and the cited papers and evidence IDs must already be linked to that paragraph. This keeps the existing semantic audit honest without adding another audit stage. Record the model judgment:

```json
{
  "model": "actual model name",
  "checks": [
    {
      "check_id": "sec2-p1-a1",
      "queue_id": "sec2-p1-a1",
      "section_id": "sec2",
      "paragraph_id": "sec2-p1",
      "text_span": "Faithful manuscript passage being reviewed",
      "cited_paper_ids": ["P001", "P002"],
      "evidence_ids": ["P001-E01", "P002-E03"],
      "source_checked": true,
      "support_scope": "full",
      "epistemic_basis": "directly_observed | consistent_with | author_proposed | review_inference",
      "verdict": "supported | needs_revision | unsupported | removed",
      "comment": "Concise claim-specific basis from the checked source"
    }
  ],
  "changes_made": ["..."],
  "unresolved_blockers": []
}
```

Select only sources that support the exact `text_span`; use `support_scope: partial` with `needs_revision` when a source supports only part of the claim. Set `source_checked: true` after opening the recorded source location. The comment must state the source fact, qualification, or contradiction that determines the verdict; a list of paper IDs plus “verified” is not an audit rationale. Compare the manuscript's certainty with the source wording: `might`, `possible`, `consistent with`, and an author-proposed mechanism do not support `confirm`, `establish`, or a universal active species without additional evidence. Treat `first`, `only`, `general`, `mature`, `most powerful`, field-wide absence, and cross-system convergence as coverage-dependent claims; bound them to the retained corpus when external calibration is incomplete. `epistemic_basis` records this judgment for readers but does not create another validator gate.

Revise `05_final_audit/final_draft.md` until every audit item is `supported`, `removed`, or replaced by a newly checked revision. Every queue ID listed in `required_high_risk_queue_ids` must have a disposition; advisory queue items may be replaced when another claim is more consequential. The semantic judgment comes from reading meaning and source context. The scanner verifies evidence IDs, paper ownership, the source-check declaration, and issue closure; it does not turn checked claims into proof that an entire section was verified or require a wording change merely to prove that the audit was active.

## 4. Release scan

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
