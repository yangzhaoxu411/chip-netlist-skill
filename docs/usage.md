# Detailed Usage

## What This Skill Does

Use `chip-netlist` when you have:

- a searchable chip data sheet in PDF form,
- a `.tel` netlist,
- a need to infer chip settings from actual schematic/netlist connections.

This skill is for pin-level chip-configuration reverse engineering and schematic review. It helps an agent compare what the data sheet says a pin or peripheral circuit should do against what the board netlist actually connects. The goal is to build an evidence chain from data sheet rule to netlist connection to inferred design intent.

It is useful for:

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

The skill is intentionally narrow. It does not try to support every EDA netlist format. It focuses on `.tel` files with `$PACKAGES` and `$NETS` sections. It is an analysis aid for engineering review, not a replacement for ERC/DRC, signal-integrity/power-integrity analysis, layout inspection, or final hardware sign-off.

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
