#!/usr/bin/env python3
"""Search and download datasheets for components from component_index.json.

Reads component_index.json, tries to find and download PDF datasheets
using curl, and records results in datasheet_sources.json.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_WORKDIR = ".chip-netlist"
DEFAULT_TIMEOUT = 30


def sanitize_filename(name: str) -> str:
    """Replace filesystem-unsafe characters with underscores."""
    return re.sub(r'[/\\:*?"<>|]', "_", name)


def load_sources(sources_path: Path) -> dict[str, Any]:
    """Load existing datasheet_sources.json or return empty structure."""
    if sources_path.exists():
        return json.loads(sources_path.read_text(encoding="utf-8"))
    return {
        "schema": "chip-netlist-datasheet-sources-v1",
        "sources": {},
    }


def save_sources(sources_path: Path, data: dict[str, Any]) -> None:
    """Write datasheet_sources.json."""
    sources_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _is_pdf(path: Path) -> bool:
    """Check if a file starts with the PDF magic bytes %PDF."""
    try:
        with open(path, "rb") as f:
            header = f.read(5)
        return header.startswith(b"%PDF")
    except OSError:
        return False


def try_download(url: str, output_path: Path, timeout: int) -> bool:
    """Attempt to download a URL to output_path using curl.

    Returns True on success (file exists and is a valid PDF), False on failure.
    """
    try:
        result = subprocess.run(
            ["curl", "-fL", "-o", str(output_path), url],
            timeout=timeout,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
            # Verify the downloaded file is actually a PDF
            if _is_pdf(output_path):
                return True
            # Not a PDF — clean up and report
            print(f"  [skip] Downloaded file is not a PDF: {url}", file=sys.stderr)
            output_path.unlink()
            return False
        # Clean up partial download
        if output_path.exists():
            output_path.unlink()
        return False
    except (subprocess.TimeoutExpired, OSError):
        if output_path.exists():
            output_path.unlink()
        return False


def extract_lcsc_pdf_url(html: str, supplier_part: str) -> str | None:
    """Try to extract a PDF datasheet URL from an LCSC product page HTML."""
    # Look for common LCSC PDF link patterns
    patterns = [
        r'(https?://atta\.szlcsc\.com/[^"\'>\s]+\.pdf)',
        r'(https?://[^"\'>\s]*szlcsc[^"\'>\s]*\.pdf)',
        r'"pdfUrl"\s*:\s*"([^"]+)"',
        r'"datasheetUrl"\s*:\s*"([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            url = match.group(1)
            # Unescape any JSON-escaped characters
            url = url.replace("\\/", "/").replace("\\u0026", "&")
            return url
    return None


def extract_semiee_pdf_url(html: str) -> str | None:
    """Try to extract a PDF datasheet URL from a semiee.com search page HTML."""
    patterns = [
        r'(https?://[^"\'>\s]*semiee[^"\'>\s]*\.pdf)',
        r'href="([^"]*\.pdf)"',
        r'"pdf_url"\s*:\s*"([^"]+)"',
        r'"datasheet_url"\s*:\s*"([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            url = match.group(1)
            url = url.replace("\\/", "/")
            return url
    return None


def search_datasheets(
    component_index: dict[str, Any],
    workdir: Path,
    refs: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Search and download datasheets for components.

    Args:
        component_index: Parsed component_index.json
        workdir: Workbench directory
        refs: Optional list of reference designators to limit search
        timeout: Curl timeout in seconds

    Returns:
        Updated datasheet_sources structure
    """
    datasheets_dir = workdir / "datasheets"
    datasheets_dir.mkdir(parents=True, exist_ok=True)

    sources_path = workdir / "datasheet_sources.json"
    sources_data = load_sources(sources_path)

    components = component_index.get("components", {})

    # Filter to requested refs if specified
    if refs:
        refs_upper = {r.upper() for r in refs}
        components = {
            ref: comp for ref, comp in components.items()
            if ref.upper() in refs_upper
        }

    # Filter to datasheet targets with high priority
    targets = {
        ref: comp
        for ref, comp in components.items()
        if comp.get("datasheet_target") and comp.get("priority") == "high"
    }

    downloaded = 0
    skipped = 0
    not_found = 0

    for ref in sorted(targets, key=_natural_ref_key):
        comp = targets[ref]
        part = comp.get("manufacturer_part") or comp.get("canonical_name") or ref
        safe_name = sanitize_filename(part)
        pdf_path = datasheets_dir / f"{safe_name}.pdf"
        rel_path = f"datasheets/{safe_name}.pdf"

        print(f"Searching {ref} ({part})...", file=sys.stderr)

        # Check if already cached
        if pdf_path.exists() and pdf_path.stat().st_size > 0:
            print(f"  [cached] {pdf_path.name}", file=sys.stderr)
            skipped += 1
            sources_data["sources"][ref] = {
                "part": part,
                "status": "downloaded",
                "url": sources_data["sources"].get(ref, {}).get("url", "cached"),
                "local_path": rel_path,
            }
            continue

        tried_urls: list[str] = []
        success = False

        # Strategy 1: Use the datasheet URL from component_index
        ds_url = comp.get("datasheet")
        if ds_url and ds_url.strip():
            tried_urls.append(ds_url)
            print(f"  Trying datasheet URL: {ds_url}", file=sys.stderr)
            if try_download(ds_url, pdf_path, timeout):
                print(f"  [downloaded] {pdf_path.name}", file=sys.stderr)
                success = True
                downloaded += 1
                sources_data["sources"][ref] = {
                    "part": part,
                    "status": "downloaded",
                    "url": ds_url,
                    "local_path": rel_path,
                }

        # Strategy 2: Search LCSC using supplier_part
        if not success:
            supplier_part = comp.get("supplier_part")
            if supplier_part and supplier_part.startswith("C"):
                lcsc_url = f"https://www.lcsc.com/product-detail/{supplier_part}.html"
                tried_urls.append(lcsc_url)
                print(f"  Trying LCSC: {lcsc_url}", file=sys.stderr)
                try:
                    result = subprocess.run(
                        ["curl", "-fL", "--max-time", str(timeout), lcsc_url],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=timeout + 5,
                    )
                    if result.returncode == 0 and result.stdout:
                        pdf_url = extract_lcsc_pdf_url(result.stdout, supplier_part)
                        if pdf_url and pdf_url not in tried_urls:
                            tried_urls.append(pdf_url)
                            print(f"  Trying LCSC PDF: {pdf_url}", file=sys.stderr)
                            if try_download(pdf_url, pdf_path, timeout):
                                print(f"  [downloaded] {pdf_path.name}", file=sys.stderr)
                                success = True
                                downloaded += 1
                                sources_data["sources"][ref] = {
                                    "part": part,
                                    "status": "downloaded",
                                    "url": pdf_url,
                                    "local_path": rel_path,
                                }
                except (subprocess.TimeoutExpired, OSError):
                    pass

        # Strategy 3: Search semiee.com
        if not success:
            mfr_part = comp.get("manufacturer_part") or comp.get("canonical_name")
            if mfr_part:
                semiee_url = f"https://www.semiee.com/search?q={mfr_part}"
                tried_urls.append(semiee_url)
                print(f"  Trying semiee: {semiee_url}", file=sys.stderr)
                try:
                    result = subprocess.run(
                        ["curl", "-fL", "--max-time", str(timeout), semiee_url],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=timeout + 5,
                    )
                    if result.returncode == 0 and result.stdout:
                        pdf_url = extract_semiee_pdf_url(result.stdout)
                        if pdf_url and pdf_url not in tried_urls:
                            tried_urls.append(pdf_url)
                            print(f"  Trying semiee PDF: {pdf_url}", file=sys.stderr)
                            if try_download(pdf_url, pdf_path, timeout):
                                print(f"  [downloaded] {pdf_path.name}", file=sys.stderr)
                                success = True
                                downloaded += 1
                                sources_data["sources"][ref] = {
                                    "part": part,
                                    "status": "downloaded",
                                    "url": pdf_url,
                                    "local_path": rel_path,
                                }
                except (subprocess.TimeoutExpired, OSError):
                    pass

        if not success:
            print(f"  [not found]", file=sys.stderr)
            not_found += 1
            sources_data["sources"][ref] = {
                "part": part,
                "status": "not_found",
                "tried_urls": tried_urls,
            }

    # Print summary
    print(
        f"\nDownloaded: {downloaded}, Skipped (cached): {skipped}, Not found: {not_found}",
        file=sys.stderr,
    )

    # Save updated sources
    save_sources(sources_path, sources_data)
    return sources_data


def _natural_ref_key(ref: str) -> tuple[str, int, str]:
    """Sort reference designators naturally (U1, U2, U10)."""
    match = re.match(r"([A-Za-z]+)(\d+)$", ref)
    if not match:
        return (ref, 10**9, ref)
    return (match.group(1), int(match.group(2)), ref)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Search and download datasheets for schematic components."
    )
    parser.add_argument(
        "component_index",
        type=Path,
        help="Path to component_index.json",
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=Path(DEFAULT_WORKDIR),
        help=f"Workbench directory (default: {DEFAULT_WORKDIR})",
    )
    parser.add_argument(
        "--refs",
        help="Comma-separated reference designators to search (e.g., U1,U5)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Curl timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    args = parser.parse_args(argv)

    if not args.component_index.exists():
        print(f"Error: {args.component_index} not found", file=sys.stderr)
        return 1

    component_index = json.loads(args.component_index.read_text(encoding="utf-8"))
    refs = args.refs.split(",") if args.refs else None

    sources = search_datasheets(
        component_index,
        workdir=args.workdir,
        refs=refs,
        timeout=args.timeout,
    )

    # Print sources JSON to stdout
    print(json.dumps(sources, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
