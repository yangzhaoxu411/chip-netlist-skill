"""Tests for check_rules.py rule engine runner."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Add scripts directory to path for imports
SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "chip-netlist" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from check_rules import run_rules

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
SAMPLE_NETLIST_PATH = FIXTURES_DIR / "sample_netlist.json"
CHECK_RULES_SCRIPT = SCRIPTS_DIR / "check_rules.py"


@pytest.fixture
def sample_netlist() -> dict:
    """Load the sample netlist fixture."""
    return json.loads(SAMPLE_NETLIST_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def empty_netlist() -> dict:
    """A minimal empty netlist with no components or nets."""
    return {
        "schema": "chip-netlist-ai-json-v1",
        "components": {},
        "nets": [],
        "pins": {},
        "warnings": {
            "no_net_pins": [],
            "single_point_nets": [],
            "low_connection_nets": [],
            "components_without_canonical_name": [],
        },
    }


class TestRunRules:
    """Tests for the run_rules function."""

    def test_empty_netlist_produces_no_findings(self, empty_netlist: dict) -> None:
        """Running rules against an empty netlist should produce zero findings."""
        findings = run_rules(empty_netlist)
        assert findings == []

    def test_run_rules_returns_list(self, sample_netlist: dict) -> None:
        """run_rules always returns a list (even if empty with no rules registered)."""
        findings = run_rules(sample_netlist)
        assert isinstance(findings, list)

    def test_run_rules_with_datasheet_flag(self, sample_netlist: dict) -> None:
        """run_rules with include_datasheet_rules=True still returns a list."""
        findings = run_rules(sample_netlist, include_datasheet_rules=True)
        assert isinstance(findings, list)

    def test_run_rules_filter_by_nonexistent_rule(self, sample_netlist: dict) -> None:
        """Filtering by a rule_id that doesn't exist returns empty list."""
        findings = run_rules(sample_netlist, rule_ids=["NONEXISTENT_RULE"])
        assert findings == []

    def test_run_rules_filter_by_rule_ids(self, sample_netlist: dict) -> None:
        """Filtering by rule_ids only returns findings from those rules."""
        all_findings = run_rules(sample_netlist)
        if not all_findings:
            pytest.skip("No rules registered yet to test filtering")

        # Pick a rule_id from the findings
        first_rule_id = all_findings[0]["rule_id"]
        filtered = run_rules(sample_netlist, rule_ids=[first_rule_id])
        for finding in filtered:
            assert finding["rule_id"] == first_rule_id

    def test_findings_have_required_fields(self, sample_netlist: dict) -> None:
        """Every finding must have rule_id, severity, category, target, message."""
        findings = run_rules(sample_netlist)
        required = {"rule_id", "severity", "category", "target", "message"}
        for finding in findings:
            assert required.issubset(finding.keys()), f"Missing fields in {finding}"


class TestR001FloatingPin:
    """Tests for R001: floating required pin."""

    def test_finds_no_net_pins(self, sample_netlist: dict) -> None:
        """R001 should find U1.1 and U1.2 as floating pins."""
        findings = run_rules(sample_netlist, rule_ids=["R001"])
        targets = [f["target"] for f in findings]
        assert "U1.1" in targets
        assert "U1.2" in targets

    def test_severity_is_high(self, sample_netlist: dict) -> None:
        """R001 findings should have severity 'high'."""
        findings = run_rules(sample_netlist, rule_ids=["R001"])
        for f in findings:
            assert f["severity"] == "high"

    def test_no_findings_when_clean(self, empty_netlist: dict) -> None:
        """R001 produces no findings when no_net_pins is empty."""
        findings = run_rules(empty_netlist, rule_ids=["R001"])
        assert findings == []

    def test_finding_has_suggestion(self, sample_netlist: dict) -> None:
        """R001 findings should include a suggestion."""
        findings = run_rules(sample_netlist, rule_ids=["R001"])
        for f in findings:
            assert "suggestion" in f
            assert "datasheet" in f["suggestion"].lower()


class TestR003MissingBypassCap:
    """Tests for R003: missing bypass capacitor."""

    def test_finds_vcc_without_cap(self, sample_netlist: dict) -> None:
        """R003 should flag VCC_3V3 net since no capacitor is present."""
        findings = run_rules(sample_netlist, rule_ids=["R003"])
        targets = [f["target"] for f in findings]
        assert "VCC_3V3" in targets

    def test_severity_is_high(self, sample_netlist: dict) -> None:
        """R003 findings should have severity 'high'."""
        findings = run_rules(sample_netlist, rule_ids=["R003"])
        for f in findings:
            assert f["severity"] == "high"

    def test_no_flag_when_cap_present(self) -> None:
        """R003 should not flag a power net that has a capacitor."""
        netlist = {
            "components": {
                "C1": {"designator": "C1", "canonical_name": "100nF", "value": "100nF"},
                "U1": {"designator": "U1", "canonical_name": "MCU", "value": "MCU"},
            },
            "nets": [
                {"net": "VCC_3V3", "connections": ["C1.1", "U1.1"]},
            ],
            "pins": {
                "C1.1": [{"net": "VCC_3V3", "pin_id": "p1", "peers": ["U1.1"]}],
                "U1.1": [{"net": "VCC_3V3", "pin_id": "p2", "peers": ["C1.1"]}],
            },
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["R003"])
        assert findings == []

    def test_no_flag_for_non_power_net(self) -> None:
        """R003 should not flag nets that are not power nets."""
        netlist = {
            "components": {"U1": {"designator": "U1"}},
            "nets": [{"net": "DATA0", "connections": ["U1.1"]}],
            "pins": {"U1.1": [{"net": "DATA0", "pin_id": "p1", "peers": []}]},
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["R003"])
        assert findings == []


class TestR004MissingPullup:
    """Tests for R004: missing pull-up on I2C/SMBus nets."""

    def test_no_findings_without_i2c_nets(self, sample_netlist: dict) -> None:
        """R004 should produce no findings when no I2C-like nets exist."""
        findings = run_rules(sample_netlist, rule_ids=["R004"])
        assert findings == []

    def test_finds_sda_without_resistor(self) -> None:
        """R004 should flag an SDA net without a pull-up resistor."""
        netlist = {
            "components": {"U1": {"designator": "U1"}, "U2": {"designator": "U2"}},
            "nets": [{"net": "SDA", "connections": ["U1.1", "U2.1"]}],
            "pins": {
                "U1.1": [{"net": "SDA", "pin_id": "p1", "peers": ["U2.1"]}],
                "U2.1": [{"net": "SDA", "pin_id": "p2", "peers": ["U1.1"]}],
            },
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["R004"])
        assert len(findings) == 1
        assert findings[0]["severity"] == "medium"
        assert "SDA" in findings[0]["target"]

    def test_no_flag_when_resistor_present(self) -> None:
        """R004 should not flag when a resistor is on the I2C net."""
        netlist = {
            "components": {
                "R1": {"designator": "R1", "value": "4.7K"},
                "U1": {"designator": "U1"},
            },
            "nets": [{"net": "I2C_SDA", "connections": ["R1.1", "U1.1"]}],
            "pins": {
                "R1.1": [{"net": "I2C_SDA", "pin_id": "p1", "peers": ["U1.1"]}],
                "U1.1": [{"net": "I2C_SDA", "pin_id": "p2", "peers": ["R1.1"]}],
            },
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["R004"])
        assert findings == []


class TestB001NoPartNumber:
    """Tests for B001: no real part number."""

    def test_finds_component_without_part_number(self) -> None:
        """B001 should flag components with empty manufacturer_part and canonical_name."""
        netlist = {
            "components": {
                "R1": {
                    "designator": "R1",
                    "manufacturer_part": "",
                    "canonical_name": "",
                },
            },
            "nets": [],
            "pins": {},
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["B001"])
        assert len(findings) == 1
        assert findings[0]["target"] == "R1"
        assert findings[0]["severity"] == "low"

    def test_no_flag_when_part_number_present(self, sample_netlist: dict) -> None:
        """B001 should not flag components that have a manufacturer_part."""
        findings = run_rules(sample_netlist, rule_ids=["B001"])
        # Both R1 and U1 in sample_netlist have manufacturer_part
        assert findings == []

    def test_no_flag_when_canonical_present(self) -> None:
        """B001 should not flag when canonical_name is set even if mfr part is empty."""
        netlist = {
            "components": {
                "R1": {
                    "designator": "R1",
                    "manufacturer_part": "",
                    "canonical_name": "10K",
                },
            },
            "nets": [],
            "pins": {},
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["B001"])
        assert findings == []


class TestB003MissingValue:
    """Tests for B003: missing component value."""

    def test_finds_component_without_value(self) -> None:
        """B003 should flag components with missing or empty value."""
        netlist = {
            "components": {
                "U1": {"designator": "U1", "value": None},
                "R1": {"designator": "R1", "value": ""},
                "C1": {"designator": "C1", "value": "{Value}"},
            },
            "nets": [],
            "pins": {},
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["B003"])
        targets = {f["target"] for f in findings}
        assert targets == {"U1", "R1", "C1"}

    def test_skips_test_points(self) -> None:
        """B003 should skip refs starting with 'TP'."""
        netlist = {
            "components": {
                "TP1": {"designator": "TP1", "value": ""},
            },
            "nets": [],
            "pins": {},
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["B003"])
        assert findings == []

    def test_skips_mounting_holes(self) -> None:
        """B003 should skip refs starting with 'MH'."""
        netlist = {
            "components": {
                "MH1": {"designator": "MH1", "value": ""},
            },
            "nets": [],
            "pins": {},
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["B003"])
        assert findings == []

    def test_finds_u1_in_sample_netlist(self, sample_netlist: dict) -> None:
        """U1 in sample_netlist has no 'value' field, so B003 should flag it."""
        findings = run_rules(sample_netlist, rule_ids=["B003"])
        targets = [f["target"] for f in findings]
        assert "U1" in targets

    def test_no_flag_r1_has_value(self, sample_netlist: dict) -> None:
        """R1 has value='10K' so B003 should not flag it."""
        findings = run_rules(sample_netlist, rule_ids=["B003"])
        targets = [f["target"] for f in findings]
        assert "R1" not in targets


class TestI001I2cMissingPullup:
    """Tests for I001: I2C/SMBus missing pull-up."""

    def test_no_findings_without_i2c_nets(self, sample_netlist: dict) -> None:
        """I001 should produce no findings when no I2C-like nets exist."""
        findings = run_rules(sample_netlist, rule_ids=["I001"])
        assert findings == []

    def test_finds_sda_without_resistor(self) -> None:
        """I001 should flag an SDA net without a pull-up resistor."""
        netlist = {
            "components": {"U1": {"designator": "U1"}, "U2": {"designator": "U2"}},
            "nets": [{"net": "SDA", "connections": ["U1.1", "U2.1"]}],
            "pins": {
                "U1.1": [{"net": "SDA", "pin_id": "p1", "peers": ["U2.1"]}],
                "U2.1": [{"net": "SDA", "pin_id": "p2", "peers": ["U1.1"]}],
            },
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["I001"])
        assert len(findings) == 1
        assert findings[0]["severity"] == "high"
        assert findings[0]["category"] == "interface"
        assert "SDA" in findings[0]["target"]

    def test_finds_scl_without_resistor(self) -> None:
        """I001 should flag an SCL net without a pull-up resistor."""
        netlist = {
            "components": {"U1": {"designator": "U1"}, "U2": {"designator": "U2"}},
            "nets": [{"net": "SCL", "connections": ["U1.2", "U2.2"]}],
            "pins": {
                "U1.2": [{"net": "SCL", "pin_id": "p1", "peers": ["U2.2"]}],
                "U2.2": [{"net": "SCL", "pin_id": "p2", "peers": ["U1.2"]}],
            },
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["I001"])
        assert len(findings) == 1
        assert findings[0]["severity"] == "high"

    def test_finds_smdata_without_resistor(self) -> None:
        """I001 should flag SMBus-specific net names (SMDATA, SMCLK, SMALERT)."""
        netlist = {
            "components": {"U1": {"designator": "U1"}},
            "nets": [
                {"net": "SMDATA", "connections": ["U1.1"]},
                {"net": "SMCLK", "connections": ["U1.2"]},
                {"net": "SMALERT", "connections": ["U1.3"]},
            ],
            "pins": {
                "U1.1": [{"net": "SMDATA", "pin_id": "p1", "peers": []}],
                "U1.2": [{"net": "SMCLK", "pin_id": "p2", "peers": []}],
                "U1.3": [{"net": "SMALERT", "pin_id": "p3", "peers": []}],
            },
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["I001"])
        targets = {f["target"] for f in findings}
        assert targets == {"SMDATA", "SMCLK", "SMALERT"}

    def test_no_flag_when_resistor_present(self) -> None:
        """I001 should not flag when a resistor is on the I2C net."""
        netlist = {
            "components": {
                "R1": {"designator": "R1", "value": "4.7K"},
                "U1": {"designator": "U1"},
            },
            "nets": [{"net": "I2C_SDA", "connections": ["R1.1", "U1.1"]}],
            "pins": {
                "R1.1": [{"net": "I2C_SDA", "pin_id": "p1", "peers": ["U1.1"]}],
                "U1.1": [{"net": "I2C_SDA", "pin_id": "p2", "peers": ["R1.1"]}],
            },
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["I001"])
        assert findings == []

    def test_finding_has_suggestion(self) -> None:
        """I001 findings should include a suggestion."""
        netlist = {
            "components": {"U1": {"designator": "U1"}},
            "nets": [{"net": "SDA", "connections": ["U1.1"]}],
            "pins": {
                "U1.1": [{"net": "SDA", "pin_id": "p1", "peers": []}],
            },
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["I001"])
        assert len(findings) == 1
        assert "suggestion" in findings[0]
        assert "pull-up" in findings[0]["suggestion"].lower()


class TestP001MissingReversePolarityProtection:
    """Tests for P001: missing reverse polarity protection."""

    def test_no_findings_without_input_power_nets(self, sample_netlist: dict) -> None:
        """P001 should produce no findings when no input power nets exist."""
        findings = run_rules(sample_netlist, rule_ids=["P001"])
        assert findings == []

    def test_finds_vin_without_protection(self) -> None:
        """P001 should flag a VIN net without a diode or MOSFET."""
        netlist = {
            "components": {"U1": {"designator": "U1"}},
            "nets": [{"net": "VIN", "connections": ["U1.1"]}],
            "pins": {
                "U1.1": [{"net": "VIN", "pin_id": "p1", "peers": []}],
            },
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["P001"])
        assert len(findings) == 1
        assert findings[0]["severity"] == "medium"
        assert findings[0]["category"] == "power"
        assert "VIN" in findings[0]["target"]

    def test_no_flag_when_diode_present(self) -> None:
        """P001 should not flag when a diode is on the input power net."""
        netlist = {
            "components": {
                "D1": {"designator": "D1", "value": "SS34"},
                "U1": {"designator": "U1"},
            },
            "nets": [{"net": "VIN", "connections": ["D1.1", "U1.1"]}],
            "pins": {
                "D1.1": [{"net": "VIN", "pin_id": "p1", "peers": ["U1.1"]}],
                "U1.1": [{"net": "VIN", "pin_id": "p2", "peers": ["D1.1"]}],
            },
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["P001"])
        assert findings == []

    def test_no_flag_when_mosfet_present(self) -> None:
        """P001 should not flag when a MOSFET (Q prefix) is on the input net."""
        netlist = {
            "components": {
                "Q1": {"designator": "Q1", "value": "SI2301"},
                "U1": {"designator": "U1"},
            },
            "nets": [{"net": "PWR_IN", "connections": ["Q1.1", "U1.1"]}],
            "pins": {
                "Q1.1": [{"net": "PWR_IN", "pin_id": "p1", "peers": ["U1.1"]}],
                "U1.1": [{"net": "PWR_IN", "pin_id": "p2", "peers": ["Q1.1"]}],
            },
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["P001"])
        assert findings == []

    def test_finding_is_medium_severity(self) -> None:
        """P001 findings should be 'medium' severity (worth reviewing, not must-fix)."""
        netlist = {
            "components": {"U1": {"designator": "U1"}},
            "nets": [{"net": "VBUS", "connections": ["U1.1"]}],
            "pins": {
                "U1.1": [{"net": "VBUS", "pin_id": "p1", "peers": []}],
            },
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["P001"])
        assert len(findings) == 1
        assert findings[0]["severity"] == "medium"

    def test_finding_has_suggestion(self) -> None:
        """P001 findings should include a suggestion."""
        netlist = {
            "components": {"U1": {"designator": "U1"}},
            "nets": [{"net": "VIN", "connections": ["U1.1"]}],
            "pins": {
                "U1.1": [{"net": "VIN", "pin_id": "p1", "peers": []}],
            },
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["P001"])
        assert len(findings) == 1
        assert "suggestion" in findings[0]
        assert "reverse" in findings[0]["suggestion"].lower()

    def test_no_flag_for_non_input_power_net(self) -> None:
        """P001 should not flag VCC/VDD nets (output power, not input)."""
        netlist = {
            "components": {"U1": {"designator": "U1"}},
            "nets": [{"net": "VCC_3V3", "connections": ["U1.1"]}],
            "pins": {
                "U1.1": [{"net": "VCC_3V3", "pin_id": "p1", "peers": []}],
            },
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["P001"])
        assert findings == []


class TestI002LogicLevelMismatch:
    """Tests for I002: logic level mismatch (stub)."""

    def test_returns_empty_list(self, sample_netlist: dict) -> None:
        """I002 is a stub and should always return an empty list."""
        findings = run_rules(sample_netlist, rule_ids=["I002"])
        assert findings == []

    def test_returns_empty_list_for_i2c_net(self) -> None:
        """I002 stub returns empty even with I2C nets present."""
        netlist = {
            "components": {"U1": {"designator": "U1"}, "U2": {"designator": "U2"}},
            "nets": [{"net": "SDA", "connections": ["U1.1", "U2.1"]}],
            "pins": {
                "U1.1": [{"net": "SDA", "pin_id": "p1", "peers": ["U2.1"]}],
                "U2.1": [{"net": "SDA", "pin_id": "p2", "peers": ["U1.1"]}],
            },
            "warnings": {"no_net_pins": []},
        }
        findings = run_rules(netlist, rule_ids=["I002"])
        assert findings == []


class TestFullRuleSet:
    """Integration tests for the full rule set against sample_netlist."""

    def test_full_run_produces_findings(self, sample_netlist: dict) -> None:
        """Running all basic rules against sample_netlist should produce findings."""
        findings = run_rules(sample_netlist)
        assert len(findings) > 0

    def test_full_run_findings_sorted_by_rule_id(self, sample_netlist: dict) -> None:
        """Findings should be generated in rule-id order."""
        findings = run_rules(sample_netlist)
        rule_ids = [f["rule_id"] for f in findings]
        assert rule_ids == sorted(rule_ids)

    def test_expected_findings_from_sample(self, sample_netlist: dict) -> None:
        """Verify the expected set of rule IDs triggered by sample_netlist."""
        findings = run_rules(sample_netlist)
        rule_ids = set(f["rule_id"] for f in findings)
        # R001: U1.1, U1.2 floating
        # R003: VCC_3V3 has no capacitor
        # B003: U1 has no value
        assert "R001" in rule_ids
        assert "R003" in rule_ids
        assert "B003" in rule_ids


class TestCLI:
    """Tests for the check_rules.py CLI interface."""

    def _run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CHECK_RULES_SCRIPT), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_cli_output_is_valid_json(self) -> None:
        """CLI output must parse as valid JSON with expected top-level keys."""
        result = self._run_cli(str(SAMPLE_NETLIST_PATH))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = json.loads(result.stdout)
        assert output["schema"] == "chip-netlist-findings-v1"
        assert "finding_count" in output
        assert "summary" in output
        assert "findings" in output
        assert output["source"] == str(SAMPLE_NETLIST_PATH)

    def test_cli_output_with_empty_netlist(self, tmp_path: Path) -> None:
        """CLI with empty netlist produces valid JSON with zero findings."""
        empty = tmp_path / "empty.json"
        empty.write_text(json.dumps({
            "schema": "chip-netlist-ai-json-v1",
            "components": {},
            "nets": [],
            "pins": {},
            "warnings": {},
        }), encoding="utf-8")
        result = self._run_cli(str(empty))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = json.loads(result.stdout)
        assert output["finding_count"] == 0
        assert output["summary"] == {}

    def test_cli_rules_filter(self) -> None:
        """--rules flag should filter to only specified rule IDs."""
        result = self._run_cli(str(SAMPLE_NETLIST_PATH), "--rules", "NONEXISTENT")
        assert result.returncode == 0, f"stderr: {result.stderr}"
        output = json.loads(result.stdout)
        assert output["finding_count"] == 0
        assert output["summary"] == {}

    def test_cli_output_to_file(self, tmp_path: Path) -> None:
        """--output flag writes findings to the specified file."""
        out_path = tmp_path / "findings.json"
        result = self._run_cli(str(SAMPLE_NETLIST_PATH), "--output", str(out_path))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert out_path.exists()
        output = json.loads(out_path.read_text(encoding="utf-8"))
        assert output["schema"] == "chip-netlist-findings-v1"

    def test_cli_datasheet_flag_requires_enriched_json(self) -> None:
        """--datasheet must fail loudly when enriched.json is missing."""
        result = self._run_cli(str(SAMPLE_NETLIST_PATH), "--datasheet")
        assert result.returncode != 0
        assert "enriched.json" in result.stderr

    def test_cli_severity_summary_counts(self) -> None:
        """Summary counts should match the actual findings by severity."""
        result = self._run_cli(str(SAMPLE_NETLIST_PATH))
        assert result.returncode == 0
        output = json.loads(result.stdout)
        # Verify summary matches actual findings
        expected_counts: dict[str, int] = {}
        for f in output["findings"]:
            sev = f.get("severity", "unknown")
            expected_counts[sev] = expected_counts.get(sev, 0) + 1
        assert output["summary"] == expected_counts
