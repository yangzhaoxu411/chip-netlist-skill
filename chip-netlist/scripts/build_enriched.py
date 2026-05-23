#!/usr/bin/env python3
"""Build enriched.json by merging component metadata with extracted datasheet facts.

Reads component_index.json, datasheet_sources.json, and datasheet_facts/*.json
to produce a single enriched.json file for downstream rule engine and LLM analysis.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_WORKDIR = ".chip-netlist"


def sanitize_filename(name: str) -> str:
    """Replace filesystem-unsafe characters with underscores.

    Matches the logic in search_datasheet.py.
    """
    return re.sub(r'[/\\:*?"<>|]', "_", name)


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON file and return its contents."""
    return json.loads(path.read_text(encoding="utf-8"))


def _natural_ref_key(ref: str) -> tuple[str, int, str]:
    """Sort reference designators naturally (U1, U2, U10)."""
    match = re.match(r"([A-Za-z]+)(\d+)$", ref)
    if not match:
        return (ref, 10**9, ref)
    return (match.group(1), int(match.group(2)), ref)


def build_facts_index(facts_dir: Path) -> dict[str, Path]:
    """Build an index mapping sanitized names to facts file paths.

    Scans datasheet_facts/*.json and indexes by:
    - The 'part' field from each facts file (sanitized)
    - The filename stem (sanitized)

    Returns:
        Dict mapping sanitized lowercase name -> Path to facts JSON
    """
    index: dict[str, Path] = {}
    if not facts_dir.is_dir():
        return index

    for facts_file in sorted(facts_dir.glob("*.json")):
        # Index by filename stem
        stem_key = sanitize_filename(facts_file.stem).lower()
        index[stem_key] = facts_file

        # Also index by the 'part' field inside the file
        try:
            data = load_json(facts_file)
            part = data.get("part", "")
            if part:
                part_key = sanitize_filename(part).lower()
                if part_key not in index:
                    index[part_key] = facts_file
        except (json.JSONDecodeError, OSError):
            pass  # Skip malformed files

    return index


def match_facts_file(
    ref: str,
    comp: dict[str, Any],
    facts_index: dict[str, Path],
) -> Path | None:
    """Try to find a matching facts file for a component.

    Matching priority:
    1. Sanitized manufacturer_part
    2. Sanitized canonical_name
    3. Component ref (e.g., U1, R1)
    """
    # Try manufacturer_part
    mfr_part = comp.get("manufacturer_part")
    if mfr_part:
        key = sanitize_filename(mfr_part).lower()
        if key in facts_index:
            return facts_index[key]

    # Try canonical_name
    canonical = comp.get("canonical_name")
    if canonical:
        key = sanitize_filename(canonical).lower()
        if key in facts_index:
            return facts_index[key]

    # Try component ref
    ref_key = sanitize_filename(ref).lower()
    if ref_key in facts_index:
        return facts_index[ref_key]

    return None


def determine_datasheet_status(
    ref: str,
    comp: dict[str, Any],
    sources: dict[str, Any],
    has_facts: bool,
) -> str:
    """Determine the datasheet status for a component.

    Returns one of:
    - 'downloaded' — datasheet was downloaded and facts extracted
    - 'downloaded_no_facts' — datasheet downloaded but no facts extracted
    - 'not_found' — datasheet search failed
    - 'not_target' — component was not a datasheet search target
    - 'not_downloaded' — component was a target but download not attempted
    """
    source_entry = sources.get(ref, {})

    if has_facts:
        return "downloaded"

    if source_entry.get("status") == "downloaded":
        return "downloaded_no_facts"

    if source_entry.get("status") == "not_found":
        return "not_found"

    if comp.get("datasheet_target"):
        return "not_downloaded"

    return "not_target"


def build_enriched(
    component_index: dict[str, Any],
    datasheet_sources: dict[str, Any],
    facts_dir: Path,
) -> dict[str, Any]:
    """Build the enriched data structure.

    Args:
        component_index: Parsed component_index.json
        datasheet_sources: Parsed datasheet_sources.json
        facts_dir: Path to datasheet_facts/ directory

    Returns:
        Enriched dictionary ready to write as enriched.json
    """
    components = component_index.get("components", {})
    sources = datasheet_sources.get("sources", {})
    facts_index = build_facts_index(facts_dir)

    enriched_components: dict[str, dict[str, Any]] = {}
    enriched_count = 0
    quality_counts: dict[str, int] = {"complete": 0, "partial": 0, "minimal": 0}

    for ref in sorted(components, key=_natural_ref_key):
        comp = components[ref]

        # Try to find matching facts
        facts_path = match_facts_file(ref, comp, facts_index)
        facts: dict[str, Any] | None = None
        has_facts = False

        if facts_path is not None:
            try:
                facts = load_json(facts_path)
                has_facts = True
                enriched_count += 1
                quality = facts.get("extraction_quality", "minimal")
                quality_counts[quality] = quality_counts.get(quality, 0) + 1
            except (json.JSONDecodeError, OSError):
                facts = None

        # Build enriched entry
        source_entry = sources.get(ref, {})
        status = determine_datasheet_status(ref, comp, sources, has_facts)

        entry: dict[str, Any] = {
            "ref": ref,
            "canonical_name": comp.get("canonical_name"),
            "manufacturer": comp.get("manufacturer"),
            "manufacturer_part": comp.get("manufacturer_part"),
            "value": comp.get("value"),
            "footprint": comp.get("supplier_footprint"),
            "datasheet_url": comp.get("datasheet") or source_entry.get("url"),
            "datasheet_status": status,
            "datasheet_local": source_entry.get("local_path"),
            "pin_table": [],
            "formulas": [],
            "abs_max": {},
            "recommended": {},
        }

        # Merge facts if available
        if facts is not None:
            entry["pin_table"] = facts.get("pin_table", [])
            entry["formulas"] = facts.get("formulas", [])
            entry["abs_max"] = facts.get("abs_max", {})
            entry["recommended"] = facts.get("recommended", {})
            entry["extraction_quality"] = facts.get("extraction_quality", "minimal")
            entry["extraction_notes"] = facts.get("extraction_notes", [])
        else:
            entry["extraction_quality"] = "none"
            entry["extraction_notes"] = []

        enriched_components[ref] = entry

    return {
        "schema": "chip-netlist-enriched-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "component_count": len(enriched_components),
        "enriched_count": enriched_count,
        "quality_summary": quality_counts,
        "components": enriched_components,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Build enriched.json by merging component metadata with datasheet facts.",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=Path(DEFAULT_WORKDIR),
        help=f"Workbench directory (default: {DEFAULT_WORKDIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path (default: <workdir>/enriched.json)",
    )
    args = parser.parse_args(argv)

    workdir = args.workdir
    output_path = args.output or (workdir / "enriched.json")

    # Validate inputs
    component_index_path = workdir / "component_index.json"
    if not component_index_path.exists():
        print(f"Error: {component_index_path} not found", file=sys.stderr)
        return 1

    sources_path = workdir / "datasheet_sources.json"
    facts_dir = workdir / "datasheet_facts"

    # Load inputs (sources and facts are optional)
    component_index = load_json(component_index_path)
    datasheet_sources: dict[str, Any] = {"schema": "", "sources": {}}
    if sources_path.exists():
        datasheet_sources = load_json(sources_path)

    # Build enriched data
    enriched = build_enriched(component_index, datasheet_sources, facts_dir)

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_json = json.dumps(enriched, ensure_ascii=False, indent=2) + "\n"
    output_path.write_text(output_json, encoding="utf-8")

    # Print summary
    total = enriched["component_count"]
    enriched_n = enriched["enriched_count"]
    quality = enriched.get("quality_summary", {})
    complete = quality.get("complete", 0)
    partial = quality.get("partial", 0)
    minimal = quality.get("minimal", 0)
    print(
        f"Enriched: {enriched_n}/{total} components, "
        f"{complete} complete, {partial} partial, {minimal} minimal",
        file=sys.stderr,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
