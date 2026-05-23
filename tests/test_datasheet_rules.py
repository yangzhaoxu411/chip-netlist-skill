"""Tests for datasheet rules (R001_enhanced, R002, R005, R006)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add scripts directory to path for imports
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "chip-netlist" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from check_rules import run_rules


# ---------------------------------------------------------------------------
# R001_enhanced: Floating pin with datasheet check
# ---------------------------------------------------------------------------

class TestR001Enhanced:
    """Tests for R001_enhanced: floating required pin (datasheet-aware)."""

    def _make_netlist(
        self,
        no_net_pins: list[str],
        pin_table: list[dict],
        ref: str = "U1",
    ) -> dict:
        return {
            "schema": "chip-netlist-ai-json-v1",
            "components": {ref: {"designator": ref}},
            "nets": [],
            "pins": {},
            "warnings": {"no_net_pins": no_net_pins},
            "_enriched": {
                "components": {
                    ref: {
                        "ref": ref,
                        "canonical_name": "TEST_IC",
                        "pin_table": pin_table,
                        "formulas": [],
                        "abs_max": {},
                        "recommended": {},
                    },
                },
            },
        }

    def test_finds_must_connect_floating_pin(self) -> None:
        """R001_enhanced should flag a 'must_connect' pin in no_net_pins."""
        netlist = self._make_netlist(
            no_net_pins=["U1.3"],
            pin_table=[
                {"number": 1, "name": "VCC", "type": "power", "description": "Power"},
                {"number": 2, "name": "GND", "type": "power", "description": "Ground"},
                {"number": 3, "name": "EN", "type": "must_connect", "description": "Enable"},
            ],
        )
        findings = run_rules(netlist, rule_ids=["R001_enhanced"], include_datasheet_rules=True)
        assert len(findings) == 1
        assert findings[0]["target"] == "U1.3"
        assert findings[0]["severity"] == "high"

    def test_finds_power_floating_pin(self) -> None:
        """R001_enhanced should flag a 'power' pin in no_net_pins as must-fix."""
        netlist = self._make_netlist(
            no_net_pins=["U1.1"],
            pin_table=[
                {"number": 1, "name": "VCC", "type": "power", "description": "Power"},
                {"number": 2, "name": "GND", "type": "power", "description": "Ground"},
            ],
        )
        findings = run_rules(netlist, rule_ids=["R001_enhanced"], include_datasheet_rules=True)
        assert len(findings) == 1
        assert findings[0]["target"] == "U1.1"
        assert findings[0]["severity"] == "must-fix"

    def test_ignores_input_pin_type(self) -> None:
        """R001_enhanced should NOT flag a plain 'input' type pin."""
        netlist = self._make_netlist(
            no_net_pins=["U1.2"],
            pin_table=[
                {"number": 1, "name": "VCC", "type": "power", "description": "Power"},
                {"number": 2, "name": "DATA", "type": "input", "description": "Data"},
            ],
        )
        findings = run_rules(netlist, rule_ids=["R001_enhanced"], include_datasheet_rules=True)
        assert findings == []

    def test_no_findings_when_no_enriched(self) -> None:
        """R001_enhanced returns empty when _enriched is absent."""
        netlist = {
            "schema": "chip-netlist-ai-json-v1",
            "components": {"U1": {"designator": "U1"}},
            "nets": [],
            "pins": {},
            "warnings": {"no_net_pins": ["U1.1"]},
        }
        findings = run_rules(netlist, rule_ids=["R001_enhanced"], include_datasheet_rules=True)
        assert findings == []

    def test_no_findings_when_pins_connected(self) -> None:
        """R001_enhanced returns empty when all required pins have nets."""
        netlist = self._make_netlist(
            no_net_pins=[],
            pin_table=[
                {"number": 1, "name": "VCC", "type": "power", "description": "Power"},
                {"number": 2, "name": "GND", "type": "power", "description": "Ground"},
            ],
        )
        findings = run_rules(netlist, rule_ids=["R001_enhanced"], include_datasheet_rules=True)
        assert findings == []

    def test_multiple_components(self) -> None:
        """R001_enhanced checks all components in enriched data."""
        netlist = {
            "schema": "chip-netlist-ai-json-v1",
            "components": {
                "U1": {"designator": "U1"},
                "U2": {"designator": "U2"},
            },
            "nets": [],
            "pins": {},
            "warnings": {"no_net_pins": ["U1.1", "U2.1"]},
            "_enriched": {
                "components": {
                    "U1": {
                        "ref": "U1",
                        "pin_table": [
                            {"number": 1, "name": "VCC", "type": "power", "description": ""},
                        ],
                    },
                    "U2": {
                        "ref": "U2",
                        "pin_table": [
                            {"number": 1, "name": "EN", "type": "must_connect", "description": ""},
                        ],
                    },
                },
            },
        }
        findings = run_rules(netlist, rule_ids=["R001_enhanced"], include_datasheet_rules=True)
        targets = {f["target"] for f in findings}
        assert "U1.1" in targets
        assert "U2.1" in targets


# ---------------------------------------------------------------------------
# R002: NC pin connected
# ---------------------------------------------------------------------------

class TestR002NcPinConnected:
    """Tests for R002: NC (no-connect) pin has a connection."""

    def test_finds_nc_pin_connected(self) -> None:
        """R002 should flag an NC pin that has a net connection."""
        netlist = {
            "schema": "chip-netlist-ai-json-v1",
            "components": {"U1": {"designator": "U1"}},
            "nets": [{"net": "SOME_NET", "connections": ["U1.5"]}],
            "pins": {
                "U1.5": [{"net": "SOME_NET", "pin_id": "p1", "peers": []}],
            },
            "warnings": {"no_net_pins": []},
            "_enriched": {
                "components": {
                    "U1": {
                        "ref": "U1",
                        "pin_table": [
                            {"number": 5, "name": "NC", "type": "nc", "description": "No connect"},
                        ],
                    },
                },
            },
        }
        findings = run_rules(netlist, rule_ids=["R002"], include_datasheet_rules=True)
        assert len(findings) == 1
        assert findings[0]["target"] == "U1.5"
        assert findings[0]["severity"] == "medium"

    def test_no_findings_when_nc_unconnected(self) -> None:
        """R002 returns empty when NC pin is correctly left unconnected."""
        netlist = {
            "schema": "chip-netlist-ai-json-v1",
            "components": {"U1": {"designator": "U1"}},
            "nets": [],
            "pins": {},
            "warnings": {"no_net_pins": ["U1.5"]},
            "_enriched": {
                "components": {
                    "U1": {
                        "ref": "U1",
                        "pin_table": [
                            {"number": 5, "name": "NC", "type": "nc", "description": "No connect"},
                        ],
                    },
                },
            },
        }
        findings = run_rules(netlist, rule_ids=["R002"], include_datasheet_rules=True)
        assert findings == []

    def test_no_findings_when_no_enriched(self) -> None:
        """R002 returns empty when _enriched is absent."""
        netlist = {
            "schema": "chip-netlist-ai-json-v1",
            "components": {"U1": {"designator": "U1"}},
            "nets": [],
            "pins": {},
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["R002"], include_datasheet_rules=True)
        assert findings == []


# ---------------------------------------------------------------------------
# R005: Voltage divider ratio check
# ---------------------------------------------------------------------------

class TestR005VoltageDivider:
    """Tests for R005: voltage divider ratio mismatch."""

    def _make_voltage_divider_netlist(
        self,
        r_top_value: str,
        r_btm_value: str,
        rec_vmin: str,
        rec_vmax: str,
        vref: float = 0.6,
    ) -> dict:
        """Build a netlist with a voltage divider on U1.FB pin.

        U1.FB (pin 3) -> R_TOP -> VIN (power)
                      -> R_BTM -> GND
        """
        return {
            "schema": "chip-netlist-ai-json-v1",
            "components": {
                "U1": {"designator": "U1"},
                "R_TOP": {"designator": "R_TOP", "value": r_top_value},
                "R_BTM": {"designator": "R_BTM", "value": r_btm_value},
            },
            "nets": [
                {"net": "FB_NET", "connections": ["U1.3", "R_TOP.1", "R_BTM.1"]},
                {"net": "VIN", "connections": ["R_TOP.2"]},
                {"net": "GND", "connections": ["R_BTM.2"]},
            ],
            "pins": {
                "U1.3": [
                    {"net": "FB_NET", "peers": ["R_TOP.1", "R_BTM.1"]},
                ],
                "R_TOP.1": [
                    {"net": "FB_NET", "peers": ["U1.3", "R_BTM.1"]},
                ],
                "R_TOP.2": [
                    {"net": "VIN", "peers": []},
                ],
                "R_BTM.1": [
                    {"net": "FB_NET", "peers": ["U1.3", "R_TOP.1"]},
                ],
                "R_BTM.2": [
                    {"net": "GND", "peers": []},
                ],
            },
            "warnings": {"no_net_pins": []},
            "_enriched": {
                "components": {
                    "U1": {
                        "ref": "U1",
                        "canonical_name": "TEST_REG",
                        "pin_table": [
                            {"number": 3, "name": "FB", "type": "input", "description": "Feedback"},
                        ],
                        "formulas": [
                            {"context": "Output voltage", "formula": f"Vout = {vref} * (1 + R_top/R_bottom)"},
                        ],
                        "abs_max": {},
                        "recommended": {
                            "V_OUT": {"min": rec_vmin, "max": rec_vmax},
                        },
                    },
                },
            },
        }

    def test_finds_voltage_mismatch(self) -> None:
        """R005 should flag when calculated Vout differs from recommended range."""
        # R_top=20K, R_btm=10K, Vref=0.6 -> Vout = 0.6*(1+20K/10K) = 1.8V
        # Recommended: 1.0V -- 1.2V => mismatch
        netlist = self._make_voltage_divider_netlist(
            r_top_value="20K",
            r_btm_value="10K",
            rec_vmin="1.0",
            rec_vmax="1.2",
            vref=0.6,
        )
        findings = run_rules(netlist, rule_ids=["R005"], include_datasheet_rules=True)
        assert len(findings) == 1
        assert findings[0]["severity"] == "high"
        assert findings[0]["rule_id"] == "R005"
        assert "1.800" in findings[0]["message"]

    def test_no_findings_when_ratio_matches(self) -> None:
        """R005 returns empty when divider ratio matches recommended range."""
        # R_top=5K, R_btm=2.5K, Vref=0.6 -> Vout = 0.6*(1+5K/2.5K) = 1.8V
        # Recommended: 1.7V -- 1.9V => match (within 5% tolerance)
        netlist = self._make_voltage_divider_netlist(
            r_top_value="5K",
            r_btm_value="2.5K",
            rec_vmin="1.7",
            rec_vmax="1.9",
            vref=0.6,
        )
        findings = run_rules(netlist, rule_ids=["R005"], include_datasheet_rules=True)
        assert findings == []

    def test_no_findings_when_no_enriched(self) -> None:
        """R005 returns empty when _enriched is absent."""
        netlist = {
            "schema": "chip-netlist-ai-json-v1",
            "components": {"U1": {"designator": "U1"}},
            "nets": [],
            "pins": {},
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["R005"], include_datasheet_rules=True)
        assert findings == []


# ---------------------------------------------------------------------------
# R006: Current limit check
# ---------------------------------------------------------------------------

class TestR006CurrentLimit:
    """Tests for R006: current limit out of range."""

    def _make_current_sense_netlist(
        self,
        r_sense_value: str,
        formula: str,
        max_current: str,
    ) -> dict:
        """Build a netlist with current-sense pins on U1.

        U1.CSP (pin 1) -> R_SENSE.1
        U1.CSN (pin 2) -> R_SENSE.2
        """
        return {
            "schema": "chip-netlist-ai-json-v1",
            "components": {
                "U1": {"designator": "U1"},
                "R_SENSE": {"designator": "R_SENSE", "value": r_sense_value},
            },
            "nets": [
                {"net": "CSP_NET", "connections": ["U1.1", "R_SENSE.1"]},
                {"net": "CSN_NET", "connections": ["U1.2", "R_SENSE.2"]},
            ],
            "pins": {
                "U1.1": [{"net": "CSP_NET", "peers": ["R_SENSE.1"]}],
                "U1.2": [{"net": "CSN_NET", "peers": ["R_SENSE.2"]}],
                "R_SENSE.1": [{"net": "CSP_NET", "peers": ["U1.1"]}],
                "R_SENSE.2": [{"net": "CSN_NET", "peers": ["U1.2"]}],
            },
            "warnings": {"no_net_pins": []},
            "_enriched": {
                "components": {
                    "U1": {
                        "ref": "U1",
                        "canonical_name": "TEST_CHARGER",
                        "pin_table": [
                            {"number": 1, "name": "CSP", "type": "input", "description": "Current sense +"},
                            {"number": 2, "name": "CSN", "type": "input", "description": "Current sense -"},
                        ],
                        "formulas": [
                            {"context": "Charge current", "formula": formula},
                        ],
                        "abs_max": {},
                        "recommended": {
                            "I_CHARGE": {"min": "0", "max": max_current},
                        },
                    },
                },
            },
        }

    def test_finds_current_over_limit(self) -> None:
        """R006 should flag when I_limit exceeds recommended max."""
        # R_SENSE=10m, V_sense=50mV -> I = 50mV / 10m = 5A, max=2A => over
        netlist = self._make_current_sense_netlist(
            r_sense_value="10m",
            formula="I_CHARGE = 50mV / R_SENSE",
            max_current="2",
        )
        findings = run_rules(netlist, rule_ids=["R006"], include_datasheet_rules=True)
        assert len(findings) == 1
        assert findings[0]["severity"] == "high"
        assert findings[0]["rule_id"] == "R006"
        assert "5.00A" in findings[0]["message"]

    def test_no_findings_when_within_range(self) -> None:
        """R006 returns empty when calculated current is within recommended range."""
        # R_SENSE=100m, V_sense=50mV -> I = 50mV / 100m = 0.5A, max=2A => ok
        netlist = self._make_current_sense_netlist(
            r_sense_value="100m",
            formula="I_CHARGE = 50mV / R_SENSE",
            max_current="2",
        )
        findings = run_rules(netlist, rule_ids=["R006"], include_datasheet_rules=True)
        assert findings == []

    def test_no_findings_when_no_enriched(self) -> None:
        """R006 returns empty when _enriched is absent."""
        netlist = {
            "schema": "chip-netlist-ai-json-v1",
            "components": {"U1": {"designator": "U1"}},
            "nets": [],
            "pins": {},
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["R006"], include_datasheet_rules=True)
        assert findings == []

    def test_no_findings_when_no_sense_resistor(self) -> None:
        """R006 returns empty when sense pins have no resistor connected."""
        netlist = {
            "schema": "chip-netlist-ai-json-v1",
            "components": {"U1": {"designator": "U1"}},
            "nets": [],
            "pins": {},
            "warnings": {"no_net_pins": []},
            "_enriched": {
                "components": {
                    "U1": {
                        "ref": "U1",
                        "pin_table": [
                            {"number": 1, "name": "CSP", "type": "input", "description": ""},
                            {"number": 2, "name": "CSN", "type": "input", "description": ""},
                        ],
                        "formulas": [],
                        "abs_max": {},
                        "recommended": {},
                    },
                },
            },
        }
        findings = run_rules(netlist, rule_ids=["R006"], include_datasheet_rules=True)
        assert findings == []

    def test_no_findings_when_no_formula(self) -> None:
        """R006 returns empty when no V_sense can be extracted."""
        netlist = {
            "schema": "chip-netlist-ai-json-v1",
            "components": {
                "U1": {"designator": "U1"},
                "R_SENSE": {"designator": "R_SENSE", "value": "10m"},
            },
            "nets": [
                {"net": "CSP_NET", "connections": ["U1.1", "R_SENSE.1"]},
            ],
            "pins": {
                "U1.1": [{"net": "CSP_NET", "peers": ["R_SENSE.1"]}],
                "R_SENSE.1": [{"net": "CSP_NET", "peers": ["U1.1"]}],
            },
            "warnings": {"no_net_pins": []},
            "_enriched": {
                "components": {
                    "U1": {
                        "ref": "U1",
                        "pin_table": [
                            {"number": 1, "name": "CSP", "type": "input", "description": ""},
                        ],
                        "formulas": [],
                        "abs_max": {},
                        "recommended": {},
                    },
                },
            },
        }
        findings = run_rules(netlist, rule_ids=["R006"], include_datasheet_rules=True)
        assert findings == []
