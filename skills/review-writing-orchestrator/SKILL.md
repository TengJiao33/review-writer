---
name: review-writing-orchestrator
description: Orchestrate an evidence-grounded review-writing workflow from discovery through audited DOCX export.
---

# Review Writing Orchestrator

Use this skill after the local paper library and parsed full texts are available.

## Workflow model

```text
evidence loop   <->   manuscript + visual loop   <->   release loop
 discovery/read       argument units/draft/assets      challenge/render/export
```

The named skills remain execution tools, not one-way stages. Reopen discovery
whenever a planned argument lacks evidence. Reopen the argument map whenever a
table, figure, contradiction, or source changes what the review should explain.
Return release defects to the source artifact instead of repairing only the
exported manuscript.

Use this diagnosis when choosing the next useful move or after a material change:

```bash
python skills/review-writing-orchestrator/scripts/review_cycle.py \
  --review-root . --project-id <project_id> --write
```

`review_state.json` combines scattered reports into evidence, manuscript/visual,
and release concerns. Treat its active loop as a suggestion: inspect the actual
article and choose the change with the greatest effect. The file is a generated
view, not an approval gate or a mandatory route through the work.

## Authoritative state

- `00_discovery/topic_contract.json` fixes the promised scope and cannot be
  narrowed by a file written later in the run.
- `01_matrix_outline/literature_matrix.json` is the evidence ledger. Paper
  metadata, titles, and abstracts do not become full-text evidence by being
  copied into it.
- `01_matrix_outline/section_blueprint.json`, `02_section_drafting/manuscript.md`,
  its compiled `section_drafts.json`, and the visual manifests form one article
  plan. A table or figure is complete
  only when its reader job, evidence, verification, and manuscript placement
  remain connected.
- `review_state.json` and Markdown/CSV reports are generated views. Never edit
  them to change the outcome.

Do not create experiment-specific Python programs to manufacture screening,
matrix, draft, audit, or run-history artifacts. Edit the canonical JSON/Markdown
artifacts directly and use repository scripts only for deterministic extraction,
validation, assembly, rendering, and reporting. If a recurring authoring action
needs code, improve the shared workflow instead of adding a project-local helper.

## Operating principles

- Discovery combines the local library with external metadata and lawful full-text locations. An external paper becomes evidence only after local full-text ingestion.
- The matrix separates evidence depth from citation purpose and links material claims to source excerpts.
- The outline and blueprint organize the argument around the topic question and available evidence.
- Drafting uses stable `[@Pxxx]` citations and paragraph-level evidence links.
- Figures and comparison tables are selected for a defined reader need and verified before merge.
- Merge assigns numeric citations and builds the reference list. Final audit checks meaning, integrity, and release format before DOCX export.

Validators enforce evidence, citation, artifact, and release integrity. Review-profile expectations expose unusually thin evidence, prose, comparison material, or visuals as a small number of holistic quality risks. A comprehensive review also has one coarse final-product floor to prevent scale regression; there are no per-section quotas. Do not game either diagnostics or the product floor with filler. Resolve the underlying weakness before release. If the user wants a smaller product, declare a new `focused` topic contract before the next run instead of writing an exception inside the run being judged.

Run `build_review_portfolio.py` after matrix validation and `init_review_visual_plan.py` before drafting. Use their output to find weak coverage, thin comparisons, and useful synthesis opportunities.

Run the quality diagnostic with `--phase prewrite` before sustained drafting and
with `--phase release` before export. Its paper, depth, comparison, and visual
signals are prompts for judgment. They do not require a model-authored approval
file and do not become hard quotas. Fix real weaknesses, narrow the declared
scope when that is the honest answer, and never manufacture prose, citations,
tables, or figures merely to move a metric.

QoderWork may make screening decisions from the topic contract and stored source material; the user may also review them in the interface. Record who decided. Unless the run is explicitly local-only, use Crossref coverage and the configured optional providers. Execute the actionable rows in `external_ingest_plan.json` when they fill a relevant evidence gap.

## Execution tools

Use the relevant deterministic tool when its input changes, and fix blockers in
the source artifact. These commands do not decide what to write:

```text
discovery     validate_screening.py
matrix        validate_evidence_matrix.py
blueprint     validate_blueprint.py
drafting      validate_section_drafts.py
merge         merge_review.py
preflight     final_audit_scan.py --phase preflight
release       final_audit_scan.py --phase release
DOCX          audit_docx.py
```

For a useful reproducibility trail, material commands may be run through the
execution recorder:

```bash
python skills/review-writing-orchestrator/scripts/run_and_record.py \
  --review-root . --project-id <project_id> --stage <stage_id> \
  --note "material decision when useful" -- \
  python <stage-script> <arguments>
```

The recorder appends `run_events.jsonl`, regenerates `run_record.md`, stores
timestamps and exit codes, and redacts common secret flags. This history helps
debugging; missing receipts do not make a sound article incomplete. Never write
or replay events merely to satisfy status output.

## Release completion

Use `review_cycle.py` for normal progress. Check core deliverable status when the
article is approaching release:

```bash
python skills/review-writing-orchestrator/scripts/project_status.py \
  --review-root . \
  --project-id <project_id>
```

Require a complete run with:

```bash
python skills/review-writing-orchestrator/scripts/project_status.py \
  --review-root . \
  --project-id <project_id> \
  --require-complete
```

The strict check covers core validation, evidence and citation integrity,
selected-asset verification, and DOCX-to-PDF visual QA. Generated Markdown
reports and command history are not completion criteria. After it succeeds,
finalize the experiment manifest:

```bash
python skills/review-writing-orchestrator/scripts/finalize_run.py \
  --review-root . --project-id <project_id> \
  --manifest <experiment-manifest.json>
```

The finalizer records the strict status command, exit code, finish time, and unresolved conditions. It writes `completed` only after a successful strict check.
