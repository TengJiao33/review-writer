# Demo-002: Workflow Validation Task

Use this task to verify that QoderWork can read the upstream workflow files and
produce a migration-boundary report before generating another text-only sample.

## Required workflow files

Read these files from the repository before writing outputs:

```text
skills/技能工作流说明.md
skills/review-writing-orchestrator/SKILL.md
skills/review-topic-paper-discovery/SKILL.md
skills/review-literature-matrix-outline/SKILL.md
skills/review-section-blueprint/SKILL.md
skills/review-section-drafting-figure-picking/SKILL.md
skills/review-draft-merge-polish/SKILL.md
skills/review-final-audit-release/SKILL.md
skills/review-export-docx/SKILL.md
```

## Sample input

Use a local, uncommitted 5-paper sample containing:

```text
metadata/*.metadata.json
papers_md/*.md
sample_manifest.json
topic_input.md
```

Do not commit the sample Markdown files if they are large or derived from
private materials.

## Required outputs

Write outputs to a local uncommitted run directory:

```text
runs/demo-002/
```

Required files:

```text
00_read_files_report.md
01_workflow_migration_map.json
02_literature_matrix.json
03_outline_options.md
04_one_section_draft.md
05_migration_validation_report.md
```

## Validation questions

The final report must answer with evidence:

- Were the workflow files actually read?
- Was the 5-paper text loop completed?
- Which upstream stages were covered by this run?
- Which upstream stages were not covered?
- Which parts need external scripts, images, Word export, or human checks?
- What conclusions are not supported by this run?
