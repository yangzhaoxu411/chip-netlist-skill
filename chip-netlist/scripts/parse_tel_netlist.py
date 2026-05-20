#!/usr/bin/env python3
"""Extract AI-ready component and connectivity data from an EasyEDA Pro .epro2 project."""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from datetime import UTC, datetime
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
DATASHEET_LOOKUP_PREFIXES = {
    "U": ("high", "integrated circuit or module"),
    "IC": ("high", "integrated circuit"),
    "Q": ("high", "transistor or MOSFET"),
    "D": ("high", "diode, TVS, LED, or protection device"),
    "F": ("medium", "fuse or protection component"),
    "L": ("medium", "inductor or magnetic component"),
    "CN": ("medium", "connector"),
    "J": ("medium", "connector"),
    "FPC": ("medium", "connector"),
}
PASSIVE_PREFIXES_TO_SKIP_BY_DEFAULT = {"R", "C"}
GLOBAL_NET_NAMES = {
    "GND",
    "AGND",
    "DGND",
    "PGND",
    "SGND",
    "VSS",
}
DEFAULT_WORKBENCH_DIR = ".chip-netlist"


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


def collect_library_attrs(records: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    library_attrs_by_device: dict[str, dict[str, Any]] = {}
    current_device_uuid: str | None = None
    for meta, data in records:
        record_type = meta.get("type")
        if record_type == "DOCHEAD":
            current_device_uuid = str(data.get("uuid")) if data.get("docType") == "DEVICE" and data.get("uuid") else None
            continue
        if record_type != "META" or not current_device_uuid:
            continue
        attrs = data.get("attributes")
        if isinstance(attrs, dict):
            library_attrs_by_device[current_device_uuid] = attrs
        current_device_uuid = None
    return library_attrs_by_device


def merge_attrs_with_library_defaults(
    instance_attrs: dict[str, Any],
    library_attrs: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(library_attrs or {})
    for key, value in instance_attrs.items():
        if first_present(value) or key not in merged:
            merged[key] = value
    return merged


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
    library_attrs_by_device: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    components: dict[str, dict[str, Any]] = {}
    component_id_to_ref: dict[str, str] = {}
    library_attrs_by_device = library_attrs_by_device or {}

    for meta, data in records:
        if meta.get("type") != "COMPONENT":
            continue

        component_id = meta.get("id")
        if not component_id:
            continue

        raw_instance_attrs = attrs_by_parent.get(component_id, {})
        device_id = first_present(raw_instance_attrs.get("Device"))
        raw_attrs = merge_attrs_with_library_defaults(
            raw_instance_attrs,
            library_attrs_by_device.get(device_id) if device_id else None,
        )
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


def ref_from_pin(pin: str) -> str:
    return pin.split(".", 1)[0]


def pin_number(pin: str) -> int | None:
    _, _, suffix = pin.partition(".")
    return int(suffix) if suffix.isdigit() else None


def ref_prefix(ref: str) -> str:
    match = re.match(r"([A-Za-z]+)", ref)
    return match.group(1).upper() if match else ref.upper()


def should_include_datasheet_candidate(ref: str, component: dict[str, Any]) -> tuple[bool, str, str]:
    prefix = ref_prefix(ref)
    if prefix in DATASHEET_LOOKUP_PREFIXES:
        priority, reason = DATASHEET_LOOKUP_PREFIXES[prefix]
        return True, priority, reason
    if prefix in PASSIVE_PREFIXES_TO_SKIP_BY_DEFAULT:
        value = str(component.get("value") or "").lower()
        canonical = str(component.get("canonical_name") or "").lower()
        if any(marker in f"{value} {canonical}" for marker in ("ntc", "ptc", "tvs", "fuse", "mohm", "mΩ", "mω")):
            return True, "medium", "passive-looking reference with protection, sensing, or power role"
        return False, "skip", "ordinary passive component"
    return False, "skip", "not a default datasheet lookup target"


def unique_list(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in out:
            out.append(text)
    return out


def build_query_terms(component: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for key in ("manufacturer_part", "canonical_name", "supplier_part", "lcsc_part_name"):
        value = first_present(component.get(key))
        if value:
            terms.append(f"{value} datasheet")
    manufacturer = first_present(component.get("manufacturer"))
    manufacturer_part = first_present(component.get("manufacturer_part"))
    if manufacturer and manufacturer_part:
        terms.append(f"{manufacturer} {manufacturer_part} datasheet")
    return unique_list(terms)


def build_datasheet_lookup(components: dict[str, dict[str, Any]]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    priority_rank = {"high": 0, "medium": 1, "low": 2}

    for ref, component in components.items():
        include, priority, reason = should_include_datasheet_candidate(ref, component)
        if not include:
            continue
        query_terms = build_query_terms(component)
        if not query_terms:
            continue
        candidates.append({
            "ref": ref,
            "priority": priority,
            "reason": reason,
            "canonical_name": component.get("canonical_name"),
            "manufacturer": component.get("manufacturer"),
            "manufacturer_part": component.get("manufacturer_part"),
            "supplier_part": component.get("supplier_part"),
            "query_terms": query_terms,
        })

    candidates.sort(key=lambda item: (priority_rank.get(item["priority"], 99), natural_ref_key(item["ref"])))
    return {
        "purpose": "When the user asks to analyze part of a circuit, use these candidates plus the selected refs/nets to search for data sheets.",
        "source_priority": [
            "official manufacturer product page or PDF data sheet",
            "authorized distributor page such as DigiKey, Mouser, Arrow, or LCSC",
            "third-party data sheet mirror only when primary sources are unavailable",
        ],
        "search_rules": [
            "Prefer manufacturer_part, then canonical_name, then supplier_part.",
            "Do not assume a data sheet is correct until the part number and package/function match the project component.",
            "Skip ordinary resistors and capacitors by default unless the selected circuit makes them critical, such as shunts, NTC/PTC parts, timing parts, or compensation networks.",
            "Record source URLs used for every data-sheet-based conclusion.",
        ],
        "candidates": candidates,
    }


def net_map_from_result(result: dict[str, Any]) -> dict[str, list[str]]:
    return {entry["net"]: entry["connections"] for entry in result.get("nets", [])}


def is_global_or_high_fanout_net(net: str, connection_count: int, max_expand_connections: int) -> bool:
    normalized = net.upper()
    if normalized in GLOBAL_NET_NAMES or normalized.endswith("_GND"):
        return True
    return connection_count > max_expand_connections


def pin_entries_for_ref(result: dict[str, Any], ref: str) -> dict[str, list[dict[str, Any]]]:
    prefix = f"{ref}."
    return {
        pin: entries
        for pin, entries in result.get("pins", {}).items()
        if pin.startswith(prefix)
    }


def matching_refs_and_nets(result: dict[str, Any], query: str) -> tuple[list[str], list[str]]:
    wanted = query.strip().upper()
    refs = [
        ref
        for ref in result.get("components", {})
        if ref.upper() == wanted
    ]
    nets = [
        entry["net"]
        for entry in result.get("nets", [])
        if entry["net"].upper() == wanted
    ]
    return refs, nets


def build_context_packet(
    result: dict[str, Any],
    query: str,
    *,
    depth: int = 1,
    max_net_connections: int = 80,
    max_expand_connections: int = 24,
) -> dict[str, Any]:
    """Build a small, AI-loadable packet for one selected ref or net."""
    matched_refs, matched_nets = matching_refs_and_nets(result, query)
    if not matched_refs and not matched_nets:
        raise ValueError(f"No reference designator or net matched context query: {query}")

    nets_by_name = net_map_from_result(result)
    included_refs = set(matched_refs)
    context_nets = set(matched_nets)
    frontier_refs = set(matched_refs)

    for _ in range(max(1, depth)):
        for ref in sorted(frontier_refs, key=natural_ref_key):
            for entries in pin_entries_for_ref(result, ref).values():
                for entry in entries:
                    context_nets.add(entry["net"])

        next_refs: set[str] = set()
        for net in context_nets:
            connections = nets_by_name.get(net, [])
            if is_global_or_high_fanout_net(net, len(connections), max_expand_connections):
                continue
            next_refs.update(ref_from_pin(pin) for pin in connections)

        next_refs.difference_update(included_refs)
        included_refs.update(next_refs)
        frontier_refs = next_refs
        if not frontier_refs:
            break

    components = result.get("components", {})
    included_refs = {ref for ref in included_refs if ref in components}

    packet_components = {
        ref: components[ref]
        for ref in sorted(included_refs, key=natural_ref_key)
    }

    packet_nets: list[dict[str, Any]] = []
    visible_connections_by_net: dict[str, set[str]] = {}
    for net in sorted(context_nets):
        connections = nets_by_name.get(net, [])
        visible_connections = [
            pin
            for pin in connections
            if ref_from_pin(pin) in included_refs
        ]
        if not visible_connections:
            visible_connections = connections[:max_net_connections]
        truncated = len(visible_connections) > max_net_connections
        if truncated:
            visible_connections = visible_connections[:max_net_connections]
        visible_connections_by_net[net] = set(visible_connections)
        expanded = not is_global_or_high_fanout_net(net, len(connections), max_expand_connections)
        packet_nets.append({
            "net": net,
            "connection_count": len(connections),
            "connections": visible_connections,
            "omitted_connection_count": max(0, len(connections) - len(visible_connections)),
            "expanded_to_peer_components": expanded,
            "truncated": truncated,
        })

    packet_pins: dict[str, list[dict[str, Any]]] = {}
    for pin, entries in result.get("pins", {}).items():
        if ref_from_pin(pin) not in included_refs:
            continue
        compact_entries: list[dict[str, Any]] = []
        for entry in entries:
            net = entry["net"]
            if net not in context_nets:
                continue
            visible_peers = [
                peer
                for peer in entry.get("peers", [])
                if peer in visible_connections_by_net.get(net, set())
            ]
            compact_entry = dict(entry)
            compact_entry["peers"] = visible_peers
            compact_entry["omitted_peer_count"] = max(0, len(entry.get("peers", [])) - len(visible_peers))
            compact_entries.append(compact_entry)
        if compact_entries:
            packet_pins[pin] = compact_entries

    candidate_by_ref = {
        candidate["ref"]: candidate
        for candidate in result.get("datasheet_lookup", {}).get("candidates", [])
    }
    targets: list[dict[str, Any]] = []
    primary_refs = set(matched_refs)
    for net in matched_nets:
        primary_refs.update(
            ref_from_pin(pin)
            for pin in nets_by_name.get(net, [])
            if ref_from_pin(pin) in included_refs
        )
    for ref in sorted(included_refs, key=natural_ref_key):
        if ref not in candidate_by_ref:
            continue
        target = dict(candidate_by_ref[ref])
        target["context_role"] = "primary" if ref in primary_refs else "neighbor"
        targets.append(target)
    target_refs = {target["ref"] for target in targets}
    support_components = {
        ref: packet_components[ref]
        for ref in sorted(included_refs - target_refs, key=natural_ref_key)
    }

    return {
        "schema": "chip-netlist-context-packet-v1",
        "generated_by": result.get("generated_by"),
        "source": result.get("source"),
        "project": result.get("project"),
        "selection": {
            "query": query,
            "matched_refs": sorted(matched_refs, key=natural_ref_key),
            "matched_nets": sorted(matched_nets),
            "depth": depth,
            "max_expand_connections": max_expand_connections,
            "purpose": "Load this packet instead of the full netlist when analyzing the selected circuit area.",
        },
        "components": packet_components,
        "support_components": support_components,
        "nets": packet_nets,
        "pins": {pin: packet_pins[pin] for pin in sorted(packet_pins, key=natural_pin_key)},
        "datasheet_lookup": {
            "source_priority": result.get("datasheet_lookup", {}).get("source_priority", []),
            "search_rules": result.get("datasheet_lookup", {}).get("search_rules", []),
            "targets": targets,
            "note": "Search or load data sheets only for these targets unless the current reasoning shows another component is critical.",
        },
    }


def build_component_index(result: dict[str, Any]) -> dict[str, Any]:
    components: dict[str, Any] = {}
    for ref, component in result.get("components", {}).items():
        include, priority, reason = should_include_datasheet_candidate(ref, component)
        components[ref] = {
            "canonical_name": component.get("canonical_name"),
            "manufacturer_part": component.get("manufacturer_part"),
            "manufacturer": component.get("manufacturer"),
            "value": component.get("value"),
            "supplier": component.get("supplier"),
            "supplier_part": component.get("supplier_part"),
            "datasheet": component.get("datasheet"),
            "supplier_footprint": component.get("supplier_footprint"),
            "datasheet_target": include,
            "priority": priority,
            "reason": reason,
            "query_terms": build_query_terms(component),
        }
    return {
        "schema": "chip-netlist-component-index-v1",
        "generated_by": result.get("generated_by"),
        "source": result.get("source"),
        "component_count": len(components),
        "components": {
            ref: components[ref]
            for ref in sorted(components, key=natural_ref_key)
        },
    }


def safe_context_filename(query: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.+-]+", "_", query.strip())
    return cleaned.strip("._") or "context"


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_if_missing(path: Path, text: str) -> None:
    if not path.exists():
        path.write_text(text, encoding="utf-8")


def write_workbench(
    result: dict[str, Any],
    workbench_dir: Path,
    context_packet: dict[str, Any] | None = None,
) -> dict[str, str]:
    workbench_dir.mkdir(parents=True, exist_ok=True)
    for dirname in ("context_packets", "datasheets", "datasheet_facts"):
        (workbench_dir / dirname).mkdir(parents=True, exist_ok=True)

    paths: dict[str, str] = {}
    netlist_path = workbench_dir / "chip_netlist.json"
    component_index_path = workbench_dir / "component_index.json"
    datasheet_sources_path = workbench_dir / "datasheet_sources.json"
    state_path = workbench_dir / "analysis_state.json"
    report_path = workbench_dir / "analysis_report.md"

    write_json(netlist_path, result)
    write_json(component_index_path, build_component_index(result))
    paths["chip_netlist"] = str(netlist_path)
    paths["component_index"] = str(component_index_path)

    datasheet_sources = {
        "schema": "chip-netlist-datasheet-sources-v1",
        "generated_by": result.get("generated_by"),
        "source": result.get("source"),
        "sources": {},
        "instructions": [
            "Store one entry per component or part number after a data sheet source is verified.",
            "Keep source URLs, matched part numbers, package/function checks, and local PDF paths when available.",
        ],
    }
    if not datasheet_sources_path.exists():
        write_json(datasheet_sources_path, datasheet_sources)
    paths["datasheet_sources"] = str(datasheet_sources_path)

    now = datetime.now(UTC).isoformat()
    state = {
        "schema": "chip-netlist-analysis-state-v1",
        "generated_by": result.get("generated_by"),
        "source": result.get("source"),
        "created_at_utc": now,
        "current_context": context_packet.get("selection") if context_packet else None,
        "confirmed_groups": [],
        "pending_groups": [],
        "rejected_groups": [],
        "notes": [],
    }
    if not state_path.exists():
        write_json(state_path, state)
    paths["analysis_state"] = str(state_path)

    report = [
        "# Chip Netlist Analysis Report",
        "",
        f"- Source: `{result.get('source')}`",
        f"- Generated by: `{result.get('generated_by', {}).get('tool')}` `{result.get('generated_by', {}).get('version')}`",
        "",
        "Append confirmed pin-group analysis here after each Y/N checkpoint.",
        "",
    ]
    write_if_missing(report_path, "\n".join(report))
    paths["analysis_report"] = str(report_path)

    if context_packet:
        filename = safe_context_filename(context_packet["selection"]["query"]) + ".json"
        context_path = workbench_dir / "context_packets" / filename
        write_json(context_path, context_packet)
        paths["context_packet"] = str(context_path)

    return paths


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
    library_attrs_by_device = collect_library_attrs(records)
    components, component_id_to_ref = collect_components(records, attrs_by_parent, library_attrs_by_device)
    nets, pin_map, observed_pins_by_ref, no_net_pins = collect_pad_nets(records, component_id_to_ref)

    result: dict[str, Any] = {
        "schema": "chip-netlist-ai-json-v1",
        "generated_by": {
            "tool": "chip-netlist",
            "version": load_version(),
            "parser": "scripts/parse_tel_netlist.py",
        },
        "ai_use": {
            "recognition": "If this JSON is uploaded later, treat it as chip-netlist generated project evidence.",
            "circuit_selection": "When the user names a ref, net, rail, connector, or functional area, collect matching components, their connected nets, and one-hop peer pins before analysis.",
            "datasheet_policy": "When no user-provided data sheet exists, search the web for data sheets for relevant active or critical components before judging circuit correctness.",
        },
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
    result["datasheet_lookup"] = build_datasheet_lookup(result["components"])
    if ref:
        result["ref_report"] = build_ref_report(ref, components, pin_map, observed_pins_by_ref)
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Extract AI-ready component and net connectivity from an .epro2 project.")
    parser.add_argument("project", nargs="?", type=Path, help="Path to an EasyEDA Pro .epro2 project")
    parser.add_argument("--ref", help="Reference designator to include as a focused report, for example U1")
    parser.add_argument("--context", help="Reference designator or net to emit as a compact AI context packet")
    parser.add_argument("--depth", type=int, default=1, help="Context expansion depth for --context, default: 1")
    parser.add_argument("--workdir", type=Path, help=f"Create or update a persistent workbench directory, default suggestion: {DEFAULT_WORKBENCH_DIR}")
    parser.add_argument("--json", action="store_true", help="Accepted for compatibility; output is always JSON")
    parser.add_argument("--version", action="version", version=f"chip-netlist {load_version()}")
    args = parser.parse_args(argv)

    if args.project is None:
        parser.error("the following arguments are required: project")

    focused_ref = args.ref or args.context
    result = analyze(args.project, focused_ref)

    context_packet = None
    if args.context:
        context_packet = build_context_packet(result, args.context, depth=args.depth)

    if args.workdir:
        paths = write_workbench(result, args.workdir, context_packet)
        output: dict[str, Any] = {
            "schema": "chip-netlist-workbench-summary-v1",
            "generated_by": result.get("generated_by"),
            "source": result.get("source"),
            "workbench": str(args.workdir),
            "paths": paths,
        }
    elif context_packet:
        output = context_packet
    else:
        output = result

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
