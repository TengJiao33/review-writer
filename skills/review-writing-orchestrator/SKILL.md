---
name: review-writing-orchestrator
description: Orchestrate an evidence-grounded review-writing workflow with adaptive discovery, lightweight planning, scholarly drafting, stable citations, deterministic merge, semantic audit, and styled DOCX export.
---

# Review Writing Orchestrator

Use after the local paper library metadata and MinerU outputs are available.

## Workflow

```text
1. review-topic-paper-discovery
2. review-literature-matrix-outline
3. review-section-blueprint
4. review-section-drafting-figure-picking
5. review-figure-style-redraw
6. review-draft-merge-polish
7. review-final-audit-release
8. review-export-docx
```

## Working Principle

```text
Discovery searches the local library and normally checks lightweight external sources, then records a topic-driven decision for every candidate.
External metadata remains coverage-only; selected OA PDFs enter the existing MinerU and metadata path before they can become evidence.
Reading notes and evidence anchors stay as concise as the source and writing task require.
The outline and blueprint identify the argument, evidence, and important coverage.
The central question and available evidence determine the manuscript organization.
Drafting uses stable [@Pxxx] citations in a lightweight structured merge envelope.
Merge deterministically assigns every [n] and generates References from the same mapping.
Final audit separates hard integrity failures from optional writing-quality suggestions.
DOCX export runs only after the release scan passes and applies deterministic academic styles.
```

Validators block evidence, citation, artifact, and release-integrity failures. They report length, section balance, comparison density, and figure use as editorial observations.

The Discovery relevance decision may be made by the user or delegated to the agent. Both routes use the topic contract and the same screening record. A local-only run must be explicit in the run record; otherwise use Semantic Scholar plus Crossref coverage. `external_ingest_plan.json` is an action queue, not another audit gate.

## Stage Validators

Run the validator associated with each stage. Revise the current artifact and rerun when it reports a blocker. Warnings do not prevent progression:

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

Revise prose and structured artifacts directly. Do not create ad hoc project-root repair scripts, edit validator reports to hide failures, or replace missing evidence with filler. Record material iterations in the run record.

Keep `review-projects/<project_id>/run_record.md` as the project-local execution record. Record the actual commands and material decisions, including an explicit local-only choice and a factual figure skip. Do not hand-author empty script outputs or mark later stages complete when an earlier stage is invalid.

Keep the project manifest descriptive rather than aspirational: record the provider response actually received, the files actually generated, and the command actually run. Set a run to `completed` only after the strict status command below exits successfully; do not infer completion from the presence of late-stage files alone.

## Status

```bash
python skills/review-writing-orchestrator/scripts/project_status.py \
  --review-root . \
  --project-id <project_id> \
  --require-complete
```

Omit `--require-complete` for an ordinary progress report. The strict form returns a non-zero exit code while any stage or the project run record is incomplete. The status script treats validation blockers, citation mismatches, unresolved evidence-integrity issues, unverified figure fidelity, missing DOCX visual QA, and upstream-stage failures as incomplete stages. Editorial warnings remain visible without blocking the workflow.
