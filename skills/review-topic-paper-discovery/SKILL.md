---
name: review-topic-paper-discovery
description: Search the local library and scholarly providers for a review topic, locate lawful full text, download or import it, run MinerU when needed, and add the result to the managed local library.
---

# Topic Paper Discovery

Use this tool for the retrieval loop:

```text
topic query -> local and external candidates -> lawful full text
-> PDF download or repository import -> MinerU when needed -> local library
```

The model supplies the topic and decides relevance. The scripts handle provider
queries, deduplication, lawful source locations, download/import, parsing, and
library registration.

## Topic input

Use a short Markdown or JSON file containing the topic, central question,
important coverage, and optional inclusion/exclusion criteria. `focused` and
`comprehensive` describe the intended scope.

## Search

```bash
python skills/review-topic-paper-discovery/scripts/discover.py \
  --review-root . \
  --topic-contract-file <topic.md-or-json> \
  --project-id <project_id>
```

The default external routes are Crossref, Europe PMC, and deposited-reference
expansion. Semantic Scholar and SciAtlas are optional enrichments. Provider
routes run independently, and the report records failures without cancelling
successful routes.

Discovery writes a ranked local/external result set and
`external_ingest_plan.json`. Provider reports distinguish no relevant results
from provider failure. Use metadata and abstracts for screening, then consult
full text for material claims in the manuscript.

## Acquire and ingest

Import every located, usable open source:

```bash
python skills/review-topic-paper-discovery/scripts/ingest_external_papers.py \
  --review-root . \
  --project-id <project_id> \
  --all-available \
  --mineru-batch-size 10
```

The importer:

- validates downloaded PDFs;
- imports official repository JATS directly when available;
- runs MinerU for PDFs;
- retains repository-native figure assets and licence text;
- reconciles discovery metadata;
- promotes the source into the managed local library;
- records receipts so interrupted work can resume.

Receipts record the completed retrieval and ingestion actions. Assess relevance,
bibliographic accuracy, scientific support, and image reuse from the source
material.

Use `--paper-key` to ingest selected rows and `--download-only` to defer
parsing. If results are weak, adjust the topic query or coverage terms and
search again. Prioritize relevance over paper count.

## Selection

`selected_discovery_results.json` is a candidate list. The model may set
`keep: false` or keep its own reading notes. Select papers for a clear reason
and open their local full text before relying on them.
