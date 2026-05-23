#!/usr/bin/env python3
"""Cross-verify rule findings against LLM analysis conclusions.

Compares findings.json (deterministic rules) with analysis.json (LLM output)
to detect contradictions and produce a unified verified report with confidence
levels: confirmed, likely, suspicious, unknown.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Lowercase and strip for comparison."""
    return text.lower().strip()


def _targets_overlap(finding: dict[str, Any], conclusion: dict[str, Any]) -> bool:
    """Check if a finding and conclusion refer to the same target (pin/net/component)."""
    f_target = _normalize(finding.get("target", ""))
    f_net = _normalize(finding.get("net", ""))

    c_text = _normalize(conclusion.get("text", "") or conclusion.get("conclusion", ""))

    if not f_target and not f_net:
        return False

    # Check if finding target appears in conclusion text
    if f_target and f_target in c_text:
        return True
    if f_net and f_net in c_text:
        return True

    return False


def _is_contradiction(finding: dict[str, Any], conclusion: dict[str, Any]) -> bool:
    """Heuristic: does the conclusion contradict the finding?

    A contradiction exists when:
    - Finding says "missing X" but conclusion says "X is present"
    - Finding says "floating pin" but conclusion says "properly connected"
    - Finding severity is high/must-fix but conclusion says "no defect"
    """
    f_msg = _normalize(finding.get("message", ""))
    c_text = _normalize(conclusion.get("text", "") or conclusion.get("conclusion", ""))
    f_severity = finding.get("severity", "")

    if not f_msg or not c_text:
        return False

    # Finding says missing, conclusion says present
    missing_keywords = ("missing", "no ", "浮空", "缺少", "没有", "未连接")
    present_keywords = ("connected", "present", "properly", "正常", "已连接", "有")

    f_says_missing = any(kw in f_msg for kw in missing_keywords)
    c_says_present = any(kw in c_text for kw in present_keywords)

    if f_says_missing and c_says_present:
        return True

    # Finding says floating, conclusion says connected
    if "floating" in f_msg or "浮空" in f_msg:
        if "connected" in c_text or "connected" in c_text:
            return True

    # Conclusion explicitly says "no defect" for a high/must-fix finding
    if f_severity in ("high", "must-fix"):
        no_defect = ("no defect", "no issue", "no problem", "没有问题", "无缺陷", "正常")
        if any(kw in c_text for kw in no_defect):
            return True

    return False


# ---------------------------------------------------------------------------
# Confidence assignment
# ---------------------------------------------------------------------------

def assign_confidence(
    finding: dict[str, Any],
    conflicting_conclusions: list[dict[str, Any]],
    supporting_conclusions: list[dict[str, Any]],
) -> str:
    """Assign confidence level to a finding based on LLM agreement.

    Returns: confirmed, likely, suspicious, unknown
    """
    if conflicting_conclusions:
        return "suspicious"

    if supporting_conclusions:
        # LLM agrees with the finding
        if finding.get("severity") in ("must-fix", "high"):
            return "confirmed"
        return "likely"

    # No LLM comment on this finding
    if finding.get("severity") in ("must-fix", "high"):
        return "likely"  # Rule caught something LLM didn't mention
    return "unknown"


def assign_conclusion_confidence(
    conclusion: dict[str, Any],
    conflicting_findings: list[dict[str, Any]],
    supporting_findings: list[dict[str, Any]],
) -> str:
    """Assign confidence level to an LLM conclusion based on rule agreement."""
    verification = conclusion.get("verification", {})
    v_status = verification.get("status", "")

    if v_status == "hallucinated":
        return "suspicious"

    if conflicting_findings:
        return "suspicious"

    if v_status == "verified":
        if supporting_findings:
            return "confirmed"
        return "likely"

    if v_status == "unverified":
        return "unknown"

    return "unknown"


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def cross_verify(
    findings: list[dict[str, Any]],
    conclusions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Cross-verify findings and conclusions.

    Args:
        findings: List of finding dicts from check_rules.py
        conclusions: List of conclusion dicts from LLM analysis

    Returns:
        Dict with verified findings, verified conclusions, and conflict report.
    """
    # Build conflict maps
    finding_conflicts: dict[int, list[int]] = {}  # finding_idx → [conc_idx]
    conclusion_conflicts: dict[int, list[int]] = {}  # conc_idx → [finding_idx]
    finding_support: dict[int, list[int]] = {}
    conclusion_support: dict[int, list[int]] = {}

    for fi, finding in enumerate(findings):
        for ci, conclusion in enumerate(conclusions):
            if _targets_overlap(finding, conclusion):
                if _is_contradiction(finding, conclusion):
                    finding_conflicts.setdefault(fi, []).append(ci)
                    conclusion_conflicts.setdefault(ci, []).append(fi)
                else:
                    finding_support.setdefault(fi, []).append(ci)
                    conclusion_support.setdefault(ci, []).append(fi)

    # Build verified findings
    verified_findings = []
    for fi, finding in enumerate(findings):
        conflicts = [conclusions[ci] for ci in finding_conflicts.get(fi, [])]
        supports = [conclusions[ci] for ci in finding_support.get(fi, [])]
        confidence = assign_confidence(finding, conflicts, supports)

        vf = {
            **finding,
            "confidence": confidence,
        }
        if conflicts:
            vf["conflicts_with"] = [
                {"index": ci, "text": conclusions[ci].get("text") or conclusions[ci].get("conclusion", "")}
                for ci in finding_conflicts[fi]
            ]
        verified_findings.append(vf)

    # Build verified conclusions
    verified_conclusions = []
    for ci, conclusion in enumerate(conclusions):
        conflicts = [findings[fi] for fi in conclusion_conflicts.get(ci, [])]
        supports = [findings[fi] for fi in conclusion_support.get(ci, [])]
        confidence = assign_conclusion_confidence(conclusion, conflicts, supports)

        vc = {
            **conclusion,
            "cross_confidence": confidence,
        }
        if conflicts:
            vc["conflicts_with"] = [
                {"rule_id": f.get("rule_id"), "target": f.get("target"), "message": f.get("message")}
                for f in conflicts
            ]
        verified_conclusions.append(vc)

    # Build conflict report
    conflicts = []
    for fi, ci_list in finding_conflicts.items():
        for ci in ci_list:
            conflicts.append({
                "finding_index": fi,
                "finding_rule": findings[fi].get("rule_id"),
                "finding_target": findings[fi].get("target"),
                "conclusion_index": ci,
                "type": "contradiction",
            })

    # Confidence summary
    confidence_counts: dict[str, int] = {}
    for vf in verified_findings:
        c = vf.get("confidence", "unknown")
        confidence_counts[c] = confidence_counts.get(c, 0) + 1

    return {
        "verified_findings": verified_findings,
        "verified_conclusions": verified_conclusions,
        "conflicts": conflicts,
        "conflict_count": len(conflicts),
        "confidence_summary": confidence_counts,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Cross-verify rule findings against LLM analysis."
    )
    parser.add_argument(
        "findings",
        type=Path,
        help="Path to findings.json",
    )
    parser.add_argument(
        "analysis",
        type=Path,
        help="Path to analysis.json (LLM conclusions)",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output path for cross_verified.json (default: stdout)",
    )
    args = parser.parse_args(argv)

    if not args.findings.exists():
        print(f"Error: {args.findings} not found", file=sys.stderr)
        return 1
    if not args.analysis.exists():
        print(f"Error: {args.analysis} not found", file=sys.stderr)
        return 1

    findings_data = json.loads(args.findings.read_text(encoding="utf-8"))
    analysis_data = json.loads(args.analysis.read_text(encoding="utf-8"))

    findings = findings_data.get("findings", [])
    conclusions = analysis_data.get("conclusions", [])

    result = cross_verify(findings, conclusions)

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"Conflicts: {result['conflict_count']}", file=sys.stderr)
        summary = result.get("confidence_summary", {})
        print(f"Confidence: {json.dumps(summary, ensure_ascii=False)}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
