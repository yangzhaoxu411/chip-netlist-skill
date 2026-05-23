"""Base rule utilities."""
from __future__ import annotations

from typing import Any


def make_finding(
    rule_id: str,
    severity: str,
    category: str,
    target: str,
    message: str,
    net: str | None = None,
    evidence: dict[str, str] | None = None,
    suggestion: str | None = None,
) -> dict[str, Any]:
    """Create a standardized finding dict."""
    finding: dict[str, Any] = {
        "rule_id": rule_id,
        "severity": severity,
        "category": category,
        "target": target,
        "message": message,
    }
    if net:
        finding["net"] = net
    if evidence:
        finding["evidence"] = evidence
    if suggestion:
        finding["suggestion"] = suggestion
    return finding
