# QoderWork Adapter

This directory contains the public adaptation layer for running the
`review-writer` chemistry review workflow in QoderWork.

## Scope

Keep this directory lightweight and public-safe:

- QoderWork task prompts
- workflow migration maps
- small public manifests
- run summaries
- utility scripts that do not contain credentials

Do not commit:

- paper PDFs
- MinerU extracted outputs
- generated images
- Word or PDF deliverables
- API tokens
- netdisk links or extraction codes
- local absolute paths
- chat screenshots

## Current status

The first local QoderWork smoke run completed a 5-paper text-only loop:

```text
topic input
-> literature matrix
-> outline options
-> selected outline
-> one drafted section
-> run report
```

This shows that QoderWork can read a small prepared sample and produce staged
text outputs. It does not yet prove full migration of the original
`review-writer` workflow, because figure extraction/redraw, final audit,
Word/PDF export, dashboard interaction, and full-corpus processing were not
covered.

## Public branch convention

Adaptation work is kept on:

```text
qoderwork-adaptation
```

Upstream source remains:

```text
XuehaiWang/review-writer
```
