# Detailed Usage

## What This Skill Does

Use `chip-netlist` when you have:

- an EasyEDA Pro `.epro2` project,
- optionally, a searchable chip data sheet in PDF form,
- a need to extract AI-readable schematic/PCB connectivity or infer chip settings from actual project connections.

This skill is for pin-level chip-configuration reverse engineering and schematic review. The parser reads the `.epro2` project directly and emits structured JSON containing component identities, real part numbers, values, nets, pin connectivity, peer pins, no-net pins, and review warnings. If a data sheet is also available, the agent can compare project evidence against the documented pin functions and typical circuits.

It is useful for:

- converting an `.epro2` project into an AI-friendly enhanced netlist,
- reverse-engineering hardware-set chip options, such as cell count, address selection, chemistry selection, mode pins, switching frequency, current limits, and enable/disable pins,
- checking whether pullups, pulldowns, jumpers, no-connect pins, tied-high pins, and tied-low pins match the data sheet,
- reviewing I2C/SMBus, alert, interrupt, NTC, sense, compensation, feedback, divider, gate-drive, bootstrap, and power-path pin groups,
- finding questionable schematic choices before PCB production or during board bring-up,
- explaining why a board is configured for a certain operating mode instead of just listing nets.

The skill can help flag issues such as:

- a configuration pin tied to the wrong logic level,
- a mode-select resistor value that implies an unexpected mode,
- a missing or unusual pullup/pulldown,
- a functional pin left floating when the data sheet expects a defined state,
- a pin grounded or tied to a rail when the typical circuit recommends a resistor/capacitor network,
- resistor dividers or sense resistors that imply suspicious voltage, current, temperature, or threshold settings,
- analog ground, signal ground, and power ground connections that deserve review,
- compensation or timing components that are far from data sheet examples,
- unused functions that are not disabled in the way the data sheet recommends.

The parser is intentionally narrow. It supports EasyEDA Pro `.epro2` projects containing `.epru` records such as `COMPONENT`, `ATTR`, `NET`, and `PAD_NET`. It is an analysis aid for engineering review, not a replacement for ERC/DRC, signal-integrity/power-integrity analysis, layout inspection, or final hardware sign-off.

## Recommended Prompt

Project-only extraction:

```text
Use $chip-netlist to parse this .epro2 project and generate AI-ready JSON evidence for all components, nets, pin connections, no-net pins, and review warnings.

Project: /path/to/board.epro2
```

Chip-configuration analysis with a data sheet:

```text
Use $chip-netlist to analyze:
Data sheet: /path/to/chip.pdf
Project: /path/to/board.epro2

Start by parsing the .epro2 project into AI-ready JSON. Then identify the target chip from the data sheet and infer the configuration one functional pin group at a time. For each group, show .epro2 project evidence, data sheet evidence, inferred result, and questionable points only when present. Wait for my Y/N confirmation before moving to the next group.
```

## Expected Workflow

1. Run `parse_tel_netlist.py` against the `.epro2` project.
2. Use the JSON output as the source of truth for `Ref.Pin -> net -> peer pins` and component identity.
3. If a PDF is provided, read enough of it to identify the chip, package, pin table, configuration tables, and typical circuits.
4. Pick a functional pin group, such as cell-count pins, chemistry pins, I2C pins, NTC pins, current-sense pins, gate-drive pins, or power-path pins.
5. Re-read the relevant data sheet section.
6. Infer the configured function or parameter.
7. Self-check the reasoning.
8. Ask the user to confirm with `Y/N`.

## Parser Usage

AI-readable JSON report:

```bash
python chip-netlist/scripts/parse_tel_netlist.py board.epro2
```

Focused report for one reference designator:

```bash
python chip-netlist/scripts/parse_tel_netlist.py board.epro2 --ref U1
```

The script name is kept for compatibility, but it is now `.epro2`-only. Output is always JSON.

The parser reports:

- project metadata from `project2.json`,
- component metadata from `COMPONENT` and `ATTR`,
- real part numbers, values, supplier parts, manufacturer names, footprints, and source IDs when present,
- all nets from `NET` and `PAD_NET`,
- `Ref.Pin -> net -> peer pins` mappings,
- focused `ref_report` data for a requested designator,
- no-net pins, single-point nets, low-connection nets, and components without clear canonical names.

## Output Style

Each analysis group should include:

- `.epro2 project evidence`,
- `data sheet evidence` when a PDF was provided,
- `inferred result`,
- `abnormal/questionable points` only if something is suspicious,
- a `Y/N` confirmation question when the user requested per-group confirmation.

The agent should not dump the entire chip analysis at once when per-group confirmation was requested.
