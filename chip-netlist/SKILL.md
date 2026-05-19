---
name: chip-netlist
description: Use when a user uploads, attaches, links, or provides both a chip PDF data sheet and a .tel netlist, even without naming this skill, especially for pin-level chip configuration, circuit reverse engineering, abnormal connection inspection, or per-group confirmation.
---

# Chip Netlist

## Overview

Use this skill for disciplined electronic-circuit reverse engineering from a searchable PDF data sheet plus a `.tel` netlist. The core rule is evidence first: parse the netlist, read the relevant data sheet section, infer one functional pin group, self-check, then stop for user confirmation.

Answer in the user's language.

If the user provides both a PDF data sheet and a `.tel` netlist, treat that file pair itself as a strong trigger for this skill even when the user only says "check these files", "analyze this chip", or similar wording.

## Required Loop

1. Read enough of the PDF data sheet to identify the chip model, package, pinout, pin functions, configuration tables, and typical application circuits.
2. Parse the `.tel` netlist with `scripts/parse_tel_netlist.py` before making pin-level claims.
3. Choose one pin or one same-function group, such as cell-count pins, chemistry pins, I2C pins, thermistor pins, current-sense pins, gate-drive pins, or power-path pins.
4. Re-read the data sheet section for that group and map the netlist states to the documented configuration rules.
5. Self-review before answering:
   - Did the parser evidence match the raw netlist?
   - Did the data sheet table use the correct pin order?
   - Is the conclusion directly supported, or is it only a hypothesis?
   - Is there any abnormal, risky, missing, or non-typical connection worth calling out?
6. Present only the current group, then ask for `Y/N` confirmation and stop.
7. Continue to the next group only after `Y`. If the user replies `N`, correct the current group before moving on.

Do not analyze the whole chip in one uninterrupted answer when the user requested per-pin or per-group confirmation.

## Netlist Parsing

Run the parser from this skill directory:

```bash
python scripts/parse_tel_netlist.py path/to/file.tel --ref U1
```

Use JSON when you need exact machine-readable evidence:

```bash
python scripts/parse_tel_netlist.py path/to/file.tel --ref U1 --json
```

The parser extracts:

- `$PACKAGES`: footprint, value, and reference designators.
- `$NETS`: net names and connected `Ref.Pin` entries.
- Reverse mappings: `Ref.Pin -> net -> peer pins`.
- Missing observed pins when the package name exposes a count such as `QFN-38`.
- Single-point nets and low-connection nets for review.

Parser warnings are clues, not final findings. Confirm each warning against the data sheet before telling the user it is unreasonable.

## Answer Format

For each group, use this structure, translated into the user's language:

```markdown
Continue group N: **<functional group name>**

**.tel netlist evidence**
<Pin -> net -> peer connections. Include no-connect evidence when relevant.>

**Data sheet evidence**
<Relevant pin function, table, threshold, formula, or typical connection.>

**Inferred result**
<The actual configured function/parameter. State confidence when needed.>

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

When the same netlist evidence supports multiple conclusions, state the primary conclusion first and defer secondary conclusions to the relevant later group.

## Anomaly Rules

Call out issues only when supported by both netlist evidence and the data sheet. Examples:

- A strap pin is floating when the data sheet says not to float it.
- A required bypass capacitor is missing, too far away by schematic intent, or oddly valued.
- Sense pins are reversed, shorted incorrectly, or missing Kelvin/filter components.
- Pull-ups are missing for open-drain or I2C pins.
- A configuration combination is invalid or inconsistent with the surrounding circuit.
- A compensation, timing, or set resistor differs significantly from the data sheet recommendation.

Use restrained language such as "worth noting", "may need confirmation", or "if this is a new design, review this". Do not overstate a finding without layout, BOM tolerance, or measurement evidence.

## PDF Handling

If the PDF text is extractable, use local PDF text extraction and search for pin names, tables, formulas, and typical applications. If the PDF is scanned or extraction fails, pause and ask for OCR or a searchable data sheet before doing detailed pin inference.
