---
name: review-source-figure-tools
description: Inventory figures extracted from managed papers and prepare source-provenance records for figures, charts, and reaction schemes that may be inserted into a review.
---

# Source Figure Tools

Use this skill when the review would benefit from a paper figure, chart, or
reaction scheme.

Build an inventory from the papers retained by discovery:

```bash
python skills/review-source-figure-tools/scripts/build_paper_figure_inventory.py \
  --review-root . \
  --project-id <project_id>
```

The default output is:

```text
review-projects/<project_id>/assets/paper_figure_inventory.json
```

Treat the inventory as a search aid: it may contain page fragments, text blocks,
blank crops, incomplete panels, tables, or publisher boilerplate. Before
insertion, open the source paper and inspect the complete figure, caption, panel
set, credit line, and readable asset.

For each chosen asset, create an `asset_manifest.json` row for the deterministic
insertion tool. A reused paper asset records:

```json
{
  "asset_id": "scheme-1",
  "kind": "scheme",
  "label": "Scheme 1",
  "path": "chosen/scheme-1.png",
  "caption": "Reaction pathways compared in the cited study.",
  "insert_marker": "<!-- insert:scheme-1 -->",
  "origin": "source_paper",
  "source_paper_id": "P123",
  "source_locator": "Scheme 3, page 7",
  "reuse_basis": "CC BY 4.0; figure credit line checked",
  "attribution": "Adapted from ... under CC BY 4.0"
}
```

Choose assets editorially after checking scientific fidelity and reuse rights;
the inventory supplies candidates and provenance details.

Reaction schemes use the same image insertion path as figures. Prefer a clean
crop of the specific reaction or source Scheme over a full multi-panel paper
figure. Set `kind: scheme` and an explicit `label`; the DOCX converter places
it as a compact, centered display between paragraphs. Keep the crop large
enough to read reagents, conditions, yields, and stereochemical labels.

Original route maps and comparison diagrams use `origin: original` and the
same insertion markers. Identify them as original in the caption and cite the
supporting papers in the surrounding text. They do not need source-paper reuse
fields.
