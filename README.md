# chip-netlist

`chip-netlist` is an Agent Skill for reverse-engineering chip configuration from a searchable PDF data sheet and a `.tel` netlist.

It is designed for electronic-circuit analysis where an agent should:

- read the chip data sheet,
- parse the `.tel` netlist,
- inspect one pin or one functional pin group at a time,
- infer the configured function or parameter,
- call out questionable connections only when there is evidence,
- stop for `Y/N` confirmation before continuing.

The skill includes a deterministic parser:

```text
chip-netlist/scripts/parse_tel_netlist.py
```

## Repository Layout

```text
chip-netlist-skill/
|-- chip-netlist/
|   |-- SKILL.md
|   |-- agents/openai.yaml
|   `-- scripts/parse_tel_netlist.py
|-- docs/
|   |-- usage.md
|   |-- codex.md
|   |-- claude-code.md
|   `-- opencode.md
|-- install.ps1
`-- install.sh
```

## Quick Install

These commands install from `yangzhaoxu411/chip-netlist-skill`.

### Windows PowerShell

Install for Codex:

```powershell
$env:TARGET="codex"; irm https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/v0.1.0/install.ps1 | iex
```

Install for Codex, Claude Code, and OpenCode:

```powershell
$env:TARGET="all"; irm https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/v0.1.0/install.ps1 | iex
```

### macOS / Linux / Git Bash

Install for Codex:

```bash
curl -fsSL https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/v0.1.0/install.sh | bash -s -- --target codex
```

Install for Codex, Claude Code, and OpenCode:

```bash
curl -fsSL https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/v0.1.0/install.sh | bash -s -- --target all
```

## Local Install From a Clone

```bash
git clone https://github.com/yangzhaoxu411/chip-netlist-skill.git
cd chip-netlist-skill
./install.sh --target codex
```

Windows:

```powershell
git clone https://github.com/yangzhaoxu411/chip-netlist-skill.git
cd chip-netlist-skill
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Target codex
```

## Usage Prompt

```text
Use $chip-netlist to analyze:
Data sheet: C:\path\to\chip.pdf
Netlist: C:\path\to\board.tel

Infer the chip configuration pin group by pin group. For each group, show netlist evidence, data sheet evidence, inferred result, and questionable points only when present. Wait for my Y/N confirmation before continuing.
```

If the agent supports implicit skills, providing both a chip PDF data sheet and a `.tel` netlist should be enough to trigger this skill.

## Tool-Specific Guides

- [Codex installation](docs/codex.md)
- [Claude Code installation](docs/claude-code.md)
- [OpenCode installation](docs/opencode.md)
- [Detailed usage](docs/usage.md)

## References

- OpenAI skills catalog: https://github.com/openai/skills
- Claude Code skills documentation: https://docs.claude.com/en/docs/claude-code/skills
- OpenCode skills documentation: https://opencode.ubitools.com/skills/
