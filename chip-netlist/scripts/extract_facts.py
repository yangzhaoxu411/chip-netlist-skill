#!/usr/bin/env python3
"""Extract structured facts from datasheet text files.

Parses pdftotext output to find pin tables, formulas, absolute maximum ratings,
and recommended operating conditions. Outputs structured JSON.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def read_text_file(path: Path) -> str:
    """Read a text file trying multiple encodings."""
    for encoding in ("utf-8", "gbk", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    # Final fallback: read as bytes and decode with replacement
    return path.read_bytes().decode("utf-8", errors="replace")


def infer_part_number(path: Path) -> str:
    """Infer part number from the filename stem."""
    stem = path.stem
    # Remove common suffixes like _TRPBF, _datasheet, etc.
    for suffix in ("_TRPBF", "_trpbf", "_Datasheet", "_datasheet"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    return stem


# ---------------------------------------------------------------------------
# Pin table extraction
# ---------------------------------------------------------------------------

# Common pin type keywords
_PIN_TYPE_KEYWORDS = {
    "power": {"vcc", "vdd", "vin", "vout", "vbat", "gnd", "vss", "pgnd",
              "agnd", "dgnd", "intvcc", "dvcc", "avcc", "pvcc", "pvdd",
              "vreg", "vbus", "vcp", "vboost", "supply", "power"},
    "input": {"in", "input", "en", "enable", "ce", "cs", "clk", "scl",
              "sda", "sdi", "sdo", "mosi", "miso", "ss", "nss", "csb",
              "sync", "pg", "pgood", "fault", "int", "alert", "comp",
              "ilim", "fb", "fbb", "tj", "timer", "wp", "hold", "run",
              "shdn", "shutdown", "reset", "rst", "por", "trig", "gpio"},
    "output": {"out", "output", "sw", "lx", "boot", "bst", "drv",
               "gate", "cp", "charge", "discharge", "flag", "power_good"},
    "nc": {"nc", "no connect", "not connected", "dnc", "reserved"},
    "thermal": {"epad", "exposed pad", "thermal pad", "pad", "slug"},
}


def _classify_pin_type(name: str, description: str = "") -> str:
    """Classify a pin type based on name and description."""
    combined = f"{name} {description}".lower()
    for pin_type, keywords in _PIN_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in combined:
                return pin_type
    return "signal"


def _extract_table_format_pins(text: str) -> list[dict[str, Any]]:
    """Extract pins from table-format datasheets.

    Looks for header lines with 'pin' + 'name'/'number' keywords,
    then parses subsequent rows.
    """
    pins = []
    lines = text.splitlines()

    for i, line in enumerate(lines):
        lower = line.lower()
        # Look for pin table header
        if re.search(r"pin\s*(num|no|#|name|function|description)", lower):
            # Parse header to find column positions
            header_line = line
            # Find subsequent data lines
            for j in range(i + 1, min(i + 200, len(lines))):
                data_line = lines[j].strip()
                if not data_line:
                    continue
                # Stop if we hit another section header (all caps, or common markers)
                if re.match(r"^[A-Z][A-Z\s]{5,}$", data_line) and not re.match(r"^\d", data_line):
                    break
                if re.match(r"^(figure|table|note|abs)", data_line.lower()):
                    break

                # Try pattern: number | name | description (with various separators)
                # Pipe-separated
                m = re.match(r"\s*(\d+)\s*[\|]\s*(\w+)\s*[\|]\s*(.+)", data_line)
                if m:
                    pin_num = int(m.group(1))
                    pin_name = m.group(2).strip()
                    desc = m.group(3).strip()
                    pins.append({
                        "number": pin_num,
                        "name": pin_name,
                        "type": _classify_pin_type(pin_name, desc),
                        "description": desc,
                    })
                    continue

                # Tab or multi-space separated: "1  VIN  Input voltage"
                m = re.match(r"\s*(\d+)\s{2,}(\w+)\s{2,}(.+)", data_line)
                if m:
                    pin_num = int(m.group(1))
                    pin_name = m.group(2).strip()
                    desc = m.group(3).strip()
                    pins.append({
                        "number": pin_num,
                        "name": pin_name,
                        "type": _classify_pin_type(pin_name, desc),
                        "description": desc,
                    })
                    continue

                # Just number and name: "1  VIN"
                m = re.match(r"\s*(\d+)\s{2,}(\w+)\s*$", data_line)
                if m:
                    pin_num = int(m.group(1))
                    pin_name = m.group(2).strip()
                    pins.append({
                        "number": pin_num,
                        "name": pin_name,
                        "type": _classify_pin_type(pin_name),
                        "description": "",
                    })
                    continue
            if pins:
                break

    return pins


def _extract_inline_pin_format(text: str) -> list[dict[str, Any]]:
    """Extract pins from inline format: PIN 1: VIN - Input supply voltage."""
    pins = []
    pattern = re.compile(
        r"PIN\s+(\d+)\s*[:=]\s*(\w+)\s*[-–]\s*(.+)",
        re.IGNORECASE,
    )
    for m in pattern.finditer(text):
        pin_num = int(m.group(1))
        pin_name = m.group(2).strip()
        desc = m.group(3).strip()
        pins.append({
            "number": pin_num,
            "name": pin_name,
            "type": _classify_pin_type(pin_name, desc),
            "description": desc,
        })
    return pins


def _extract_pinout_format(text: str) -> list[dict[str, Any]]:
    """Extract pins from pinout block format.

    Common in QFN/TSSOP datasheets:
        1  VIN
        2  GND
        3  EN
    """
    pins = []
    # Find a block of consecutive "number name" lines
    lines = text.splitlines()
    current_run: list[dict[str, Any]] = []

    for line in lines:
        m = re.match(r"^\s*(\d+)\s+(\w+)\s*$", line)
        if m:
            pin_num = int(m.group(1))
            pin_name = m.group(2).strip()
            current_run.append({
                "number": pin_num,
                "name": pin_name,
                "type": _classify_pin_type(pin_name),
                "description": "",
            })
        else:
            # Keep the longest run
            if len(current_run) > len(pins):
                pins = current_run
            current_run = []

    if len(current_run) > len(pins):
        pins = current_run

    return pins


def extract_pin_table(text: str) -> list[dict[str, Any]]:
    """Extract pin table from datasheet text.

    Tries multiple strategies and returns the best result.
    """
    # Strategy 1: Table format
    pins = _extract_table_format_pins(text)

    # Strategy 2: Inline format
    inline_pins = _extract_inline_pin_format(text)
    if len(inline_pins) > len(pins):
        pins = inline_pins

    # Strategy 3: Simple pinout format (only if no better result)
    if len(pins) < 3:
        pinout_pins = _extract_pinout_format(text)
        if len(pinout_pins) > len(pins):
            pins = pinout_pins

    # Deduplicate by pin number, keeping first occurrence
    seen: set[int] = set()
    deduped: list[dict[str, Any]] = []
    for p in pins:
        if p["number"] not in seen:
            seen.add(p["number"])
            deduped.append(p)
    return sorted(deduped, key=lambda p: p["number"])


# ---------------------------------------------------------------------------
# Formula extraction
# ---------------------------------------------------------------------------

def extract_formulas(text: str) -> list[dict[str, Any]]:
    """Extract mathematical formulas from datasheet text.

    Looks for lines containing equations with = and common operators.
    """
    formulas: list[dict[str, Any]] = []
    lines = text.splitlines()

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # Pattern: something = expression with math operators
        # Must have at least one = and one of: / * + - ( )
        if "=" not in stripped:
            continue

        # Skip lines that are likely not formulas
        lower = stripped.lower()
        if any(skip in lower for skip in [
            "http", "www.", ".com", "copyright", "page ", "rev ",
            "figure ", "table ", "note ", "document",
        ]):
            continue

        # Look for formula-like patterns
        # Variable = expression
        formula_match = re.match(
            r"([A-Za-z_]\w*(?:\s*[-–]\s*\w+)?)\s*=\s*(.+)",
            stripped,
        )
        if not formula_match:
            continue

        lhs = formula_match.group(1).strip()
        rhs = formula_match.group(2).strip()

        # Check that RHS has mathematical content
        math_chars = set("*/+−-()^")
        if not any(c in rhs for c in math_chars):
            continue

        # Skip if RHS is just a number or simple value
        if re.match(r"^[\d.]+\s*[A-Za-z]*$", rhs):
            continue

        # Try to infer context from surrounding lines
        context = ""
        for j in range(max(0, i - 3), i):
            ctx_line = lines[j].strip()
            if ctx_line and len(ctx_line) > 5 and not ctx_line.startswith("="):
                context = ctx_line
                break

        # Extract variables from the formula
        variables: dict[str, str] = {}
        var_pattern = re.compile(r"[A-Za-z_]\w*")
        for v in var_pattern.findall(stripped):
            if len(v) > 1 and v.lower() not in ("where", "the", "for", "and", "or", "is", "of"):
                variables[v] = ""

        formulas.append({
            "context": context,
            "formula": stripped,
            "variables": variables,
        })

    # Deduplicate by formula text
    seen_formulas: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for f in formulas:
        if f["formula"] not in seen_formulas:
            seen_formulas.add(f["formula"])
            deduped.append(f)

    return deduped


# ---------------------------------------------------------------------------
# Absolute maximum ratings extraction
# ---------------------------------------------------------------------------

def _extract_ratings_section(
    text: str,
    section_pattern: str,
) -> dict[str, dict[str, str]]:
    """Extract ratings from a section matching the given header pattern."""
    ratings: dict[str, dict[str, str]] = {}
    lines = text.splitlines()
    in_section = False
    section_end_patterns = re.compile(
        r"^(?:\d+\.|[A-Z][A-Z\s]{5,}$|recommended|typical|electrical|pin\s*(?:num|name|desc))",
        re.IGNORECASE,
    )

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Check for section header
        if re.search(section_pattern, stripped, re.IGNORECASE):
            in_section = True
            continue

        if not in_section:
            continue

        # Stop at next major section
        if section_end_patterns.match(stripped) and not re.match(r"^\s*$", stripped):
            # Make sure this isn't just a sub-item
            if re.match(r"^[A-Z][A-Z\s]{5,}$", stripped) and len(stripped) > 10:
                break

        # Parse rating entries
        # Pattern: "Parameter: min to max" or "Parameter: value"
        # Common formats:
        #   V_IN: -0.3V to 42V
        #   Supply Voltage (VCC)  -0.3 to 6.0  V
        #   Input Voltage  -0.3V to VCC+0.3V

        # Try colon-separated: "Param: value" or "Param: min to max"
        m = re.match(
            r"([A-Za-z_][\w\s()/\-]*?)\s*[:]\s*(-?[\d.]+\s*[A-Za-z°℃]*)\s*(?:to|[-–])\s*(-?[\d.]+\s*[A-Za-z°℃]*)",
            stripped,
        )
        if m:
            param = m.group(1).strip().replace(" ", "_")
            ratings[param] = {
                "min": m.group(2).strip(),
                "max": m.group(3).strip(),
            }
            continue

        # Try space-separated with unit column:
        # "Supply Voltage (VCC)  -0.3  6.0  V"
        m = re.match(
            r"([A-Za-z_][\w\s()/\-]*?)\s{2,}(-?[\d.]+)\s{2,}(-?[\d.]+)\s+([A-Za-z°℃/]+)",
            stripped,
        )
        if m:
            param = m.group(1).strip().replace(" ", "_")
            unit = m.group(4).strip()
            ratings[param] = {
                "min": f"{m.group(2)}{unit}",
                "max": f"{m.group(3)}{unit}",
            }
            continue

        # Try: "Parameter  value" (single value, usually max)
        m = re.match(
            r"([A-Za-z_][\w\s()/\-]*?)\s{2,}(-?[\d.]+\s*[A-Za-z°℃]*)\s*$",
            stripped,
        )
        if m:
            param = m.group(1).strip().replace(" ", "_")
            val = m.group(2).strip()
            ratings[param] = {"min": "", "max": val}
            continue

    return ratings


def extract_abs_max_ratings(text: str) -> dict[str, dict[str, str]]:
    """Extract absolute maximum ratings section."""
    return _extract_ratings_section(
        text,
        r"absolute\s+maximum\s+rating|绝对最大额定值|abs(?:olute)?\s*\.?\s*max",
    )


def extract_recommended_conditions(text: str) -> dict[str, dict[str, str]]:
    """Extract recommended operating conditions."""
    return _extract_ratings_section(
        text,
        r"recommended\s+operating|operating\s+conditions|recommended\s+conditions|推荐工作条件",
    )


# ---------------------------------------------------------------------------
# Main extraction pipeline
# ---------------------------------------------------------------------------

def extract_facts(
    input_path: Path,
    part: str | None = None,
) -> dict[str, Any]:
    """Extract structured facts from a datasheet text file.

    Args:
        input_path: Path to .txt file (pdftotext output) or .pdf file
        part: Part number for metadata (inferred from filename if not given)

    Returns:
        Structured facts dictionary
    """
    notes: list[str] = []

    # Handle PDF: convert to text first
    if input_path.suffix.lower() == ".pdf":
        txt_path = input_path.with_suffix(".txt")
        if not txt_path.exists():
            notes.append(f"PDF file provided but no .txt companion found at {txt_path}")
            return {
                "schema": "chip-netlist-datasheet-facts-v1",
                "part": part or infer_part_number(input_path),
                "source_file": str(input_path),
                "pin_table": [],
                "formulas": [],
                "abs_max": {},
                "recommended": {},
                "extraction_quality": "minimal",
                "extraction_notes": notes + ["PDF provided without text extraction; run pdftotext first"],
            }
        input_path = txt_path

    # Read the text
    text = read_text_file(input_path)
    if not text.strip():
        notes.append("Input file is empty")
        return {
            "schema": "chip-netlist-datasheet-facts-v1",
            "part": part or infer_part_number(input_path),
            "source_file": str(input_path),
            "pin_table": [],
            "formulas": [],
            "abs_max": {},
            "recommended": {},
            "extraction_quality": "minimal",
            "extraction_notes": notes,
        }

    if part is None:
        part = infer_part_number(input_path)

    # Extract each section
    pin_table = extract_pin_table(text)
    notes.append(f"Found {len(pin_table)} pin entries")

    formulas = extract_formulas(text)
    notes.append(f"Found {len(formulas)} formulas")

    abs_max = extract_abs_max_ratings(text)
    if abs_max:
        notes.append(f"Found {len(abs_max)} absolute max ratings")
    else:
        notes.append("No absolute max section found")

    recommended = extract_recommended_conditions(text)
    if recommended:
        notes.append(f"Found {len(recommended)} recommended conditions")
    else:
        notes.append("No recommended conditions section found")

    # Determine extraction quality
    has_pins = len(pin_table) > 0
    has_formulas = len(formulas) > 0
    has_ratings = len(abs_max) > 0 or len(recommended) > 0

    if has_pins and (has_formulas or has_ratings):
        quality = "complete"
    elif has_pins or has_formulas or has_ratings:
        quality = "partial"
    else:
        quality = "minimal"

    return {
        "schema": "chip-netlist-datasheet-facts-v1",
        "part": part,
        "source_file": str(input_path),
        "pin_table": pin_table,
        "formulas": formulas,
        "abs_max": abs_max,
        "recommended": recommended,
        "extraction_quality": quality,
        "extraction_notes": notes,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Extract structured facts from datasheet text files.",
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to datasheet .txt or .pdf file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path (default: stdout)",
    )
    parser.add_argument(
        "--part",
        default=None,
        help="Part number for metadata (inferred from filename if not given)",
    )
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"Error: {args.input} not found", file=sys.stderr)
        return 1

    result = extract_facts(args.input, part=args.part)

    output_json = json.dumps(result, ensure_ascii=False, indent=2) + "\n"

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_json, encoding="utf-8")
        print(
            f"Extracted {len(result['pin_table'])} pins, "
            f"{len(result['formulas'])} formulas to {args.output}",
            file=sys.stderr,
        )
    else:
        print(output_json)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
