# Migration Map

This file records the migration boundary from the original Codex
`review-writer` workflow to QoderWork.

| Stage | Upstream skill | QoderWork status | Evidence | Missing dependency |
| --- | --- | --- | --- | --- |
| Paper parsing | `mineru-precise-parse-review-writer` | not tested | Not included in text-only smoke run. | MinerU token, raw PDFs, extracted sidecars. |
| Metadata preparation | `review-metadata-prep` | not tested | Smoke run used pre-existing metadata. | Metadata scripts and human review dashboard. |
| Topic and paper discovery | `review-topic-paper-discovery` | prompt_only | Smoke run used a fixed 5-paper sample. | Full local retrieval over the metadata library. |
| Matrix and outline | `review-literature-matrix-outline` | prompt_only | Smoke run produced a 5-paper literature matrix and two outline options. | Larger sample and workflow-file validation. |
| Section blueprint | `review-section-blueprint` | not tested | Smoke run selected an outline but did not produce `section_blueprint.json`. | Rule-pack enforcement and paragraph-level constraints. |
| Section drafting | `review-section-drafting-figure-picking` | prompt_only | Smoke run produced one text-only section. | Paragraph IDs, figure candidates, source figure inventory. |
| Figure redraw | `review-figure-style-redraw` | not tested | Images were intentionally skipped. | MinerU extracted images and image-edit API. |
| Draft merge | `review-draft-merge-polish` | not tested | No full draft merge was attempted. | Section files, citation aggregation, figure insertion. |
| Final audit | `review-final-audit-release` | not tested | No final audit scan was run. | Deterministic scan script and full draft. |
| Word export | `review-export-docx` | not tested | No Word export was generated. | `python-docx`, template, stable final Markdown. |

Status values:

```text
direct
prompt_only
external_script_needed
blocked
not_tested
```
