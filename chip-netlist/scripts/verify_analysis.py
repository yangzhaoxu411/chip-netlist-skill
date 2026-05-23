#!/usr/bin/env python3
"""Verify LLM analysis conclusions against parsed netlist data.

Checks each claim in an analysis JSON against chip_netlist.json to detect
hallucinated or unsupported conclusions.  Outputs a verified analysis with
confidence tags: verified, unverified, hallucinated.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

# Match patterns like "U1.10", "R4.2", "C10.1"
_PIN_REF_RE = re.compile(r"\b([A-Z]+\d+)\.(\d+)\b")
# Match patterns like "U1", "R4" (component refs without pin number)
_COMP_REF_RE = re.compile(r"\b([A-Z]+\d+)\b")
# Match net names like "$1N48", "VIN", "GND"
_NET_NAME_RE = re.compile(r"\b(\$?\w+)\b")


def extract_pin_refs(text: str) -> list[tuple[str, str]]:
    """Extract component.pin references from text (e.g. U1.10 → ("U1", "10"))."""
    return _PIN_REF_RE.findall(text)


def extract_comp_refs(text: str) -> list[str]:
    """Extract component references from text (e.g. U1, R4, C10)."""
    refs = set()
    for match in _COMP_REF_RE.finditer(text):
        ref = match.group(1)
        # Skip common words that look like refs
        if ref.upper() not in {"AC", "DC", "ESR", "PDF", "USB", "I2C", "SPI"}:
            refs.add(ref)
    return sorted(refs)


def extract_net_names(text: str) -> list[str]:
    """Extract net names from text (quoted or $-prefixed)."""
    nets = set()
    # Quoted net names: "VIN", 'GND'
    for match in re.finditer(r'["\'](\$?[^"\']+)["\']', text):
        nets.add(match.group(1))
    # $-prefixed net names: $1N48
    for match in re.finditer(r'\$\w+', text):
        nets.add(match.group(0))
    return sorted(nets)


# ---------------------------------------------------------------------------
# Verification logic
# ---------------------------------------------------------------------------

def build_netlist_index(netlist: dict[str, Any]) -> dict[str, Any]:
    """Build lookup indexes from netlist for fast verification."""
    pins: dict[str, list[dict[str, Any]]] = netlist.get("pins", {})
    components: dict[str, dict[str, Any]] = netlist.get("components", {})
    nets: list[dict[str, Any]] = netlist.get("nets", [])

    # Net name → set of connection refs
    net_connections: dict[str, set[str]] = {}
    for net_entry in nets:
        name = net_entry.get("net", "")
        net_connections[name] = set(net_entry.get("connections", []))

    # Pin ref → set of net names
    pin_to_nets: dict[str, set[str]] = {}
    for pin_ref, entries in pins.items():
        pin_to_nets[pin_ref] = {e.get("net", "") for e in entries}

    return {
        "pins": pins,
        "components": components,
        "net_connections": net_connections,
        "pin_to_nets": pin_to_nets,
    }


def verify_pin_claim(
    comp: str, pin: str, index: dict[str, Any]
) -> tuple[str, str]:
    """Verify a component.pin claim. Returns (status, detail).

    status: "verified" | "unverified" | "hallucinated"
    """
    pin_ref = f"{comp}.{pin}"
    pins = index["pins"]

    if pin_ref in pins:
        entries = pins[pin_ref]
        nets = [e.get("net", "") for e in entries]
        return "verified", f"Pin {pin_ref} exists, nets: {nets}"

    # Component exists but pin number may be wrong
    if comp in index["components"]:
        comp_pins = [k for k in pins if k.startswith(f"{comp}.")]
        return "hallucinated", (
            f"Pin {pin_ref} not found. "
            f"Known pins for {comp}: {comp_pins[:10]}"
        )

    return "hallucinated", f"Component {comp} not found in netlist"


def verify_net_claim(
    net_name: str, index: dict[str, Any]
) -> tuple[str, str]:
    """Verify a net name claim. Returns (status, detail)."""
    net_conns = index["net_connections"]

    if net_name in net_conns:
        conns = sorted(net_conns[net_name])
        return "verified", f"Net '{net_name}' exists, connections: {conns[:10]}"

    # Fuzzy match — check if net name is a substring
    fuzzy_matches = [n for n in net_conns if net_name.upper() in n.upper() or n.upper() in net_name.upper()]
    if fuzzy_matches:
        return "unverified", (
            f"Net '{net_name}' not exact match. Similar: {fuzzy_matches[:5]}"
        )

    return "hallucinated", f"Net '{net_name}' not found in netlist"


def verify_component_claim(
    ref: str, index: dict[str, Any]
) -> tuple[str, str]:
    """Verify a component reference exists. Returns (status, detail)."""
    if ref in index["components"]:
        comp = index["components"][ref]
        part = comp.get("manufacturer_part") or comp.get("canonical_name") or "?"
        return "verified", f"Component {ref} exists ({part})"

    return "hallucinated", f"Component {ref} not found in netlist"


def verify_conclusion(
    conclusion: dict[str, Any], index: dict[str, Any]
) -> dict[str, Any]:
    """Verify a single analysis conclusion against the netlist index.

    Returns the conclusion dict augmented with verification results.
    """
    text = conclusion.get("text", "") or conclusion.get("conclusion", "") or ""
    if not text:
        return {**conclusion, "verification": {"status": "unverified", "detail": "No text to verify"}}

    checks: list[dict[str, Any]] = []
    overall_status = "verified"

    # Check pin references
    for comp, pin in extract_pin_refs(text):
        status, detail = verify_pin_claim(comp, pin, index)
        checks.append({"type": "pin", "ref": f"{comp}.{pin}", "status": status, "detail": detail})
        if status == "hallucinated":
            overall_status = "hallucinated"
        elif status == "unverified" and overall_status != "hallucinated":
            overall_status = "unverified"

    # Check component references (only those not already covered by pin refs)
    pin_comps = {comp for comp, _ in extract_pin_refs(text)}
    for ref in extract_comp_refs(text):
        if ref not in pin_comps:
            status, detail = verify_component_claim(ref, index)
            checks.append({"type": "component", "ref": ref, "status": status, "detail": detail})
            if status == "hallucinated":
                overall_status = "hallucinated"

    # Check net name claims
    for net_name in extract_net_names(text):
        if net_name.startswith("$") or len(net_name) <= 6:
            status, detail = verify_net_claim(net_name, index)
            checks.append({"type": "net", "ref": net_name, "status": status, "detail": detail})
            if status == "hallucinated":
                overall_status = "hallucinated"
            elif status == "unverified" and overall_status != "hallucinated":
                overall_status = "unverified"

    if not checks:
        overall_status = "unverified"

    return {
        **conclusion,
        "verification": {
            "status": overall_status,
            "checks": checks,
        },
    }


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def verify_analysis(
    analysis: dict[str, Any],
    netlist: dict[str, Any],
) -> dict[str, Any]:
    """Verify all conclusions in an analysis against the netlist.

    Args:
        analysis: Analysis dict with a "conclusions" list.
        netlist: Parsed chip_netlist.json.

    Returns:
        Analysis dict augmented with verification results.
    """
    index = build_netlist_index(netlist)
    conclusions = analysis.get("conclusions", [])

    verified_conclusions = []
    for conc in conclusions:
        verified_conclusions.append(verify_conclusion(conc, index))

    # Count statuses
    status_counts: dict[str, int] = {}
    for vc in verified_conclusions:
        st = vc.get("verification", {}).get("status", "unknown")
        status_counts[st] = status_counts.get(st, 0) + 1

    return {
        **analysis,
        "conclusions": verified_conclusions,
        "verification_summary": status_counts,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Verify LLM analysis conclusions against netlist data."
    )
    parser.add_argument(
        "analysis",
        type=Path,
        help="Path to analysis.json (LLM conclusions)",
    )
    parser.add_argument(
        "netlist",
        type=Path,
        help="Path to chip_netlist.json (parsed netlist)",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output path for verified_analysis.json (default: stdout)",
    )
    args = parser.parse_args(argv)

    if not args.analysis.exists():
        print(f"Error: {args.analysis} not found", file=sys.stderr)
        return 1
    if not args.netlist.exists():
        print(f"Error: {args.netlist} not found", file=sys.stderr)
        return 1

    analysis = json.loads(args.analysis.read_text(encoding="utf-8"))
    netlist = json.loads(args.netlist.read_text(encoding="utf-8"))

    result = verify_analysis(analysis, netlist)

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
        summary = result.get("verification_summary", {})
        print(f"Verified: {summary.get('verified', 0)}, "
              f"Unverified: {summary.get('unverified', 0)}, "
              f"Hallucinated: {summary.get('hallucinated', 0)}",
              file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
