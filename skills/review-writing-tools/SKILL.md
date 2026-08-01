---
name: review-writing-tools
description: Use a lightweight toolbox to search a managed paper library, inspect a Markdown chemistry review, and choose the next useful writing or visual action while keeping editorial judgment with the writer.
---

# Review Writing Tools

Write one canonical Markdown manuscript. Keep optional notes and helper scripts
inside the review project.

Let the topic and emerging argument shape the literature set. Use the initial
reading set to establish vocabulary, main approaches, and a useful structure,
then let drafting expose the next research questions. Before treating the
evidence base as mature, connect each central claim and major comparison to
direct full-text sources. Use categories to navigate the topic, not to infer
evidentiary depth.

A missing historical link, an unresolved disagreement, an unsupported
comparison, or a section carried mainly by an orientation review creates a
targeted search. Follow the question into primary studies and later developments,
then revise the claim or scope as the evidence requires. Treat further search as
having diminishing value when new targeted searches mostly repeat approaches
and evidence already understood.

Use roughly 40 genuinely relevant cited sources as a scale cue for a broad,
comprehensive chemistry review. When the bibliography is much smaller, look
again for thin method coverage, unsupported comparisons, missing historical
links, and representative developments. Keep the final number responsive to the
actual scope and evidence.

Use reviews to learn the vocabulary, history, and neighboring approaches.
Follow their references to the primary studies needed for specific methods and
comparisons, and follow later citations when the field has revised the original
picture. A paper belongs in the manuscript because it contributes to the
argument. Locally available papers may remain uncited.

Keep navigation lightweight. A few scratch lines may connect approaches to
direct full-text sources, but the manuscript itself should carry the resulting
synthesis. State material coverage limits briefly.

A comprehensive review normally contains a title, concise Abstract,
introduction, thematic synthesis, conclusion, and references. Adapt this shape
to the subject. Make the Abstract state the main conclusions and a material
remaining gap, not only list the sections.

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

The snapshot reports substantive word count, stable citations and local
full-text resolution, image paths, Markdown tables, missing Abstract or legacy
chemistry markup, and suspicious cited metadata.

The default snapshot omits a word target. If the user asks for a length
reference, or a mature draft appears seriously out of proportion to its
evidence, add `--include-word-advisory`. Use the result only after substantive
revision; do not draft toward its lower or upper number.

The inspector returns a non-zero exit code only for broken local mechanics such
as an unknown stable paper ID or a missing local image. Length, visual density,
table use, balance, and synthesis remain editorial observations.

## Writing boundary

Use tools to locate, copy, number, format, browse, and render material. Judge
claim support, visual value, synthesis quality, and page appearance from the
sources, manuscript, and rendered pages.

When evidence is thin, narrow the claim or retrieve more evidence. When a tool
has a defect, record the issue and make a transparent manual edit.

Use search results and abstracts to decide what to read. Base substantive
claims on full text opened in the current run. Prefer primary evidence for
specific experimental, measured, mechanistic, or computational claims. Earlier
summaries may guide navigation, then the source supplies the wording and limits
of the claim.

Organize around the questions and differences that matter to the reader.
Bring together papers that answer, extend, or contest the same question. Let
sections represent patterns in the literature rather than one paper at a time.

Use comparative labels such as “preferred,” “most general,” “broader,” or
“superior” only after comparing aligned evidence. Otherwise describe the
observed difference directly.

For fact-sensitive statements, re-open the most direct source and check the
identity of the studied system, preparation or operating conditions,
measurement basis, comparison basis, and source of the reported effect or
selectivity. Preserve the source's distinction among observation, control
experiment, calculation, author proposal, and review-level inference. Do this
while writing; do not create a proof file.

## Visual expression

Choose visual form while reading and drafting, not after the article is
finished. Browse source visuals when prose would force the reader to reconstruct
a structure, transformation, apparatus, spatial relationship, sequence,
measured trend, or comparison. Depending on the subject, useful evidence may
be a reaction Scheme, spectrum, chromatogram, micrograph, crystal structure,
phase diagram, apparatus, process flow, computed surface, or data plot.

Use source visuals for concrete evidence. Use a table when aligned values or
conditions are the point. An original integrative visual may summarize
cross-paper relationships with verified labels and citations when the model can
express them accurately. Do not ask the model to redraw detailed chemical
structures or reaction Schemes.

Once a lawful, useful source visual has been selected for a clear reader
question, carry it into the manuscript unless later reading shows that it is
unsuitable. Do not demote all selected visuals to optional enhancement at
export. Use a table when the reader benefits from seeing methods or cases side
by side and the compared items share a meaningful basis. Use prose to develop
mechanism, causation, and context. Let the argument determine whether a table
is useful and what it contains.

Do not set a figure quota. Reconsider a long, chemically dense stretch that
contains only prose, but keep it as prose when a visual would not improve
understanding. A visual earns its place by making an important relationship or
piece of evidence easier to grasp.
