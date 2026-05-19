#!/usr/bin/env python3
"""Parse a .tel netlist into package, net, and pin-connection evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


PIN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_$-]*\.[A-Za-z0-9_$-]+$")
PACKAGE_COUNT_PATTERNS = [
    re.compile(r"\b(?:QFN|TQFP|TSSOP|SSOP|SOP|DFN|LQFP|QFP)-(\d+)(?=[^0-9]|$)", re.I),
    re.compile(r"\b(?:PDFN\d+|POWERPAK-\d+)-(\d+)(?=[^0-9]|$)", re.I),
]


def read_text(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16", "gb18030", "latin-1"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8-replace"


def section(text: str, start: str, *stops: str) -> str:
    lines = text.splitlines()
    inside = False
    out: list[str] = []
    stop_set = {s.upper() for s in stops}
    for line in lines:
        marker = line.strip().upper()
        if marker == start.upper():
            inside = True
            continue
        if inside and marker in stop_set:
            break
        if inside:
            out.append(line)
    return "\n".join(out)


def clean_header_part(text: str) -> str:
    return text.strip().strip(",").strip()


def split_refs(text: str) -> list[str]:
    cleaned = text.replace(",", " ")
    return [token.strip() for token in cleaned.split() if token.strip()]


def parse_packages(text: str) -> dict[str, dict[str, str]]:
    packages_section = section(text, "$PACKAGES", "$A_PROPERTIES", "$NETS", "$SCHEDULE", "$END")
    packages: dict[str, dict[str, str]] = {}
    header_parts: list[str] = []

    for raw_line in packages_section.splitlines():
        line = clean_header_part(raw_line)
        if not line:
            continue

        if ";" not in line:
            header_parts.append(line)
            continue

        before, after = line.split(";", 1)
        before = clean_header_part(before)
        if before:
            header_parts.append(before)
        header = " ".join(header_parts).replace(" ,", "").replace(", ", " ").strip()
        fields = [part.strip().strip(",") for part in header.split("!")]
        footprint = fields[0] if len(fields) > 0 else ""
        package = fields[1] if len(fields) > 1 else ""
        value = fields[2] if len(fields) > 2 else ""

        for ref in split_refs(after):
            packages[ref] = {
                "footprint": footprint,
                "package": package,
                "value": value.strip("'"),
            }
        header_parts = []

    return packages


def normalize_net_name(name: str) -> str:
    return name.strip().strip(",").strip().strip("'").strip('"')


def parse_nets(text: str) -> dict[str, list[str]]:
    nets_section = section(text, "$NETS", "$SCHEDULE", "$END")
    nets: dict[str, list[str]] = {}
    current_net: str | None = None
    current_connections: list[str] = []

    def flush() -> None:
        nonlocal current_net, current_connections
        if current_net is not None:
            nets[current_net] = [c for c in current_connections if PIN_RE.match(c)]
        current_net = None
        current_connections = []

    for raw_line in nets_section.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ";" in line:
            flush()
            before, after = line.split(";", 1)
            current_net = normalize_net_name(before)
            current_connections.extend(split_refs(after))
        elif current_net is not None:
            current_connections.extend(split_refs(line))

    flush()
    return nets


def build_pin_map(nets: dict[str, list[str]]) -> dict[str, list[dict[str, Any]]]:
    pin_map: dict[str, list[dict[str, Any]]] = {}
    for net, connections in nets.items():
        for pin in connections:
            peers = [other for other in connections if other != pin]
            pin_map.setdefault(pin, []).append({"net": net, "peers": peers})
    return pin_map


def ref_of(pin: str) -> str:
    return pin.split(".", 1)[0]


def pin_number(pin: str) -> int | None:
    suffix = pin.split(".", 1)[1]
    return int(suffix) if suffix.isdigit() else None


def natural_pin_key(pin: str) -> tuple[int, str]:
    number = pin_number(pin)
    return (number if number is not None else 10**9, pin)


def infer_package_pin_count(package_info: dict[str, str] | None) -> int | None:
    if not package_info:
        return None
    haystack = " ".join(package_info.values())
    for pattern in PACKAGE_COUNT_PATTERNS:
        match = pattern.search(haystack)
        if match:
            return int(match.group(1))
    return None


def ref_report(ref: str, packages: dict[str, dict[str, str]], pin_map: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    prefix = f"{ref}."
    observed = sorted([pin for pin in pin_map if pin.startswith(prefix)], key=natural_pin_key)
    package_info = packages.get(ref)
    package_count = infer_package_pin_count(package_info)

    observed_numbers = [pin_number(pin) for pin in observed if pin_number(pin) is not None]
    max_observed = max(observed_numbers, default=0)
    max_pin = max(package_count or 0, max_observed)

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

    extra = [pin for pin in observed if pin_number(pin) is None]
    for pin in extra:
        pins.append({
            "pin": pin,
            "number": pin_number(pin),
            "connected": True,
            "connections": pin_map.get(pin, []),
        })

    return {
        "ref": ref,
        "package": package_info,
        "package_pin_count": package_count,
        "observed_connected_pins": len(observed),
        "pins": pins,
    }


def analyze(path: Path, ref: str | None = None) -> dict[str, Any]:
    text, encoding = read_text(path)
    packages = parse_packages(text)
    nets = parse_nets(text)
    pin_map = build_pin_map(nets)

    single_point_nets = [net for net, pins in nets.items() if len(pins) == 1]
    low_connection_nets = [net for net, pins in nets.items() if 1 < len(pins) <= 2]

    result: dict[str, Any] = {
        "source": str(path),
        "encoding": encoding,
        "package_count": len(packages),
        "net_count": len(nets),
        "packages": packages,
        "nets": [{"net": net, "connections": pins} for net, pins in nets.items()],
        "pins": pin_map,
        "warnings": {
            "single_point_nets": single_point_nets,
            "low_connection_nets": low_connection_nets,
        },
    }
    if ref:
        result["ref_report"] = ref_report(ref, packages, pin_map)
    return result


def print_human(result: dict[str, Any], ref: str | None) -> None:
    print(f"Source: {result['source']}")
    print(f"Encoding: {result['encoding']}")
    print(f"Packages: {result['package_count']}")
    print(f"Nets: {result['net_count']}")
    print()

    if not ref:
        print("References:")
        for name, info in sorted(result["packages"].items()):
            value = f", value={info['value']}" if info.get("value") else ""
            print(f"  {name}: footprint={info.get('footprint', '')}{value}")
        return

    report = result["ref_report"]
    info = report.get("package") or {}
    print(f"Reference: {ref}")
    if info:
        print(f"Footprint: {info.get('footprint', '')}")
        print(f"Package: {info.get('package', '')}")
        print(f"Value: {info.get('value', '')}")
    if report.get("package_pin_count"):
        print(f"Inferred package pin count: {report['package_pin_count']}")
    print(f"Observed connected pins: {report['observed_connected_pins']}")
    print()

    for pin in report["pins"]:
        if pin["connected"]:
            for conn in pin["connections"]:
                peers = ", ".join(conn["peers"]) if conn["peers"] else "(no peers)"
                print(f"{pin['pin']}: net={conn['net']} peers={peers}")
        else:
            print(f"{pin['pin']}: NO_NET (not present in $NETS)")

    singles = result["warnings"]["single_point_nets"]
    if singles:
        print()
        print("Single-point nets for review:")
        for net in singles:
            print(f"  {net}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Parse a .tel netlist and report chip pin connections.")
    parser.add_argument("netlist", type=Path, help="Path to .tel netlist")
    parser.add_argument("--ref", help="Reference designator to report, for example U1")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args(argv)

    result = analyze(args.netlist, args.ref)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_human(result, args.ref)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
