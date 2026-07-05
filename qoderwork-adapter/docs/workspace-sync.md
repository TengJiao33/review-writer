# Workspace Sync Rules

This document defines how local QoderWork runs are synchronized with the public
fork.

## Directory Roles

The local QoderWork workspace is the runtime area. It may contain prepared
inputs, run outputs, logs, temporary files, and local samples.

The public `qoderwork-adapter/` directory is the collaboration record. It should
contain only public-safe adaptation material:

- task prompts
- migration maps
- run summaries
- public sample manifests
- utility scripts without credentials
- collaboration notes that do not expose private data

## Sync Rule

Do not copy a local run directory directly into GitHub.

After each local run, inspect the output and copy only the public-safe summary
or reusable task material into `qoderwork-adapter/`.

## Allowed In The Public Adapter

- QoderWork task templates
- workflow migration boundary records
- summaries of local runs
- sample manifests without paper full text
- scripts that do not contain credentials
- notes without local absolute paths

## Not Allowed In The Public Adapter

- paper PDFs
- full MinerU Markdown corpora
- MinerU extracted images or sidecar files
- generated figures
- Word or PDF deliverables
- API tokens, cookies, credentials, or account data
- netdisk links or extraction codes
- private Notion content
- chat screenshots, recordings, or raw transcripts
- local absolute paths
- full drafts with unverified claims

## Current Collaboration State

- Public fork: `TengJiao33/review-writer`
- Working branch: `qoderwork-adaptation`
- Public adapter directory: `qoderwork-adapter/`
- Collaborator invited: `kenqia`

## Evidence Boundary

The current public adapter records that a local 5-paper text-only QoderWork run
completed staged text outputs. It does not record or claim completion of full
workflow migration, figure extraction/redraw, full-corpus processing, final
audit, or Word/PDF export.
