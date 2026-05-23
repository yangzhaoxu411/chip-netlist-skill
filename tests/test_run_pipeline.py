"""Tests for the deterministic run_pipeline.py orchestrator."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "chip-netlist" / "scripts"))
from run_pipeline import build_analysis_stub, build_strict_claims_draft, collect_limitations, resolve_workdir, write_json_file


def test_collect_limitations_reports_missing_datasheet_artifacts(tmp_path: Path) -> None:
    """Missing datasheet evidence is recorded as a limitation, not guessed over."""
    workdir = tmp_path / ".chip-netlist"
    workdir.mkdir()
    sources = {
        "sources": {
            "U1": {"part": "STM32F103C8T6", "status": "not_found"},
            "U2": {"part": "LM74700", "status": "downloaded"},
        }
    }
    enriched = {
        "components": {
            "U1": {"part": "STM32F103C8T6", "datasheet_status": "not_found"},
            "U2": {"part": "LM74700", "datasheet_status": "downloaded_no_facts"},
        }
    }
    write_json_file(workdir / "datasheet_sources.json", sources)
    write_json_file(workdir / "enriched.json", enriched)

    limitations = collect_limitations(workdir, pdftotext_available=False)

    reasons = [item["reason"] for item in limitations["limitations"]]
    assert "pdftotext_not_available" in reasons
    assert "datasheet_not_found" in reasons
    assert "datasheet_facts_missing" in reasons


def test_build_analysis_stub_defers_deep_review_to_user_requested_mode(tmp_path: Path) -> None:
    """The default pipeline creates structured inputs but no free-form conclusions."""
    workdir = tmp_path / ".chip-netlist"
    workdir.mkdir()
    findings_path = workdir / "findings.json"
    limitations_path = workdir / "limitations.json"
    write_json_file(findings_path, {
        "finding_count": 1,
        "findings": [{"rule_id": "R001", "severity": "high", "target": "U1.1"}],
    })
    write_json_file(limitations_path, {"limitations": [{"reason": "datasheet_not_found"}]})

    stub = build_analysis_stub(
        project_name="Demo",
        project_file=Path("demo.epro2"),
        workdir=workdir,
        findings_path=findings_path,
        limitations_path=limitations_path,
    )

    assert stub["schema"] == "chip-netlist-analysis-stub-v1"
    assert stub["mode"] == "strict-auto-scan"
    assert stub["requires_user_requested_deep_review"] is True
    assert stub["conclusions"] == []
    assert stub["inputs"]["findings"] == str(findings_path)
    assert stub["summary"]["finding_count"] == 1


def test_resolve_workdir_places_relative_paths_under_project_root(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    resolved = resolve_workdir(Path(".chip-netlist"), project_root)

    assert resolved == project_root / ".chip-netlist"


def test_build_strict_claims_draft_contains_no_unverified_claims(tmp_path: Path) -> None:
    workdir = tmp_path / ".chip-netlist"
    workdir.mkdir()

    draft = build_strict_claims_draft(workdir)

    assert draft["schema"] == "chip-netlist-claims-v1"
    assert draft["mode"] == "strict"
    assert draft["claims"] == []
    assert draft["instruction"] == "Add claims only after citing netlist_evidence and datasheet_evidence."
