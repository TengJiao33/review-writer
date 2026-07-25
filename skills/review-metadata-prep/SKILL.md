---
name: review-metadata-prep
description: Register MinerU or repository full text in the managed paper library, extract bibliographic metadata, validate local paths, and repair paths after a repository move.
---

# Review Metadata Tools

Build or extend the managed library:

```bash
python skills/review-metadata-prep/scripts/prepare_metadata.py \
  --review-root . \
  --mineru-output mineru-outputs \
  --pdf-root chem_papers \
  --discover-from-pdf-root \
  --append-registry
```

Validate records and source paths:

```bash
python skills/review-metadata-prep/scripts/validate_metadata.py \
  --review-root .
```

Repair stored paths after moving the repository:

```bash
python skills/review-metadata-prep/scripts/remap_source_paths.py \
  --review-root . \
  --extract-archives \
  --write
```

Metadata extraction is fallible. Leave unavailable author, title, year,
journal, DOI, page, or article-number fields empty, then repair them from the
paper front matter or a reliable bibliographic record.

The legacy eight chemistry tags remain available for older local retrieval, but
they are optional enrichment and should not control a general-domain review.
Use LLM retagging only when those tags are genuinely useful:

```bash
python skills/review-metadata-prep/scripts/batch_llm_retag_metadata.py \
  --review-root . \
  --batch-size 3
```

Core outputs are `review-library/registry/papers.jsonl` and
`review-library/metadata/papers/<paper_id>.metadata.json`. Validation reports
describe the mechanical completeness of those records.
