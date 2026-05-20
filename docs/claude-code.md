# Install for Claude Code

Claude Code supports skills as folders under `~/.claude/skills/<skill-name>/SKILL.md`.

## One-Line Install

These commands install from `yangzhaoxu411/chip-netlist-skill`.

Windows PowerShell:

```powershell
$env:TARGET="claude"; irm https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/v0.1.8/install.ps1 | iex
```

macOS / Linux / Git Bash:

```bash
curl -fsSL https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/v0.1.8/install.sh | bash -s -- --target claude
```

## Update to Latest

Windows PowerShell:

```powershell
$env:TARGET="claude"; $tag=(irm https://api.github.com/repos/yangzhaoxu411/chip-netlist-skill/releases/latest).tag_name; irm "https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/$tag/install.ps1" | iex
```

View the installed version:

Windows:

```powershell
python "$env:USERPROFILE\.claude\skills\chip-netlist\scripts\parse_tel_netlist.py" --version
```

macOS / Linux:

```bash
python ~/.claude/skills/chip-netlist/scripts/parse_tel_netlist.py --version
```

## Manual Install

Windows:

```powershell
git clone https://github.com/yangzhaoxu411/chip-netlist-skill.git
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\skills" | Out-Null
Copy-Item -Recurse -Force .\chip-netlist-skill\chip-netlist "$env:USERPROFILE\.claude\skills\chip-netlist"
```

macOS / Linux:

```bash
git clone https://github.com/yangzhaoxu411/chip-netlist-skill.git
mkdir -p ~/.claude/skills
rm -rf ~/.claude/skills/chip-netlist
cp -R chip-netlist-skill/chip-netlist ~/.claude/skills/chip-netlist
```

Restart Claude Code after installation.

## Usage

```text
Use $chip-netlist to analyze this .epro2 project and optional chip PDF data sheet. Infer the configuration one small functional pin group at a time. In each reply, focus on exactly one current group, explain what the connection makes the circuit do, calculate the resulting parameter when possible, self-check your judgment before answering, and wait for my Y/N confirmation before moving to the next group.
```


