# Detailed Usage

## What This Skill Does

Use `chip-netlist` when you have:

- a searchable chip data sheet in PDF form,
- a `.tel` netlist,
- a need to infer chip settings from actual schematic/netlist connections.

The skill is intentionally narrow. It does not try to support every EDA netlist format. It focuses on `.tel` files with `$PACKAGES` and `$NETS` sections.

## Recommended Prompt

```text
Use $chip-netlist to analyze:
Data sheet: /path/to/chip.pdf
Netlist: /path/to/board.tel

Start by identifying the chip and package from the data sheet. Then parse the .tel netlist and infer the configuration one functional pin group at a time. For each group, show .tel evidence, data sheet evidence, inferred result, and questionable points only when present. Wait for my Y/N confirmation before moving to the next group.
```

## Expected Workflow

1. Read enough of the PDF to identify the chip, package, pin table, configuration tables, and typical circuits.
2. Run `parse_tel_netlist.py` against the `.tel` file.
3. Pick a functional pin group, such as cell-count pins, chemistry pins, I2C pins, NTC pins, current-sense pins, gate-drive pins, or power-path pins.
4. Re-read the relevant data sheet section.
5. Infer the configured function or parameter.
6. Self-check the reasoning.
7. Ask the user to confirm with `Y/N`.

## Parser Usage

Human-readable report:

```bash
python chip-netlist/scripts/parse_tel_netlist.py board.tel --ref U1
```

JSON report:

```bash
python chip-netlist/scripts/parse_tel_netlist.py board.tel --ref U1 --json
```

The parser reports:

- package metadata from `$PACKAGES`,
- all nets from `$NETS`,
- `Ref.Pin -> net -> peer pins` mappings,
- inferred package pin counts when the footprint exposes a pin count,
- no-net pins when a package pin is not present in `$NETS`,
- single-point and low-connection nets for review.

## Output Style

Each group should include:

- `.tel netlist evidence`,
- `data sheet evidence`,
- `inferred result`,
- `abnormal/questionable points` only if something is suspicious,
- a `Y/N` confirmation question.

The agent should not dump the entire chip analysis at once when per-group confirmation was requested.
