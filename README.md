# chip-netlist

`chip-netlist` is an Agent Skill for reverse-engineering chip configuration from a searchable PDF data sheet and a `.tel` netlist.

## 简介 / Introduction

`chip-netlist` 是一个面向电子电路分析的 Agent Skill。它的核心用途不是简单地把网表打印出来，而是让 Codex、Claude Code、OpenCode 这类 AI 编程/分析助手按照工程师审图的方式，把芯片数据手册和实际原理图网表放在一起交叉核对，逐个引脚、逐个功能组反推出芯片在这张板子上的真实配置。

`chip-netlist` is an Agent Skill for electronic-circuit analysis. It is not just a netlist printer. It helps AI coding and analysis agents such as Codex, Claude Code, and OpenCode review a design like a hardware engineer: compare the chip data sheet with the actual schematic netlist, inspect pins and functional pin groups one by one, and reverse-engineer how the chip is really configured on the board.

在实际硬件设计中，很多芯片的工作模式并不是通过软件设置的，而是由引脚连接决定的，例如电池节数选择、充电化学体系选择、I2C/SMBus 上拉、地址配置、开关频率电阻、NTC 温度检测、MPPT/电源路径、限流采样、电流检测、栅极驱动、补偿网络等。`chip-netlist` 会先读取数据手册中的引脚说明、配置表、典型应用电路和推荐参数，再解析 `.tel` 网表中的实际连接关系，然后根据“引脚 -> 网络 -> 外围器件 -> 数据手册规则”的证据链，推断这颗芯片被设计成了什么模式、使用了哪些参数、哪些功能被启用或禁用。

In real hardware designs, many chip operating modes are not configured by software. They are set by pin connections and external components, such as battery cell-count selection, charger chemistry selection, I2C/SMBus pullups, address pins, switching-frequency resistors, NTC temperature sensing, MPPT or power-path behavior, current-limit sampling, current sensing, gate driving, and compensation networks. `chip-netlist` reads the pin descriptions, configuration tables, typical application circuits, and recommended values in the data sheet, then parses the actual connections in the `.tel` netlist. From the evidence chain of `pin -> net -> external component -> data sheet rule`, it infers the selected mode, configured parameters, and enabled or disabled functions.

它也可以用于辅助排查 PCB 原理图设计中的错误和不合理之处。比如：配置脚上下拉方向是否接反、应悬空的脚是否误接、关键功能脚是否缺少上拉/下拉、补偿电容电阻是否与数据手册推荐值明显不符、I2C 上拉电阻是否缺失、模拟地和功率地连接是否可疑、检测电阻/分压电阻取值是否导致阈值异常、未使用功能是否按手册要求处理、引脚连接是否与目标电池节数或目标工作模式不一致等。它不会替代 ERC/DRC，也不会替代工程师最终判断，但可以作为原理图审查、PCB 设计复核、芯片外围电路检查和硬件 bring-up 前风险排查的辅助工具。

It can also help find schematic and PCB-design mistakes or questionable choices. Examples include configuration pins pulled the wrong way, pins that should be floating but are connected, missing pullups or pulldowns on key function pins, compensation capacitors or resistors that differ sharply from the data sheet recommendation, missing I2C pullups, suspicious analog-ground and power-ground connections, sense or divider resistor values that imply abnormal thresholds, unused functions not handled as recommended, or pin connections that conflict with the intended battery cell count or operating mode. It does not replace ERC/DRC or final engineering judgment, but it is useful for schematic review, PCB design review, peripheral-circuit checking, and pre-bring-up risk screening.

The skill is designed for circuit-review workflows where an agent should:

- read the chip data sheet,
- parse the `.tel` netlist,
- inspect one pin or one functional pin group at a time,
- infer the configured function or parameter,
- compare the actual schematic connection against the data sheet recommendation,
- call out questionable schematic or PCB-design choices only when there is evidence,
- stop for `Y/N` confirmation before continuing.

Typical review targets include configuration pins, mode-select pins, pullups and pulldowns, sense networks, divider networks, compensation networks, I2C/SMBus pins, power-path pins, thermal/NTC pins, and pins that are tied high, tied low, floating, or connected differently from the data sheet's typical application.

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
$env:TARGET="codex"; irm https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/v0.1.2/install.ps1 | iex
```

Install for Codex, Claude Code, and OpenCode:

```powershell
$env:TARGET="all"; irm https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/v0.1.2/install.ps1 | iex
```

### macOS / Linux / Git Bash

Install for Codex:

```bash
curl -fsSL https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/v0.1.2/install.sh | bash -s -- --target codex
```

Install for Codex, Claude Code, and OpenCode:

```bash
curl -fsSL https://raw.githubusercontent.com/yangzhaoxu411/chip-netlist-skill/v0.1.2/install.sh | bash -s -- --target all
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

