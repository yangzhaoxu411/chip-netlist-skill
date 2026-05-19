---
name: chip-netlist
description: Use when a user uploads, attaches, links, or provides an EasyEDA Pro .epro2 project, with or without a chip PDF data sheet, especially for AI-readable connectivity extraction, pin-level chip configuration, schematic review, abnormal connection inspection, or per-group confirmation.
---

# Chip Netlist

## Overview

Use this skill to extract AI-ready component and connectivity data from an EasyEDA Pro `.epro2` project. When a searchable PDF data sheet is also available, use the extracted project evidence plus the data sheet to reverse-engineer chip configuration one functional pin group at a time.

Answer in the user's language.

If the user provides an `.epro2` project file, treat that file as a strong trigger for this skill even when the user only says "check this project", "extract the connections", "analyze this chip", or similar wording. A PDF data sheet is optional for connectivity extraction and required for data-sheet-based chip-configuration conclusions.

## Required Loop

1. Parse the `.epro2` project with `scripts/parse_tel_netlist.py` before making pin-level claims.
2. Use the parser JSON as the primary project evidence: component metadata, real part numbers, values, footprints, nets, `Ref.Pin -> net -> peer pins`, no-net pins, and low-connection nets.
3. If a PDF data sheet is provided, read enough of it to identify the chip model, package, pinout, pin functions, configuration tables, and typical application circuits.
4. Choose one pin or one same-function group, such as cell-count pins, chemistry pins, I2C pins, thermistor pins, current-sense pins, gate-drive pins, or power-path pins.
5. Re-read the data sheet section for that group and map the project connection states to the documented configuration rules.
6. Self-review before answering:
   - Did the parser evidence match the project records?
   - Did the component identity come from real `.epro2` attributes such as `Manufacturer Part`, `Value`, or `partId`?
   - Did the data sheet table use the correct pin order?
   - Is the conclusion directly supported, or is it only a hypothesis?
   - Is there any abnormal, risky, missing, or non-typical connection worth calling out?
7. Present only the current group, then ask for `Y/N` confirmation and stop.
8. Continue to the next group only after `Y`. If the user replies `N`, correct the current group before moving on.

Do not analyze the whole chip in one uninterrupted answer when the user requested per-pin or per-group confirmation.

## Project Parsing

Run the parser from this skill directory:

```bash
python scripts/parse_tel_netlist.py path/to/project.epro2 --ref U1
```

The script name is kept for compatibility, but the parser is `.epro2`-only. Output is always JSON, even without `--json`.

The parser extracts:

- `COMPONENT` and `ATTR`: reference designators, real part names, manufacturer parts, supplier parts, values, footprints, and source object IDs.
- `NET`: project net names.
- `PAD_NET`: `Ref.Pin -> net` connectivity.
- Reverse mappings: `Ref.Pin -> net -> peer pins`.
- Focused `ref_report` data for one requested designator.
- No-net pins, single-point nets, low-connection nets, and components without clear canonical names.

Parser warnings are clues, not final findings. Confirm each warning against the data sheet or design intent before telling the user it is unreasonable.

## Answer Format

For each group, use this structure, translated into the user's language:

```markdown
Continue group N: **<functional group name>**

**.epro2 project evidence**
<Component identity plus Pin -> net -> peer connections. Include no-net evidence when relevant.>

**Data sheet evidence**
<Relevant pin function, table, threshold, formula, or typical connection. Omit this section if no data sheet was provided and the task is only connectivity extraction.>

**Inferred result**
<The actual configured function/parameter, or the extracted connectivity result. State confidence when needed.>

**Abnormal or questionable points**
<Only include this section when something is actually suspicious.>

Please confirm whether this group is correct: Y/N
```

If there is no abnormal point, omit the `Abnormal or questionable points` section entirely.

## Grouping Guidance

Prefer grouping pins that form one configuration decision:

- Strap/config pins: analyze all pins in the table together, preserving the data sheet's bit/order convention.
- Interfaces: group supply, pull-ups, clock/data, alert, enable, and connector pins when they only make sense together.
- Sense networks: group positive/negative sense pins and their resistor/capacitor filters.
- Power stage: group switch node, gate-drive, bootstrap, driver supply, MOSFETs, inductor, and current paths.
- Grounds and supplies: group analog ground, power ground, exposed pad, internal regulators, and bypass capacitors.

When the same project evidence supports multiple conclusions, state the primary conclusion first and defer secondary conclusions to the relevant later group.

## Anomaly Rules

Call out issues only when supported by project evidence and, when applicable, the data sheet. Examples:

- A strap pin is floating when the data sheet says not to float it.
- A required bypass capacitor is missing, too far away by schematic intent, or oddly valued.
- Sense pins are reversed, shorted incorrectly, or missing Kelvin/filter components.
- Pull-ups are missing for open-drain or I2C pins.
- A configuration combination is invalid or inconsistent with the surrounding circuit.
- A compensation, timing, or set resistor differs significantly from the data sheet recommendation.
- A component has no clear real part, value, or canonical name in the project.

Use restrained language such as "worth noting", "may need confirmation", or "if this is a new design, review this". Do not overstate a finding without layout, BOM tolerance, or measurement evidence.

## PDF Handling

If the PDF text is extractable, use local PDF text extraction and search for pin names, tables, formulas, and typical applications. If the PDF is scanned or extraction fails, pause and ask for OCR or a searchable data sheet before doing detailed pin inference.
