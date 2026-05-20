# Install for OpenCode

OpenCode discovers skills from locations including `~/.config/opencode/skill/<name>/SKILL.md` and Claude-compatible `~/.claude/skills/<name>/SKILL.md`.

This installer uses the native OpenCode global path:

```text
~/.config/opencode/skill/chip-netlist/SKILL.md
```

## One-Line Install

These commands install from `yangzhaoxu411/chip-netlist-skill`.

Windows PowerShell:

```powershell
$env:TARGET="opencode"; irm https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/v0.1.7/install.ps1 | iex
```

macOS / Linux / Git Bash:

```bash
curl -fsSL https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/v0.1.7/install.sh | bash -s -- --target opencode
```

## Update to Latest

Windows PowerShell:

```powershell
$env:TARGET="opencode"; $tag=(irm https://api.github.com/repos/yangzhaoxu411/chip-netlist-skill/releases/latest).tag_name; irm "https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/$tag/install.ps1" | iex
```

View the installed version:

Windows:

```powershell
python "$env:USERPROFILE\.config\opencode\skill\chip-netlist\scripts\parse_tel_netlist.py" --version
```

macOS / Linux:

```bash
python ~/.config/opencode/skill/chip-netlist/scripts/parse_tel_netlist.py --version
```

## Manual Install

Windows:

```powershell
git clone https://github.com/yangzhaoxu411/chip-netlist-skill.git
New-Item -ItemType Directory -Force "$env:USERPROFILE\.config\opencode\skill" | Out-Null
Copy-Item -Recurse -Force .\chip-netlist-skill\chip-netlist "$env:USERPROFILE\.config\opencode\skill\chip-netlist"
```

macOS / Linux:

```bash
git clone https://github.com/yangzhaoxu411/chip-netlist-skill.git
mkdir -p ~/.config/opencode/skill
rm -rf ~/.config/opencode/skill/chip-netlist
cp -R chip-netlist-skill/chip-netlist ~/.config/opencode/skill/chip-netlist
```

Restart OpenCode after installation.

## Usage

```text
Use chip-netlist to analyze this .epro2 project and optional chip PDF data sheet. Infer the configuration one functional pin group at a time and wait for my Y/N confirmation after each group.
```


