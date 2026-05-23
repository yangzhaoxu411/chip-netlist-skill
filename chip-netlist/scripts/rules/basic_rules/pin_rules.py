"""Pin-level rules — R001, R003, R004."""
from __future__ import annotations

from typing import Any

from rules import register
from rules.base import make_finding


@register("R001")
def r001_floating_required_pin(netlist: dict[str, Any]) -> list[dict[str, Any]]:
    """R001: Floating required pin.

    Check netlist['warnings']['no_net_pins'] — these are pins with no net
    connection.  For each such pin, create a finding with severity "high".
    """
    findings: list[dict[str, Any]] = []
    no_net_pins: list[str] = netlist.get("warnings", {}).get("no_net_pins", [])

    for pin_ref in no_net_pins:
        findings.append(make_finding(
            rule_id="R001",
            severity="high",
            category="pin",
            target=pin_ref,
            message=f"Pin {pin_ref} has no net connection (floating).",
            suggestion="Check the datasheet evidence before deciding whether this "
                       "pin needs a connection or an explicit tie to VCC/GND.",
        ))

    return findings


@register("R003")
def r003_missing_bypass_capacitor(netlist: dict[str, Any]) -> list[dict[str, Any]]:
    """R003: Missing bypass capacitor.

    Find power nets (names containing VCC, VIN, VDD, VPP, VPWR, V+, VBAT,
    VBUS) and check that at least one peer component on the same net starts
    with "C" (capacitor).  If none is found, emit a finding with severity "high".
    """
    findings: list[dict[str, Any]] = []
    power_prefixes = ("VCC", "VIN", "VDD", "VPP", "VPWR", "V+", "VBAT", "VBUS")

    pins: dict[str, list[dict[str, Any]]] = netlist.get("pins", {})
    visited_nets: set[str] = set()

    for pin_ref, pin_entries in pins.items():
        for entry in pin_entries:
            net_name: str = entry.get("net", "")
            if net_name in visited_nets:
                continue
            if not net_name.upper().startswith(power_prefixes):
                continue
            visited_nets.add(net_name)

            # Collect all peer refs on this net plus the pin itself
            all_refs = [pin_ref] + entry.get("peers", [])
            has_cap = any(ref.split(".")[0].upper().startswith("C") for ref in all_refs)
            if not has_cap:
                findings.append(make_finding(
                    rule_id="R003",
                    severity="high",
                    category="power",
                    target=net_name,
                    message=f"Power net '{net_name}' has no bypass capacitor.",
                    net=net_name,
                    suggestion="Add a bypass capacitor (e.g. 100 nF) close to the "
                               "power pin on this net.",
                ))

    return findings


@register("R004")
def r004_missing_pullup(netlist: dict[str, Any]) -> list[dict[str, Any]]:
    """R004: Missing pull-up resistor on I2C/SMBus-like nets.

    Check for net names matching I2C/SMBus signals (SDA, SCL, SMBUS, I2C,
    ALERT, INT).  For each such net, verify at least one peer component
    starts with "R" (resistor).  If none found, emit a finding with
    severity "medium".
    """
    findings: list[dict[str, Any]] = []
    # Power net names that must NEVER be flagged as I2C/SMBus
    power_nets = {
        "VCC", "VDD", "VIN", "VBAT", "VBUS", "INTVCC", "DVCC", "AVCC",
        "PVCC", "PVDD", "DRVCC", "VREG", "VPP", "VPWR", "VCP", "VBOOST",
        "GND", "AGND", "DGND", "PGND", "SGND", "VSS",
    }
    # I2C/SMBus signal keywords — must be a complete token in the net name
    i2c_keywords = ("SDA", "SCL", "SMBUS", "I2C", "ALERT", "INT", "NINT")

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

            # Check if net name contains an I2C keyword as a complete token
            # Token = keyword is at start/end of name, or surrounded by separators
            has_i2c = False
            for kw in i2c_keywords:
                idx = upper.find(kw)
                if idx == -1:
                    continue
                # Check boundaries: keyword must be a whole token
                before_ok = (idx == 0) or (upper[idx - 1] in "_-.")
                after_pos = idx + len(kw)
                after_ok = (after_pos >= len(upper)) or (upper[after_pos] in "_-.")
                if before_ok and after_ok:
                    has_i2c = True
                    break

            if not has_i2c:
                continue
            visited_nets.add(net_name)

            all_refs = [pin_ref] + entry.get("peers", [])
            has_resistor = any(ref.split(".")[0].upper().startswith("R") for ref in all_refs)
            if not has_resistor:
                findings.append(make_finding(
                    rule_id="R004",
                    severity="medium",
                    category="pin",
                    target=net_name,
                    message=f"I2C/SMBus net '{net_name}' has no pull-up resistor.",
                    net=net_name,
                    suggestion="Add a pull-up resistor (e.g. 4.7 kΩ) to VCC on this net.",
                ))

    return findings
