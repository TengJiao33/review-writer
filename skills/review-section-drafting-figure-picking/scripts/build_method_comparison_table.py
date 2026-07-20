#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_FIELDS = [
    "substrate_class",
    "coupling_partner",
    "catalyst_system",
    "activation_mode",
    "conditions",
    "product_topology",
    "selectivity",
    "limitations",
]

FIELD_LABELS = {
    "method_family": "Method family",
    "substrate_class": "Substrate",
    "leaving_group": "Leaving group",
    "coupling_partner": "Partner",
    "catalyst_system": "Catalyst / ligand",
    "activation_mode": "Activation",
    "conditions": "Representative conditions",
    "product_topology": "Product",
    "scope": "Scope",
    "selectivity": "Selectivity",
    "limitations": "Limitations",
    "operational_notes": "Operational notes",
    "mechanistic_basis": "Mechanistic basis",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def escape_cell(value: Any) -> str:
    text = str(value or "—").replace("\n", " ").replace("|", "\\|")
    return " ".join(text.split())


def display_label(card: dict[str, Any]) -> str:
    value = str(card.get("method_family") or card.get("display_label") or card.get("title") or "Method").strip()
    return value if len(value) <= 90 else value[:87].rstrip() + "…"


def selected_fields(cards: list[dict[str, Any]], requested: list[str]) -> list[str]:
    unknown = [field for field in requested if field not in FIELD_LABELS]
    if unknown:
        raise SystemExit("Unknown method-card fields: " + ", ".join(unknown))
    return [field for field in requested if any(card.get(field) for card in cards)]


def run(args: argparse.Namespace) -> int:
    review_root = Path(args.review_root).resolve()
    project = review_root / "review-projects" / args.project_id
    cards_path = project / "01_matrix_outline" / "method_cards.json"
    if not cards_path.exists():
        raise SystemExit(f"method_cards.json not found: {cards_path}")
    payload = read_json(cards_path)
    cards = payload.get("method_cards") if isinstance(payload, dict) else None
    if not isinstance(cards, list):
        raise SystemExit("method_cards.json does not contain a method_cards list")
    wanted = set(args.paper_id or [])
    cards = [
        card
        for card in cards
        if isinstance(card, dict)
        and card.get("paper_id")
        and (not wanted or str(card.get("paper_id")) in wanted)
    ]
    fields = [item.strip() for item in args.fields.split(",") if item.strip()]
    fields = selected_fields(cards, fields)
    cards = [card for card in cards if any(card.get(field) for field in fields)]
    if not cards or not fields:
        raise SystemExit(
            "No comparison-ready method-card values were found. Reopen only the sources and fields needed for the reader's decision."
        )

    header = ["Method / source"] + [FIELD_LABELS[field] for field in fields]
    rows = []
    cells = []
    unverified = []
    for card in cards:
        paper_id = str(card["paper_id"])
        rows.append([f"{display_label(card)} [@{paper_id}]"] + [escape_cell(card.get(field)) for field in fields])
        evidence_map = card.get("field_evidence") if isinstance(card.get("field_evidence"), dict) else {}
        for field in fields:
            value = card.get(field)
            if not value:
                continue
            evidence_ids = [str(item) for item in evidence_map.get(field) or [] if str(item).strip()]
            cell = {
                "paper_id": paper_id,
                "field": field,
                "value": value,
                "evidence_ids": evidence_ids,
                "verification_status": "traceable" if evidence_ids else "source_check_required",
            }
            cells.append(cell)
            if not evidence_ids:
                unverified.append(f"{paper_id}:{field}")

    markdown = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    markdown.extend("| " + " | ".join(row) + " |" for row in rows)
    stage = project / "02_section_drafting"
    stage.mkdir(parents=True, exist_ok=True)
    table_path = stage / "method_comparison_table.md"
    manifest_path = stage / "method_comparison_table_manifest.json"
    table_path.write_text("\n".join(markdown) + "\n", encoding="utf-8")
    manifest = {
        "project_id": args.project_id,
        "created_at": utc_now(),
        "status": "verified" if not unverified else "source_check_required",
        "table_path": str(table_path),
        "paper_ids": [str(card["paper_id"]) for card in cards],
        "fields": fields,
        "cells": cells,
        "unverified_cells": unverified,
        "note": "Null fields remain em dashes and do not imply a negative result. Copy or adapt the table only after resolving selected cell provenance.",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {table_path} and {manifest_path}")
    if args.require_traceable and unverified:
        print("Cells requiring a source check:")
        for item in unverified:
            print(f"- {item}")
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an evidence-traceable method comparison table from selected method-card fields.")
    parser.add_argument("--review-root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--fields", default=",".join(DEFAULT_FIELDS))
    parser.add_argument("--paper-id", action="append", default=[])
    parser.add_argument("--require-traceable", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
