# Usage

`chip-netlist` runs a strict EasyEDA Pro schematic/netlist review pipeline. It supports `.epro2` and `.epro` project files.

## Strict Pipeline

From the directory containing the project file:

```bash
python "<skill-dir>/scripts/run_pipeline.py" "board.epro2" --workdir .chip-netlist
```

The workbench contains:

```text
.chip-netlist/
|-- chip_netlist.json
|-- component_index.json
|-- enriched.json
|-- evidence_ledger.json
|-- claims_draft.json
|-- verified_claims.json
|-- findings.json
|-- report.md
|-- limitations.json
|-- datasheets/
|-- datasheet_facts/
`-- context_packets/
```

`report.md` is triage. Chip-level conclusions are only final when they appear in `verified_claims.json` with `strict_status: accepted`.

## Focused Context

For a specific ref or net:

```bash
python "<skill-dir>/scripts/parse_project.py" "board.epro2" --context U5 --workdir .chip-netlist
```

Then use `.chip-netlist/context_packets/U5.json` plus matching data-sheet facts.

## Claim Validation

Draft claims in JSON:

```json
{
  "schema": "chip-netlist-claims-v1",
  "mode": "strict",
  "claims": [
    {
      "id": "C1",
      "claim_type": "recommended_wiring",
      "targets": ["U5", "U5.8"],
      "text": "Evidence-backed conclusion.",
      "netlist_evidence": [{"path": ".chip-netlist/chip_netlist.json", "target": "U5.8"}],
      "datasheet_evidence": [{"ref": "U5", "path": ".chip-netlist/datasheet_facts/<part>.json"}]
    }
  ]
}
```

Validate:

```bash
python "<skill-dir>/scripts/strict_claims.py" --workdir .chip-netlist --claims claims.json --output .chip-netlist/verified_claims.json
```

Do not present rejected claims as conclusions.
