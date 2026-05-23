#!/usr/bin/env python3
"""Generate a Markdown report from findings and analysis."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SEVERITY_ORDER = {"must-fix": 0, "high": 1, "medium": 2, "low": 3, "info": 4, "unknown": 5}
SEVERITY_LABELS = {
    "must-fix": "MUST FIX",
    "high": "HIGH",
    "medium": "MEDIUM",
    "low": "LOW",
    "info": "INFO",
    "unknown": "UNKNOWN",
}

# Color-coded HTML badges for severity levels
SEVERITY_BADGE = {
    "must-fix": '<span style="background:#d32f2f;color:#fff;padding:2px 8px;border-radius:4px;font-weight:bold;">MUST FIX</span>',
    "high":     '<span style="background:#f57c00;color:#fff;padding:2px 8px;border-radius:4px;font-weight:bold;">HIGH</span>',
    "medium":   '<span style="background:#fbc02d;color:#333;padding:2px 8px;border-radius:4px;font-weight:bold;">MEDIUM</span>',
    "low":      '<span style="background:#1976d2;color:#fff;padding:2px 8px;border-radius:4px;font-weight:bold;">LOW</span>',
    "info":     '<span style="background:#757575;color:#fff;padding:2px 8px;border-radius:4px;">INFO</span>',
    "unknown":  '<span style="background:#bdbdbd;color:#333;padding:2px 8px;border-radius:4px;">UNKNOWN</span>',
}

# Color-coded HTML badges for confidence levels
CONFIDENCE_BADGE = {
    "confirmed":  '<span style="background:#388e3c;color:#fff;padding:2px 8px;border-radius:4px;font-weight:bold;">Confirmed</span>',
    "likely":     '<span style="background:#1976d2;color:#fff;padding:2px 8px;border-radius:4px;">Likely</span>',
    "suspicious": '<span style="background:#d32f2f;color:#fff;padding:2px 8px;border-radius:4px;font-weight:bold;">Suspicious</span>',
    "unknown":    '<span style="background:#bdbdbd;color:#333;padding:2px 8px;border-radius:4px;">Unknown</span>',
}


def _badge(level: str, badge_map: dict[str, str]) -> str:
    """Return colored HTML badge, fallback to plain text."""
    return badge_map.get(level, f"`{level}`")


def generate_report(findings: list[dict[str, Any]], project_name: str = "") -> str:
    """Generate Markdown report from findings list."""
    lines = [
        "# Chip Netlist Report",
        "",
    ]
    if project_name:
        lines.append(f"**Project:** {project_name}")
        lines.append("")

    # Summary table stays plain-text so it is easy to parse and diff.
    severity_counts: dict[str, int] = {}
    for f in findings:
        sev = f.get("severity", "unknown")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    lines.append("## Summary")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|----------|-------|")
    for sev in ("must-fix", "high", "medium", "low", "info", "unknown"):
        count = severity_counts.get(sev, 0)
        if count > 0:
            lines.append(f"| {SEVERITY_LABELS[sev]} | {count} |")
    lines.append(f"| **Total** | **{len(findings)}** |")
    lines.append("")

    if not findings:
        lines.append("No defects found. The schematic passed all automated checks.")
        lines.append("")
        return "\n".join(lines)

    # Findings by severity
    sorted_findings = sorted(findings, key=lambda f: SEVERITY_ORDER.get(f.get("severity", "unknown"), 99))

    current_severity = None
    for f in sorted_findings:
        sev = f.get("severity", "unknown")
        if sev != current_severity:
            current_severity = sev
            lines.append(f"## {SEVERITY_LABELS[sev]}")
            lines.append("")

        rule_id = f.get("rule_id", "?")
        target = f.get("target", "?")
        net = f.get("net", "")
        message = f.get("message", "")
        suggestion = f.get("suggestion", "")
        confidence = f.get("confidence", "")

        # Badge line: severity + optional confidence
        badge_line = _badge(sev, SEVERITY_BADGE)
        if confidence:
            badge_line += f" &nbsp; {_badge(confidence, CONFIDENCE_BADGE)}"

        lines.append(f"### [{rule_id}] {target}")
        lines.append(badge_line)
        lines.append("")
        if net:
            lines.append(f"**Net:** `{net}`")
        lines.append(f"**Issue:** {message}")
        if suggestion:
            lines.append(f"**Suggestion:** {suggestion}")

        # Show conflicts if any
        conflicts = f.get("conflicts_with", [])
        if conflicts:
            lines.append("")
            lines.append("**Conflicts with LLM analysis:**")
            for c in conflicts:
                lines.append(f"- {c.get('text', '')}")
        lines.append("")

    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Generate chip netlist report.")
    parser.add_argument("findings", type=Path, help="Path to findings.json")
    parser.add_argument("--output", type=Path, help="Output path for report.md")
    parser.add_argument("--project", default="", help="Project name")
    args = parser.parse_args(argv)

    if not args.findings.exists():
        print(f"Error: Findings file not found: {args.findings}", file=sys.stderr)
        return 1

    try:
        data = json.loads(args.findings.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {args.findings}: {e}", file=sys.stderr)
        return 1

    findings = data.get("findings", [])
    report = generate_report(findings, args.project)

    if args.output:
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
