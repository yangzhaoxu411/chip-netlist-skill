"""Tests for generate_report.py."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Ensure the scripts directory is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "chip-netlist" / "scripts"))
from generate_report import generate_report


# ---------------------------------------------------------------------------
# Unit tests for generate_report()
# ---------------------------------------------------------------------------


class TestGenerateReportEmpty:
    """Test 1: generate_report() with empty findings -> just header + summary."""

    def test_empty_findings(self):
        report = generate_report([])
        assert "# Chip Netlist Report" in report
        assert "## Summary" in report
        assert "**Total** | **0**" in report
        # No severity sections should appear
        assert "## HIGH" not in report
        assert "## MEDIUM" not in report

    def test_empty_findings_with_project(self):
        report = generate_report([], project_name="TestProj")
        assert "**Project:** TestProj" in report


class TestSeveritySorting:
    """Test 2: Multiple severities are sorted correctly."""

    def test_sort_order(self):
        findings = [
            {"rule_id": "R003", "severity": "low", "message": "low issue"},
            {"rule_id": "R001", "severity": "high", "message": "high issue"},
            {"rule_id": "R004", "severity": "info", "message": "info issue"},
            {"rule_id": "R002", "severity": "medium", "message": "medium issue"},
            {"rule_id": "R000", "severity": "must-fix", "message": "must-fix issue"},
        ]
        report = generate_report(findings)

        # Sections must appear in severity order
        pos_mustfix = report.index("## MUST FIX")
        pos_high = report.index("## HIGH")
        pos_medium = report.index("## MEDIUM")
        pos_low = report.index("## LOW")
        pos_info = report.index("## INFO")

        assert pos_mustfix < pos_high < pos_medium < pos_low < pos_info

    def test_unknown_severity_at_end(self):
        findings = [
            {"rule_id": "R001", "severity": "unknown", "message": "unknown issue"},
            {"rule_id": "R002", "severity": "high", "message": "high issue"},
        ]
        report = generate_report(findings)
        pos_high = report.index("## HIGH")
        pos_unknown = report.index("## UNKNOWN")
        assert pos_high < pos_unknown


class TestFieldPresence:
    """Test 3: Findings with and without optional fields."""

    def test_finding_with_all_fields(self):
        finding = {
            "rule_id": "R001",
            "severity": "high",
            "target": "U1.38",
            "net": "VCC_3V3",
            "message": "Pin floating",
            "suggestion": "Connect per datasheet",
        }
        report = generate_report([finding])
        assert "[R001]" in report
        assert "U1.38" in report
        assert "`VCC_3V3`" in report
        assert "Pin floating" in report
        assert "Connect per datasheet" in report

    def test_finding_without_optional_fields(self):
        finding = {
            "rule_id": "R002",
            "severity": "medium",
            "message": "Some issue",
        }
        report = generate_report([finding])
        assert "[R002]" in report
        assert "Some issue" in report
        # target defaults to "?"
        assert "?]" in report or "[R002] ?" in report
        # No net line should appear
        assert "**Net:**" not in report
        # No suggestion line should appear
        assert "**Suggestion:**" not in report

    def test_severity_defaults_to_unknown(self):
        finding = {"rule_id": "R003", "message": "no severity"}
        report = generate_report([finding])
        assert "## UNKNOWN" in report

    def test_summary_counts(self):
        findings = [
            {"severity": "high"},
            {"severity": "high"},
            {"severity": "low"},
        ]
        report = generate_report(findings)
        assert "| HIGH | 2 |" in report
        assert "| LOW | 1 |" in report
        assert "**Total** | **3**" in report


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestCLI:
    """Test 4 & 5: CLI with --project flag and --output writes to file."""

    SCRIPT = str(Path(__file__).resolve().parent.parent / "chip-netlist" / "scripts" / "generate_report.py")

    @staticmethod
    def _write_findings(tmp_path: Path, findings: list[dict]) -> Path:
        """Helper: write a findings JSON file and return its path."""
        data = {
            "schema": "chip-netlist-findings-v1",
            "source": "test.json",
            "finding_count": len(findings),
            "summary": {},
            "findings": findings,
        }
        fp = tmp_path / "findings.json"
        fp.write_text(json.dumps(data), encoding="utf-8")
        return fp

    def test_cli_project_flag(self, tmp_path):
        fp = self._write_findings(tmp_path, [{"severity": "low", "message": "test"}])
        result = subprocess.run(
            [sys.executable, self.SCRIPT, str(fp), "--project", "MyProject"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "**Project:** MyProject" in result.stdout

    def test_cli_output_writes_file(self, tmp_path):
        fp = self._write_findings(tmp_path, [{"severity": "high", "message": "issue"}])
        out_path = tmp_path / "report.md"
        result = subprocess.run(
            [sys.executable, self.SCRIPT, str(fp), "--output", str(out_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert out_path.exists()
        content = out_path.read_text(encoding="utf-8")
        assert "# Chip Netlist Report" in content
        assert "issue" in content

    def test_cli_stdout_without_output(self, tmp_path):
        fp = self._write_findings(tmp_path, [{"severity": "info", "message": "note"}])
        result = subprocess.run(
            [sys.executable, self.SCRIPT, str(fp)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "note" in result.stdout
