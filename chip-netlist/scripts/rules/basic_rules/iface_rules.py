"""Interface rules — I001, I002."""
from __future__ import annotations

from typing import Any

from rules import register
from rules.base import make_finding


@register("I001")
def i001_i2c_missing_pullup(netlist: dict[str, Any]) -> list[dict[str, Any]]:
    """I001: I2C/SMBus missing pull-up.

    Check net names containing: sda, scl, smdata, smclk, smalert.
    For each, check if any peer component starts with "R" (resistor).
    If no pull-up found, severity "high".
    This is the canonical I2C pull-up check (see also R004).
    """
    findings: list[dict[str, Any]] = []
    i2c_keywords = ("SDA", "SCL", "SMDATA", "SMCLK", "SMALERT")
    # Power net names that must NEVER be flagged
    power_nets = {
        "VCC", "VDD", "VIN", "VBAT", "VBUS", "INTVCC", "DVCC", "AVCC",
        "PVCC", "PVDD", "DRVCC", "VREG", "VPP", "VPWR", "VCP", "VBOOST",
        "GND", "AGND", "DGND", "PGND", "SGND", "VSS",
    }

    pins: dict[str, list[dict[str, Any]]] = netlist.get("pins", {})
    visited_nets: set[str] = set()

    for pin_ref, pin_entries in pins.items():
        for entry in pin_entries:
            net_name: str = entry.get("net", "")
            if net_name in visited_nets:
                continue
            upper = net_name.upper()

            # Skip known power nets
            if upper in power_nets:
                continue

            if not any(kw in upper for kw in i2c_keywords):
                continue
            visited_nets.add(net_name)

            all_refs = [pin_ref] + entry.get("peers", [])
            has_resistor = any(
                ref.split(".")[0].upper().startswith("R") for ref in all_refs
            )
            if not has_resistor:
                findings.append(make_finding(
                    rule_id="I001",
                    severity="high",
                    category="interface",
                    target=net_name,
                    message=f"I2C/SMBus net '{net_name}' has no pull-up resistor.",
                    net=net_name,
                    suggestion=(
                        "Add a pull-up resistor (e.g. 4.7 kΩ to VCC) on this "
                        "I2C/SMBus line to ensure proper bus operation."
                    ),
                ))

    return findings


@register("I002")
def i002_logic_level_mismatch(netlist: dict[str, Any]) -> list[dict[str, Any]]:
    """I002: Logic level mismatch (stub).

    Full implementation requires datasheet data to compare logic levels
    between connected devices.  Returns empty list for now.
    """
    # Stub — needs datasheet data to compare V_IH/V_IL thresholds
    return []
