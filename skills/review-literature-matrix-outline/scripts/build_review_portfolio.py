#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


METHOD_FIELDS = (
    "study_design",
    "subject_or_substrate",
    "intervention_or_method",
    "comparator",
    "conditions_or_context",
    "outcome_or_metric",
    "main_result",
    "scope",
    "limitations",
    "operational_notes",
    "mechanistic_basis",
)

ALIASES = {
    "study_design": ("study_design", "design", "paper_type", "study_type"),
    "subject_or_substrate": (
        "subject_or_substrate",
        "substrate_class",
        "substrate",
        "substrate_classes",
        "population",
        "material",
    ),
    "intervention_or_method": (
        "intervention_or_method",
        "method_family",
        "method",
        "reaction_type",
        "reaction_summary",
        "catalyst_system",
        "catalyst_or_method",
    ),
    "comparator": ("comparator", "control", "baseline", "coupling_partner"),
    "conditions_or_context": (
        "conditions_or_context",
        "conditions",
        "representative_conditions",
        "setting",
        "activation_mode",
    ),
    "outcome_or_metric": (
        "outcome_or_metric",
        "outcome",
        "metric",
        "endpoint",
        "selectivity",
        "product_topology",
        "product_class",
    ),
    "main_result": ("main_result", "result", "effect", "quantitative_result"),
    "scope": ("scope", "scope_summary", "scope_boundaries"),
    "limitations": ("limitations", "limitation", "main_limitation", "scope_boundaries"),
    "operational_notes": ("operational_notes", "practical_notes"),
    "mechanistic_basis": ("mechanistic_basis", "mechanism", "mechanistic_evidence"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def text_value(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, list):
        joined = "; ".join(str(item).strip() for item in value if str(item).strip())
        return joined or None
    if isinstance(value, dict):
        joined = "; ".join(
            f"{key}: {text}"
            for key, raw in value.items()
            if (text := text_value(raw))
        )
        return joined or None
    return str(value).strip() or None


def matrix_rows(payload: Any) -> tuple[str, list[dict[str, Any]]]:
    if isinstance(payload, dict):
        topic = str(payload.get("review_topic") or payload.get("topic") or "")
        rows = payload.get("papers")
        return topic, [row for row in rows or [] if isinstance(row, dict)]
    if isinstance(payload, list):
        return "", [row for row in payload if isinstance(row, dict)]
    return "", []


def nested_sources(row: dict[str, Any]) -> list[dict[str, Any]]:
    sources = [row]
    for key in ("method_card", "structured_tags", "evidence_card"):
        value = row.get(key)
        if isinstance(value, dict):
            sources.append(value)
    return sources


def field_value(row: dict[str, Any], field: str) -> str | None:
    for source in nested_sources(row):
        for alias in ALIASES[field]:
            value = text_value(source.get(alias))
            if value:
                return value
    return None


def field_evidence_ids(row: dict[str, Any], field: str) -> list[str]:
    """Return explicitly recorded evidence for one method-card field.

    Do not infer provenance from a paper-level anchor list: a populated field is
    comparison-ready only when the reviewer records which anchor supports it.
    """
    for source in nested_sources(row):
        for key in ("method_field_evidence", "field_evidence"):
            mapping = source.get(key)
            if not isinstance(mapping, dict):
                continue
            raw = mapping.get(field)
            if isinstance(raw, str):
                values = [item.strip() for item in re.split(r"[,;]", raw) if item.strip()]
            elif isinstance(raw, list):
                values = [str(item).strip() for item in raw if str(item).strip()]
            else:
                values = []
            if values:
                return list(dict.fromkeys(values))
    return []


def portfolio_role(row: dict[str, Any]) -> str:
    role = str(row.get("portfolio_role") or row.get("role_after_reading") or "background").lower()
    if role == "support":
        role = "supporting"
    return role if role in {"core", "supporting", "background", "excluded"} else "background"


def citation_roles(row: dict[str, Any], role: str) -> list[str]:
    raw = row.get("citation_roles")
    if isinstance(raw, str):
        values = [item.strip() for item in re.split(r"[,;]", raw) if item.strip()]
    elif isinstance(raw, list):
        values = [str(item).strip() for item in raw if str(item).strip()]
    else:
        defaults = {
            "core": ["core_evidence"],
            "supporting": ["comparative_support"],
            "background": ["context"],
            "excluded": ["excluded"],
        }
        values = defaults[role]
    return list(dict.fromkeys(values))


def evidence_ids(row: dict[str, Any]) -> list[str]:
    anchors = row.get("evidence_anchors")
    if not isinstance(anchors, list):
        return []
    return [
        str(anchor.get("evidence_id"))
        for anchor in anchors
        if isinstance(anchor, dict) and anchor.get("evidence_id")
    ]


def source_levels(row: dict[str, Any]) -> list[str]:
    anchors = row.get("evidence_anchors")
    if not isinstance(anchors, list):
        return []
    return sorted(
        {
            str(anchor.get("source_level"))
            for anchor in anchors
            if isinstance(anchor, dict) and anchor.get("source_level")
        }
    )


def build_method_card(row: dict[str, Any], role: str, roles: list[str]) -> dict[str, Any]:
    card = {
        "paper_id": str(row.get("paper_id") or ""),
        "title": str(row.get("title") or ""),
        "display_label": str(row.get("method_label") or row.get("short_label") or row.get("title") or ""),
        "portfolio_role": role,
        "citation_roles": roles,
    }
    for field in METHOD_FIELDS:
        card[field] = field_value(row, field)
    card["field_evidence"] = {
        field: field_evidence_ids(row, field)
        for field in METHOD_FIELDS
        if card[field]
    }
    card["evidence_ids"] = evidence_ids(row)
    card["populated_fields"] = [field for field in METHOD_FIELDS if card[field]]
    card["missing_fields"] = [field for field in METHOD_FIELDS if not card[field]]
    if not card["populated_fields"]:
        card["recording_status"] = "unreviewed_for_comparison"
    elif any(not card["field_evidence"].get(field) for field in card["populated_fields"]):
        card["recording_status"] = "values_need_field_provenance"
    else:
        card["recording_status"] = "recorded_with_field_provenance"
    return card


def editorial_issue_rows(
    role_counts: Counter[str],
    citation_counts: Counter[str],
    method_cards: list[dict[str, Any]],
    ledger: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a decision queue for gaps that prevent comparison-ready synthesis."""
    issues: list[dict[str, Any]] = []
    if not role_counts.get("supporting") and not role_counts.get("background"):
        issues.append(
            {
                "decision_id": "PORT-ROLE-MIX",
                "question": "Does an all-core portfolio give readers enough historical, comparative, and boundary context?",
                "observed_condition": "No supporting or background paper is recorded.",
                "available_responses": [
                    "address_with_sources",
                    "narrow_scope",
                    "accept_with_reader_reason",
                    "not_applicable",
                ],
            }
        )
    empty_cards = [card["paper_id"] for card in method_cards if not card["populated_fields"]]
    provenance_cards = [
        card["paper_id"]
        for card in method_cards
        if card["populated_fields"]
        and any(not card["field_evidence"].get(field) for field in card["populated_fields"])
    ]
    if empty_cards:
        issues.append(
            {
                "decision_id": "PORT-METHOD-CARDS-EMPTY",
                "question": "Which method-choice fields are actually needed for this manuscript, and should those sources be reopened?",
                "observed_condition": "Method cards with no comparison fields: " + ", ".join(empty_cards),
                "available_responses": [
                    "deepen_selected_fields",
                    "exclude_from_comparison",
                    "accept_with_reader_reason",
                    "not_applicable",
                ],
            }
        )
    if provenance_cards:
        issues.append(
            {
                "decision_id": "PORT-METHOD-FIELD-PROVENANCE",
                "question": "Are method-card values used for prose or tables linked to the exact evidence anchors that support them?",
                "observed_condition": "Cards with populated values but incomplete field provenance: " + ", ".join(provenance_cards),
                "available_responses": [
                    "add_field_provenance",
                    "remove_untraced_values",
                    "accept_with_reader_reason",
                    "not_applicable",
                ],
            }
        )
    attention = [str(item.get("coverage_id")) for item in ledger if item.get("status") in {"thin", "unmapped"}]
    if attention:
        issues.append(
            {
                "decision_id": "PORT-COVERAGE-ATTENTION",
                "question": "Should thin declared coverage be strengthened, explicitly bounded, or removed from the review promise?",
                "observed_condition": "Thin or unmapped coverage items: " + ", ".join(attention),
                "available_responses": [
                    "address_with_sources",
                    "narrow_scope",
                    "accept_with_reader_reason",
                    "not_applicable",
                ],
            }
        )
    if not any(role in citation_counts for role in ("historical_bridge", "comparative_support", "limitation")):
        issues.append(
            {
                "decision_id": "PORT-CITATION-JOBS",
                "question": "Does the citation set do more than enumerate methods?",
                "observed_condition": "No historical_bridge, comparative_support, or limitation citation role is recorded.",
                "available_responses": [
                    "assign_existing_sources",
                    "address_with_sources",
                    "accept_with_reader_reason",
                    "not_applicable",
                ],
            }
        )
    return issues


def merge_editorial_review(path: Path, project_id: str, issues: list[dict[str, Any]]) -> dict[str, Any]:
    existing = read_json(path) if path.exists() else {}
    old_rows = existing.get("decisions") if isinstance(existing, dict) else []
    old_by_id = {
        str(row.get("decision_id")): row
        for row in old_rows or []
        if isinstance(row, dict) and row.get("decision_id")
    }
    decisions = []
    for issue in issues:
        old = old_by_id.get(issue["decision_id"], {})
        decisions.append(
            {
                **issue,
                "status": str(old.get("status") or "pending"),
                "decision": str(old.get("decision") or ""),
                "rationale": str(old.get("rationale") or ""),
                "actions": old.get("actions") if isinstance(old.get("actions"), list) else [],
            }
        )
    pending = [row["decision_id"] for row in decisions if row["status"] != "resolved"]
    return {
        "project_id": project_id,
        "updated_at": utc_now(),
        "purpose": "Resolve reader-facing portfolio gaps before the pre-writing quality gate.",
        "allowed_statuses": ["pending", "resolved"],
        "status": "pending" if pending else "resolved",
        "pending_decision_ids": pending,
        "decisions": decisions,
    }


def topic_coverage_items(topic_contract: Any) -> list[dict[str, Any]]:
    if not isinstance(topic_contract, dict):
        return []
    raw_items: list[Any] = []
    for key in ("important_coverage", "coverage_dimensions", "priority_dimensions", "comparison_axes"):
        value = topic_contract.get(key)
        if isinstance(value, list):
            raw_items.extend(value)
    scope = topic_contract.get("scope")
    if isinstance(scope, dict):
        for key in ("include", "must_cover", "priorities"):
            value = scope.get(key)
            if isinstance(value, list):
                raw_items.extend(value)
    items = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_items, start=1):
        if isinstance(raw, dict):
            label = str(raw.get("name") or raw.get("label") or raw.get("dimension") or "").strip()
            rationale = text_value(raw.get("reason") or raw.get("rationale"))
        else:
            label = str(raw).strip()
            rationale = None
        key = label.lower()
        if not label or key in seen:
            continue
        seen.add(key)
        items.append({"coverage_id": f"COV-{index:02d}", "label": label, "rationale": rationale})
    return items


def coverage_tokens(label: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}|[\u4e00-\u9fff]{2,}", label)
        if token.lower() not in {"and", "the", "with", "from", "review", "研究", "方法"}
    }


def build_coverage_ledger(items: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    paper_blobs = {
        str(row.get("paper_id")): json.dumps(row, ensure_ascii=False).lower()
        for row in rows
        if row.get("paper_id") and portfolio_role(row) != "excluded"
    }
    ledger = []
    for item in items:
        signals = coverage_tokens(item["label"])
        paper_ids = [pid for pid, blob in paper_blobs.items() if signals and any(sig in blob for sig in signals)]
        status = "mapped" if len(paper_ids) >= 2 else "thin" if paper_ids else "unmapped"
        ledger.append(
            {
                **item,
                "paper_ids": paper_ids,
                "status": status,
                "editorial_note": (
                    "Use this mapping as a reading prompt; verify semantic fit before drafting."
                    if paper_ids
                    else "Consider a bounded scope statement, another source, or an explicit omission."
                ),
            }
        )
    return ledger


def report_markdown(
    project_id: str,
    topic: str,
    role_counts: Counter[str],
    citation_counts: Counter[str],
    method_cards: list[dict[str, Any]],
    ledger: list[dict[str, Any]],
) -> str:
    sparse_cards = [card for card in method_cards if len(card["missing_fields"]) >= len(METHOD_FIELDS) // 2]
    coverage_attention = [item for item in ledger if item["status"] != "mapped"]
    lines = [
        "# Review Literature Portfolio",
        "",
        f"- Project: `{project_id}`",
        f"- Topic: {topic or 'not recorded'}",
        f"- Papers represented: {sum(role_counts.values())}",
        f"- Method cards: {len(method_cards)}",
        "",
        "## Portfolio roles",
        "",
    ]
    lines.extend(f"- {name}: {count}" for name, count in sorted(role_counts.items()))
    lines.extend(["", "## Citation roles", ""])
    lines.extend(f"- {name}: {count}" for name, count in sorted(citation_counts.items()))
    lines.extend(["", "## Editorial issues to resolve before the pre-writing quality gate", ""])
    if sparse_cards:
        lines.append(
            f"- {len(sparse_cards)} method cards are still sparse; deepen only fields needed for comparison, method choice, limitations, or reproducibility."
        )
    if coverage_attention:
        lines.append(
            f"- {len(coverage_attention)} declared coverage items are thin or unmapped; narrow the scope, add sources, or explain the omission."
        )
    if not role_counts.get("background"):
        lines.append("- No background papers are marked; consider whether readers need a bounded historical or conceptual bridge.")
    if not any(role in citation_counts for role in ("method_example", "comparative_support")):
        lines.append("- Citation roles do not yet expose method examples or comparative support; add them where they would improve navigation.")
    if lines[-1] == "":
        lines.append("- No obvious portfolio-level opportunity was detected; rely on close reading and section-level judgment.")
    lines.extend(
        [
            "",
            "Missing fields must remain null rather than being inferred from titles or generic domain knowledge. The pre-writing quality gate requires enough evidence-traceable cards for the selected review profile.",
            "",
        ]
    )
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    review_root = Path(args.review_root).resolve()
    project = review_root / "review-projects" / args.project_id
    stage = project / "01_matrix_outline"
    matrix_path = stage / "literature_matrix.json"
    if not matrix_path.exists():
        raise SystemExit(f"literature_matrix.json not found: {matrix_path}")
    topic, rows = matrix_rows(read_json(matrix_path))
    topic_path = project / "00_discovery" / "topic_contract.json"
    topic_contract = read_json(topic_path) if topic_path.exists() else {}
    discovery_path = project / "00_discovery" / "selected_discovery_results.json"
    discovery = read_json(discovery_path) if discovery_path.exists() else {}
    decision_rows = discovery.get("screening_decisions") if isinstance(discovery, dict) else []
    decisions = {
        str(row.get("paper_id")): row
        for row in decision_rows or []
        if isinstance(row, dict) and row.get("paper_id")
    }
    enriched_rows = []
    for row in rows:
        enriched = dict(row)
        screening = decisions.get(str(row.get("paper_id") or ""), {})
        if not enriched.get("citation_roles") and screening.get("citation_role_hints"):
            enriched["citation_roles"] = screening["citation_role_hints"]
        if not enriched.get("coverage_tags") and screening.get("coverage_tags"):
            enriched["coverage_tags"] = screening["coverage_tags"]
        if screening.get("portfolio_intent_hint"):
            enriched["screening_portfolio_intent_hint"] = screening["portfolio_intent_hint"]
        enriched_rows.append(enriched)
    rows = enriched_rows

    entries = []
    cards = []
    role_counts: Counter[str] = Counter()
    citation_counts: Counter[str] = Counter()
    for row in rows:
        role = portfolio_role(row)
        roles = citation_roles(row, role)
        role_counts[role] += 1
        citation_counts.update(roles)
        entry = {
            "paper_id": str(row.get("paper_id") or ""),
            "title": str(row.get("title") or ""),
            "portfolio_role": role,
            "screening_portfolio_intent_hint": text_value(row.get("screening_portfolio_intent_hint")),
            "citation_roles": roles,
            "chronology_role": text_value(row.get("chronology_role")),
            "coverage_tags": row.get("coverage_tags") if isinstance(row.get("coverage_tags"), list) else [],
            "evidence_ids": evidence_ids(row),
            "source_levels": source_levels(row),
        }
        entries.append(entry)
        if role != "excluded":
            cards.append(build_method_card(row, role, roles))

    ledger = build_coverage_ledger(topic_coverage_items(topic_contract), rows)
    common = {
        "project_id": args.project_id,
        "review_topic": topic,
        "created_at": utc_now(),
        "editorial_status": "advisory_not_a_release_gate",
    }
    write_json(
        stage / "literature_portfolio.json",
        {**common, "role_counts": dict(role_counts), "citation_role_counts": dict(citation_counts), "papers": entries},
    )
    write_json(stage / "method_cards.json", {**common, "method_cards": cards})
    write_json(stage / "coverage_ledger.json", {**common, "coverage_items": ledger})
    review_path = stage / "portfolio_editorial_review.json"
    write_json(
        review_path,
        merge_editorial_review(
            review_path,
            args.project_id,
            editorial_issue_rows(role_counts, citation_counts, cards, ledger),
        ),
    )
    (stage / "portfolio_report.md").write_text(
        report_markdown(args.project_id, topic, role_counts, citation_counts, cards, ledger),
        encoding="utf-8",
    )
    print(
        f"Wrote literature portfolio, {len(cards)} method cards, {len(ledger)} coverage items, "
        f"and an editorial decision queue to {stage}"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build advisory literature roles, method cards, and a coverage ledger.")
    parser.add_argument("--review-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--project-id", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
