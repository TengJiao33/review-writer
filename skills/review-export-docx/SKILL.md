---
name: review-export-docx
description: Convert a release-ready review Markdown manuscript into a consistently styled academic DOCX with deterministic chemistry scripts, headings, spacing, tables, figures, references, and structural QA.
---

# Export Review DOCX

Export only after the final release scan has zero blocking issues.

## Input Gate

Read:

```text
05_final_audit/final_draft.md
05_final_audit/format_scan.json
```

Stop when `format_scan.json.blocking_issues` is non-empty.

## Markdown Chemistry Conventions

Use explicit script markup when notation is ambiguous:

```markdown
CO_2_
H_2_O
sp^2^
S_N2_
10^-3^
$\ce{PdCl_2}$
```

The converter also recognizes Unicode subscripts/superscripts and conservatively formats common multi-element formulae such as `CO2`, `H2O`, and `PdCl2`, plus parenthesized coordination formulae such as `Ni(PCy3)2Cl2` and `Ni(cod)2`. Use explicit markup for locants, labels, oxidation states, and ambiguous notation.

## Deterministic Academic Style

The Python converter applies:

```text
US Letter; 1 inch margins
Times New Roman throughout
title 18 pt bold centered
body 12 pt left-aligned, 1.5 line spacing, 6 pt after
section heading 14 pt bold
subsection heading 12 pt bold
third-level heading 11 pt bold italic
abstract and keywords 11 pt
references and captions 10 pt single-spaced
inline figures with adjacent captions
fixed-width tables with cell margins
real Word numbering for lists and references
right-aligned footer page number
```

Do not rely on Word defaults or direct formatting as the primary style system.

## Export

Run:

```bash
python skills/review-export-docx/scripts/md2docx.py \
  --input review-projects/<project_id>/05_final_audit/final_draft.md \
  --output review-projects/<project_id>/05_final_audit/final_draft.docx
```

The command fails when stable citation tokens, editor paragraph markers, or missing images remain.

## Structural Audit

Run:

```bash
python skills/review-export-docx/scripts/audit_docx.py \
  --input review-projects/<project_id>/05_final_audit/final_draft.docx \
  --markdown review-projects/<project_id>/05_final_audit/final_draft.md \
  --output-json review-projects/<project_id>/05_final_audit/docx_audit.json
```

Stop on nonzero exit.

The structural audit also rejects a figure placed inside the Abstract block; figures belong with the section argument they support.

## One Visual QA Pass

Perform one visual pass after the structural audit; do not add a second release gate. Render the DOCX to page images and inspect every page for headings, body rhythm, chemical scripts, reference wrapping, figure-caption adjacency, tables, page breaks, and font substitution.

Use LibreOffice when it is available. On Windows, Microsoft Word is also a valid renderer: export the DOCX to PDF through Word automation or Word's Save as PDF command, then rasterize the PDF with `pdftoppm` or the available PDF rendering skill. Absence of LibreOffice alone is not a reason to mark rendering unavailable.

After page inspection, rerun the structural audit with `--render-qa passed`. Use `--render-qa unavailable` only after neither LibreOffice nor Word can render the document. The default `not_run` means the visual pass has not yet been performed; it is never inferred merely from executable discovery.

## Outputs

Write:

```text
05_final_audit/final_draft.docx
05_final_audit/docx_audit.json
```
