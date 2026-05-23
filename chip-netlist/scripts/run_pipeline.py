#!/usr/bin/env python3
"""Run the deterministic chip netlist pipeline end to end."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from strict_claims import build_evidence_ledger, validate_claims


DEFAULT_WORKDIR = ".chip-netlist"
SCRIPT_DIR = Path(__file__).resolve().parent


def write_json_file(path: Path, data: dict[str, Any]) -> None:
    """Write JSON with the skill's stable UTF-8 formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json_file(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    """Load JSON from path, or return default when the file is missing/invalid."""
    if not path.exists():
        return default or {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default or {}


def _script(name: str) -> str:
    return str(SCRIPT_DIR / name)


def resolve_workdir(workdir: Path, project_root: Path) -> Path:
    """Resolve relative workbench paths under the schematic project root."""
    if workdir.is_absolute():
        return workdir
    return project_root / workdir


def run_step(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a child script with UTF-8 output capture."""
    return subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )


def require_success(result: subprocess.CompletedProcess[str], label: str) -> None:
    """Raise a readable error when a pipeline step fails."""
    if result.returncode == 0:
        return
    detail = (result.stderr or result.stdout or "").strip()
    raise RuntimeError(f"{label} failed with exit code {result.returncode}: {detail}")


def convert_datasheets(workdir: Path) -> list[dict[str, str]]:
    """Convert downloaded PDF datasheets to text when pdftotext is available."""
    datasheets_dir = workdir / "datasheets"
    results: list[dict[str, str]] = []
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        return results

    for pdf in sorted(datasheets_dir.glob("*.pdf")):
        txt = pdf.with_suffix(".txt")
        if txt.exists() and txt.stat().st_size > 0:
            results.append({"pdf": str(pdf), "txt": str(txt), "status": "cached"})
            continue
        result = run_step([pdftotext, "-layout", str(pdf), str(txt)], cwd=workdir.parent)
        status = "converted" if result.returncode == 0 and txt.exists() else "failed"
        results.append({"pdf": str(pdf), "txt": str(txt), "status": status})
    return results


def extract_datasheet_facts(workdir: Path, project_root: Path) -> list[dict[str, str]]:
    """Extract structured facts from every datasheet text file."""
    datasheets_dir = workdir / "datasheets"
    facts_dir = workdir / "datasheet_facts"
    facts_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, str]] = []

    for txt in sorted(datasheets_dir.glob("*.txt")):
        output = facts_dir / f"{txt.stem}.json"
        result = run_step(
            [sys.executable, _script("extract_facts.py"), str(txt), "--output", str(output)],
            cwd=project_root,
        )
        status = "extracted" if result.returncode == 0 and output.exists() else "failed"
        results.append({"text": str(txt), "facts": str(output), "status": status})
    return results


def collect_limitations(workdir: Path, pdftotext_available: bool | None = None) -> dict[str, Any]:
    """Collect evidence gaps the agent must disclose instead of guessing over."""
    if pdftotext_available is None:
        pdftotext_available = shutil.which("pdftotext") is not None

    limitations: list[dict[str, str]] = []
    if not pdftotext_available:
        limitations.append({
            "reason": "pdftotext_not_available",
            "detail": "PDF datasheets could not be converted to text on this machine.",
        })

    sources = load_json_file(workdir / "datasheet_sources.json", {"sources": {}})
    for ref, source in sorted(sources.get("sources", {}).items()):
        status = source.get("status")
        if status == "not_found":
            limitations.append({
                "reason": "datasheet_not_found",
                "ref": ref,
                "part": str(source.get("part", "")),
            })

    enriched = load_json_file(workdir / "enriched.json", {"components": {}})
    for ref, comp in sorted(enriched.get("components", {}).items()):
        status = comp.get("datasheet_status")
        if status == "downloaded_no_facts":
            limitations.append({
                "reason": "datasheet_facts_missing",
                "ref": ref,
                "part": str(comp.get("part", "")),
            })
        elif status == "not_downloaded":
            limitations.append({
                "reason": "datasheet_not_downloaded",
                "ref": ref,
                "part": str(comp.get("part", "")),
            })

    return {
        "schema": "chip-netlist-limitations-v1",
        "limitation_count": len(limitations),
        "limitations": limitations,
    }


def build_analysis_stub(
    *,
    project_name: str,
    project_file: Path,
    workdir: Path,
    findings_path: Path,
    limitations_path: Path,
) -> dict[str, Any]:
    """Create a safe analysis skeleton for optional user-requested deep review."""
    findings = load_json_file(findings_path, {"finding_count": 0, "findings": []})
    limitations = load_json_file(limitations_path, {"limitation_count": 0, "limitations": []})
    return {
        "schema": "chip-netlist-analysis-stub-v1",
        "mode": "strict-auto-scan",
        "project": project_name,
        "project_file": str(project_file),
        "workdir": str(workdir),
        "requires_user_requested_deep_review": True,
        "inputs": {
            "chip_netlist": str(workdir / "chip_netlist.json"),
            "component_index": str(workdir / "component_index.json"),
            "enriched": str(workdir / "enriched.json"),
            "findings": str(findings_path),
            "limitations": str(limitations_path),
            "evidence_ledger": str(workdir / "evidence_ledger.json"),
            "claims_draft": str(workdir / "claims_draft.json"),
            "verified_claims": str(workdir / "verified_claims.json"),
        },
        "summary": {
            "finding_count": findings.get("finding_count", len(findings.get("findings", []))),
            "limitation_count": limitations.get("limitation_count", len(limitations.get("limitations", []))),
        },
        "conclusions": [],
        "next_step": "Ask the user which component or net to review deeply before adding conclusions.",
    }


def build_strict_claims_draft(workdir: Path) -> dict[str, Any]:
    """Create an empty claim file that cannot smuggle in unsupported conclusions."""
    return {
        "schema": "chip-netlist-claims-v1",
        "mode": "strict",
        "workdir": str(workdir),
        "instruction": "Add claims only after citing netlist_evidence and datasheet_evidence.",
        "claims": [],
    }


def run_pipeline(
    project_file: Path,
    *,
    project_root: Path,
    workdir: Path,
    project_name: str,
    skip_datasheets: bool = False,
) -> dict[str, Any]:
    """Run parse, rules, datasheet evidence, report, and analysis-stub steps."""
    workdir.mkdir(parents=True, exist_ok=True)
    paths = {
        "chip_netlist": workdir / "chip_netlist.json",
        "component_index": workdir / "component_index.json",
        "findings": workdir / "findings.json",
        "limitations": workdir / "limitations.json",
        "report": workdir / "report.md",
        "analysis_stub": workdir / "analysis_stub.json",
        "evidence_ledger": workdir / "evidence_ledger.json",
        "claims_draft": workdir / "claims_draft.json",
        "verified_claims": workdir / "verified_claims.json",
    }

    result = run_step(
        [sys.executable, _script("parse_project.py"), str(project_file), "--workdir", str(workdir)],
        cwd=project_root,
    )
    require_success(result, "parse_project")

    result = run_step(
        [
            sys.executable,
            _script("check_rules.py"),
            str(paths["chip_netlist"]),
            "--output",
            str(workdir / "findings_basic.json"),
        ],
        cwd=project_root,
    )
    require_success(result, "check_rules basic")

    conversions: list[dict[str, str]] = []
    fact_extractions: list[dict[str, str]] = []
    if not skip_datasheets:
        result = run_step(
            [
                sys.executable,
                _script("search_datasheet.py"),
                str(paths["component_index"]),
                "--workdir",
                str(workdir),
            ],
            cwd=project_root,
        )
        require_success(result, "search_datasheet")
        conversions = convert_datasheets(workdir)
        fact_extractions = extract_datasheet_facts(workdir, project_root)

    result = run_step([sys.executable, _script("build_enriched.py"), "--workdir", str(workdir)], cwd=project_root)
    require_success(result, "build_enriched")

    result = run_step(
        [
            sys.executable,
            _script("check_rules.py"),
            str(paths["chip_netlist"]),
            "--datasheet",
            "--output",
            str(paths["findings"]),
        ],
        cwd=project_root,
    )
    require_success(result, "check_rules datasheet")

    limitations = collect_limitations(workdir)
    write_json_file(paths["limitations"], limitations)

    evidence_ledger = build_evidence_ledger(workdir)
    write_json_file(paths["evidence_ledger"], evidence_ledger)

    claims_draft = build_strict_claims_draft(workdir)
    write_json_file(paths["claims_draft"], claims_draft)

    verified_claims = validate_claims(claims_draft, evidence_ledger)
    write_json_file(paths["verified_claims"], verified_claims)

    result = run_step(
        [
            sys.executable,
            _script("generate_report.py"),
            str(paths["findings"]),
            "--project",
            project_name,
            "--output",
            str(paths["report"]),
        ],
        cwd=project_root,
    )
    require_success(result, "generate_report")

    stub = build_analysis_stub(
        project_name=project_name,
        project_file=project_file,
        workdir=workdir,
        findings_path=paths["findings"],
        limitations_path=paths["limitations"],
    )
    write_json_file(paths["analysis_stub"], stub)

    summary = {
        "schema": "chip-netlist-pipeline-summary-v1",
        "project": project_name,
        "project_file": str(project_file),
        "workdir": str(workdir),
        "paths": {key: str(value) for key, value in paths.items()},
        "datasheet_conversions": conversions,
        "fact_extractions": fact_extractions,
    }
    write_json_file(workdir / "pipeline_summary.json", summary)
    return summary


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run the chip netlist pipeline.")
    parser.add_argument("project", type=Path, help="Path to an EasyEDA Pro .epro2 or .epro project")
    parser.add_argument("--workdir", type=Path, default=Path(DEFAULT_WORKDIR))
    parser.add_argument("--project-name", default="")
    parser.add_argument("--skip-datasheets", action="store_true", help="Skip network datasheet lookup")
    args = parser.parse_args(argv)

    project = args.project.resolve()
    if not project.exists():
        print(f"Error: project file not found: {project}", file=sys.stderr)
        return 1

    project_root = project.parent
    project_name = args.project_name or project.stem
    workdir = resolve_workdir(args.workdir, project_root)
    try:
        summary = run_pipeline(
            project,
            project_root=project_root,
            workdir=workdir,
            project_name=project_name,
            skip_datasheets=args.skip_datasheets,
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
