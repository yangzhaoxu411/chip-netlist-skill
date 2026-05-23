#!/usr/bin/env python3
"""Strict Accuracy Mode evidence ledger and claim validation."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


STRICT_CHIP_CLAIM_TYPES = {
    "pin_function",
    "pin_state",
    "configuration",
    "parameter",
    "threshold",
    "formula",
    "rating",
    "recommended_wiring",
}
ACTIVE_REF_PREFIXES = ("U", "IC", "Q", "D", "F", "L")


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return default or {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default or {}


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_part(value: Any) -> str:
    """Normalize a part identifier for conservative file/fact matching."""
    text = str(value or "").upper()
    return re.sub(r"[^A-Z0-9]+", "", text)


def ref_prefix(ref: str) -> str:
    match = re.match(r"([A-Za-z]+)", ref or "")
    return match.group(1).upper() if match else ""


def is_active_ref(ref: str) -> bool:
    return ref_prefix(ref) in ACTIVE_REF_PREFIXES


def _fact_index(facts_dir: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    if not facts_dir.exists():
        return index
    for path in sorted(facts_dir.glob("*.json")):
        facts = load_json(path)
        keys = {normalize_part(path.stem), normalize_part(facts.get("part"))}
        for key in keys:
            if key:
                index.setdefault(key, path)
    return index


def _find_fact_path(ref: str, comp: dict[str, Any], facts_index: dict[str, Path]) -> Path | None:
    candidates = [
        comp.get("part"),
        comp.get("manufacturer_part"),
        comp.get("canonical_name"),
        ref,
    ]
    for candidate in candidates:
        key = normalize_part(candidate)
        if key and key in facts_index:
            return facts_index[key]
    return None


def build_evidence_ledger(workdir: Path) -> dict[str, Any]:
    """Build a compact index of project and datasheet evidence availability."""
    enriched = load_json(workdir / "enriched.json", {"components": {}})
    facts_index = _fact_index(workdir / "datasheet_facts")
    components: dict[str, Any] = {}

    for ref, comp in sorted(enriched.get("components", {}).items()):
        fact_path = _find_fact_path(ref, comp, facts_index)
        facts = load_json(fact_path) if fact_path else {}
        pin_table = facts.get("pin_table") or comp.get("pin_table") or []
        formulas = facts.get("formulas") or comp.get("formulas") or []
        components[ref] = {
            "ref": ref,
            "part": comp.get("part") or comp.get("manufacturer_part") or comp.get("canonical_name"),
            "manufacturer_part": comp.get("manufacturer_part"),
            "canonical_name": comp.get("canonical_name"),
            "datasheet_status": comp.get("datasheet_status", "unknown"),
            "datasheet_url": comp.get("datasheet_url"),
            "datasheet_local": comp.get("datasheet_local"),
            "datasheet_facts_path": str(fact_path) if fact_path else None,
            "has_datasheet_facts": fact_path is not None and bool(pin_table or formulas or facts.get("recommended") or facts.get("abs_max")),
            "pin_count": len(pin_table),
            "formula_count": len(formulas),
            "source_file": facts.get("source_file"),
        }

    return {
        "schema": "chip-netlist-evidence-ledger-v1",
        "workdir": str(workdir),
        "strict_policy": {
            "datasheet_required_for_chip_claims": True,
            "reject_uncited_chip_claims": True,
        },
        "components": components,
    }


def claim_needs_datasheet(claim: dict[str, Any]) -> bool:
    claim_type = str(claim.get("claim_type", "")).lower()
    if claim_type in STRICT_CHIP_CLAIM_TYPES:
        return True
    targets = [str(t) for t in claim.get("targets", [])]
    return any(is_active_ref(target.split(".")[0]) for target in targets)


def _matching_datasheet_evidence(
    claim: dict[str, Any],
    ledger: dict[str, Any],
) -> list[dict[str, Any]]:
    components = ledger.get("components", {})
    evidence = claim.get("datasheet_evidence", []) or []
    matches: list[dict[str, Any]] = []
    for item in evidence:
        ref = str(item.get("ref") or "").split(".")[0]
        if not ref:
            continue
        comp = components.get(ref)
        if not comp:
            continue
        if comp.get("has_datasheet_facts"):
            matches.append(item)
    return matches


def validate_single_claim(claim: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    """Validate one claim against strict datasheet-evidence requirements."""
    reasons: list[str] = []
    if claim_needs_datasheet(claim) and not _matching_datasheet_evidence(claim, ledger):
        reasons.append("missing_datasheet_evidence")

    if claim.get("claim_type") in {"pin_state", "configuration", "parameter", "threshold"}:
        if not claim.get("netlist_evidence"):
            reasons.append("missing_netlist_evidence")

    return {
        **claim,
        "strict_status": "rejected" if reasons else "accepted",
        "strict_reasons": reasons,
    }


def validate_claims(claims_data: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    checked = [validate_single_claim(claim, ledger) for claim in claims_data.get("claims", [])]
    summary: dict[str, int] = {"accepted": 0, "rejected": 0}
    for claim in checked:
        summary[claim["strict_status"]] = summary.get(claim["strict_status"], 0) + 1
    return {
        "schema": "chip-netlist-verified-claims-v1",
        "claims": checked,
        "summary": summary,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Build evidence ledger or validate strict schematic claims.")
    parser.add_argument("--workdir", type=Path, default=Path(".chip-netlist"))
    parser.add_argument("--claims", type=Path, help="Claims JSON to validate")
    parser.add_argument("--ledger-output", type=Path, help="Write evidence ledger JSON")
    parser.add_argument("--output", type=Path, help="Write verified claims JSON")
    args = parser.parse_args(argv)

    ledger = build_evidence_ledger(args.workdir)
    if args.ledger_output:
        write_json(args.ledger_output, ledger)

    if args.claims:
        claims_data = load_json(args.claims, {"claims": []})
        result = validate_claims(claims_data, ledger)
        if args.output:
            write_json(args.output, result)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    elif not args.ledger_output:
        print(json.dumps(ledger, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
