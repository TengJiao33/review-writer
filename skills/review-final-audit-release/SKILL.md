---
name: review-final-audit-release
description: Run deterministic release checks and a topic-driven semantic evidence audit over a complete review manuscript.
---

# Final Audit and Release

Complete a deterministic preflight, a semantic evidence review, and a final release scan.

## Inputs

Read:

```text
00_discovery/topic_contract.json
04_first_draft/first_draft.md
04_first_draft/citations.json
01_matrix_outline/literature_matrix.json
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

This checks manuscript structure, citation/reference numbering, metadata alignment, duplicate prose, internal-token leakage, and release formatting. A cited reference needs journal and year plus either a DOI or a usable volume-and-page/article locator; a title-only provider record is not release-ready metadata.

Preflight also writes `semantic_audit_queue.json`. It ranks a small set of high-risk cited passages across the manuscript and supplies the paragraph-linked papers and anchors as candidates. It deliberately leaves the selected `cited_paper_ids` and `evidence_ids` empty: choose the minimum supporting subset only after opening the linked source. Replace or extend the sample when the topic makes another claim more consequential. The queue prepares the existing audit; it is not another validator.

## 2. Semantic audit

Build the audit from the current topic and manuscript. Concentrate on statements where an error would materially change the review, such as numerical results, causal or mechanistic explanations, comparisons, broad generalizations, priority statements, recommendations, and topic-specific focal points. For a multi-paper synthesis, check whether each cited source supports the whole statement or only part of it, and narrow the wording when needed.

For each selected passage, compare its meaning with the linked evidence anchor and source. `text_span` must be an actual passage from the identified structured paragraph, and the cited papers and evidence IDs must already be linked to that paragraph. This keeps the existing semantic audit honest without adding another audit stage. Record the model judgment:

```json
{
  "model": "actual model name",
  "checks": [
    {
      "check_id": "sec2-p1-a1",
      "section_id": "sec2",
      "paragraph_id": "sec2-p1",
      "text_span": "Faithful manuscript passage being reviewed",
      "cited_paper_ids": ["P001", "P002"],
      "evidence_ids": ["P001-E01", "P002-E03"],
      "source_checked": true,
      "support_scope": "full",
      "epistemic_basis": "directly_observed | consistent_with | author_proposed | review_inference",
      "verdict": "supported | needs_revision | unsupported | removed",
      "comment": "Concise semantic judgment"
    }
  ],
  "changes_made": ["..."],
  "unresolved_blockers": []
}
```

Select only sources that support the exact `text_span`; use `support_scope: partial` with `needs_revision` when a source supports only part of the claim. Set `source_checked: true` after opening the recorded source location. Compare the manuscript's certainty with the source wording: `might`, `possible`, `consistent with`, and an author-proposed mechanism do not support `confirm`, `establish`, or a universal active species without additional evidence. Treat `first`, `only`, `general`, `mature`, `most powerful`, field-wide absence, and cross-system convergence as coverage-dependent claims; bound them to the retained corpus when external calibration is incomplete. `epistemic_basis` records this judgment for readers but does not create another validator gate.

Revise `05_final_audit/final_draft.md` until every audit item is `supported`, `removed`, or replaced by a newly checked revision. The semantic judgment comes from reading meaning and source context. The scanner verifies evidence IDs, paper ownership, the source-check declaration, and issue closure; it does not turn one sampled claim into a claim that an entire section was verified or require a change merely to prove that the audit was active.

## 3. Release scan

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
05_final_audit/content_audit_report.md
05_final_audit/format_audit_report.md
05_final_audit/final_draft.md
05_final_audit/final_remaining_issues.md
05_final_audit/release_report.md
```
