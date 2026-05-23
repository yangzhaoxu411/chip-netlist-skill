"""Parameter verification datasheet rules -- R005, R006."""
from __future__ import annotations

import re
from typing import Any

from rules import register
from rules.base import make_finding


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_POWER_NET_KEYWORDS = ("VCC", "VIN", "VDD", "VPP", "VPWR", "VBAT", "VBUS", "3V3", "5V")
_GND_NET_KEYWORDS = ("GND", "GROUND", "AGND", "DGND")

_FEEDBACK_PIN_PATTERNS = ("FB", "ADJ", "VADJ", "VREF")
_SENSE_PIN_PATTERNS = ("CSP", "CSN", "SENSE", "ISNS", "ISENSE")


def _parse_numeric_value(value_str: str) -> float | None:
    """Parse a value string like ``'10K'``, ``'0.01'``, ``'4.7K'``, ``'50m'``,
    ``'0.05V'``, ``'50mV'`` into a float.

    Returns ``None`` if parsing fails.
    """
    if not value_str:
        return None

    value_str = str(value_str).strip()
    if not value_str:
        return None

    # Match: digits (with optional decimal), optional suffix
    # Suffix can include K/k/M/m/R and an optional trailing V/v
    match = re.match(r"([0-9]*\.?[0-9]+)\s*([KkMmRr]?[Vv]?)", value_str)
    if not match:
        return None

    number = float(match.group(1))
    raw_suffix = match.group(2)

    # Strip optional trailing V/v (unit indicator)
    suffix = raw_suffix.rstrip("Vv").upper()

    multiplier_map = {
        "": 1.0,
        "K": 1_000.0,
        "M": 1_000_000.0,
        "R": 1.0,  # R suffix means ohms
    }
    # 'm' (lowercase) = milli
    if raw_suffix and raw_suffix[0] == "m":
        return number * 0.001
    return number * multiplier_map.get(suffix, 1.0)


def _is_power_net(net_name: str) -> bool:
    upper = net_name.upper()
    return any(kw in upper for kw in _POWER_NET_KEYWORDS)


def _is_gnd_net(net_name: str) -> bool:
    upper = net_name.upper()
    return any(kw in upper for kw in _GND_NET_KEYWORDS)


def _find_connected_resistors(
    pin_ref: str,
    pins: dict[str, Any],
) -> list[str]:
    """Return ref-designators of resistors connected to *pin_ref*.

    Looks for peers whose ref starts with ``'R'``.
    """
    resistors: list[str] = []
    for entry in pins.get(pin_ref, []):
        for peer in entry.get("peers", []):
            ref = peer.split(".")[0]
            if ref.upper().startswith("R") and ref not in resistors:
                resistors.append(ref)
    return resistors


def _get_resistor_value(ref: str, pins: dict[str, Any], components: dict[str, Any]) -> float | None:
    """Return the resistance of *ref* (e.g. ``'R1'``) in ohms, or ``None``."""
    comp = components.get(ref, {})
    value_str = comp.get("value", "")
    return _parse_numeric_value(value_str)


def _extract_vref_from_formula(formulas: list[dict[str, Any]]) -> float | None:
    """Extract a reference voltage from formula entries (R005).

    Searches formula strings for voltage values associated with Vref, V_FB,
    etc.  Returns the first numeric match found, or ``None``.
    """
    for f_entry in formulas:
        formula = f_entry.get("formula", "")
        if not formula:
            continue

        # Look for "Vref = X", "V_FB = X", "Vout = X", etc.
        # [A-Za-z_]+ allows lowercase after V (e.g. Vout, Vref)
        m = re.search(r"[Vv][A-Za-z_]+\s*=\s*([0-9]*\.?[0-9]+)\s*[KkMm]?[Vv]?", formula)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass

    # Fallback: try to find any numeric value followed by V/mV (less reliable)
    for f_entry in formulas:
        formula = f_entry.get("formula", "")
        nums = re.findall(r"([0-9]*\.?[0-9]+)\s*[KkMm]?[Vv]", formula)
        for n in nums:
            try:
                v = float(n)
                if 0.05 < v < 20.0:  # Reasonable Vref range
                    return v
            except ValueError:
                pass

    return None


def _extract_vout_from_recommended(recommended: dict[str, Any]) -> tuple[float | None, float | None]:
    """Extract min/max output voltage from recommended operating conditions."""
    for key in ("V_OUT", "VOUT", "V_O", "OUTPUT", "V_OUTPUT"):
        entry = recommended.get(key)
        if isinstance(entry, dict):
            vmin = _parse_numeric_value(entry.get("min", ""))
            vmax = _parse_numeric_value(entry.get("max", ""))
            if vmin is not None or vmax is not None:
                return vmin, vmax
    return None, None


def _extract_sense_voltage(formulas: list[dict[str, Any]], recommended: dict[str, Any]) -> float | None:
    """Extract current-sense voltage threshold from formulas or recommended (R006).

    Tries (in order):
    1. Numeric values from formula strings (e.g. "I = 50mV / R_SENSE")
    2. "V_SENSE = X" pattern in formula strings
    3. V_SENSE / VSENSE / V_CS entries in recommended operating conditions
    """
    # Try formulas first: look for context mentioning sense/threshold
    for f_entry in formulas:
        ctx = (f_entry.get("context") or "").lower()
        if any(kw in ctx for kw in ("sense", "threshold", "limit", "charge")):
            formula = f_entry.get("formula", "")
            # Extract numeric values with optional unit suffixes (mV, V)
            nums = re.findall(
                r"([0-9]*\.?[0-9]+)\s*([KkMm]?[Vv])",
                formula, re.IGNORECASE,
            )
            for n_str, unit in nums:
                try:
                    val = float(n_str)
                    # Apply multiplier from unit prefix
                    if unit.lower().startswith("m"):
                        val *= 0.001
                    return val
                except ValueError:
                    pass

    # Try formula string directly for "V_SENSE = X" pattern
    for f_entry in formulas:
        formula = f_entry.get("formula", "")
        m = re.search(
            r"[Vv]_?SENSE\s*=\s*([0-9]*\.?[0-9]+)\s*([KkMm]?[Vv]?)",
            formula,
        )
        if m:
            try:
                val = float(m.group(1))
                unit = m.group(2)
                if unit.lower().startswith("m"):
                    val *= 0.001
                return val
            except ValueError:
                pass

    # Try recommended operating conditions
    for key in ("V_SENSE", "VSENSE", "V_CS", "SENSE"):
        entry = recommended.get(key)
        if entry is None:
            continue
        if isinstance(entry, dict):
            return _parse_numeric_value(entry.get("min", ""))
        return _parse_numeric_value(str(entry))

    return None


def _extract_max_current(recommended: dict[str, Any]) -> float | None:
    """Extract maximum current from recommended operating conditions."""
    for key in ("I_CHARGE", "ICHARGE", "I_OUT", "IOUT", "I_LOAD", "I_MAX"):
        entry = recommended.get(key)
        if isinstance(entry, dict):
            return _parse_numeric_value(entry.get("max", ""))
        return _parse_numeric_value(str(entry))
    return None


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

@register("R005")
def r005_voltage_divider_ratio(netlist: dict[str, Any]) -> list[dict[str, Any]]:
    """R005: Voltage divider ratio check.

    Look for resistor divider networks connected to feedback pins (FB, VFB,
    ADJ).  Calculate the divider ratio::

        Vout = Vref * (1 + R_top / R_bottom)

    Compare with recommended output voltage from the datasheet.  If mismatch,
    severity ``high``.
    """
    enriched: dict[str, Any] = netlist.get("_enriched", {})
    if not enriched:
        return []

    components = enriched.get("components", {})
    pins: dict[str, Any] = netlist.get("pins", {})
    findings: list[dict[str, Any]] = []

    # Collect feedback pins per component
    fb_pins: dict[str, list[tuple[int, str]]] = {}
    for ref, comp in components.items():
        for pin in comp.get("pin_table", []):
            pin_name = (pin.get("name") or "").upper()
            if any(pat in pin_name for pat in _FEEDBACK_PIN_PATTERNS):
                fb_pins.setdefault(ref, []).append((pin["number"], pin["name"]))

    for ref, fbs in fb_pins.items():
        comp = components.get(ref, {})
        formulas = comp.get("formulas", [])
        recommended = comp.get("recommended", {})
        comp_components = netlist.get("components", {})

        for pin_num, pin_name in fbs:
            pin_ref = f"{ref}.{pin_num}"
            resistors = _find_connected_resistors(pin_ref, pins)
            if len(resistors) < 2:
                continue

            # Determine which resistor goes to power (top) and which to GND (bottom)
            # For each resistor, find the pin connected to FB, then check the
            # OTHER pin of that resistor to see if it connects to power or GND.
            r_top_ref: str | None = None
            r_btm_ref: str | None = None

            for r_ref in resistors:
                # Find which pin of this resistor is connected to the FB pin
                fb_pin_of_r: str | None = None
                for entry in pins.get(pin_ref, []):
                    for peer in entry.get("peers", []):
                        if peer.startswith(r_ref + "."):
                            fb_pin_of_r = peer
                            break
                    if fb_pin_of_r:
                        break

                if fb_pin_of_r is None:
                    continue

                # Get the net of the OTHER pin of this resistor
                # Most two-terminal resistor symbols use {ref}.1 and {ref}.2.
                ref_base = fb_pin_of_r.rsplit(".", 1)[0]
                other_pin_ref: str | None = None
                for pin_key in pins:
                    if pin_key.startswith(ref_base + ".") and pin_key != fb_pin_of_r:
                        other_pin_ref = pin_key
                        break

                if other_pin_ref is None:
                    continue

                other_net = ""
                for pe in pins.get(other_pin_ref, []):
                    other_net = pe.get("net", "")
                    break

                if _is_power_net(other_net) and r_top_ref is None:
                    r_top_ref = r_ref
                elif _is_gnd_net(other_net) and r_btm_ref is None:
                    r_btm_ref = r_ref

            if r_top_ref is None or r_btm_ref is None:
                continue

            r_top = _get_resistor_value(r_top_ref, pins, comp_components)
            r_btm = _get_resistor_value(r_btm_ref, pins, comp_components)
            if r_top is None or r_btm is None or r_btm == 0:
                continue

            # Extract Vref from formulas or derive from recommended V_OUT
            vref = _extract_vref_from_formula(formulas)
            if vref is None:
                vmin, _ = _extract_vout_from_recommended(recommended)
                if vmin is not None:
                    ratio = 1 + r_top / r_btm
                    if ratio != 0:
                        vref = vmin / ratio

            if vref is None:
                continue

            vout_calc = vref * (1 + r_top / r_btm)
            rec_vmin, rec_vmax = _extract_vout_from_recommended(recommended)

            if rec_vmin is not None and rec_vmax is not None:
                tolerance = 0.05  # 5%
                in_range = (
                    (1 - tolerance) * rec_vmin <= vout_calc <= (1 + tolerance) * rec_vmax
                )
                if not in_range:
                    findings.append(make_finding(
                        rule_id="R005",
                        severity="high",
                        category="analog",
                        target=ref,
                        message=(
                            f"Voltage divider on {ref} ({pin_name}) produces "
                            f"Vout={vout_calc:.3f}V, but recommended range is "
                            f"{rec_vmin:.3f}V -- {rec_vmax:.3f}V."
                        ),
                        evidence={
                            "r_top": f"{r_top_ref}={r_top}",
                            "r_bottom": f"{r_btm_ref}={r_btm}",
                            "vref": str(vref),
                            "calculated_vout": f"{vout_calc:.3f}V",
                            "recommended_vout": f"{rec_vmin:.3f}V -- {rec_vmax:.3f}V",
                        },
                        suggestion=(
                            "Adjust R_top/R_bottom ratio so that "
                            "Vout = Vref * (1 + R_top/R_bottom) "
                            "matches the target output voltage."
                        ),
                    ))

    return findings


# Mark as needing datasheet data
r005_voltage_divider_ratio.needs_datasheet = True


@register("R006")
def r006_current_limit_check(netlist: dict[str, Any]) -> list[dict[str, Any]]:
    """R006: Current limit check.

    Look for current-sense pins (CSN, CSP, SENSE) and associated sense
    resistors.  Calculate::

        I_limit = V_sense / R_sense

    using the datasheet formula.  Compare with recommended current from the
    datasheet.  If out of range, severity ``high``.
    """
    enriched: dict[str, Any] = netlist.get("_enriched", {})
    if not enriched:
        return []

    components = enriched.get("components", {})
    pins: dict[str, Any] = netlist.get("pins", {})
    comp_components: dict[str, Any] = netlist.get("components", {})
    findings: list[dict[str, Any]] = []

    # Collect current-sense pins per component
    cs_pins: dict[str, list[tuple[int, str, str]]] = {}
    for ref, comp in components.items():
        for pin in comp.get("pin_table", []):
            pin_name = (pin.get("name") or "").upper()
            pin_type = (pin.get("type") or "").lower()
            if pin_type == "nc":
                continue
            if any(pat in pin_name for pat in _SENSE_PIN_PATTERNS):
                cs_pins.setdefault(ref, []).append(
                    (pin["number"], pin["name"], pin_type)
                )

    for ref, sense_list in cs_pins.items():
        comp = components.get(ref, {})
        formulas = comp.get("formulas", [])
        recommended = comp.get("recommended", {})

        # Find a sense resistor connected to any of the sense pins
        sense_r_ref: str | None = None
        for pin_num, _, _ in sense_list:
            pin_ref = f"{ref}.{pin_num}"
            for r_ref in _find_connected_resistors(pin_ref, pins):
                if sense_r_ref is None or r_ref == sense_r_ref:
                    sense_r_ref = r_ref

        if sense_r_ref is None:
            continue

        r_sense = _get_resistor_value(sense_r_ref, pins, comp_components)
        if r_sense is None or r_sense <= 0:
            continue

        # Extract sense voltage and max current
        v_sense = _extract_sense_voltage(formulas, recommended)
        if v_sense is None:
            continue

        max_current = _extract_max_current(recommended)
        i_limit = v_sense / r_sense

        if max_current is not None and i_limit > max_current:
            findings.append(make_finding(
                rule_id="R006",
                severity="high",
                category="power",
                target=ref,
                message=(
                    f"Current limit on {ref} is {i_limit:.2f}A "
                    f"(V_sense={v_sense}mV / R_sense={r_sense}), "
                    f"but recommended max is {max_current:.2f}A."
                ),
                evidence={
                    "sense_resistor": f"{sense_r_ref}={r_sense}",
                    "v_sense": f"{v_sense}mV",
                    "calculated_limit": f"{i_limit:.2f}A",
                    "recommended_max": f"{max_current:.2f}A",
                },
                suggestion=(
                    "Increase R_sense to lower the current limit, "
                    "or verify the sense voltage threshold in the datasheet."
                ),
            ))

    return findings


# Mark as needing datasheet data
r006_current_limit_check.needs_datasheet = True
