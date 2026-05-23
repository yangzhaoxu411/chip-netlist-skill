"""BOM rules — B001, B003."""
from __future__ import annotations

from typing import Any

from rules import register
from rules.base import make_finding


@register("B001")
def b001_no_real_part_number(netlist: dict[str, Any]) -> list[dict[str, Any]]:
    """B001: No real part number.

    Check each component in netlist['components'].  If both
    ``manufacturer_part`` and ``canonical_name`` are empty or missing,
    create a finding with severity "low".
    """
    findings: list[dict[str, Any]] = []
    components: dict[str, Any] = netlist.get("components", {})

    for ref, comp in components.items():
        mfr_part = (comp.get("manufacturer_part") or "").strip()
        canonical = (comp.get("canonical_name") or "").strip()
        if not mfr_part and not canonical:
            findings.append(make_finding(
                rule_id="B001",
                severity="low",
                category="bom",
                target=ref,
                message=f"Component {ref} has no manufacturer part number or canonical name.",
                suggestion="Assign a real part number to the component for BOM accuracy.",
            ))

    return findings


@register("B003")
def b003_missing_value(netlist: dict[str, Any]) -> list[dict[str, Any]]:
    """B003: Missing component value.

    Check each component in netlist['components'].  Skip refs starting with
    "TP" (test points) or "MH" (mounting holes).  If ``value`` is empty,
    None, or the placeholder "{Value}", create a finding with severity "low".
    """
    findings: list[dict[str, Any]] = []
    skip_prefixes = ("TP", "MH")
    placeholder = "{Value}"
    components: dict[str, Any] = netlist.get("components", {})

    for ref, comp in components.items():
        if ref.upper().startswith(skip_prefixes):
            continue
        value = comp.get("value")
        if value is None or str(value).strip() == "" or str(value).strip() == placeholder:
            findings.append(make_finding(
                rule_id="B003",
                severity="low",
                category="bom",
                target=ref,
                message=f"Component {ref} has no value assigned.",
                suggestion="Set a meaningful value (resistance, capacitance, etc.).",
            ))

    return findings
