---
name: review-topic-paper-discovery
description: Start a review project, retrieve a high-recall candidate pool from the structured local library and optional external sources, and record a topic-driven relevance decision for every candidate.
---

# Review Topic Paper Discovery

Build a broad candidate pool, then produce a screened set that directly serves the review question. The user may screen in the web interface or delegate the decision to the agent.

Treat screening as construction of a literature portfolio, not a contest for a small core set. A paper may merit inclusion because it supplies direct evidence, a representative method, a comparison or limitation, a historical bridge, field orientation, or a declared coverage dimension. Exclude genuinely out-of-scope, duplicate, unusable, or misleading records; do not exclude a useful background paper merely because it cannot support the review's highest-risk claim.

## Topic contract

Use one topic contract as the source of truth. Do not retype a shortened contract in a run script. Complete `topic_contract.json`, or pass the structured Markdown topic file directly:

```json
{
  "topic": "...",
  "central_question": "...",
  "important_coverage": ["..."],
  "inclusion_criteria": ["..."],
  "exclusion_criteria": ["..."]
}
```

The criteria describe the current project. They may concern a material, method, population, outcome, period, evidence type, or any other topic-relevant dimension.

## Retrieval

Local retrieval uses the eight structured tag categories defined in `<review-root>/allene_classification_rules.py`:

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

Run local retrieval:

```bash
python skills/review-topic-paper-discovery/scripts/discover.py \
  --review-root . \
  --topic-contract-file <topic_input.md-or-json> \
  --project-id <project_id>
```

When invoking `--topic` directly, pass the retrieval query rather than the manuscript title. Explicit CLI values override matching fields loaded from `--topic-contract-file`.

Keyword expansion must follow actual topic signals. Do not add alternative materials, catalysts, populations, or methods merely because they share a generic word such as `catalysis` or `synthesis`. Candidate ranking combines matches across the topic contract and multiple keyword categories; it must not rank by the best single keyword alone.

When the topic contract explicitly excludes records because a named subject is absent, treat that subject as a retrieval prerequisite. The broader per-keyword results remain available for coverage, while screening receives the records that satisfy the stated prerequisite.

Repeat `--important-coverage`, `--inclusion-criterion`, and `--exclusion-criterion` as needed. With no provider flags, the command automatically runs lightweight Semantic Scholar and Crossref coverage. Use `--local-only` only when the task explicitly requires a bounded local/offline run. Provider flags may still select a specific external path:

```bash
python skills/review-topic-paper-discovery/scripts/discover.py \
  --review-root . \
  --topic "<review topic>" \
  --project-id <project_id> \
  --semantic-scholar-search \
  --web-search
```

Semantic Scholar supplies relevance-ranked metadata and open-access PDF locations; Crossref supplies DOI and publication metadata. Crossref components and supplementary-material records are filtered before ranking, so the paper count refers to article-like records rather than attached files. `--external-query-limit` defaults to six expanded keywords so agent-generated keyword expansion does not become dozens of API calls. `SEMANTIC_SCHOLAR_API_KEY` is optional, while SciAtlas still reads `SCIATLAS_API_BASE_URL` and `SCIATLAS_API_KEY` when `--sciatlas-search` is requested.

Describe provider activity from `web_results_by_keyword.json`: a rate limit remains an error even when another provider returns results. Requested providers, attempted/successful query counts, returned-record counts, retained-record counts, and provider errors remain distinct. A successful query with no retained topical result is `no_retained_results`, not an error, and failure sentinel rows do not enter the candidate set.

Before screening is finalized, use one or two close recent reviews or perspectives to calibrate recall when they are available. Check whether their framing and references expose a missing method family, seminal paper, or search term. Record the useful comparison and any known gap in `coverage_calibration.json`. This is an editorial coverage aid, not a completeness claim or another validator gate. If provider failure leaves the calibration weak, keep field-wide priority, absence, and generality claims explicitly bounded.

External metadata is for coverage discovery, not manuscript evidence. Results are matched against local DOI/title metadata and receive one promotion action in `external_ingest_plan.json`: `use_local`, `download_then_mineru`, or `locate_pdf`.

For selected open-access papers, one command performs the normal promotion path—bounded to three papers per run by default—without adding another validator. Repeat selectively when the coverage portfolio exposes a consequential gap; do not ingest papers merely to inflate a count:

```bash
python skills/review-topic-paper-discovery/scripts/ingest_external_papers.py \
  --review-root . \
  --project-id <project_id>
```

The command downloads only planned OA PDF URLs into `chem_papers/web-imports/`, parses each new PDF through the existing incremental MinerU skill, then appends managed metadata. After a new local `paper_id` is resolved, it is added to `selected_discovery_results.json` with an `uncertain` screening decision and any prior confirmation is reopened. Use repeated `--paper-key` to choose exact records or `--download-only` when parsing should be deferred. Only managed papers with a local `paper_id` and full-text source may support evidence anchors.

## Screening

For every local candidate, record:

```json
{
  "paper_id": "P001",
  "decision": "include | exclude | uncertain",
  "relevance_summary": "How this paper relates to the central question",
  "decision_basis": "The source information and project criterion used",
  "portfolio_intent_hint": "core | supporting | background | needs_reading",
  "citation_role_hints": ["method_example", "comparative_support", "context"],
  "coverage_tags": ["a declared topic dimension"]
}
```

The intent and citation-role fields are reading prompts and may change in the matrix stage. They keep useful context and comparison literature visible without lowering evidence depth for key claims. There is no target proportion or minimum reference count. After screening, inspect the retained role mix and important-coverage tags: if the set answers only the central mechanism or result question but cannot orient readers, compare methods, or show boundaries, reopen the most relevant candidates before shrinking the scope.

Store these rows in `screening_decisions`. Store only `include` papers in `local_papers`. Set `screening.status` to `confirmed` and `screening.decided_by` to `user` or `agent`. A delegated agent screens from the candidate title, abstract, structured tags, and source paths stored in `selected_discovery_results.json`. Open the linked source when the abstract is missing or the decision remains uncertain.

Validate the completed screening:

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
external_ingest_plan.json
combined_results_by_keyword.json
selected_discovery_results.json
discovery_report.md
human_check_state.json
screening_validation.json
external_ingest_receipt.json (after promotion is run)
coverage_calibration.json (when a review or seminal-paper calibration is performed)
```

Candidate count is adaptive. `--max-local-candidates` applies only when the user requests an explicit cap, and the cap is applied after aggregate topic-contract ranking rather than after a single-keyword match.
