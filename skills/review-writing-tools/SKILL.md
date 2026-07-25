---
name: review-writing-tools
description: Use a lightweight toolbox to search a managed paper library, inspect a Markdown review, and choose the next useful writing action while keeping editorial judgment with the writer.
---

# Review Writing Tools

Write the review in one canonical Markdown manuscript. Use notes, outlines, or
comparison tables whenever they help the writing.

Do not choose a paper count in advance. Use enough relevant full-text sources
to cover the main approaches, important differences, and representative
developments in the stated scope. If an obvious route is still missing, keep
searching; otherwise start writing. Briefly state material coverage limits in
the manuscript or handoff instead of creating a separate sufficiency record.

## Available tools

Search managed metadata and full text:

```bash
python skills/review-writing-tools/scripts/search_library.py \
  --review-root . \
  --query "reaction mechanism selectivity limitation"
```

Inspect a manuscript without gating it:

```bash
python skills/review-writing-tools/scripts/inspect_review.py \
  --review-root . \
  --input review-projects/<project_id>/manuscript.md \
  --profile comprehensive \
  --output review-projects/<project_id>/review_snapshot.json
```

The snapshot reports:

- substantive word count;
- stable paper citations and whether they resolve locally;
- how many cited papers have local full text;
- local image paths and Markdown tables;
- an advisory word range derived from the number of cited papers with usable
  local full text.

Word ranges are suggestions, not pass/fail thresholds. For a comprehensive
review the center is `1500 + 200 * usable_cited_sources`, bounded to
4,000-12,000 words; the reported range is 80-120% of that center. Focused
reviews use `1200 + 160 * usable_cited_sources`, bounded to 2,500-8,000 words.

The inspector returns a non-zero exit code only for broken local mechanics such
as an unknown stable paper ID or a missing local image. Short prose, few
figures, few tables, and an imbalanced review remain editorial observations.

## Writing boundary

Use the tools to locate, count, copy, number, format, and render material. Judge
claim support, figure reuse, synthesis quality, and page appearance from the
papers, assets, manuscript, and rendered pages themselves.

When evidence is thin, narrow the claim or retrieve more evidence. When a tool
has a defect, record the issue and make a transparent manual edit.

For reaction-specific statements, re-open the primary full text and check the
reagents, conditions, starting-material chirality, and whether stereocontrol
comes from the substrate or catalyst. Do this as part of writing; do not create
a separate proof file.

For a substantive review, normally include an original synthesis visual when
it clarifies the literature—for example, a route map, mechanism taxonomy, or
method-selection diagram. Keep it evidence-based and label it as original;
do not add a decorative diagram merely to increase the figure count.
