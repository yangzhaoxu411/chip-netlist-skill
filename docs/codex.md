# Install for Codex

Codex skills are self-contained folders with a required `SKILL.md`. This repository installs the `chip-netlist/` folder into your Codex skills directory.

## One-Line Install

These commands install from `yangzhaoxu411/chip-netlist-skill`.

Windows PowerShell:

```powershell
$env:TARGET="codex"; irm https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/v0.1.7/install.ps1 | iex
```

macOS / Linux / Git Bash:

```bash
curl -fsSL https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/v0.1.7/install.sh | bash -s -- --target codex
```

## Update to Latest

Windows PowerShell:

```powershell
$env:TARGET="codex"; $tag=(irm https://api.github.com/repos/yangzhaoxu411/chip-netlist-skill/releases/latest).tag_name; irm "https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/$tag/install.ps1" | iex
```

macOS / Linux / Git Bash:

```bash
tag="$(curl -fsSL https://api.github.com/repos/yangzhaoxu411/chip-netlist-skill/releases/latest | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -n1)" && curl -fsSL "https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/${tag}/install.sh" | bash -s -- --target codex
```

## Manual Install

Windows:

```powershell
git clone https://github.com/yangzhaoxu411/chip-netlist-skill.git
New-Item -ItemType Directory -Force "$env:USERPROFILE\.codex\skills" | Out-Null
Copy-Item -Recurse -Force .\chip-netlist-skill\chip-netlist "$env:USERPROFILE\.codex\skills\chip-netlist"
```

macOS / Linux:

```bash
git clone https://github.com/yangzhaoxu411/chip-netlist-skill.git
mkdir -p ~/.codex/skills
rm -rf ~/.codex/skills/chip-netlist
cp -R chip-netlist-skill/chip-netlist ~/.codex/skills/chip-netlist
```

Restart Codex after installation so the skill index refreshes.

## Verify

```bash
python ~/.codex/skills/chip-netlist/scripts/parse_tel_netlist.py /path/to/board.epro2 --ref U1
```

On Windows:

```powershell
python "$env:USERPROFILE\.codex\skills\chip-netlist\scripts\parse_tel_netlist.py" C:\path\to\board.epro2 --ref U1
```

View the installed version:

Windows:

```powershell
python "$env:USERPROFILE\.codex\skills\chip-netlist\scripts\parse_tel_netlist.py" --version
```

macOS / Linux:

```bash
python ~/.codex/skills/chip-netlist/scripts/parse_tel_netlist.py --version
```


