---
name: chip-netlist
description: "Use when a user provides an EasyEDA Pro .epro2/.epro project or chip-netlist JSON for strict datasheet-backed defect review, chip analysis, pin-connection validation, parameter checking, or any schematic conclusion that must not be guessed."
---

# Chip Netlist - Strict Accuracy Mode

Data must come from chip datasheets and parsed project evidence. Do not invent pin functions, thresholds, formulas, configuration meanings, ratings, or recommended wiring.

## Non-Negotiable Rule

For any chip, transistor, diode, fuse, inductor, connector, or protection-device conclusion:

1. Cite project evidence from `.chip-netlist/chip_netlist.json` or a focused context packet.
2. Cite datasheet evidence from `.chip-netlist/datasheet_facts/` or extracted datasheet text.
3. Validate the conclusion with `strict_claims.py`.
4. Present only accepted claims from `.chip-netlist/verified_claims.json`.

If datasheet evidence is absent, the answer is `unknown`. Do not fill the gap with engineering memory or "common practice".

## Default Command

Resolve `scripts/` relative to this skill directory. Run from the directory containing the user's `.epro2` or `.epro` file:

```bash
python "<skill-dir>/scripts/run_pipeline.py" "<project.epro2>" --workdir .chip-netlist
```

The pipeline creates:

```text
.chip-netlist/
  chip_netlist.json
  component_index.json
  enriched.json
  evidence_ledger.json
  claims_draft.json
  verified_claims.json
  findings.json
  report.md
  limitations.json
  analysis_stub.json
  datasheets/
  datasheet_facts/
  context_packets/
```

## Strict Pipeline

The default pipeline:

1. Parses the project into component, pin, and net evidence.
2. Runs basic deterministic schematic rules.
3. Downloads datasheets for active and high-priority components.
4. Converts datasheet PDFs to text when `pdftotext` is available.
5. Extracts datasheet facts: pin tables, formulas, ratings, recommended conditions.
6. Builds `enriched.json`.
7. Runs datasheet-backed deterministic rules.
8. Builds `evidence_ledger.json`.
9. Writes an empty `claims_draft.json`.
10. Validates the empty draft into `verified_claims.json`.
11. Generates `report.md` and `limitations.json`.

The empty draft is intentional: no LLM conclusion is trusted until it is written as a claim and validated.

## Evidence Ledger

Before writing any chip-level conclusion, read `.chip-netlist/evidence_ledger.json`.

For each target component, confirm:

- `has_datasheet_facts` is `true`
- `datasheet_facts_path` points to the matching part's facts file
- `pin_count` or `formula_count` is sufficient for the claim
- `datasheet_status` is not `not_found`, `not_downloaded`, or `downloaded_no_facts`

If any check fails, mark the claim `unknown` and explain which evidence is missing.

## Claim Schema

Write conclusions to a claims JSON file before presenting them:

```json
{
  "schema": "chip-netlist-claims-v1",
  "mode": "strict",
  "claims": [
    {
      "id": "C1",
      "claim_type": "pin_function",
      "text": "Evidence-backed conclusion.",
      "targets": ["U3"],
      "netlist_evidence": [
        {"path": ".chip-netlist/chip_netlist.json", "target": "U3.1"}
      ],
      "datasheet_evidence": [
        {"ref": "U3", "path": ".chip-netlist/datasheet_facts/<part>.json"}
      ]
    }
  ]
}
```

Validate claims:

```bash
python "<skill-dir>/scripts/strict_claims.py" --workdir .chip-netlist --claims claims.json --ledger-output .chip-netlist/evidence_ledger.json --output .chip-netlist/verified_claims.json
```

Do not present rejected claims. If `verified_claims.json` marks a claim as `rejected`, remove it or rewrite it with matching datasheet evidence.

## General Review

For a general chip netlist:

1. Run the default command.
2. Summarize `.chip-netlist/report.md`.
3. Summarize `.chip-netlist/limitations.json`.
4. Say that chip-level conclusions remain `unknown` unless accepted in `.chip-netlist/verified_claims.json`.
5. Ask which component or net should be analyzed with strict claims.

Do not add unvalidated chip conclusions during the general review.

## Component or Net Deep Review

When the user requests a specific component or net:

1. Ensure the default pipeline has run.
2. Build a focused context packet:

```bash
python "<skill-dir>/scripts/parse_project.py" "<project.epro2>" --context "<ref-or-net>" --workdir .chip-netlist
```

3. Read the context packet under `.chip-netlist/context_packets/`.
4. Read the component entry in `.chip-netlist/evidence_ledger.json`.
5. Read the matching file in `.chip-netlist/datasheet_facts/`.
6. Draft claims using the claim schema.
7. Run `strict_claims.py`.
8. Present only accepted claims.

## Claim Types Requiring Datasheet Evidence

These claim types always require matching datasheet evidence:

- `pin_function`
- `pin_state`
- `configuration`
- `parameter`
- `threshold`
- `formula`
- `rating`
- `recommended_wiring`

Claims about actual schematic connectivity also require `netlist_evidence`.

## Deterministic Rule Output

`findings.json` and `report.md` are useful triage, not final chip analysis. Treat rule findings as candidates unless their evidence is complete.

If a deterministic rule depends on datasheet facts, `check_rules.py --datasheet` must run after `build_enriched.py`. If `enriched.json` is missing, stop and fix the pipeline instead of reporting datasheet-backed results.

## Response Rules

Answer in the user's language.

Use only these statuses:

- `accepted`: claim passed strict validation.
- `rejected`: claim failed validation; do not present as a conclusion.
- `unknown`: required datasheet or netlist evidence is missing.
- `conflict`: datasheet evidence and project evidence disagree.

Avoid uncertain wording for chip facts. If you cannot cite datasheet evidence, write `unknown`.

## Script Reference

```bash
python "<skill-dir>/scripts/run_pipeline.py" "<project.epro2>" --workdir .chip-netlist
python "<skill-dir>/scripts/strict_claims.py" --workdir .chip-netlist --claims claims.json --output .chip-netlist/verified_claims.json
python "<skill-dir>/scripts/generate_report.py" .chip-netlist/findings.json --project "<project name>" --output .chip-netlist/report.md
```

`strict_claims.py` is the gate. No accepted claim, no chip conclusion.
