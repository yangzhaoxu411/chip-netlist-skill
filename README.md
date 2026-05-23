# chip-netlist

`chip-netlist` is an Agent Skill for strict, datasheet-backed review of EasyEDA Pro `.epro2` and `.epro` projects.

This version runs in **Strict Accuracy Mode**: chip-level conclusions must be supported by parsed project evidence and matching data-sheet evidence, then pass `strict_claims.py` before they are presented as conclusions.

## What It Does

- Parses EasyEDA Pro projects into AI-readable component, pin, and net evidence.
- Builds a persistent `.chip-netlist` workbench with `chip_netlist.json`, `component_index.json`, context packets, downloaded data sheets, extracted facts, findings, reports, and limitations.
- Downloads and extracts data-sheet facts for active or high-priority parts where possible.
- Runs deterministic schematic checks and datasheet-backed checks.
- Requires LLM-written claims to be validated before they are treated as accepted chip conclusions.

## Repository Layout

```text
chip-netlist-skill/
|-- chip-netlist/
|   |-- SKILL.md
|   |-- VERSION
|   |-- agents/openai.yaml
|   `-- scripts/
|       |-- run_pipeline.py
|       |-- parse_project.py
|       |-- strict_claims.py
|       |-- search_datasheet.py
|       |-- extract_facts.py
|       |-- build_enriched.py
|       |-- check_rules.py
|       |-- generate_report.py
|       `-- parse_tel_netlist.py
|-- tests/
|-- install.ps1
`-- install.sh
```

`parse_tel_netlist.py` is retained as a compatibility wrapper for older workflows; new workflows should use `parse_project.py` or `run_pipeline.py`.

## Quick Install

Install for Codex:

```powershell
$env:TARGET="codex"; irm https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/main/install.ps1 | iex
```

Install for Claude Code:

```powershell
$env:TARGET="claude"; irm https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/main/install.ps1 | iex
```

Install for Codex, Claude Code, and OpenCode:

```powershell
$env:TARGET="all"; irm https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/main/install.ps1 | iex
```

macOS / Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/main/install.sh | bash -s -- --target codex
```

## Manual Use

After installation, resolve `scripts/` relative to the installed `chip-netlist` skill directory. From the directory containing the target project:

```bash
python "<skill-dir>/scripts/run_pipeline.py" "<project.epro2>" --workdir .chip-netlist
```

The generated `report.md` is triage. Data-sheet-backed chip claims should be placed in a claims JSON file and validated:

```bash
python "<skill-dir>/scripts/strict_claims.py" --workdir .chip-netlist --claims claims.json --output .chip-netlist/verified_claims.json
```

No accepted claim means no chip-level conclusion.
