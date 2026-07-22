---
name: review-topic-paper-discovery
description: Start a review project, retrieve candidates from local and external sources, acquire lawful full text, and record topic-based screening decisions.
---

# Review Topic Paper Discovery

Build a candidate pool that covers the review question, then screen every local candidate. QoderWork may make the decisions from the stored sources; the user may review them in the interface.

Include papers that provide direct evidence, representative methods, comparisons, limitations, historical links, or field orientation. Exclude duplicates, unusable records, and material outside the declared scope.

## Topic contract

Keep the full project scope in one `topic_contract.json` or structured Markdown file:

```json
{
  "topic": "...",
  "review_profile": "focused | comprehensive",
  "central_question": "...",
  "important_coverage": ["..."],
  "inclusion_criteria": ["..."],
  "exclusion_criteria": ["..."]
}
```

Use `focused` for a deliberately bounded question and `comprehensive` for a broad field or process-chain review. The profile supplies depth expectations and risk signals; it does not prescribe the outline or force filler. QoderWork must not downgrade the profile or narrow the promised scope without explicit user approval.

Criteria may define materials, methods, populations, outcomes, periods, or evidence types. A subject named as mandatory in the exclusion criteria becomes a retrieval prerequisite.

## Retrieval

Run:

```bash
python skills/review-topic-paper-discovery/scripts/discover.py \
  --review-root . \
  --topic-contract-file <topic_input.md-or-json> \
  --project-id <project_id>
```

With `--topic`, pass a retrieval query. Explicit CLI values override the matching fields in the topic file.

Local retrieval uses these structured tags:

```text
product
substrate
catalyst_or_method
organometallic_partner
ligand_or_chiral_source
leaving_group
reaction_type
document_scope
```

Keyword expansion follows the topic contract. Ranking aggregates matches across the contract and keyword categories. Generic words such as `catalysis` or `synthesis` are insufficient grounds for adding a material or method.

The default external path uses Crossref and deposited-reference expansion. Add `--semantic-scholar-search` for Semantic Scholar enrichment, `--sciatlas-search` for a configured SciAtlas service, or `--local-only` for an explicitly bounded offline run. Provider status in `web_results_by_keyword.json` records attempted queries, returned and retained records, and errors separately.

Crossref supplies DOI metadata, licensed full-text locations, and deposited references. The search filters components, supplementary records, peer-review reports, decisions, author responses, and versioned copies before ranking. Reference expansion uses up to two close reviews or guidelines and retains up to 30 topic-relevant references by default. `--external-query-limit` defaults to six expanded keywords.

Use one or two close reviews or perspectives to check missing method families, seminal papers, and search terms. Record useful findings and known gaps in `coverage_calibration.json`. Bound field-wide claims when this comparison remains weak.

External records enter `external_ingest_plan.json` with one action:

```text
use_local
download_then_mineru
locate_pdf
```

## Full-text ingestion

Import the default batch of up to three planned papers:

```bash
python skills/review-topic-paper-discovery/scripts/ingest_external_papers.py \
  --review-root . \
  --project-id <project_id>
```

After inspecting the plan, import every row with a usable open source:

```bash
python skills/review-topic-paper-discovery/scripts/ingest_external_papers.py \
  --review-root . \
  --project-id <project_id> \
  --all-available \
  --mineru-batch-size 10
```

The importer accepts direct open PDFs and licensed publisher full-text pages. It validates PDF signatures, uses short deterministic filenames, reconciles DOI/title/year from discovery, and falls back to an official Europe PMC copy when available. Europe PMC JATS XML is retained with provenance-linked Markdown when its PDF endpoint returns a confirmation page.

Downloads are limited to planned lawful sources in `chem_papers/web-imports/`. Receipts are updated after each download; completed PDF, XML, Markdown, and metadata work is reused on rerun. Metadata preparation is bounded to the sources selected by this invocation, so importing new papers does not reprocess existing library records. Repeated `--paper-key` values select exact rows, and `--download-only` defers parsing. Each imported paper receives a local `paper_id`, returns to screening as `uncertain`, and reopens any previous confirmation.

Manuscript evidence requires a managed local paper with full text. Titles, abstracts, and external metadata support discovery and bounded background only.

## Screening

Record one row per local candidate:

```json
{
  "paper_id": "P001",
  "decision": "include | exclude | uncertain",
  "study_type": "primary_research | primary_dataset | methods_validation | systematic_review | review | perspective | standard | other",
  "relevance_summary": "Relation to the central question",
  "decision_basis": "Source information and project criterion",
  "portfolio_intent_hint": "core | supporting | background | needs_reading",
  "citation_role_hints": ["method_example", "comparative_support", "context"],
  "coverage_tags": ["declared topic dimension"]
}
```

Open the linked source when the abstract is absent or the decision is uncertain. Store all rows in `screening_decisions`, include only retained papers in `local_papers`, and set `screening.status` to `confirmed` with `screening.decided_by` equal to `user` or `agent`. Reopen screening when the retained set cannot orient the reader, support comparison, or show the important boundaries in the topic contract.

Do not stop retrieval because one convenient batch was acquired. After matrix reading, use the pre-writing quality report to make one explicit decision: continue, expand the evidence base, or propose a narrower scope. Depth counts are diagnostic signals. If a signal remains, only the user may approve continuing with the exception or narrower promise.

Validate:

```bash
python skills/review-topic-paper-discovery/scripts/validate_screening.py \
  --review-root . \
  --project-id <project_id>
```

## Outputs

Write under `review-projects/<project_id>/00_discovery/`:

```text
topic_input.md
topic_contract.json
keyword_set.draft.json
local_results_by_keyword.json
web_results_by_keyword.json
reference_expansion.json
external_ingest_plan.json
combined_results_by_keyword.json
selected_discovery_results.json
discovery_report.md
human_check_state.json
screening_validation.json
external_ingest_receipt.json
coverage_calibration.json
```

Candidate count follows the topic. `--max-local-candidates` applies an explicit cap after aggregate ranking.
