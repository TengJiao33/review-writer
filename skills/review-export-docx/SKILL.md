---
name: review-export-docx
description: Convert review Markdown to styled academic DOCX, render that DOCX to PDF immediately, and inspect the real rendered pages.
---

# Export Review DOCX and PDF

Export whenever the manuscript is ready for layout review.

## DOCX

```bash
python skills/review-export-docx/scripts/md2docx.py \
  --input review-projects/<project_id>/deliverables/review.md \
  --output review-projects/<project_id>/deliverables/review.docx \
  --author "<author when known>" \
  --subject "Scholarly review manuscript" \
  --keywords "<topic keywords>"
```

The converter supports Markdown headings, tables, images, references, inline
math, chemical subscripts/superscripts, page numbers, and academic styles.
Figure, Scheme, Chart, and Table prefixes in image alt text become caption
styles. Markdown tables render as white three-line academic tables. Scheme
images render as compact centered displays, while ordinary figures may use
the full text width. Use explicit chemistry markup when notation is ambiguous:

```markdown
CO_2_
sp^2^
10^-3^
$\ce{PdCl_2}$
```

## PDF and page images

Immediately render the DOCX:

```bash
python skills/review-export-docx/scripts/render_docx.py \
  --input review-projects/<project_id>/deliverables/review.docx \
  --output-pdf review-projects/<project_id>/deliverables/review.pdf \
  --pages-dir review-projects/<project_id>/deliverables/rendered_pages \
  --report review-projects/<project_id>/deliverables/render_report.json
```

Render the PDF from the DOCX so the inspected pages match the editable
deliverable. Open the rendered page images and inspect every page at readable
zoom for clipping, blank figures, broken reaction schemes, wrong captions, font
substitution, table overflow, reference wrapping, and bad page breaks.

`audit_docx.py` is an optional structural diagnostic:

```bash
python skills/review-export-docx/scripts/audit_docx.py \
  --input review-projects/<project_id>/deliverables/review.docx \
  --markdown review-projects/<project_id>/deliverables/review.md \
  --output-json review-projects/<project_id>/deliverables/docx_structure.json
```

Render and structural reports record conversion details; page appearance still
requires inspection of the rendered images.
