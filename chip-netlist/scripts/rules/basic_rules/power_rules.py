"""Power net rules — P001."""
from __future__ import annotations

from typing import Any

from rules import register
from rules.base import make_finding


@register("P001")
def p001_missing_reverse_polarity_protection(netlist: dict[str, Any]) -> list[dict[str, Any]]:
    """P001: Missing reverse polarity protection.

    Check for power input nets (names containing VIN, VPWR, V+, VBAT, VBUS,
    POWER, PWR_IN, INPUT).  For each such net, look for a component that could
    provide reverse-polarity protection: a diode (ref starts with "D") or a
    MOSFET (ref starts with "Q").  If none found, emit a finding with
    severity "medium" as a heuristic "worth reviewing" flag.
    """
    findings: list[dict[str, Any]] = []
    input_power_keywords = ("VIN", "VPWR", "V+", "VBAT", "VBUS", "POWER", "PWR_IN", "INPUT")
    protection_prefixes = ("D", "Q")  # Diode or MOSFET

    pins: dict[str, list[dict[str, Any]]] = netlist.get("pins", {})
    visited_nets: set[str] = set()

    for pin_ref, pin_entries in pins.items():
        for entry in pin_entries:
            net_name: str = entry.get("net", "")
            if net_name in visited_nets:
                continue
            upper = net_name.upper()
            if not any(kw in upper for kw in input_power_keywords):
                continue
            visited_nets.add(net_name)

            all_refs = [pin_ref] + entry.get("peers", [])
            has_protection = any(
                ref.split(".")[0].upper().startswith(protection_prefixes)
                for ref in all_refs
            )
            if not has_protection:
                findings.append(make_finding(
                    rule_id="P001",
                    severity="medium",
                    category="power",
                    target=net_name,
                    message=(
                        f"Power input net '{net_name}' has no visible reverse "
                        f"polarity protection (diode or MOSFET)."
                    ),
                    net=net_name,
                    suggestion=(
                        "Consider adding a reverse polarity protection diode or "
                        "MOSFET on the input power net to prevent damage from "
                        "reversed supply connections."
                    ),
                ))

    return findings
