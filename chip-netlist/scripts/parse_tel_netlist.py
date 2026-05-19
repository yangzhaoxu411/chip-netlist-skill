#!/usr/bin/env python3
"""Extract AI-ready component and connectivity data from an EasyEDA Pro .epro2 project."""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any


PACKAGE_COUNT_PATTERNS = [
    re.compile(r"\b(?:QFN|TQFP|TSSOP|SSOP|SOP|DFN|LQFP|QFP|SOT)-?(\d+)(?=[^0-9]|$)", re.I),
    re.compile(r"\b(?:PDFN\d+|POWERPAK-\d+)-(\d+)(?=[^0-9]|$)", re.I),
]
FIELD_MAP = {
    "Designator": "designator",
    "Name": "name",
    "Value": "value",
    "Device": "device_id",
    "Footprint": "footprint_id",
    "Supplier Footprint": "supplier_footprint",
    "Supplier": "supplier",
    "Supplier Part": "supplier_part",
    "LCSC Part Name": "lcsc_part_name",
    "Manufacturer": "manufacturer",
    "Manufacturer Part": "manufacturer_part",
    "Datasheet": "datasheet",
    "Unique ID": "unique_id",
}


def load_version() -> str:
    version_file = Path(__file__).resolve().parents[1] / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def first_present(*values: str | None) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text and text not in {"{Value}", "null", "None"}:
            return text
    return None


def read_project(path: Path) -> tuple[dict[str, Any], str, str]:
    if path.suffix.lower() != ".epro2":
        raise ValueError(f"Only .epro2 project files are supported: {path}")

    with zipfile.ZipFile(path) as project:
        names = project.namelist()
        epru_names = [name for name in names if name.lower().endswith(".epru")]
        if not epru_names:
            raise ValueError(f"No .epru document found inside {path}")

        metadata: dict[str, Any] = {}
        if "project2.json" in names:
            metadata = json.loads(project.read("project2.json").decode("utf-8-sig", errors="replace"))

        epru_name = epru_names[0]
        epru_text = project.read(epru_name).decode("utf-8-sig", errors="replace")

    return metadata, epru_name, epru_text


def parse_record_stream(text: str) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    records: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for raw in text.split("|\n"):
        line = raw.strip()
        if not line or "||" not in line:
            continue
        meta_text, data_text = line.split("||", 1)
        if data_text.endswith("|"):
            data_text = data_text[:-1]
        if not meta_text.strip() or not data_text.strip():
            continue
        records.append((json.loads(meta_text), json.loads(data_text)))
    return records


def parse_json_id(value: Any) -> list[Any] | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


def collect_attrs(records: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    attrs_by_parent: dict[str, dict[str, Any]] = {}
    for meta, data in records:
        if meta.get("type") != "ATTR":
            continue
        parent = data.get("parentId")
        key = data.get("key")
        if not parent or not key:
            continue
        attrs_by_parent.setdefault(parent, {})[str(key)] = data.get("value")
    return attrs_by_parent


def resolve_formula(value: Any, attrs: dict[str, Any]) -> Any:
    if not isinstance(value, str):
        return value
    match = re.fullmatch(r"=\{([^}]+)\}", value.strip())
    if not match:
        return value
    return attrs.get(match.group(1), value)


def normalized_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for original, target in FIELD_MAP.items():
        value = resolve_formula(attrs.get(original), attrs)
        if value is not None and str(value).strip():
            normalized[target] = value
    return normalized


def infer_pin_count(component: dict[str, Any]) -> int | None:
    haystack = " ".join(
        str(component.get(key) or "")
        for key in ("supplier_footprint", "footprint_id", "part_id", "canonical_name", "manufacturer_part")
    )
    for pattern in PACKAGE_COUNT_PATTERNS:
        match = pattern.search(haystack)
        if match:
            return int(match.group(1))
    return None


def merge_component(target: dict[str, Any], candidate: dict[str, Any]) -> None:
    target.setdefault("source_component_ids", [])
    target.setdefault("source_part_ids", [])
    target.setdefault("source_unique_ids", [])
    target.setdefault("attributes", {})

    source_id = candidate.get("source_component_id")
    if source_id and source_id not in target["source_component_ids"]:
        target["source_component_ids"].append(source_id)

    part_id = candidate.get("part_id")
    if part_id and part_id not in target["source_part_ids"]:
        target["source_part_ids"].append(part_id)

    unique_id = candidate.get("unique_id")
    if unique_id and unique_id not in target["source_unique_ids"]:
        target["source_unique_ids"].append(unique_id)

    for key, value in candidate.get("attributes", {}).items():
        if key not in target["attributes"] or not first_present(target["attributes"].get(key)):
            target["attributes"][key] = value

    for key in (
        "designator",
        "canonical_name",
        "manufacturer_part",
        "value",
        "name",
        "manufacturer",
        "supplier",
        "supplier_part",
        "lcsc_part_name",
        "datasheet",
        "supplier_footprint",
        "footprint_id",
        "device_id",
    ):
        current = target.get(key)
        incoming = candidate.get(key)
        if not first_present(current) and first_present(incoming):
            target[key] = incoming


def collect_components(
    records: list[tuple[dict[str, Any], dict[str, Any]]],
    attrs_by_parent: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    components: dict[str, dict[str, Any]] = {}
    component_id_to_ref: dict[str, str] = {}

    for meta, data in records:
        if meta.get("type") != "COMPONENT":
            continue

        component_id = meta.get("id")
        if not component_id:
            continue

        raw_attrs = attrs_by_parent.get(component_id, {})
        attrs = normalized_attrs(raw_attrs)
        designator = first_present(attrs.get("designator"))
        if not designator:
            continue

        part_id = first_present(data.get("partId"))
        canonical_name = first_present(
            attrs.get("manufacturer_part"),
            attrs.get("value"),
            attrs.get("name"),
            part_id[:-2] if part_id and part_id.endswith(".1") else part_id,
        )

        candidate = {
            "source_component_id": component_id,
            "designator": designator,
            "canonical_name": canonical_name,
            "part_id": part_id,
            "attributes": raw_attrs,
            **attrs,
        }
        component_id_to_ref[component_id] = designator
        components.setdefault(designator, {"designator": designator})
        merge_component(components[designator], candidate)

    for component in components.values():
        component["pin_count_hint"] = infer_pin_count(component)
        for key in ("source_component_ids", "source_part_ids", "source_unique_ids"):
            component[key] = sorted(component.get(key, []))

    return components, component_id_to_ref


def natural_ref_key(ref: str) -> tuple[str, int, str]:
    match = re.match(r"([A-Za-z]+)(\d+)$", ref)
    if not match:
        return (ref, 10**9, ref)
    return (match.group(1), int(match.group(2)), ref)


def natural_pin_key(pin: str) -> tuple[str, int, str]:
    ref, _, number = pin.partition(".")
    return (ref, int(number) if number.isdigit() else 10**9, number)


def pin_number(pin: str) -> int | None:
    _, _, suffix = pin.partition(".")
    return int(suffix) if suffix.isdigit() else None


def collect_pad_nets(
    records: list[tuple[dict[str, Any], dict[str, Any]]],
    component_id_to_ref: dict[str, str],
) -> tuple[dict[str, list[str]], dict[str, list[dict[str, Any]]], dict[str, set[int]], list[str]]:
    nets: dict[str, list[str]] = {}
    pin_map: dict[str, list[dict[str, Any]]] = {}
    observed_pins_by_ref: dict[str, set[int]] = {}
    no_net_pins: list[str] = []

    for meta, data in records:
        if meta.get("type") != "PAD_NET":
            continue
        parts = parse_json_id(meta.get("id"))
        if not parts or len(parts) < 4:
            continue

        _, component_id, pad_number, pin_id = parts[:4]
        ref = component_id_to_ref.get(str(component_id))
        if not ref:
            continue

        pin = f"{ref}.{pad_number}"
        if str(pad_number).isdigit():
            observed_pins_by_ref.setdefault(ref, set()).add(int(pad_number))

        net = first_present(data.get("padNet"))
        if not net:
            no_net_pins.append(pin)
            continue

        nets.setdefault(net, []).append(pin)
        pin_map.setdefault(pin, []).append({"net": net, "pin_id": pin_id, "peers": []})

    for net, connections in nets.items():
        unique_connections = sorted(set(connections), key=natural_pin_key)
        nets[net] = unique_connections
        for pin in unique_connections:
            for entry in pin_map.get(pin, []):
                if entry["net"] == net:
                    entry["peers"] = [other for other in unique_connections if other != pin]

    return nets, pin_map, observed_pins_by_ref, sorted(set(no_net_pins), key=natural_pin_key)


def build_ref_report(
    ref: str,
    components: dict[str, dict[str, Any]],
    pin_map: dict[str, list[dict[str, Any]]],
    observed_pins_by_ref: dict[str, set[int]],
) -> dict[str, Any]:
    component = components.get(ref)
    observed_numbers = set(observed_pins_by_ref.get(ref, set()))
    for pin in pin_map:
        if pin.startswith(f"{ref}."):
            number = pin_number(pin)
            if number is not None:
                observed_numbers.add(number)

    max_observed = max(observed_numbers, default=0)
    max_pin = max(max_observed, component.get("pin_count_hint") or 0 if component else 0)

    pins: list[dict[str, Any]] = []
    for number in range(1, max_pin + 1):
        pin = f"{ref}.{number}"
        entries = pin_map.get(pin, [])
        pins.append({
            "pin": pin,
            "number": number,
            "connected": bool(entries),
            "connections": entries,
        })

    return {
        "ref": ref,
        "component": component,
        "observed_pins": sorted(observed_numbers),
        "observed_connected_pins": sum(1 for pin in pins if pin["connected"]),
        "pins": pins,
    }


def analyze(path: Path, ref: str | None = None) -> dict[str, Any]:
    metadata, epru_name, epru_text = read_project(path)
    records = parse_record_stream(epru_text)
    attrs_by_parent = collect_attrs(records)
    components, component_id_to_ref = collect_components(records, attrs_by_parent)
    nets, pin_map, observed_pins_by_ref, no_net_pins = collect_pad_nets(records, component_id_to_ref)

    result: dict[str, Any] = {
        "source": str(path),
        "source_type": "epro2",
        "project": {
            "title": metadata.get("title"),
            "editor_version": metadata.get("editorVersion"),
            "epru_file": epru_name,
        },
        "record_count": len(records),
        "component_count": len(components),
        "net_count": len(nets),
        "components": {ref_name: components[ref_name] for ref_name in sorted(components, key=natural_ref_key)},
        "nets": [
            {"net": net, "connections": nets[net]}
            for net in sorted(nets)
        ],
        "pins": {pin: pin_map[pin] for pin in sorted(pin_map, key=natural_pin_key)},
        "warnings": {
            "no_net_pins": no_net_pins,
            "single_point_nets": [net for net, pins in sorted(nets.items()) if len(pins) == 1],
            "low_connection_nets": [net for net, pins in sorted(nets.items()) if 1 < len(pins) <= 2],
            "components_without_canonical_name": [
                name for name, info in sorted(components.items(), key=lambda item: natural_ref_key(item[0]))
                if not first_present(info.get("canonical_name"))
            ],
        },
    }
    if ref:
        result["ref_report"] = build_ref_report(ref, components, pin_map, observed_pins_by_ref)
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Extract AI-ready component and net connectivity from an .epro2 project.")
    parser.add_argument("project", nargs="?", type=Path, help="Path to an EasyEDA Pro .epro2 project")
    parser.add_argument("--ref", help="Reference designator to include as a focused report, for example U1")
    parser.add_argument("--json", action="store_true", help="Accepted for compatibility; output is always JSON")
    parser.add_argument("--version", action="version", version=f"chip-netlist {load_version()}")
    args = parser.parse_args(argv)

    if args.project is None:
        parser.error("the following arguments are required: project")

    result = analyze(args.project, args.ref)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
