"""Contract tests for the skill instructions and UI metadata."""
from __future__ import annotations

from pathlib import Path

import yaml


SKILL_DIR = Path(__file__).resolve().parent.parent / "chip-netlist"


def test_skill_points_default_users_to_run_pipeline() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "run_pipeline.py" in text
    assert "Strict Accuracy Mode" in text
    assert "Data must come from chip datasheets" in text
    assert "strict_claims.py" in text


def test_skill_default_path_has_no_hardcoded_project_examples() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    forbidden = ("U1.38", "U6.8", "LTC4015", "grep -A")
    for token in forbidden:
        assert token not in text


def test_skill_requires_claim_validation_before_presenting_chip_conclusions() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "verified_claims.json" in text
    assert "rejected" in text
    assert "Do not present rejected claims" in text


def test_agents_openai_yaml_uses_policy_shape() -> None:
    data = yaml.safe_load((SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8"))
    assert data["interface"]["display_name"] == "Chip Netlist Strict Review"
    assert "$chip-netlist" in data["interface"]["default_prompt"]
    assert data["policy"]["allow_implicit_invocation"] is True
