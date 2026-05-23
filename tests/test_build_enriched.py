"""Tests for build_enriched.py."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Ensure the scripts directory is importable
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "chip-netlist" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from build_enriched import (
    build_enriched,
    build_facts_index,
    determine_datasheet_status,
    load_json,
    main,
    match_facts_file,
    sanitize_filename,
)

BUILD_SCRIPT = SCRIPTS_DIR / "build_enriched.py"


# ---------------------------------------------------------------------------
# Fixtures: mock data
# ---------------------------------------------------------------------------


def _make_component_index(components: dict | None = None) -> dict:
    """Create a minimal component_index.json structure."""
    return {
        "schema": "chip-netlist-component-index-v1",
        "component_count": len(components) if components else 0,
        "components": components or {},
    }


def _make_datasheet_sources(sources: dict | None = None) -> dict:
    """Create a minimal datasheet_sources.json structure."""
    return {
        "schema": "chip-netlist-datasheet-sources-v1",
        "sources": sources or {},
    }


def _make_facts(part: str, quality: str = "complete", pins: int = 5) -> dict:
    """Create a minimal facts JSON structure."""
    pin_table = [
        {"number": i, "name": f"PIN{i}", "type": "signal", "description": f"Pin {i}"}
        for i in range(1, pins + 1)
    ]
    return {
        "schema": "chip-netlist-datasheet-facts-v1",
        "part": part,
        "source_file": f"datasheets/{part}.txt",
        "pin_table": pin_table,
        "formulas": [{"context": "test", "formula": "V = I * R", "variables": {}}],
        "abs_max": {"V_IN": {"min": "-0.3V", "max": "42V"}},
        "recommended": {"V_IN": {"min": "4.5V", "max": "35V"}},
        "extraction_quality": quality,
        "extraction_notes": [f"Found {pins} pin entries"],
    }


# ---------------------------------------------------------------------------
# Test sanitize_filename
# ---------------------------------------------------------------------------


class TestSanitizeFilename:
    """Test filename sanitization."""

    def test_simple_name(self):
        assert sanitize_filename("LTC4015") == "LTC4015"

    def test_slash_replaced(self):
        assert sanitize_filename("LM5069MM-1/NOPB") == "LM5069MM-1_NOPB"

    def test_special_chars(self):
        # : * ? " < > | — 7 unsafe characters
        assert sanitize_filename('test:*?"<>|file') == "test_______file"

    def test_parentheses_kept(self):
        """Parentheses are not in the unsafe set."""
        assert sanitize_filename("SI7617DN(ES)") == "SI7617DN(ES)"


# ---------------------------------------------------------------------------
# Test build_facts_index
# ---------------------------------------------------------------------------


class TestBuildFactsIndex:
    """Test facts file indexing."""

    def test_empty_directory(self, tmp_path: Path):
        facts_dir = tmp_path / "datasheet_facts"
        facts_dir.mkdir()
        index = build_facts_index(facts_dir)
        assert index == {}

    def test_nonexistent_directory(self, tmp_path: Path):
        facts_dir = tmp_path / "nonexistent"
        index = build_facts_index(facts_dir)
        assert index == {}

    def test_indexes_by_stem(self, tmp_path: Path):
        facts_dir = tmp_path / "datasheet_facts"
        facts_dir.mkdir()
        facts_file = facts_dir / "LTC4015.json"
        facts_file.write_text(json.dumps(_make_facts("LTC4015")), encoding="utf-8")

        index = build_facts_index(facts_dir)
        assert "ltc4015" in index
        assert index["ltc4015"] == facts_file

    def test_indexes_by_part_field(self, tmp_path: Path):
        facts_dir = tmp_path / "datasheet_facts"
        facts_dir.mkdir()
        # File named differently from part field
        facts_file = facts_dir / "chip_A.json"
        facts_file.write_text(
            json.dumps(_make_facts("LTC4015IUHF")), encoding="utf-8"
        )

        index = build_facts_index(facts_dir)
        # Should be indexed by both stem and part
        assert "chip_a" in index
        assert "ltc4015iuhf" in index

    def test_skips_malformed_json(self, tmp_path: Path):
        facts_dir = tmp_path / "datasheet_facts"
        facts_dir.mkdir()
        good = facts_dir / "good.json"
        good.write_text(json.dumps(_make_facts("GOOD")), encoding="utf-8")
        bad = facts_dir / "bad.json"
        bad.write_text("not json {{{", encoding="utf-8")

        index = build_facts_index(facts_dir)
        assert "good" in index
        assert "bad" in index  # Stem is still indexed even if JSON is bad


# ---------------------------------------------------------------------------
# Test match_facts_file
# ---------------------------------------------------------------------------


class TestMatchFactsFile:
    """Test component-to-facts matching."""

    def test_match_by_manufacturer_part(self, tmp_path: Path):
        facts_dir = tmp_path / "datasheet_facts"
        facts_dir.mkdir()
        facts_file = facts_dir / "LTC4015IUHF_TRPBF.json"
        facts_file.write_text(
            json.dumps(_make_facts("LTC4015IUHF#TRPBF")), encoding="utf-8"
        )

        index = build_facts_index(facts_dir)
        comp = {"manufacturer_part": "LTC4015IUHF#TRPBF", "canonical_name": "LTC4015"}
        result = match_facts_file("U1", comp, index)
        assert result == facts_file

    def test_match_by_canonical_name(self, tmp_path: Path):
        facts_dir = tmp_path / "datasheet_facts"
        facts_dir.mkdir()
        facts_file = facts_dir / "LM74700.json"
        facts_file.write_text(json.dumps(_make_facts("LM74700")), encoding="utf-8")

        index = build_facts_index(facts_dir)
        comp = {"manufacturer_part": None, "canonical_name": "LM74700"}
        result = match_facts_file("U5", comp, index)
        assert result == facts_file

    def test_match_by_ref(self, tmp_path: Path):
        facts_dir = tmp_path / "datasheet_facts"
        facts_dir.mkdir()
        facts_file = facts_dir / "U1.json"
        facts_file.write_text(json.dumps(_make_facts("U1")), encoding="utf-8")

        index = build_facts_index(facts_dir)
        comp = {"manufacturer_part": None, "canonical_name": "Unknown"}
        result = match_facts_file("U1", comp, index)
        assert result == facts_file

    def test_no_match(self, tmp_path: Path):
        facts_dir = tmp_path / "datasheet_facts"
        facts_dir.mkdir()
        facts_file = facts_dir / "OTHER.json"
        facts_file.write_text(json.dumps(_make_facts("OTHER")), encoding="utf-8")

        index = build_facts_index(facts_dir)
        comp = {"manufacturer_part": "NOMATCH", "canonical_name": "NOMATCH"}
        result = match_facts_file("U99", comp, index)
        assert result is None

    def test_manufacturer_part_takes_priority(self, tmp_path: Path):
        facts_dir = tmp_path / "datasheet_facts"
        facts_dir.mkdir()
        mfr_file = facts_dir / "MFR_PART.json"
        mfr_file.write_text(json.dumps(_make_facts("MFR_PART")), encoding="utf-8")
        canonical_file = facts_dir / "CANONICAL.json"
        canonical_file.write_text(
            json.dumps(_make_facts("CANONICAL")), encoding="utf-8"
        )

        index = build_facts_index(facts_dir)
        comp = {"manufacturer_part": "MFR_PART", "canonical_name": "CANONICAL"}
        result = match_facts_file("U1", comp, index)
        assert result == mfr_file


# ---------------------------------------------------------------------------
# Test determine_datasheet_status
# ---------------------------------------------------------------------------


class TestDetermineDatasheetStatus:
    """Test datasheet status determination."""

    def test_has_facts_downloaded(self):
        status = determine_datasheet_status(
            "U1", {}, {}, has_facts=True
        )
        assert status == "downloaded"

    def test_source_downloaded_no_facts(self):
        sources = {"U1": {"status": "downloaded"}}
        status = determine_datasheet_status(
            "U1", {}, sources, has_facts=False
        )
        assert status == "downloaded_no_facts"

    def test_source_not_found(self):
        sources = {"U1": {"status": "not_found"}}
        status = determine_datasheet_status(
            "U1", {}, sources, has_facts=False
        )
        assert status == "not_found"

    def test_target_not_downloaded(self):
        comp = {"datasheet_target": True}
        status = determine_datasheet_status(
            "U1", comp, {}, has_facts=False
        )
        assert status == "not_downloaded"

    def test_not_target(self):
        comp = {"datasheet_target": False}
        status = determine_datasheet_status(
            "R1", comp, {}, has_facts=False
        )
        assert status == "not_target"


# ---------------------------------------------------------------------------
# Test build_enriched
# ---------------------------------------------------------------------------


class TestBuildEnriched:
    """Test the full enriched build pipeline."""

    def test_basic_merge(self, tmp_path: Path):
        """Components with facts should be merged correctly."""
        comp_index = _make_component_index({
            "U1": {
                "canonical_name": "LTC4015",
                "manufacturer_part": "LTC4015IUHF#TRPBF",
                "manufacturer": "ADI",
                "value": None,
                "supplier_footprint": "QFN-38",
                "datasheet": "https://example.com/ds.pdf",
                "datasheet_target": True,
                "priority": "high",
            },
        })
        sources = _make_datasheet_sources({
            "U1": {
                "part": "LTC4015IUHF#TRPBF",
                "status": "downloaded",
                "url": "https://example.com/ds.pdf",
                "local_path": "datasheets/LTC4015IUHF_TRPBF.pdf",
            },
        })
        facts_dir = tmp_path / "datasheet_facts"
        facts_dir.mkdir()
        (facts_dir / "LTC4015IUHF_TRPBF.json").write_text(
            json.dumps(_make_facts("LTC4015IUHF#TRPBF")), encoding="utf-8"
        )

        result = build_enriched(comp_index, sources, facts_dir)

        assert result["schema"] == "chip-netlist-enriched-v1"
        assert result["component_count"] == 1
        assert result["enriched_count"] == 1
        assert "U1" in result["components"]

        u1 = result["components"]["U1"]
        assert u1["ref"] == "U1"
        assert u1["canonical_name"] == "LTC4015"
        assert u1["manufacturer"] == "ADI"
        assert u1["datasheet_status"] == "downloaded"
        assert len(u1["pin_table"]) == 5
        assert u1["extraction_quality"] == "complete"

    def test_component_without_facts(self, tmp_path: Path):
        """Components without facts should get empty data."""
        comp_index = _make_component_index({
            "R1": {
                "canonical_name": "10K",
                "manufacturer_part": None,
                "manufacturer": None,
                "value": "10K",
                "supplier_footprint": "0402",
                "datasheet": None,
                "datasheet_target": False,
                "priority": "skip",
            },
        })
        sources = _make_datasheet_sources()
        facts_dir = tmp_path / "datasheet_facts"
        facts_dir.mkdir()

        result = build_enriched(comp_index, sources, facts_dir)

        assert result["component_count"] == 1
        assert result["enriched_count"] == 0

        r1 = result["components"]["R1"]
        assert r1["ref"] == "R1"
        assert r1["datasheet_status"] == "not_target"
        assert r1["pin_table"] == []
        assert r1["formulas"] == []
        assert r1["abs_max"] == {}
        assert r1["recommended"] == {}
        assert r1["extraction_quality"] == "none"

    def test_mixed_components(self, tmp_path: Path):
        """Mix of components with and without facts."""
        comp_index = _make_component_index({
            "U1": {
                "canonical_name": "LTC4015",
                "manufacturer_part": "LTC4015",
                "manufacturer": "ADI",
                "datasheet_target": True,
                "priority": "high",
            },
            "R1": {
                "canonical_name": "10K",
                "manufacturer_part": None,
                "manufacturer": None,
                "datasheet_target": False,
                "priority": "skip",
            },
            "U5": {
                "canonical_name": "LM74700",
                "manufacturer_part": "LM74700QDBVRQ1",
                "manufacturer": "TI",
                "datasheet_target": True,
                "priority": "high",
            },
        })
        sources = _make_datasheet_sources({
            "U1": {"status": "downloaded", "local_path": "datasheets/LTC4015.pdf"},
            "U5": {"status": "not_found"},
        })
        facts_dir = tmp_path / "datasheet_facts"
        facts_dir.mkdir()
        (facts_dir / "LTC4015.json").write_text(
            json.dumps(_make_facts("LTC4015", quality="complete")), encoding="utf-8"
        )

        result = build_enriched(comp_index, sources, facts_dir)

        assert result["component_count"] == 3
        assert result["enriched_count"] == 1
        assert result["components"]["U1"]["datasheet_status"] == "downloaded"
        assert result["components"]["R1"]["datasheet_status"] == "not_target"
        assert result["components"]["U5"]["datasheet_status"] == "not_found"

    def test_output_schema_fields(self, tmp_path: Path):
        """Output should have all required top-level fields."""
        comp_index = _make_component_index()
        sources = _make_datasheet_sources()
        facts_dir = tmp_path / "datasheet_facts"
        facts_dir.mkdir()

        result = build_enriched(comp_index, sources, facts_dir)

        assert "schema" in result
        assert "generated_at" in result
        assert "component_count" in result
        assert "enriched_count" in result
        assert "quality_summary" in result
        assert "components" in result

    def test_component_entry_fields(self, tmp_path: Path):
        """Each component entry should have all required fields."""
        comp_index = _make_component_index({
            "U1": {
                "canonical_name": "TEST",
                "manufacturer_part": "TEST",
                "manufacturer": "TEST_MFR",
                "value": None,
                "supplier_footprint": "SOIC-8",
                "datasheet": "https://example.com",
                "datasheet_target": True,
                "priority": "high",
            },
        })
        sources = _make_datasheet_sources()
        facts_dir = tmp_path / "datasheet_facts"
        facts_dir.mkdir()

        result = build_enriched(comp_index, sources, facts_dir)
        entry = result["components"]["U1"]

        required_fields = [
            "ref", "canonical_name", "manufacturer", "manufacturer_part",
            "value", "footprint", "datasheet_url", "datasheet_status",
            "datasheet_local", "pin_table", "formulas", "abs_max",
            "recommended", "extraction_quality", "extraction_notes",
        ]
        for field in required_fields:
            assert field in entry, f"Missing field: {field}"

    def test_generated_at_is_iso_format(self, tmp_path: Path):
        """generated_at should be a valid ISO timestamp."""
        comp_index = _make_component_index()
        sources = _make_datasheet_sources()
        facts_dir = tmp_path / "datasheet_facts"
        facts_dir.mkdir()

        result = build_enriched(comp_index, sources, facts_dir)
        # Should be parseable as ISO format
        assert "T" in result["generated_at"]
        assert result["generated_at"].endswith("+00:00") or "Z" in result["generated_at"] or "+" in result["generated_at"]

    def test_components_sorted_naturally(self, tmp_path: Path):
        """Components should be sorted by natural ref order."""
        comp_index = _make_component_index({
            "U10": {"canonical_name": "A"},
            "U2": {"canonical_name": "B"},
            "U1": {"canonical_name": "C"},
            "R1": {"canonical_name": "D"},
        })
        sources = _make_datasheet_sources()
        facts_dir = tmp_path / "datasheet_facts"
        facts_dir.mkdir()

        result = build_enriched(comp_index, sources, facts_dir)
        refs = list(result["components"].keys())
        assert refs == ["R1", "U1", "U2", "U10"]

    def test_quality_summary(self, tmp_path: Path):
        """Quality summary should count extraction qualities."""
        comp_index = _make_component_index({
            "U1": {"canonical_name": "A", "manufacturer_part": "A", "datasheet_target": True},
            "U2": {"canonical_name": "B", "manufacturer_part": "B", "datasheet_target": True},
            "U3": {"canonical_name": "C", "manufacturer_part": "C", "datasheet_target": True},
        })
        sources = _make_datasheet_sources()
        facts_dir = tmp_path / "datasheet_facts"
        facts_dir.mkdir()
        (facts_dir / "A.json").write_text(
            json.dumps(_make_facts("A", quality="complete")), encoding="utf-8"
        )
        (facts_dir / "B.json").write_text(
            json.dumps(_make_facts("B", quality="partial")), encoding="utf-8"
        )
        (facts_dir / "C.json").write_text(
            json.dumps(_make_facts("C", quality="minimal")), encoding="utf-8"
        )

        result = build_enriched(comp_index, sources, facts_dir)
        assert result["quality_summary"]["complete"] == 1
        assert result["quality_summary"]["partial"] == 1
        assert result["quality_summary"]["minimal"] == 1


# ---------------------------------------------------------------------------
# Test main() function
# ---------------------------------------------------------------------------


class TestMainFunction:
    """Test the main() CLI function."""

    def test_missing_component_index(self, tmp_path: Path):
        """Should return error code when component_index.json is missing."""
        ret = main(["--workdir", str(tmp_path)])
        assert ret == 1

    def test_default_output_path(self, tmp_path: Path):
        """Default output should be <workdir>/enriched.json."""
        comp_index = _make_component_index()
        (tmp_path / "component_index.json").write_text(
            json.dumps(comp_index), encoding="utf-8"
        )

        ret = main(["--workdir", str(tmp_path)])
        assert ret == 0
        assert (tmp_path / "enriched.json").exists()

    def test_custom_output_path(self, tmp_path: Path):
        """--output should override default output path."""
        comp_index = _make_component_index()
        (tmp_path / "component_index.json").write_text(
            json.dumps(comp_index), encoding="utf-8"
        )
        output_path = tmp_path / "custom" / "out.json"

        ret = main(["--workdir", str(tmp_path), "--output", str(output_path)])
        assert ret == 0
        assert output_path.exists()

    def test_output_is_valid_json(self, tmp_path: Path):
        """Output should be valid JSON with correct schema."""
        comp_index = _make_component_index()
        (tmp_path / "component_index.json").write_text(
            json.dumps(comp_index), encoding="utf-8"
        )
        output_path = tmp_path / "enriched.json"

        ret = main(["--workdir", str(tmp_path), "--output", str(output_path)])
        assert ret == 0

        data = json.loads(output_path.read_text(encoding="utf-8"))
        assert data["schema"] == "chip-netlist-enriched-v1"

    def test_with_datasheet_sources(self, tmp_path: Path):
        """Should use datasheet_sources.json when present."""
        comp_index = _make_component_index({
            "U1": {
                "canonical_name": "CHIP",
                "manufacturer_part": "CHIP",
                "datasheet_target": True,
                "priority": "high",
            },
        })
        (tmp_path / "component_index.json").write_text(
            json.dumps(comp_index), encoding="utf-8"
        )
        sources = _make_datasheet_sources({
            "U1": {"status": "downloaded", "local_path": "datasheets/CHIP.pdf"},
        })
        (tmp_path / "datasheet_sources.json").write_text(
            json.dumps(sources), encoding="utf-8"
        )
        facts_dir = tmp_path / "datasheet_facts"
        facts_dir.mkdir()
        (facts_dir / "CHIP.json").write_text(
            json.dumps(_make_facts("CHIP")), encoding="utf-8"
        )

        output_path = tmp_path / "enriched.json"
        ret = main(["--workdir", str(tmp_path), "--output", str(output_path)])
        assert ret == 0

        data = json.loads(output_path.read_text(encoding="utf-8"))
        assert data["enriched_count"] == 1
        assert data["components"]["U1"]["datasheet_status"] == "downloaded"


# ---------------------------------------------------------------------------
# Test CLI via subprocess
# ---------------------------------------------------------------------------


class TestCLI:
    """Tests for the build_enriched.py CLI via subprocess."""

    def _run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(BUILD_SCRIPT), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_missing_workdir(self):
        result = self._run_cli("--workdir", "/nonexistent/path")
        assert result.returncode != 0

    def test_basic_run(self, tmp_path: Path):
        comp_index = _make_component_index()
        (tmp_path / "component_index.json").write_text(
            json.dumps(comp_index), encoding="utf-8"
        )
        result = self._run_cli("--workdir", str(tmp_path))
        assert result.returncode == 0
        assert (tmp_path / "enriched.json").exists()

    def test_output_flag(self, tmp_path: Path):
        comp_index = _make_component_index()
        (tmp_path / "component_index.json").write_text(
            json.dumps(comp_index), encoding="utf-8"
        )
        output = tmp_path / "out.json"
        result = self._run_cli("--workdir", str(tmp_path), "--output", str(output))
        assert result.returncode == 0
        assert output.exists()

    def test_stderr_summary(self, tmp_path: Path):
        """Should print summary to stderr."""
        comp_index = _make_component_index({
            "U1": {"canonical_name": "A", "manufacturer_part": "A", "datasheet_target": True},
            "R1": {"canonical_name": "10K", "datasheet_target": False},
        })
        (tmp_path / "component_index.json").write_text(
            json.dumps(comp_index), encoding="utf-8"
        )
        facts_dir = tmp_path / "datasheet_facts"
        facts_dir.mkdir()
        (facts_dir / "A.json").write_text(
            json.dumps(_make_facts("A")), encoding="utf-8"
        )

        result = self._run_cli("--workdir", str(tmp_path))
        assert result.returncode == 0
        assert "Enriched:" in result.stderr
        assert "1/2" in result.stderr

    def test_json_output_format(self, tmp_path: Path):
        """Output JSON should have correct structure."""
        comp_index = _make_component_index({
            "U1": {
                "canonical_name": "CHIP",
                "manufacturer_part": "CHIP",
                "manufacturer": "MFR",
                "datasheet_target": True,
            },
        })
        (tmp_path / "component_index.json").write_text(
            json.dumps(comp_index), encoding="utf-8"
        )

        result = self._run_cli("--workdir", str(tmp_path))
        assert result.returncode == 0

        data = json.loads((tmp_path / "enriched.json").read_text(encoding="utf-8"))
        assert data["schema"] == "chip-netlist-enriched-v1"
        assert "generated_at" in data
        assert "component_count" in data
        assert "enriched_count" in data
        assert "components" in data
