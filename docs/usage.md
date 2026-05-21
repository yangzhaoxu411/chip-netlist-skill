# Detailed Usage

## What This Skill Does

Use `chip-netlist` when you have:

- an EasyEDA Pro `.epro2` project,
- optionally, a searchable chip data sheet in PDF form,
- a need to extract AI-readable schematic/PCB connectivity or infer chip settings from actual project connections.

This skill is for pin-level chip-configuration reverse engineering and schematic review. The parser reads the `.epro2` project directly and emits structured JSON containing component identities, real part numbers, values, nets, pin connectivity, peer pins, no-net pins, and review warnings. If a data sheet is also available, the agent can compare project evidence against the documented pin functions and typical circuits.

The generated JSON is intended to be re-uploaded and recognized later. If a file contains `schema: "chip-netlist-ai-json-v1"` or `generated_by.tool: "chip-netlist"`, the agent should treat it as already-parsed project evidence and can analyze circuit sections from it without needing the original `.epro2`.

For large projects, use the persistent workbench workflow. The full project is stored on disk, while the agent loads only a small context packet for the current circuit area. This reduces context loss and avoids mixing unrelated data sheets.

It is useful for:

- converting an `.epro2` project into an AI-friendly enhanced netlist,
- analyzing a previously generated chip-netlist JSON file,
- finding data sheets online for the relevant components when the user did not provide PDFs,
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

## Generated JSON Recognition

The parser output starts with machine-readable identity fields:

```json
{
  "schema": "chip-netlist-ai-json-v1",
  "generated_by": {
    "tool": "chip-netlist",
    "version": "0.1.13"
  }
}
```

When this JSON is provided to an AI agent, it should use the JSON directly:

- `components` for reference designators, real part numbers, values, supplier parts, and footprints,
- `nets` for net-to-pin connectivity,
- `pins` for `Ref.Pin -> net -> peer pins`,
- `warnings` for no-net pins and low-connection nets,
- `datasheet_lookup` for suggested data-sheet search targets and search rules.

A focused context packet starts with:

```json
{
  "schema": "chip-netlist-context-packet-v1",
  "selection": {
    "query": "U5"
  }
}
```

When this JSON is provided, the agent should treat it as the active circuit slice and avoid loading the full project unless the packet is missing required evidence.

## Recommended Prompt

Project-only extraction:

```text
Use $chip-netlist to parse this .epro2 project and generate AI-ready JSON evidence for all components, nets, pin connections, no-net pins, and review warnings.

Project: /path/to/board.epro2
```

Generated JSON analysis:

```text
Use $chip-netlist to analyze this chip-netlist generated JSON.

Analyze the U6 input protection / hot-swap section. Use the JSON to identify related components and nets. If data sheets are not included, search the web for the relevant component data sheets first, then judge whether the circuit is reasonable.
```

Chip-configuration analysis with a data sheet:

```text
Use $chip-netlist to analyze:
Data sheet: /path/to/chip.pdf
Project: /path/to/board.epro2

Start by parsing the .epro2 project into AI-ready JSON. Then identify the target chip from the data sheet and infer the configuration one small functional pin group at a time. Before assigning any pin function, map parser pins such as U1.1 to the exact physical package pinout and data-sheet function; do not treat parser pin numbers as schematic-symbol order. In each reply, focus on exactly one current group, self-check your judgment before answering, show pin mapping evidence, .epro2 project evidence, data sheet evidence, the functional/electrical effect of the connection, inferred result, and questionable points only when present. When a resistor, capacitor, divider, shunt, strap, or pullup/pulldown sets a parameter, calculate the resulting current, voltage threshold, timing, frequency, logic state, or mode when the data sheet provides enough information. When naming MOSFET or other peer-component pin functions, deduce them from controlling-IC data-sheet pin functions plus parser net evidence; do not assume pin functions from package numbering habits. Wait for my Y/N confirmation before moving to the next group.
```

## Expected Workflow

1. Run `parse_tel_netlist.py` against the `.epro2` project.
2. If the input is already chip-netlist generated JSON, skip parsing and use it directly.
3. For long sessions or large projects, create `.chip-netlist` with `--workdir`.
4. If the user names a circuit area, generate or load `context_packets/<area>.json`.
5. Use the context packet as the source of truth for the current `Ref.Pin -> net -> peer pins` evidence.
6. If a PDF is provided, read only the relevant pin table, configuration table, formulas, limits, and typical circuits.
7. If no PDF is provided, use `datasheet_lookup.targets` in the context packet to search for data sheets online.
8. Store verified source URLs in `datasheet_sources.json` and extracted facts in `datasheet_facts/`.
9. Build a parser-pin to data-sheet-function mapping table from the exact package pinout before assigning functions. Treat `Ref.N` as a project pad/physical package pin identifier, not schematic-symbol order.
10. Pick exactly one smallest useful functional pin group for the current reply, such as one supply path, one sense pair, one threshold divider, one timer pin, one gate-drive path, or one strap/config table.
11. Infer the configured function or parameter. Do not stop at connectivity; explain what the connection makes the circuit do.
12. When a value-setting resistor, capacitor, divider, shunt, strap, or pullup/pulldown is present, calculate the resulting current limit, threshold, timing, switching frequency, logic state, or mode if the data sheet gives enough information.
13. When naming peer component pin functions, deduce those functions from the controlling IC data sheet plus parser net evidence. Do not assume MOSFET source/drain/gate or connector/module pin roles from numbering conventions alone.
14. Self-check that the judgment is limited to this one group, includes the functional/electrical effect, and is directly supported by project evidence plus data sheet/source evidence.
15. Update `analysis_state.json` and append confirmed findings to `analysis_report.md` after user confirmation.
16. Tell the user that the current group/part has been completely analyzed, then ask the user to confirm with `Y/N` and stop. Move to the next group only after confirmation.

## Parser Usage

AI-readable JSON report:

```bash
python chip-netlist/scripts/parse_tel_netlist.py board.epro2
```

Focused report for one reference designator:

```bash
python chip-netlist/scripts/parse_tel_netlist.py board.epro2 --ref U1
```

Create or update a persistent workbench:

```bash
python chip-netlist/scripts/parse_tel_netlist.py board.epro2 --workdir .chip-netlist
```

Generate a small context packet for one circuit area and save it into the workbench:

```bash
python chip-netlist/scripts/parse_tel_netlist.py board.epro2 --context U5 --workdir .chip-netlist
```

Generate the same context packet to stdout:

```bash
python chip-netlist/scripts/parse_tel_netlist.py board.epro2 --context U5
```

The script name is kept for compatibility, but it is now `.epro2`-only. Output is always JSON.

The parser reports:

- `schema` and `generated_by`, so AI agents can recognize generated files,
- project metadata from `project2.json`,
- component metadata from `COMPONENT` and `ATTR`,
- real part numbers, values, supplier parts, manufacturer names, footprints, and source IDs when present,
- all nets from `NET` and `PAD_NET`,
- `Ref.Pin -> net -> peer pins` mappings,
- focused `ref_report` data for a requested designator,
- `datasheet_lookup` candidates and source-priority rules,
- no-net pins, single-point nets, low-connection nets, and components without clear canonical names.

## Persistent Workbench Files

The `--workdir` option creates these files:

- `chip_netlist.json`: complete extracted project evidence.
- `component_index.json`: compact `Ref -> part/value/footprint/search terms` index.
- `context_packets/<area>.json`: small context packets for the requested circuit areas.
- `datasheet_sources.json`: verified data-sheet URLs and local cached PDF paths.
- `datasheet_facts/`: extracted facts such as pinout tables, formulas, thresholds, absolute maximum limits, and recommended application values.
- `datasheets/`: downloaded or user-provided PDFs.
- `analysis_state.json`: confirmed, pending, and rejected groups plus current context.
- `analysis_report.md`: human-readable review notes.

State and report files are created only if missing, so user notes and confirmed analysis are not overwritten by rerunning the parser.

## Automatic Data Sheet Lookup

When the user asks to analyze a circuit section and no data sheet is supplied, the agent should search the web for relevant component data sheets. Use the context packet to decide what matters:

- Prefer active and critical parts: ICs, modules, MOSFETs, BJTs, diodes, TVS/protection parts, fuses, inductors, connectors, sensors, regulators, and hot-swap controllers.
- Skip ordinary resistors and capacitors by default, unless they are shunts, NTC/PTC parts, feedback dividers, set resistors, timing parts, or compensation components.
- Prefer `datasheet_lookup.targets` from the context packet. If there is no context packet, use full-netlist `datasheet_lookup.candidates`.
- Search `context_role: "primary"` targets first. Search `neighbor` targets only when their data sheet affects the current conclusion.
- Prefer `manufacturer_part`, then `canonical_name`, then `supplier_part` when building search queries.
- Prefer verified local cache first, then 半导小芯 / Semiee (China), then 立创商城 / LCSC China, then official manufacturer product pages or PDF data sheets, then other authorized distributors such as DigiKey, Mouser, or Arrow, then data-sheet mirrors only as a fallback.
- If the official manufacturer site has network problems such as timeout, access denial, region blocking, TLS/download failure, or repeated slow responses, stop retrying it and switch to the China-first sources above.
- Use `supplier_part` LCSC `C` codes when searching 立创商城.
- Prefer `Datasheet` URLs extracted from the `.epro2` project before doing a new search.
- If WebFetch or browser access fails, try shell-based retrieval with `curl`, `wget`, or PowerShell `Invoke-WebRequest`, then cache the PDF in `.chip-netlist/datasheets/`.
- For LCSC pages, download the HTML page when possible and extract PDF links such as `https://atta.szlcsc.com...pdf`; if the file lands in `/tmp`, copy it into the workspace or another Windows-readable path before using file-reading tools.
- Verify that the data sheet matches the exact part number, family, package, and function before using it.
- Record verified sources and local cache paths in `datasheet_sources.json`.
- Extract only the facts needed for the current analysis into `datasheet_facts/<part>.json`.
- Include source URLs for every data-sheet-based claim.
- If no reliable data sheet is found, say so and limit the conclusion to project connectivity evidence.

Do not load a large batch of unrelated PDFs. Load or search only the data sheets needed for the current context packet.

## Pin Numbering Convention

Parser pins such as `U1.1` come from `.epro2` `PAD_NET` project pad identifiers. They must be treated as physical package pins or footprint pads, not schematic-symbol logical order. Before any functional conclusion, map parser pins to the exact data-sheet package pinout:

- build `Parser Pin -> Physical Package Pin/Pad -> Data-sheet Function -> Net/Connection Status`,
- use the package-specific pinout, not a generic family table or a symbol drawing,
- if the data sheet says `Pin 38 = CELLS0`, only `U1.38` can prove the CELLS0 connection,
- if the expected physical pin is absent, no-net, or `connected: false`, report it as not observed/floating unless raw project records prove otherwise,
- do not infer a missing pin's connection from neighboring pins, same-function names, or schematic symbol order.

If PDF text extraction is needed, use `pdftotext -layout` when available and search the text for exact part numbers, pin names, formulas, and threshold terms. If the PDF is scanned or extraction is incomplete, ask the user for OCR, screenshots, or manual confirmation. Do not fall back to generic package pin assumptions.

## Component Pin Function Deduction

Do not infer a peer component's pin function from pin numbering habits. MOSFET source/drain/gate, connector pin roles, module pins, and multi-pin transistor pins must be mapped from evidence:

- identify the controlling IC pin function from its data sheet,
- use `Ref.Pin -> net -> peer pins` to see which external pins share that net,
- assign the external pin function from that circuit relationship,
- then verify against the external component's own data sheet if available.

For example, if a hot-swap controller data sheet says `OUT` connects to the MOSFET source and parser evidence shows `U6.OUT` shares a net with `Q3.1`, `Q3.2`, and `Q3.3`, treat those Q3 pins as source pins in this circuit unless the MOSFET data sheet or project evidence proves otherwise.

## Output Style

Each analysis group should include:

- one explicit current focus group,
- pin mapping evidence for the current group, and a full mapping before the first functional conclusion when pin numbering could be ambiguous,
- `.epro2 project evidence`,
- `data sheet evidence` when a PDF was provided or found online,
- `functional/electrical effect`, including formulas and numeric results when possible,
- `inferred result`,
- `abnormal/questionable points` only if something is suspicious,
- one concise self-review result,
- one completion status sentence saying the current group/part has been completely analyzed,
- a `Y/N` confirmation question when the user requested per-group confirmation.

The agent should not dump the entire chip analysis at once when per-group confirmation was requested. Each reply should contain exactly one group. Do not include multiple `Continue group` sections, multiple independent conclusions, or a table of pending group results in the same reply.

For dense power ICs, the default grouping should be finer than a whole functional block. For example, a hot-swap controller should normally be split into:

- `VIN/SENSE/OUT/GATE + pass FET + sense resistor`,
- `UVLO divider`,
- `OVLO divider`,
- `TIMER capacitor`,
- `PWR or power-limit resistor`,
- `PGD and other logic/status pins`.

Analyze one of these groups, ask for `Y/N`, then stop. Continue only after confirmation.
