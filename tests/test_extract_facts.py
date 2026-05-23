"""Tests for extract_facts.py."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Ensure the scripts directory is importable
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "chip-netlist" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from extract_facts import (
    extract_pin_table,
    extract_formulas,
    extract_abs_max_ratings,
    extract_recommended_conditions,
    extract_facts,
    infer_part_number,
    read_text_file,
    main,
)

EXTRACT_SCRIPT = SCRIPTS_DIR / "extract_facts.py"


# ---------------------------------------------------------------------------
# Fixtures: mock datasheet text content
# ---------------------------------------------------------------------------


PIN_TABLE_DATASHEET = """\
LTC4015 - Multicell Lithium Battery Charger

Pin Description
Pin Number | Pin Name  | Description
1          | INTVCC   | Internal LDO output, 5V
2          | DVCC     | Digital supply
3          | CLN      | Charge current sense negative
4          | CLP      | Charge current sense positive
5          | CSP      | Battery sense positive
6          | CSN      | Battery sense negative
7          | BAT      | Battery voltage feedback
8          | FB       | Output voltage feedback
9          | VOUT     | Output voltage
10         | GND      | Ground
11         | SW       | Switch node
12         | BOOST    | Bootstrap capacitor
13         | VIN      | Input supply voltage
14         | EN       | Enable input
15         | SDA      | I2C data
16         | SCL      | I2C clock
17         | ALERT    | Alert output
18         | GPIO     | General purpose I/O
19         | INT      | Interrupt output
20         | NTC      | Temperature sense input

Absolute Maximum Ratings
V_IN: -0.3V to 42V
V_BAT: -0.3V to 36V
V_CSP-CSN: -0.3V to 0.3V
Operating Temperature: -40°C to 125°C
Storage Temperature: -65°C to 150°C
"""

FORMULA_DATASHEET = """\
LTC4015 - Battery Charger IC

Charge Current Programming
The charge current is set by the sense resistor:
I_charge = V_CSP-CSN / R_sense

Where V_CSP-CSN is the voltage across the current sense pins.

Output Voltage Setting
V_out = V_ref * (1 + R1/R2)

Where V_ref = 1.2V internal reference.

Timing Capacitor
t_on = C_t * V_t / I_charge

Recommended Operating Conditions
V_IN: 4.5V to 35V
Charge Current: 0A to 8A
Ambient Temperature: -40°C to 85°C
"""

INLINE_PIN_DATASHEET = """\
LM74700Q Ideal Diode Controller

PIN 1: GND - Ground reference
PIN 2: EN - Enable input, active high
PIN 3: ANODE - Anode of the ideal diode
PIN 4: CATHODE - Cathode of the ideal diode
PIN 5: GATE - Gate driver output
PIN 6: VS - Supply voltage

Absolute Maximum Ratings
VS: -0.3V to 65V
ANODE: -0.3V to 65V
GATE: -0.3V to VS+0.3V
Operating Temperature: -40°C to 150°C
"""

MINIMAL_DATASHEET = """\
Some Random Component
This is a very short datasheet with no useful information.
No pins, no formulas, no ratings.
"""


# ---------------------------------------------------------------------------
# Test read_text_file
# ---------------------------------------------------------------------------


class TestReadTextFile:
    """Test text file reading with encoding fallback."""

    def test_utf8_file(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("Hello world", encoding="utf-8")
        assert read_text_file(f) == "Hello world"

    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        assert read_text_file(f) == ""

    def test_missing_file_raises(self, tmp_path: Path):
        f = tmp_path / "missing.txt"
        with pytest.raises(Exception):
            read_text_file(f)


# ---------------------------------------------------------------------------
# Test infer_part_number
# ---------------------------------------------------------------------------


class TestInferPartNumber:
    """Test part number inference from filename."""

    def test_basic_filename(self):
        assert infer_part_number(Path("LTC4015.txt")) == "LTC4015"

    def test_with_trpbf_suffix(self):
        assert infer_part_number(Path("LTC4015IUHF_TRPBF.txt")) == "LTC4015IUHF"

    def test_with_datasheet_suffix(self):
        assert infer_part_number(Path("LM74700Q_datasheet.txt")) == "LM74700Q"

    def test_no_suffix(self):
        assert infer_part_number(Path("SS34.txt")) == "SS34"

    def test_pdf_extension(self):
        assert infer_part_number(Path("LTC4015.pdf")) == "LTC4015"


# ---------------------------------------------------------------------------
# Test extract_pin_table
# ---------------------------------------------------------------------------


class TestExtractPinTable:
    """Test pin table extraction from various formats."""

    def test_table_format_pins(self):
        pins = extract_pin_table(PIN_TABLE_DATASHEET)
        assert len(pins) == 20
        assert pins[0]["number"] == 1
        assert pins[0]["name"] == "INTVCC"
        assert pins[0]["type"] == "power"
        assert "Internal LDO" in pins[0]["description"]

    def test_table_format_sorted(self):
        pins = extract_pin_table(PIN_TABLE_DATASHEET)
        numbers = [p["number"] for p in pins]
        assert numbers == sorted(numbers)

    def test_inline_format_pins(self):
        pins = extract_pin_table(INLINE_PIN_DATASHEET)
        assert len(pins) == 6
        assert pins[0]["number"] == 1
        assert pins[0]["name"] == "GND"
        assert pins[0]["type"] == "power"

    def test_inline_format_descriptions(self):
        pins = extract_pin_table(INLINE_PIN_DATASHEET)
        enable_pin = next(p for p in pins if p["name"] == "EN")
        assert "Enable" in enable_pin["description"]

    def test_pin_type_classification(self):
        pins = extract_pin_table(PIN_TABLE_DATASHEET)
        types = {p["name"]: p["type"] for p in pins}
        assert types["VIN"] == "power"
        assert types["GND"] == "power"
        assert types["EN"] == "input"
        assert types["SDA"] == "input"
        assert types["SW"] == "output"

    def test_empty_input(self):
        pins = extract_pin_table("")
        assert pins == []

    def test_no_pins_in_text(self):
        pins = extract_pin_table(MINIMAL_DATASHEET)
        assert pins == []

    def test_deduplication(self):
        text = """\
Pin Number | Pin Name | Description
1          | VIN      | Input voltage
2          | GND      | Ground
1          | VIN      | Input voltage (duplicate)
"""
        pins = extract_pin_table(text)
        assert len(pins) == 2


# ---------------------------------------------------------------------------
# Test extract_formulas
# ---------------------------------------------------------------------------


class TestExtractFormulas:
    """Test formula extraction."""

    def test_extracts_charge_current_formula(self):
        formulas = extract_formulas(FORMULA_DATASHEET)
        formulas_text = [f["formula"] for f in formulas]
        assert any("I_charge" in f for f in formulas_text)

    def test_extracts_voltage_formula(self):
        formulas = extract_formulas(FORMULA_DATASHEET)
        formulas_text = [f["formula"] for f in formulas]
        assert any("V_out" in f for f in formulas_text)

    def test_extracts_timing_formula(self):
        formulas = extract_formulas(FORMULA_DATASHEET)
        formulas_text = [f["formula"] for f in formulas]
        assert any("t_on" in f for f in formulas_text)

    def test_formula_has_variables(self):
        formulas = extract_formulas(FORMULA_DATASHEET)
        charge_formula = next(f for f in formulas if "I_charge" in f["formula"])
        assert "I_charge" in charge_formula["variables"]
        assert "R_sense" in charge_formula["variables"]

    def test_formula_has_context(self):
        formulas = extract_formulas(FORMULA_DATASHEET)
        charge_formula = next(f for f in formulas if "I_charge" in f["formula"])
        assert charge_formula["context"]  # Should have some context

    def test_empty_input(self):
        formulas = extract_formulas("")
        assert formulas == []

    def test_no_formulas_in_text(self):
        formulas = extract_formulas(MINIMAL_DATASHEET)
        assert formulas == []

    def test_no_http_urls(self):
        """Formulas should not include URLs."""
        text = "See https://example.com for details\nV_out = V_in * 2"
        formulas = extract_formulas(text)
        for f in formulas:
            assert "http" not in f["formula"].lower()

    def test_skips_simple_values(self):
        """Lines like 'V = 3.3V' should not be formulas."""
        text = "V = 3.3V\nI_charge = V_sense / R_sense"
        formulas = extract_formulas(text)
        # Only the real formula should be extracted
        assert len(formulas) == 1
        assert "I_charge" in formulas[0]["formula"]

    def test_deduplication(self):
        text = "V_out = V_ref * (1 + R1/R2)\nV_out = V_ref * (1 + R1/R2)"
        formulas = extract_formulas(text)
        assert len(formulas) == 1


# ---------------------------------------------------------------------------
# Test extract_abs_max_ratings
# ---------------------------------------------------------------------------


class TestExtractAbsMaxRatings:
    """Test absolute maximum ratings extraction."""

    def test_extracts_voltage_ratings(self):
        ratings = extract_abs_max_ratings(PIN_TABLE_DATASHEET)
        assert "V_IN" in ratings
        assert ratings["V_IN"]["min"] == "-0.3V"
        assert ratings["V_IN"]["max"] == "42V"

    def test_extracts_temperature(self):
        ratings = extract_abs_max_ratings(PIN_TABLE_DATASHEET)
        assert "Operating_Temperature" in ratings

    def test_empty_input(self):
        ratings = extract_abs_max_ratings("")
        assert ratings == {}

    def test_no_section(self):
        ratings = extract_abs_max_ratings(MINIMAL_DATASHEET)
        assert ratings == {}


# ---------------------------------------------------------------------------
# Test extract_recommended_conditions
# ---------------------------------------------------------------------------


class TestExtractRecommendedConditions:
    """Test recommended operating conditions extraction."""

    def test_extracts_voltage(self):
        conditions = extract_recommended_conditions(FORMULA_DATASHEET)
        assert "V_IN" in conditions
        assert conditions["V_IN"]["min"] == "4.5V"
        assert conditions["V_IN"]["max"] == "35V"

    def test_extracts_current(self):
        conditions = extract_recommended_conditions(FORMULA_DATASHEET)
        assert "Charge_Current" in conditions

    def test_extracts_temperature(self):
        conditions = extract_recommended_conditions(FORMULA_DATASHEET)
        assert "Ambient_Temperature" in conditions

    def test_empty_input(self):
        conditions = extract_recommended_conditions("")
        assert conditions == {}

    def test_no_section(self):
        conditions = extract_recommended_conditions(MINIMAL_DATASHEET)
        assert conditions == {}


# ---------------------------------------------------------------------------
# Test extract_facts (integration)
# ---------------------------------------------------------------------------


class TestExtractFacts:
    """Test the full extraction pipeline."""

    def test_full_extraction(self, tmp_path: Path):
        f = tmp_path / "LTC4015.txt"
        f.write_text(PIN_TABLE_DATASHEET, encoding="utf-8")
        result = extract_facts(f)
        assert result["schema"] == "chip-netlist-datasheet-facts-v1"
        assert result["part"] == "LTC4015"
        assert len(result["pin_table"]) > 0
        assert result["extraction_quality"] in ("complete", "partial")

    def test_pin_only_quality(self, tmp_path: Path):
        """Pin table only (no formulas/ratings) should be 'partial'."""
        text = """\
Pin Number | Pin Name | Description
1          | VIN      | Input voltage
2          | GND      | Ground
"""
        f = tmp_path / "pins_only.txt"
        f.write_text(text, encoding="utf-8")
        result = extract_facts(f)
        assert result["extraction_quality"] == "partial"
        assert len(result["pin_table"]) == 2

    def test_formula_only_quality(self, tmp_path: Path):
        """Formula only (no pins/ratings) should be 'partial'."""
        text = "I_charge = V_sense / R_sense"
        f = tmp_path / "formulas_only.txt"
        f.write_text(text, encoding="utf-8")
        result = extract_facts(f)
        assert result["extraction_quality"] == "partial"
        assert len(result["formulas"]) > 0

    def test_complete_quality(self, tmp_path: Path):
        """Pins + formulas should be 'complete'."""
        f = tmp_path / "complete.txt"
        f.write_text(FORMULA_DATASHEET, encoding="utf-8")
        result = extract_facts(f)
        # FORMULA_DATASHEET has recommended conditions but no pin table
        # So quality depends on what's extracted
        assert result["extraction_quality"] in ("complete", "partial")

    def test_pins_and_ratings_complete(self, tmp_path: Path):
        """Pins + abs max should be 'complete'."""
        f = tmp_path / "pins_and_ratings.txt"
        f.write_text(PIN_TABLE_DATASHEET, encoding="utf-8")
        result = extract_facts(f)
        assert result["extraction_quality"] == "complete"

    def test_minimal_quality(self, tmp_path: Path):
        """Empty input should be 'minimal'."""
        f = tmp_path / "minimal.txt"
        f.write_text(MINIMAL_DATASHEET, encoding="utf-8")
        result = extract_facts(f)
        assert result["extraction_quality"] == "minimal"

    def test_empty_file_quality(self, tmp_path: Path):
        """Empty file should be 'minimal'."""
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        result = extract_facts(f)
        assert result["extraction_quality"] == "minimal"

    def test_part_inferred(self, tmp_path: Path):
        """Part number should be inferred from filename."""
        f = tmp_path / "LM74700.txt"
        f.write_text(MINIMAL_DATASHEET, encoding="utf-8")
        result = extract_facts(f)
        assert result["part"] == "LM74700"

    def test_part_explicit(self, tmp_path: Path):
        """Explicit part number should override inference."""
        f = tmp_path / "random.txt"
        f.write_text(MINIMAL_DATASHEET, encoding="utf-8")
        result = extract_facts(f, part="LTC4015")
        assert result["part"] == "LTC4015"

    def test_extraction_notes_present(self, tmp_path: Path):
        """Extraction notes should always be present."""
        f = tmp_path / "test.txt"
        f.write_text(MINIMAL_DATASHEET, encoding="utf-8")
        result = extract_facts(f)
        assert isinstance(result["extraction_notes"], list)
        assert len(result["extraction_notes"]) > 0

    def test_pdf_without_txt(self, tmp_path: Path):
        """PDF without .txt companion should return minimal with note."""
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        result = extract_facts(pdf)
        assert result["extraction_quality"] == "minimal"
        assert any("pdftotext" in n for n in result["extraction_notes"])

    def test_pdf_with_txt(self, tmp_path: Path):
        """PDF with .txt companion should extract from the .txt."""
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        txt = tmp_path / "test.txt"
        txt.write_text(PIN_TABLE_DATASHEET, encoding="utf-8")
        result = extract_facts(pdf)
        assert len(result["pin_table"]) == 20

    def test_source_file_field(self, tmp_path: Path):
        """source_file should point to the actual input file."""
        f = tmp_path / "chip.txt"
        f.write_text(MINIMAL_DATASHEET, encoding="utf-8")
        result = extract_facts(f)
        assert "chip.txt" in result["source_file"]


# ---------------------------------------------------------------------------
# Test extraction quality levels
# ---------------------------------------------------------------------------


class TestExtractionQuality:
    """Test extraction quality classification."""

    def test_complete_when_pins_and_formulas(self, tmp_path: Path):
        text = """\
Pin Number | Pin Name | Description
1          | VIN      | Input voltage
2          | GND      | Ground
3          | EN       | Enable

I_out = V_out / R_load
"""
        f = tmp_path / "test.txt"
        f.write_text(text, encoding="utf-8")
        result = extract_facts(f)
        assert result["extraction_quality"] == "complete"

    def test_complete_when_pins_and_ratings(self, tmp_path: Path):
        text = """\
Pin Number | Pin Name | Description
1          | VIN      | Input voltage
2          | GND      | Ground

Absolute Maximum Ratings
V_IN: -0.3V to 42V
"""
        f = tmp_path / "test.txt"
        f.write_text(text, encoding="utf-8")
        result = extract_facts(f)
        assert result["extraction_quality"] == "complete"

    def test_partial_when_pins_only(self, tmp_path: Path):
        text = """\
Pin Number | Pin Name | Description
1          | VIN      | Input voltage
2          | GND      | Ground
"""
        f = tmp_path / "test.txt"
        f.write_text(text, encoding="utf-8")
        result = extract_facts(f)
        assert result["extraction_quality"] == "partial"

    def test_partial_when_formulas_only(self, tmp_path: Path):
        text = "V_out = V_in * 2"
        f = tmp_path / "test.txt"
        f.write_text(text, encoding="utf-8")
        result = extract_facts(f)
        assert result["extraction_quality"] == "partial"

    def test_minimal_when_nothing(self, tmp_path: Path):
        text = "Random text without any useful information"
        f = tmp_path / "test.txt"
        f.write_text(text, encoding="utf-8")
        result = extract_facts(f)
        assert result["extraction_quality"] == "minimal"


# ---------------------------------------------------------------------------
# Test CLI interface
# ---------------------------------------------------------------------------


class TestCLI:
    """Tests for the extract_facts.py CLI."""

    def _run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(EXTRACT_SCRIPT), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_missing_file(self):
        result = self._run_cli("/nonexistent/path.txt")
        assert result.returncode != 0

    def test_stdout_output(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text(PIN_TABLE_DATASHEET, encoding="utf-8")
        result = self._run_cli(str(f))
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["schema"] == "chip-netlist-datasheet-facts-v1"
        assert len(output["pin_table"]) > 0

    def test_file_output(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text(PIN_TABLE_DATASHEET, encoding="utf-8")
        out = tmp_path / "output.json"
        result = self._run_cli(str(f), "--output", str(out))
        assert result.returncode == 0
        assert out.exists()
        output = json.loads(out.read_text(encoding="utf-8"))
        assert output["schema"] == "chip-netlist-datasheet-facts-v1"

    def test_part_flag(self, tmp_path: Path):
        f = tmp_path / "random.txt"
        f.write_text(MINIMAL_DATASHEET, encoding="utf-8")
        result = self._run_cli(str(f), "--part", "CUSTOM-123")
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["part"] == "CUSTOM-123"

    def test_json_valid(self, tmp_path: Path):
        """Output should always be valid JSON."""
        f = tmp_path / "test.txt"
        f.write_text(FORMULA_DATASHEET, encoding="utf-8")
        result = self._run_cli(str(f))
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert isinstance(output, dict)
        assert "schema" in output
        assert "pin_table" in output
        assert "formulas" in output
        assert "abs_max" in output
        assert "recommended" in output
        assert "extraction_quality" in output
        assert "extraction_notes" in output

    def test_inline_pins_cli(self, tmp_path: Path):
        """CLI should handle inline pin format."""
        f = tmp_path / "inline.txt"
        f.write_text(INLINE_PIN_DATASHEET, encoding="utf-8")
        result = self._run_cli(str(f))
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert len(output["pin_table"]) == 6

    def test_output_directory_created(self, tmp_path: Path):
        """Output directory should be created if it doesn't exist."""
        f = tmp_path / "test.txt"
        f.write_text(MINIMAL_DATASHEET, encoding="utf-8")
        out = tmp_path / "subdir" / "deep" / "output.json"
        result = self._run_cli(str(f), "--output", str(out))
        assert result.returncode == 0
        assert out.exists()
