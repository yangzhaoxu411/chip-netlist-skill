# Claude Code Install

Install the skill for Claude Code:

```powershell
$env:TARGET="claude"; irm https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/main/install.ps1 | iex
```

Verify:

```powershell
python "$env:USERPROFILE\.claude\skills\chip-netlist\scripts\run_pipeline.py" --help
python "$env:USERPROFILE\.claude\skills\chip-netlist\scripts\strict_claims.py" --help
```

Use:

```powershell
python "$env:USERPROFILE\.claude\skills\chip-netlist\scripts\run_pipeline.py" "C:\path\to\board.epro2" --workdir .chip-netlist
```
