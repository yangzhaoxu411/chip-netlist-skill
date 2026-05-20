# chip-netlist

`chip-netlist` is an Agent Skill for extracting AI-ready connectivity from an EasyEDA Pro `.epro2` project and reverse-engineering chip configuration from that project plus an optional searchable PDF data sheet.

**文件范围 / File scope:** 当前版本只支持 EasyEDA Pro `.epro2` 工程文件；不支持 `.epro`、`.tel` 或其它网表格式。  
**File scope:** This version supports only EasyEDA Pro `.epro2` project files; `.epro`, `.tel`, and other netlist formats are not supported.

## 简介 / Introduction

`chip-netlist` 是一个面向电子电路分析的 Agent Skill。它的核心用途不是简单地把网表打印出来，而是让 Codex、Claude Code、OpenCode 这类 AI 编程/分析助手从 EasyEDA Pro `.epro2` 工程文件中提取 AI 容易理解的器件信息和网络连接，再按照工程师审图的方式逐个引脚、逐个功能组反推出芯片在这张板子上的真实配置。

`chip-netlist` is an Agent Skill for electronic-circuit analysis. It is not just a netlist printer. It helps AI coding and analysis agents such as Codex, Claude Code, and OpenCode extract AI-friendly component and connectivity data from an EasyEDA Pro `.epro2` project, then review the design like a hardware engineer: inspect pins and functional pin groups one by one and reverse-engineer how the chip is really configured on the board.

在实际硬件设计中，很多芯片的工作模式并不是通过软件设置的，而是由引脚连接决定的，例如电池节数选择、充电化学体系选择、I2C/SMBus 上拉、地址配置、开关频率电阻、NTC 温度检测、MPPT/电源路径、限流采样、电流检测、栅极驱动、补偿网络等。`chip-netlist` 会解析 `.epro2` 工程内部的 `COMPONENT / ATTR / NET / PAD_NET` 记录，提取“位号 -> 真实器件型号/参数/封装”和“位号.引脚 -> 网络 -> 同网连接对象”，再结合数据手册中的引脚说明、配置表、典型应用电路和推荐参数，推断这颗芯片被设计成了什么模式、使用了哪些参数、哪些功能被启用或禁用。

In real hardware designs, many chip operating modes are not configured by software. They are set by pin connections and external components, such as battery cell-count selection, charger chemistry selection, I2C/SMBus pullups, address pins, switching-frequency resistors, NTC temperature sensing, MPPT or power-path behavior, current-limit sampling, current sensing, gate driving, and compensation networks. `chip-netlist` parses `COMPONENT / ATTR / NET / PAD_NET` records inside the `.epro2` project to extract `reference -> real part/value/footprint` and `reference.pin -> net -> peer pins`, then combines that evidence with data sheet pin descriptions, configuration tables, typical application circuits, and recommended values to infer selected modes, configured parameters, and enabled or disabled functions.

它也可以用于辅助排查 PCB 原理图设计中的错误和不合理之处。比如：配置脚上下拉方向是否接反、应悬空的脚是否误接、关键功能脚是否缺少上拉/下拉、补偿电容电阻是否与数据手册推荐值明显不符、I2C 上拉电阻是否缺失、模拟地和功率地连接是否可疑、检测电阻/分压电阻取值是否导致阈值异常、未使用功能是否按手册要求处理、引脚连接是否与目标电池节数或目标工作模式不一致等。它不会替代 ERC/DRC，也不会替代工程师最终判断，但可以作为原理图审查、PCB 设计复核、芯片外围电路检查和硬件 bring-up 前风险排查的辅助工具。

It can also help find schematic and PCB-design mistakes or questionable choices. Examples include configuration pins pulled the wrong way, pins that should be floating but are connected, missing pullups or pulldowns on key function pins, compensation capacitors or resistors that differ sharply from the data sheet recommendation, missing I2C pullups, suspicious analog-ground and power-ground connections, sense or divider resistor values that imply abnormal thresholds, unused functions not handled as recommended, or pin connections that conflict with the intended battery cell count or operating mode. It does not replace ERC/DRC or final engineering judgment, but it is useful for schematic review, PCB design review, peripheral-circuit checking, and pre-bring-up risk screening.

The skill is designed for circuit-review workflows where an agent should:

- read the chip data sheet,
- parse the `.epro2` project into AI-ready JSON,
- inspect exactly one small pin group or one functional decision per reply,
- infer the configured function or parameter,
- explain what the connection makes the circuit do, not only how it is connected,
- calculate resulting values such as current limits, thresholds, timing, frequency, or logic state when data sheet formulas and project values are available,
- self-check the focused judgment before answering,
- compare the actual schematic connection against the data sheet recommendation,
- call out questionable schematic or PCB-design choices only when there is evidence,
- stop for `Y/N` confirmation before continuing.

For dense power ICs, the default group should be small. For example, a hot-swap controller should be reviewed as separate groups for `VIN/SENSE/OUT/GATE`, `UVLO`, `OVLO`, `TIMER`, `PWR`, and `PGD/status`, instead of one large all-in-one answer.

Typical review targets include configuration pins, mode-select pins, pullups and pulldowns, sense networks, divider networks, compensation networks, I2C/SMBus pins, power-path pins, thermal/NTC pins, and pins that are tied high, tied low, floating, or connected differently from the data sheet's typical application.

The skill includes a deterministic parser:

```text
chip-netlist/scripts/parse_tel_netlist.py
```

The parser output is designed to be re-used by AI agents. Generated JSON includes:

```json
{
  "schema": "chip-netlist-ai-json-v1",
  "generated_by": {
    "tool": "chip-netlist"
  }
}
```

If a user later uploads this JSON and asks to analyze a circuit section, the agent can use it directly without the original `.epro2` file.

## Automatic Data Sheet Lookup

The skill can work without user-provided data sheets. When the user asks to analyze a circuit area such as `U6`, `+28V_IN`, `12V output`, or `Q1/Q2 surrounding circuit`, the agent should:

- identify the matching refs, nets, rails, and peer components from the generated JSON,
- choose relevant active or critical parts from `datasheet_lookup.candidates`,
- search online for matching data sheets or product pages,
- prefer official manufacturer sources, then authorized distributors, then data-sheet mirrors only as fallback,
- cite the source URLs used for every data-sheet-based conclusion,
- clearly state when no reliable data sheet was found.

Ordinary resistors and capacitors are skipped by default unless they are part of a critical network such as shunts, feedback dividers, NTC/PTC sensing, timing, or compensation.

## Memory-Safe Workbench

For large boards, the skill should not load the full project and many unrelated PDFs into one long conversation. Use a persistent `.chip-netlist` workbench and analyze one small context packet at a time:

```bash
python chip-netlist/scripts/parse_tel_netlist.py board.epro2 --workdir .chip-netlist
python chip-netlist/scripts/parse_tel_netlist.py board.epro2 --context U5 --workdir .chip-netlist
```

The workbench stores:

- `chip_netlist.json`: full extracted project evidence,
- `component_index.json`: compact component identity and search-term index,
- `context_packets/<area>.json`: small AI-loadable circuit slices,
- `datasheet_sources.json`: verified data-sheet URLs and local PDF paths,
- `datasheet_facts/`: extracted pinouts, formulas, limits, and application notes,
- `analysis_state.json`: confirmed/pending/rejected groups,
- `analysis_report.md`: human-readable review notes.

This lets Codex, Claude Code, or OpenCode resume after long conversations, reload only the current circuit area, and avoid confusing unrelated component data sheets.
Context packets mark data-sheet targets as `primary` or `neighbor`, so the agent searches the selected chip first and only checks neighboring parts when their limits or formulas matter.

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
$env:TARGET="codex"; irm https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/v0.1.8/install.ps1 | iex
```

Install for Codex, Claude Code, and OpenCode:

```powershell
$env:TARGET="all"; irm https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/v0.1.8/install.ps1 | iex
```

### macOS / Linux / Git Bash

Install for Codex:

```bash
curl -fsSL https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/v0.1.8/install.sh | bash -s -- --target codex
```

Install for Codex, Claude Code, and OpenCode:

```bash
curl -fsSL https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/v0.1.8/install.sh | bash -s -- --target all
```

## Update to Latest

Update the Codex installation to the newest GitHub release:

```powershell
$env:TARGET="codex"; $tag=(irm https://api.github.com/repos/yangzhaoxu411/chip-netlist-skill/releases/latest).tag_name; irm "https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/$tag/install.ps1" | iex
```

Update Codex, Claude Code, and OpenCode together:

```powershell
$env:TARGET="all"; $tag=(irm https://api.github.com/repos/yangzhaoxu411/chip-netlist-skill/releases/latest).tag_name; irm "https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/$tag/install.ps1" | iex
```

macOS / Linux / Git Bash:

```bash
tag="$(curl -fsSL https://api.github.com/repos/yangzhaoxu411/chip-netlist-skill/releases/latest | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -n1)" && curl -fsSL "https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/${tag}/install.sh" | bash -s -- --target codex
```

## View Version

Windows PowerShell:

Codex:

```powershell
python "$env:USERPROFILE\.codex\skills\chip-netlist\scripts\parse_tel_netlist.py" --version
```

Claude Code:

```powershell
python "$env:USERPROFILE\.claude\skills\chip-netlist\scripts\parse_tel_netlist.py" --version
```

OpenCode:

```powershell
python "$env:USERPROFILE\.config\opencode\skill\chip-netlist\scripts\parse_tel_netlist.py" --version
```

macOS / Linux / Git Bash:

Codex:

```bash
python ~/.codex/skills/chip-netlist/scripts/parse_tel_netlist.py --version
```

Claude Code:

```bash
python ~/.claude/skills/chip-netlist/scripts/parse_tel_netlist.py --version
```

OpenCode:

```bash
python ~/.config/opencode/skill/chip-netlist/scripts/parse_tel_netlist.py --version
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
Project: C:\path\to\board.epro2

Extract AI-ready connectivity from the .epro2 project. If a data sheet is also provided, infer the chip configuration pin group by pin group. In each reply, focus on exactly one small group, self-check the judgment before answering, show project evidence, data sheet evidence, functional/electrical effect, inferred result, and questionable points only when present. Do not stop at connectivity; when a resistor, capacitor, divider, shunt, strap, or pullup/pulldown sets a parameter, calculate the resulting current, voltage threshold, timing, frequency, logic state, or mode when possible. Wait for my Y/N confirmation before continuing.
```

If the agent supports implicit skills, providing an EasyEDA Pro `.epro2` project should be enough to trigger this skill. A PDF data sheet is optional for connectivity extraction and required for data-sheet-based chip configuration judgment.

## Tool-Specific Guides

- [Codex installation](docs/codex.md)
- [Claude Code installation](docs/claude-code.md)
- [OpenCode installation](docs/opencode.md)
- [Detailed usage](docs/usage.md)

## References

- OpenAI skills catalog: https://github.com/openai/skills
- Claude Code skills documentation: https://docs.claude.com/en/docs/claude-code/skills
- OpenCode skills documentation: https://opencode.ubitools.com/skills/

