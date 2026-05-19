# Install for Claude Code

Claude Code supports skills as folders under `~/.claude/skills/<skill-name>/SKILL.md`.

## One-Line Install

These commands install from `yangzhaoxu411/chip-netlist-skill`.

Windows PowerShell:

```powershell
$env:TARGET="claude"; irm https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/v0.1.2/install.ps1 | iex
```

macOS / Linux / Git Bash:

```bash
curl -fsSL https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/v0.1.2/install.sh | bash -s -- --target claude
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
Use $chip-netlist to analyze this chip PDF data sheet and .tel netlist. Infer the configuration one functional pin group at a time and wait for my Y/N confirmation after each group.
```


