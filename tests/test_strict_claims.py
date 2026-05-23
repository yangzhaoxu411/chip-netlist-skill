"""Tests for Strict Accuracy Mode claim validation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "chip-netlist" / "scripts"))
from strict_claims import build_evidence_ledger, validate_claims


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_evidence_ledger_indexes_datasheet_fact_files(tmp_path: Path) -> None:
    workdir = tmp_path / ".chip-netlist"
    _write_json(workdir / "enriched.json", {
        "components": {
            "U1": {
                "part": "ABC123",
                "manufacturer_part": "ABC123",
                "datasheet_status": "downloaded",
                "pin_table": [{"number": "1", "name": "VIN"}],
                "formulas": [{"name": "VOUT"}],
            }
        }
    })
    _write_json(workdir / "datasheet_facts" / "ABC123.json", {
        "part": "ABC123",
        "pin_table": [{"number": "1", "name": "VIN"}],
        "formulas": [{"name": "VOUT"}],
        "source_file": "datasheets/ABC123.txt",
    })

    ledger = build_evidence_ledger(workdir)

    assert ledger["schema"] == "chip-netlist-evidence-ledger-v1"
    assert ledger["components"]["U1"]["has_datasheet_facts"] is True
    assert ledger["components"]["U1"]["pin_count"] == 1
    assert ledger["components"]["U1"]["formula_count"] == 1


def test_validate_claims_rejects_chip_claim_without_datasheet_evidence(tmp_path: Path) -> None:
    workdir = tmp_path / ".chip-netlist"
    _write_json(workdir / "enriched.json", {
        "components": {
            "U1": {"part": "ABC123", "datasheet_status": "not_found"}
        }
    })
    ledger = build_evidence_ledger(workdir)
    claims = {
        "schema": "chip-netlist-claims-v1",
        "claims": [
            {
                "id": "C1",
                "claim_type": "pin_function",
                "text": "U1 pin 1 is VIN.",
                "targets": ["U1"],
                "netlist_evidence": [],
                "datasheet_evidence": [],
            }
        ],
    }

    result = validate_claims(claims, ledger)

    checked = result["claims"][0]
    assert checked["strict_status"] == "rejected"
    assert "missing_datasheet_evidence" in checked["strict_reasons"]


def test_validate_claims_accepts_chip_claim_with_matching_datasheet_evidence(tmp_path: Path) -> None:
    workdir = tmp_path / ".chip-netlist"
    _write_json(workdir / "enriched.json", {
        "components": {
            "U1": {"part": "ABC123", "datasheet_status": "downloaded", "pin_table": [{"number": "1"}]}
        }
    })
    _write_json(workdir / "datasheet_facts" / "ABC123.json", {
        "part": "ABC123",
        "pin_table": [{"number": "1", "name": "VIN"}],
    })
    ledger = build_evidence_ledger(workdir)
    claims = {
        "schema": "chip-netlist-claims-v1",
        "claims": [
            {
                "id": "C1",
                "claim_type": "pin_function",
                "text": "U1 pin 1 is VIN.",
                "targets": ["U1"],
                "netlist_evidence": [{"path": ".chip-netlist/chip_netlist.json", "target": "U1.1"}],
                "datasheet_evidence": [{"ref": "U1", "path": ".chip-netlist/datasheet_facts/ABC123.json"}],
            }
        ],
    }

    result = validate_claims(claims, ledger)

    checked = result["claims"][0]
    assert checked["strict_status"] == "accepted"
    assert checked["strict_reasons"] == []
