"""Pin function datasheet rules -- R001_enhanced, R002."""
from __future__ import annotations

from typing import Any

from rules import register
from rules.base import make_finding


# Pin types that require a connection per datasheet
_CONNECT_REQUIRED_TYPES = {"must_connect", "power"}


@register("R001_enhanced")
def r001_enhanced_floating_required_pin(netlist: dict[str, Any]) -> list[dict[str, Any]]:
    """R001_enhanced: Floating pin with datasheet check.

    For each component with a pin_table in enriched data, check if any pin
    marked as ``must_connect`` or ``power`` type appears in the netlist's
    ``no_net_pins`` list.  More accurate than basic R001 because the pin
    table from the datasheet tells us which pins actually need a connection.

    Severity: ``must-fix`` for power pins, ``high`` for signal pins.
    """
    enriched: dict[str, Any] = netlist.get("_enriched", {})
    if not enriched:
        return []

    components = enriched.get("components", {})
    no_net_pins: set[str] = set(netlist.get("warnings", {}).get("no_net_pins", []))
    if not no_net_pins:
        return []

    findings: list[dict[str, Any]] = []

    for ref, comp in components.items():
        pin_table = comp.get("pin_table", [])
        if not pin_table:
            continue

        for pin in pin_table:
            pin_num = pin.get("number")
            pin_name = pin.get("name", "")
            pin_type = pin.get("type", "").lower()

            if pin_type not in _CONNECT_REQUIRED_TYPES:
                continue

            # Build the pin reference used in the netlist (e.g. "U1.1")
            pin_ref = f"{ref}.{pin_num}"
            if pin_ref not in no_net_pins:
                continue

            severity = "must-fix" if pin_type == "power" else "high"
            findings.append(make_finding(
                rule_id="R001_enhanced",
                severity=severity,
                category="pin",
                target=pin_ref,
                message=(
                    f"Pin {pin_ref} ({pin_name}) is marked as '{pin_type}' in "
                    f"the datasheet but has no net connection."
                ),
                suggestion=(
                    f"Connect pin {pin_name} as specified in the datasheet. "
                    f"Use the datasheet pin description and reference circuit "
                    f"to choose VCC, GND, pull-up, pull-down, or bypass wiring."
                ),
            ))

    return findings


# Mark as needing datasheet data
r001_enhanced_floating_required_pin.needs_datasheet = True


@register("R002")
def r002_nc_pin_connected(netlist: dict[str, Any]) -> list[dict[str, Any]]:
    """R002: NC (no-connect) pin has a connection.

    For each component with a pin_table in enriched data, find pins marked
    as ``nc`` (no-connect) type.  If any such pin has a connection in the
    netlist, flag it with severity ``medium``.
    """
    enriched: dict[str, Any] = netlist.get("_enriched", {})
    if not enriched:
        return []

    components = enriched.get("components", {})
    pins: dict[str, Any] = netlist.get("pins", {})
    findings: list[dict[str, Any]] = []

    for ref, comp in components.items():
        pin_table = comp.get("pin_table", [])
        if not pin_table:
            continue

        for pin in pin_table:
            pin_num = pin.get("number")
            pin_name = pin.get("name", "")
            pin_type = pin.get("type", "").lower()

            if pin_type != "nc":
                continue

            # If the pin appears in the netlist pins dict, it has a connection
            pin_ref = f"{ref}.{pin_num}"
            if pin_ref in pins:
                findings.append(make_finding(
                    rule_id="R002",
                    severity="medium",
                    category="pin",
                    target=pin_ref,
                    message=(
                        f"Pin {pin_ref} ({pin_name}) is marked as NC (no-connect) "
                        f"in the datasheet but is connected in the schematic."
                    ),
                    suggestion=(
                        f"Disconnect pin {pin_ref} ({pin_name}). "
                        "NC pins should not have any connection per the datasheet."
                    ),
                ))

    return findings


# Mark as needing datasheet data
r002_nc_pin_connected.needs_datasheet = True
