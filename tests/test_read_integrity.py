"""Tests for file-read integrity gates."""
from __future__ import annotations

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "chip-netlist" / "scripts"))
from parse_project import analyze
from run_pipeline import build_artifact_integrity_audit


def _record(record_type: str, record_id: str, data: dict[str, object]) -> str:
    meta = {"type": record_type, "id": record_id}
    return json.dumps(meta, separators=(",", ":")) + "||" + json.dumps(data, separators=(",", ":")) + "|\n"


def test_analyze_marks_componentless_project_as_read_integrity_failed(tmp_path: Path) -> None:
    """A readable file with no schematic components must not be treated as analyzable."""
    project = tmp_path / "empty.epro"
    project.write_text(
        _record("DOCHEAD", "doc1", {"docType": "SCHEMATIC", "uuid": "sheet1"}),
        encoding="utf-8",
    )

    result = analyze(project)

    integrity = result["read_integrity"]
    assert integrity["status"] == "failed"
    assert "schematic_components_found" in integrity["failed_required_checks"]
    assert "schematic_nets_found" in integrity["failed_required_checks"]
    assert result["ai_use"]["read_integrity_policy"] == (
        "If read_integrity.status is not passed, do not make chip-level conclusions."
    )


def test_analyze_marks_valid_minimal_project_as_read_integrity_passed(tmp_path: Path) -> None:
    """A minimal project with components and real pin connectivity passes read integrity."""
    project = tmp_path / "minimal.epro"
    project.write_text(
        "".join([
            _record("COMPONENT", "comp_r1", {"partId": "res.1"}),
            _record("ATTR", "attr_r1_ref", {"parentId": "comp_r1", "key": "Designator", "value": "R1"}),
            _record("ATTR", "attr_r1_val", {"parentId": "comp_r1", "key": "Value", "value": "10K"}),
            _record("COMPONENT", "comp_u1", {"partId": "mcu.1"}),
            _record("ATTR", "attr_u1_ref", {"parentId": "comp_u1", "key": "Designator", "value": "U1"}),
            _record("ATTR", "attr_u1_val", {"parentId": "comp_u1", "key": "Manufacturer Part", "value": "STM32F103C8T6"}),
            _record("PAD_NET", '["PAD_NET","comp_r1","1","pin_r1_1"]', {"padNet": "VCC"}),
            _record("PAD_NET", '["PAD_NET","comp_u1","1","pin_u1_1"]', {"padNet": "VCC"}),
        ]),
        encoding="utf-8",
    )

    result = analyze(project)

    integrity = result["read_integrity"]
    assert integrity["status"] == "passed"
    assert integrity["failed_required_checks"] == []
    assert integrity["metrics"]["component_count"] == 2
    assert integrity["metrics"]["net_count"] == 1
    assert integrity["metrics"]["connected_pin_count"] == 2


def test_artifact_integrity_audit_rejects_mismatched_workbench_counts() -> None:
    """Generated artifacts are cross-checked before later analysis can proceed."""
    chip_netlist = {
        "schema": "chip-netlist-ai-json-v1",
        "read_integrity": {"status": "passed"},
        "component_count": 2,
        "net_count": 1,
        "components": {"R1": {}, "U1": {}},
        "nets": [{"net": "VCC", "connections": ["R1.1", "U1.1"]}],
        "pins": {"R1.1": [{"net": "VCC"}], "U1.1": [{"net": "VCC"}]},
    }
    component_index = {
        "schema": "chip-netlist-component-index-v1",
        "component_count": 1,
        "components": {"R1": {}},
    }

    audit = build_artifact_integrity_audit(chip_netlist, component_index)

    assert audit["status"] == "failed"
    assert "component_index_count_matches_chip_netlist" in audit["failed_required_checks"]
    assert audit["policy"] == "If status is failed, stop and report read_integrity_failed instead of analyzing."
