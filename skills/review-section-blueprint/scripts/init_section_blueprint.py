#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STOPWORDS = {
    "and",
    "the",
    "from",
    "with",
    "for",
    "into",
    "via",
    "section",
    "introduction",
    "conclusion",
    "outlook",
    "synthesis",
    "review",
    "chemistry",
    "allene",
    "allenes",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def tokens(text: str) -> set[str]:
    return {
        t.lower()
        for t in re.findall(r"[A-Za-z][A-Za-z0-9'′-]{2,}", text or "")
        if t.lower() not in STOPWORDS
    }


def value_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(value_text(v) for v in value)
    if isinstance(value, dict):
        return " ".join(value_text(v) for v in value.values())
    return str(value)


def paper_value(paper: dict[str, Any], key: str) -> str:
    aliases = {
        "product": ["product", "product_class"],
        "substrate": ["substrate", "substrate_class"],
        "catalyst_or_method": ["catalyst_or_method", "catalyst_logic", "activation_mode"],
        "reaction_type": ["reaction_type", "activation_mode"],
        "limitation": ["limitation", "main_limitation"],
        "selectivity": ["selectivity", "selectivity_mode"],
    }
    for candidate in aliases.get(key, [key]):
        value = paper.get(candidate)
        if value:
            return str(value)
    structured = paper.get("structured_tags")
    if isinstance(structured, dict):
        value = structured.get(key)
        if value:
            return str(value)
    evidence = paper.get("evidence_card")
    if isinstance(evidence, dict):
        evidence_aliases = {
            "product": ["product_classes"],
            "substrate": ["substrate_classes"],
            "catalyst_or_method": ["catalyst_system"],
            "reaction_type": ["reaction_summary"],
            "limitation": ["scope_boundaries"],
            "selectivity": ["selectivity"],
        }
        for candidate in evidence_aliases.get(key, [key]):
            value = evidence.get(candidate)
            if value:
                return value_text(value)
    return ""


def build_coverage_contract(topic: str, papers: list[dict[str, Any]], axes: list[str]) -> dict[str, Any]:
    topic_low = (topic or "").lower()
    blobs = {
        str(paper.get("paper_id")): value_text(paper).lower()
        for paper in papers
        if paper.get("paper_id")
    }
    term_groups = {
        "substrate_class": {
            "propargylic alcohols": ["propargylic alcohol", "alcohols"],
            "propargylic acetates": ["propargylic acetate", "acetates"],
            "propargylic carbonates": ["propargylic carbonate", "carbonates"],
            "propargylic halides": ["propargylic halide", "propargyl halide", "halides"],
            "propargylic sulfonates": ["mesylate", "sulfonate", "tosylate"],
            "propargylic amines": ["propargylic amine", "propargyl amine"],
        },
        "catalyst_or_method": {
            "palladium catalysis": ["palladium", "pd-catal"],
            "copper catalysis": ["copper", "cu-catal"],
            "nickel catalysis": ["nickel", "ni-catal"],
            "organocatalysis": ["organocatal", "chiral phosphoric", "brønsted acid"],
            "photoredox catalysis": ["photoredox", "photocatal"],
            "electrochemistry": ["electrochemical", "electroreduct", "electrocatal"],
            "enzymatic catalysis": ["enzyme", "enzymatic", "lipase"],
        },
        "review_question": {
            "regioselectivity": ["regioselect"],
            "stereoselectivity": ["stereoselect", "enantioselect", "axial chirality"],
            "mechanistic pathways": ["mechanism", "mechanistic"],
            "scope and limitations": ["scope", "limitation", "functional-group tolerance"],
        },
    }
    dimensions = []
    for dimension_name, terms in term_groups.items():
        items = []
        for label, signals in terms.items():
            required = any(signal in topic_low for signal in signals)
            if dimension_name == "review_question" and label in {
                "regioselectivity",
                "stereoselectivity",
                "mechanistic pathways",
                "scope and limitations",
            }:
                required = required or any(label.split()[0] in str(axis).lower() for axis in axes)
            covered_by = [
                paper_id
                for paper_id, blob in blobs.items()
                if any(signal in blob for signal in signals)
            ]
            if required or covered_by:
                items.append({"name": label, "required": required, "covered_by": covered_by})
        if items:
            dimensions.append({"name": dimension_name, "items": items})
    return {
        "suggested_manuscript_words": 5000,
        "dimensions": dimensions,
    }


def parse_outline_sections(text: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    in_outline = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.match(r"^#{1,3}\s+Outline\b", line, flags=re.I):
            in_outline = True
            continue
        if in_outline and re.match(r"^#{1,3}\s+", line):
            break
        match = re.match(r"^(?:[-*]\s*)?(\d+)[.)]\s+(.+?)\s*$", line)
        if match:
            title = match.group(2).strip()
            if title:
                sections.append({"section_id": f"sec{len(sections) + 1}", "title": title})
    if sections:
        return sections

    for raw in text.splitlines():
        line = raw.strip()
        match = re.match(r"^(?:[-*]\s*)?(\d+)[.)]\s+(.+?)\s*$", line)
        if match:
            title = match.group(2).strip()
            sections.append({"section_id": f"sec{len(sections) + 1}", "title": title})
    return sections


def load_matrix(path: Path) -> tuple[str, list[dict[str, Any]], list[str]]:
    data = read_json(path)
    if isinstance(data, dict):
        topic = str(data.get("review_topic") or data.get("topic") or "")
        papers = data.get("papers") if isinstance(data.get("papers"), list) else []
        axes = data.get("comparison_axes") if isinstance(data.get("comparison_axes"), list) else []
        return topic, [p for p in papers if isinstance(p, dict)], [str(a) for a in axes]
    if isinstance(data, list):
        return "", [p for p in data if isinstance(p, dict)], []
    return "", [], []


def load_notes(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    data = read_json(path)
    if not isinstance(data, list):
        return {}
    return {str(row.get("paper_id")): row for row in data if isinstance(row, dict) and row.get("paper_id")}


def select_rule_pack(skill_root: Path, topic: str) -> tuple[str, str]:
    manifest_path = skill_root / "references" / "rule_packs.json"
    try:
        manifest = read_json(manifest_path)
    except Exception:
        return "allenation", "references/rule_packs/allenation"
    default = str(manifest.get("default_rule_pack") or "allenation")
    packs = manifest.get("rule_packs") if isinstance(manifest, dict) else {}
    if not isinstance(packs, dict):
        return default, f"references/rule_packs/{default}"
    topic_low = (topic or "").lower()
    for name, cfg in packs.items():
        if not isinstance(cfg, dict):
            continue
        signals = cfg.get("topic_signals")
        if isinstance(signals, list) and any(str(signal).lower() in topic_low for signal in signals):
            return str(name), str(cfg.get("path") or f"references/rule_packs/{name}")
    cfg = packs.get(default)
    if isinstance(cfg, dict):
        return default, str(cfg.get("path") or f"references/rule_packs/{default}")
    return default, f"references/rule_packs/{default}"


def paper_blob(paper: dict[str, Any], note: dict[str, Any] | None) -> str:
    fields = [
        "title",
        "substrate",
        "reaction_type",
        "product",
        "catalyst_or_method",
        "selectivity",
        "limitation",
        "role_after_reading",
        "review_topic_relevance",
    ]
    blob = " ".join(paper_value(paper, k) or value_text(paper.get(k)) for k in fields)
    if note:
        blob += " " + value_text(note.get("why_relevant"))
        blob += " " + value_text(note.get("key_evidence"))
        blob += " " + value_text(note.get("limitations"))
    return blob


def score_paper(section_title: str, paper: dict[str, Any], note: dict[str, Any] | None) -> int:
    section_tokens = tokens(section_title)
    blob_tokens = tokens(paper_blob(paper, note))
    score = len(section_tokens & blob_tokens) * 3
    relevance = str(paper.get("review_topic_relevance") or "").lower()
    role = str(paper.get("role_after_reading") or "").lower()
    if relevance == "high":
        score += 2
    if role == "core":
        score += 2
    if role == "supporting":
        score += 1
    return score


def select_papers(section_title: str, papers: list[dict[str, Any]], notes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    scored = []
    for paper in papers:
        pid = str(paper.get("paper_id") or "")
        if not pid:
            continue
        score = score_paper(section_title, paper, notes.get(pid))
        if score > 0:
            scored.append((score, pid, paper))
    scored.sort(key=lambda row: (-row[0], row[1]))
    selected = [paper for _, _, paper in scored[:8]]
    if not selected:
        selected = [
            p
            for p in papers
            if str(p.get("review_topic_relevance") or "").lower() == "high"
            or str(p.get("role_after_reading") or "").lower() == "core"
        ][:6]
    return selected


def infer_logic(title: str) -> str:
    low = title.lower()
    if any(w in low for w in ["radical", "photoredox", "cross-electrophile", "reductive"]):
        return "mechanistic_pathway"
    if any(w in low for w in ["carbonate", "ester", "alcohol", "bromide", "phosphate", "sulfide", "derivative"]):
        return "precursor_class"
    if any(w in low for w in ["stereo", "enantio", "chiral", "chirality", "selectivity"]):
        return "stereochemical_control"
    if any(w in low for w in ["application", "target", "useful"]):
        return "application"
    if any(w in low for w in ["outlook", "challenge", "conclusion"]):
        return "outlook"
    return "reaction_type"


def target_depth(title: str, selected_count: int) -> tuple[int, int]:
    low = title.lower()
    if any(word in low for word in ["introduction", "background"]):
        return 4, 650
    if any(word in low for word in ["conclusion", "outlook", "future"]):
        return 4, 700
    if selected_count >= 6:
        return 6, 1250
    return 5, 1000


def infer_claim_type(title: str, index: int) -> str:
    low = title.lower()
    if index == 0 and any(w in low for w in ["foundational", "classical", "introduction"]):
        return "foundation"
    if any(w in low for w in ["mechanism", "radical", "photoredox"]):
        return "mechanism"
    if any(w in low for w in ["scope", "functionalized", "classes"]):
        return "scope"
    if any(w in low for w in ["challenge", "outlook", "limitation"]):
        return "limitation"
    return ["foundation", "extension", "contrast", "limitation"][min(index, 3)]


def common_values(papers: list[dict[str, Any]], key: str, limit: int = 3) -> list[str]:
    values: list[str] = []
    for paper in papers:
        raw = paper_value(paper, key).strip()
        if raw:
            values.append(raw)
    counts = Counter(values)
    return [value for value, _ in counts.most_common(limit)]


def join_values(values: list[str], fallback: str) -> str:
    if not values:
        return fallback
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + f", and {values[-1]}"


def section_thesis(title: str, selected: list[dict[str, Any]], dominant_logic: str) -> str:
    substrates = join_values(common_values(selected, "substrate"), "the assigned precursor classes")
    activations = join_values(common_values(selected, "reaction_type"), "the assigned reaction types")
    products = join_values(common_values(selected, "product"), "the target allene classes")
    low = title.lower()
    if "introduction" in low:
        return f"Frame the review around how propargylic alcohols and derivatives access {products}, emphasizing why precursor activation mode and substitution pattern define the field."
    if "outlook" in low or "challenge" in low or "conclusion" in low:
        return f"Synthesize the remaining limits across {substrates}, especially where {activations} still leave gaps in scope, selectivity, mechanism, or practicality."
    if dominant_logic == "mechanistic_pathway":
        return f"Compare how {activations} redirect propargylic precursors toward {products}, while separating supported mechanisms from proposed rationales."
    if dominant_logic == "stereochemical_control":
        return f"Use the assigned papers to distinguish chirality transfer, catalyst control, and selectivity erosion in the synthesis of {products}."
    if dominant_logic == "precursor_class":
        return f"Show how {substrates} function as distinct allene precursors rather than interchangeable leaving-group variants, with {activations} setting the main comparison axis."
    return f"Explain how {activations} convert {substrates} into {products}, and define the scope and limitation boundaries that matter for this section."


def review_problem(title: str, selected: list[dict[str, Any]], dominant_logic: str) -> str:
    axes = {
        "mechanistic_pathway": "Which mechanistic manifold changes the accessible allene products, and how strong is the evidence for that manifold?",
        "stereochemical_control": "Which stereochemical control mode is operating, and where does the method lose fidelity or generality?",
        "precursor_class": "What does this precursor class enable that adjacent propargylic substrates do not, and what boundary remains?",
        "application": "What practical or synthetic value is demonstrated beyond method development?",
        "outlook": "Which limitations are common across the assigned methods, and which are specific to one precursor or catalyst class?",
    }
    return axes.get(dominant_logic, "Which activation mode, substrate class, or product class best explains the papers grouped in this section?")


def normalize_role(raw: str) -> str:
    low = (raw or "").lower()
    if "core" in low:
        return "strategic extension"
    if "support" in low:
        return "comparison source"
    if "background" in low:
        return "foundational method"
    return "comparison source"


def claim_from_papers(section_id: str, title: str, idx: int, papers: list[dict[str, Any]], axes: list[str]) -> dict[str, Any]:
    claim_type = infer_claim_type(title, idx)
    paper_refs = []
    for paper in papers[:4]:
        pid = str(paper.get("paper_id"))
        use_for = [
            k.replace("_", " ")
            for k in ["substrate", "reaction_type", "product", "selectivity", "limitation"]
            if paper_value(paper, k)
        ][:3]
        caveat = paper_value(paper, "limitation")
        paper_refs.append(
            {
                "paper_id": pid,
                "role": normalize_role(str(paper.get("role_after_reading") or "")),
                "use_for": use_for,
                "caveat": caveat,
            }
        )
    axis_values = [a.replace("_", " ") for a in axes[:3]] or ["substrate class", "activation mode", "scope boundary"]
    substrates = join_values(common_values(papers, "substrate", 2), "the assigned substrate classes")
    activations = join_values(common_values(papers, "reaction_type", 2), "the assigned reaction types")
    products = join_values(common_values(papers, "product", 2), "the assigned allene products")
    limitations = common_values(papers, "limitation", 2)
    limitation_text = join_values(limitations, "the stated substrate and condition boundaries")
    selectivity = join_values(common_values(papers, "selectivity", 2), "the reported selectivity pattern")
    if claim_type == "foundation":
        claim = f"Establish {activations} of {substrates} as the baseline logic for accessing {products}, while naming the selectivity problem that makes the section review-relevant."
    elif claim_type == "extension":
        claim = f"Show how the assigned papers extend the baseline toward {products}, especially through changes in precursor class, catalyst logic, or coupling partner."
    elif claim_type == "contrast":
        claim = f"Contrast {activations} by how they control {selectivity}, rather than treating the papers as equivalent allene syntheses."
    elif claim_type == "limitation":
        claim = f"Qualify the section's apparent generality by preserving the main boundaries: {limitation_text}."
    elif claim_type == "mechanism":
        claim = f"Separate mechanism-supported claims from proposed rationales when discussing {activations} and their conversion of {substrates} to {products}."
    elif claim_type == "scope":
        claim = f"Compress scope around product and substrate classes: {substrates} leading to {products}, with boundaries stated explicitly."
    else:
        claim = f"Use the assigned papers to develop a bounded review claim about {title}, with explicit scope and mechanism limits."
    return {
        "claim_id": f"{section_id}_c{idx + 1}",
        "claim": claim,
        "claim_type": claim_type,
        "supporting_papers": paper_refs,
        "logic_relationship": {
            "foundation": "foundation_to_extension",
            "extension": "limitation_repair",
            "contrast": "contrast",
            "limitation": "scope_boundary",
            "mechanism": "mechanistic_partition",
            "scope": "scope_boundary",
        }.get(claim_type, "contrast"),
        "comparison_axes": axis_values,
        "evidence_strength": "needs verification",
        "wording_constraints": [
            "Name the substrate or product class when making a scope claim.",
            "State proposed mechanisms as proposed unless the assigned paper reports direct evidence.",
            "Avoid one-paper-one-paragraph narration.",
        ],
    }


def build_section(section: dict[str, str], papers: list[dict[str, Any]], axes: list[str], notes: dict[str, dict[str, Any]], prev_title: str, next_title: str) -> dict[str, Any]:
    title = section["title"]
    selected = select_papers(title, papers, notes)
    paper_ids = [str(p.get("paper_id")) for p in selected if p.get("paper_id")]
    claim_count = 2 if title.lower() in {"introduction", "conclusion"} else min(4, max(2, len(selected) // 2 or 2))
    claims = []
    for idx in range(claim_count):
        claim_papers = selected[idx * 2 : idx * 2 + 4] or selected[:4]
        claims.append(claim_from_papers(section["section_id"], title, idx, claim_papers, axes))
    dominant_logic = infer_logic(title)
    target_paragraphs, target_words = target_depth(title, len(selected))
    title_low = title.lower()
    substantive = not any(term in title_low for term in ("introduction", "conclusion", "outlook", "abstract"))
    paragraph_types = ["context", "synthesis"]
    if substantive:
        paragraph_types = ["comparison", "mechanism", "limitation_or_gap", "synthesis"]
    elif "conclusion" in title_low or "outlook" in title_low:
        paragraph_types = ["synthesis", "limitation_or_gap", "outlook"]
    return {
        "section_id": section["section_id"],
        "title": title,
        "section_thesis": section_thesis(title, selected, dominant_logic),
        "review_problem": review_problem(title, selected, dominant_logic),
        "target_paragraphs": target_paragraphs,
        "target_words": target_words,
        "dominant_logic": dominant_logic,
        "major_papers": paper_ids,
        "review_claims": claims,
        "paragraph_types_suggested": paragraph_types,
        "figure_or_table_needs": [
            {
                "type": "scheme" if infer_logic(title) != "outlook" else "comparison table",
                "purpose": "Show the reaction logic, representative precursor/product classes, or comparison axis that anchors this section.",
                "candidate_papers": paper_ids[:3],
            }
        ],
        "depth_requirements": [
            "Use the evidence map as a guide and reopen Markdown/PDF evidence for high-risk details.",
            "Choose the section depth and paragraph pattern that best serves the argument.",
            "Do not add prose solely to satisfy a word or paragraph target.",
        ],
        "section_transition": {
            "from_previous": f"Connect from {prev_title}." if prev_title else "Open the review scope and organizing logic.",
            "to_next": f"Set up {next_title}." if next_title else "Close with unresolved limitations and future directions.",
        },
        "avoid_patterns": [
            "Do not summarize papers in chronological order unless chronology is the section logic.",
            "Do not collapse distinct activation modes into generic substitution language.",
            "Do not use broad/generic scope adjectives without substrate boundaries.",
        ],
    }


def write_plan(path: Path, blueprint: dict[str, Any]) -> None:
    lines = [
        "# Section Writing Plan",
        "",
        f"- Project ID: `{blueprint['project_id']}`",
        f"- Review topic: {blueprint.get('review_topic') or ''}",
        f"- Rule pack: `{blueprint.get('rule_pack')}` ({blueprint.get('rule_pack_path')})",
        f"- Created at: {blueprint.get('created_at')}",
        "",
    ]
    for section in blueprint["sections"]:
        lines.extend(
            [
                f"## {section['section_id']}. {section['title']}",
                "",
                f"Thesis: {section['section_thesis']}",
                "",
                f"Major papers: {', '.join(section['major_papers']) or 'TBD'}",
                "",
                "Claims:",
            ]
        )
        for claim in section["review_claims"]:
            papers = ", ".join(p["paper_id"] for p in claim["supporting_papers"])
            lines.append(f"- `{claim['claim_id']}` {claim['claim']} Papers: {papers or 'TBD'}")
        lines.extend(["", f"Figure/table need: {section['figure_or_table_needs'][0]['type']} - {section['figure_or_table_needs'][0]['purpose']}", ""])
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    review_root = Path(args.review_root).resolve()
    skill_root = Path(__file__).resolve().parents[1]
    project_dir = review_root / "review-projects" / args.project_id
    stage_dir = project_dir / "01_matrix_outline"
    selected_outline = stage_dir / "selected_outline.md"
    matrix_path = stage_dir / "literature_matrix.json"
    notes_path = stage_dir / "paper_reading_notes.json"
    if not selected_outline.exists():
        raise SystemExit(f"selected_outline.md not found: {selected_outline}")
    if not matrix_path.exists():
        raise SystemExit(f"literature_matrix.json not found: {matrix_path}")

    outline_text = read_text(selected_outline)
    sections = parse_outline_sections(outline_text)
    if not sections:
        raise SystemExit("No numbered outline sections found in selected_outline.md")

    topic, papers, axes = load_matrix(matrix_path)
    rule_pack, rule_pack_path = select_rule_pack(skill_root, topic or outline_text)
    notes = load_notes(notes_path)
    blueprint_sections = []
    for idx, section in enumerate(sections):
        prev_title = sections[idx - 1]["title"] if idx > 0 else ""
        next_title = sections[idx + 1]["title"] if idx + 1 < len(sections) else ""
        blueprint_sections.append(build_section(section, papers, axes, notes, prev_title, next_title))

    blueprint = {
        "project_id": args.project_id,
        "review_topic": topic,
        "outline_source": str(selected_outline),
        "matrix_source": str(matrix_path),
        "rule_pack": rule_pack,
        "rule_pack_path": rule_pack_path,
        "created_at": utc_now(),
        "status": "draft_initialization_needs_semantic_review",
        "coverage_contract": build_coverage_contract(topic, papers, axes),
        "sections": blueprint_sections,
    }
    out_json = stage_dir / "section_blueprint.json"
    out_md = stage_dir / "section_writing_plan.md"
    write_json(out_json, blueprint)
    write_plan(out_md, blueprint)
    print(f"Wrote {out_json}")
    print(f"Wrote {out_md}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize section_blueprint.json from selected outline and literature matrix.")
    parser.add_argument("--review-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--project-id", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
