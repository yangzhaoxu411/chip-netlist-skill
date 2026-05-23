#!/usr/bin/env python3
"""Run deterministic rules against a parsed netlist JSON."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Add scripts directory to path for rule imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rules import get_basic_rules, get_datasheet_rules


def run_rules(
    netlist: dict[str, Any],
    rule_ids: list[str] | None = None,
    include_datasheet_rules: bool = False,
) -> list[dict[str, Any]]:
    """Run rules against netlist, return findings."""
    rules = get_basic_rules()
    if include_datasheet_rules:
        rules.update(get_datasheet_rules())

    if rule_ids:
        rules = {rid: func for rid, func in rules.items() if rid in rule_ids}

    findings: list[dict[str, Any]] = []
    for rule_id, rule_func in sorted(rules.items()):
        try:
            results = rule_func(netlist)
            findings.extend(results)
        except Exception as e:
            findings.append({
                "rule_id": rule_id,
                "severity": "error",
                "category": "rule_error",
                "target": "system",
                "message": f"Rule {rule_id} failed: {e}",
            })

    return findings


def _load_enriched_data(netlist_path: Path) -> dict[str, Any] | None:
    """Try to load enriched.json from the same directory as the netlist."""
    enriched_path = netlist_path.parent / "enriched.json"
    if not enriched_path.exists():
        return None
    try:
        return json.loads(enriched_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run chip netlist rules.")
    parser.add_argument("netlist", type=Path, help="Path to netlist.json")
    parser.add_argument("--rules", help="Comma-separated rule IDs to run")
    parser.add_argument("--datasheet", action="store_true", help="Include datasheet rules")
    parser.add_argument("--output", type=Path, help="Output path for findings.json")
    args = parser.parse_args(argv)

    if not args.netlist.exists():
        print(f"Error: Netlist file not found: {args.netlist}", file=sys.stderr)
        return 1

    try:
        netlist = json.loads(args.netlist.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {args.netlist}: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"Error: Cannot read {args.netlist}: {e}", file=sys.stderr)
        return 1

    # Validate required fields
    missing_fields = [f for f in ("components", "nets", "pins") if f not in netlist]
    if missing_fields:
        print(f"Error: Netlist missing required fields: {missing_fields}", file=sys.stderr)
        return 1

    # Load enriched data when running datasheet rules
    if args.datasheet:
        enriched = _load_enriched_data(args.netlist)
        if not enriched:
            print(
                f"Error: --datasheet requires enriched.json next to {args.netlist}. "
                "Run build_enriched.py first.",
                file=sys.stderr,
            )
            return 1
        netlist["_enriched"] = enriched

    rule_ids = args.rules.split(",") if args.rules else None
    findings = run_rules(netlist, rule_ids, include_datasheet_rules=args.datasheet)

    severity_counts: dict[str, int] = {}
    for f in findings:
        sev = f.get("severity", "unknown")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    output = {
        "schema": "chip-netlist-findings-v1",
        "source": str(args.netlist),
        "finding_count": len(findings),
        "summary": severity_counts,
        "findings": findings,
    }

    text = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
