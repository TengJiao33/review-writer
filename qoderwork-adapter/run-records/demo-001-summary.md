# Demo-001 Summary

Date: 2026-07-05

## Purpose

Check whether QoderWork can read a prepared 5-paper local sample and produce a
minimal text-only review workflow output.

## Inputs

- 5 paper metadata JSON files: `P001` to `P005`
- 5 corresponding MinerU Markdown files
- one topic file
- one QoderWork task file

## Outputs Observed

The run produced:

```text
00_topic_input.md
01_literature_matrix.json
02_outline_options.md
03_selected_outline.md
04_one_section_draft.md
05_run_report.md
```

## Evidence

- `01_literature_matrix.json` parsed successfully.
- The matrix contained exactly `P001`, `P002`, `P003`, `P004`, and `P005`.
- No paper IDs outside the five-paper sample were observed.
- No image, Word, or PDF output was generated.
- The one drafted section used `P001`, `P002`, and `P004`, matching the selected
  copper-catalysis section.

## Boundary

This run supports only a narrow claim: QoderWork can complete a prepared
5-paper text-only loop.

It does not support full workflow migration. The run did not cover MinerU
parsing, metadata preparation, local retrieval over the full library, section
blueprint JSON generation, figure extraction/redraw, full draft merge, final
audit, or Word/PDF export.
