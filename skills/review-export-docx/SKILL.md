---
name: review-export-docx
description: Convert a released Markdown review into styled academic DOCX and PDF deliverables, then verify their structure and rendered pages.
---

# Export Review DOCX and PDF

Export after the final release scan reports no blocking issues.

## Inputs

```text
05_final_audit/final_draft.md
05_final_audit/format_scan.json
```

## Chemistry markup

Use explicit scripts when notation is ambiguous:

```markdown
CO_2_
H_2_O
sp^2^
S_N2_
10^-3^
$\ce{PdCl_2}$
```

The converter also handles Unicode scripts and common formulae such as `CO2`, `H2O`, `PdCl2`, `Ni(PCy3)2Cl2`, and `Ni(cod)2`. Use explicit markup for locants, labels, oxidation states, and ambiguous notation.

## Document style

The converter applies:

```text
US Letter; 1 inch margins
Times New Roman throughout
title 18 pt bold centered
body 12 pt, 1.5 line spacing, 6 pt after
section heading 14 pt bold
subsection heading 12 pt bold
third-level heading 11 pt bold italic
abstract and keywords 11 pt
references and captions 10 pt single-spaced
inline figures with adjacent captions
fixed-width tables with cell margins
wide-table continuation blocks with the identifying column repeated
Word numbering for lists and references
right-aligned footer page number
clean document metadata
```

## Export and structural audit

Run:

```bash
python skills/review-export-docx/scripts/md2docx.py \
  --input review-projects/<project_id>/05_final_audit/final_draft.md \
  --output review-projects/<project_id>/05_final_audit/final_draft.docx \
  --author "<author when known>" \
  --subject "Scholarly review manuscript" \
  --keywords "<topic keywords>"
```

The converter stops on stable citation tokens, editor paragraph markers, or missing images.

Audit the DOCX:

```bash
python skills/review-export-docx/scripts/audit_docx.py \
  --input review-projects/<project_id>/05_final_audit/final_draft.docx \
  --markdown review-projects/<project_id>/05_final_audit/final_draft.md \
  --output-json review-projects/<project_id>/05_final_audit/docx_audit.json
```

Resolve every structural error, including a figure placed inside the Abstract.

## Visual QA

`final_draft.pdf` must be rendered from the final `final_draft.docx`; do not
build a separate PDF from Markdown or LaTeX. This keeps the inspected PDF tied
to the deliverable the user will edit. Render the DOCX and inspect every page:

```bash
python skills/review-export-docx/scripts/render_docx.py \
  --input review-projects/<project_id>/05_final_audit/final_draft.docx \
  --output-pdf review-projects/<project_id>/05_final_audit/final_draft.pdf \
  --pages-dir review-projects/<project_id>/05_final_audit/rendered_pages \
  --report review-projects/<project_id>/05_final_audit/render_qa_report.json
```

Open the actual page images at readable zoom and check headings, body rhythm,
chemical scripts, reference wrapping, figure-caption adjacency, source
attribution, tables, page breaks, and font substitution. Do not create or run a
helper that merely marks all pages inspected.

After the first render, create a concise inspection JSON from the pages actually
viewed. Use the page hashes written in `render_qa_report.json`:

```json
{"pages": [{"page_number": 1, "page_sha256": "...", "verdict": "passed", "observation": "Title, abstract, margins, and first heading are intact; no clipping is visible."}]}
```

Rerun the render command with `--inspection-file <inspection.json>`. Inline
`--inspected-pages all` and a single global “passed” note are rejected. If any
page is `needs_revision`, fix the canonical manuscript or export input,
rerender, and inspect the changed page set again.

Finally rerun `audit_docx.py` with `--render-qa passed`. Use `--render-qa unavailable` only when neither LibreOffice nor Microsoft Word can render the document. Completion requires `render_qa_report.json` with `inspection_status: passed`.

## Outputs

```text
05_final_audit/final_draft.docx
05_final_audit/docx_audit.json
05_final_audit/final_draft.pdf
05_final_audit/rendered_pages/
05_final_audit/render_qa_report.json
```
