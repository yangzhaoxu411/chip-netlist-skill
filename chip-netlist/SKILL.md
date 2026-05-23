---
name: chip-netlist
description: "Use when a user provides an EasyEDA Pro .epro2/.epro project or chip-netlist JSON for strict datasheet-backed defect review, chip analysis, pin-connection validation, parameter checking, or any schematic conclusion that must not be guessed."
---

# Chip Netlist - Strict Accuracy Mode

Data must come from chip datasheets and parsed project evidence. Do not invent pin functions, thresholds, formulas, configuration meanings, ratings, or recommended wiring.

## Non-Negotiable Rule

For any chip, transistor, diode, fuse, inductor, connector, or protection-device conclusion:

1. Confirm `.chip-netlist/read_integrity.json` and `.chip-netlist/integrity_audit.json` both have `status: passed`.
2. Cite project evidence from `.chip-netlist/chip_netlist.json` or a focused context packet.
3. Cite datasheet evidence from `.chip-netlist/datasheet_facts/` or extracted datasheet text.
4. Validate the conclusion with `strict_claims.py`.
5. Present only accepted claims from `.chip-netlist/verified_claims.json`.

If datasheet evidence is absent, the answer is `unknown`. Do not fill the gap with engineering memory or "common practice".

Do not analyze from corrupted or partial reads. If either integrity file is missing or failed, stop and report `read_integrity_failed` with the failed checks.

## Default Command

Resolve `scripts/` relative to this skill directory. Run from the directory containing the user's `.epro2` or `.epro` file:

```bash
python "<skill-dir>/scripts/run_pipeline.py" "<project.epro2>" --workdir .chip-netlist
```

The pipeline creates:

```text
.chip-netlist/
  chip_netlist.json
  read_integrity.json
  integrity_audit.json
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
2. Writes `read_integrity.json` and fails closed if records, components, nets, or pin connections are missing.
3. Cross-checks generated `chip_netlist.json` against `component_index.json` in `integrity_audit.json`.
4. Runs basic deterministic schematic rules.
5. Downloads datasheets for active and high-priority components.
6. Converts datasheet PDFs to text when `pdftotext` is available.
7. Extracts datasheet facts: pin tables, formulas, ratings, recommended conditions.
8. Builds `enriched.json`.
9. Runs datasheet-backed deterministic rules.
10. Builds `evidence_ledger.json`.
11. Writes an empty `claims_draft.json`.
12. Validates the empty draft into `verified_claims.json`.
13. Generates `report.md` and `limitations.json`.

The empty draft is intentional: no LLM conclusion is trusted until it is written as a claim and validated.

## Read Integrity Gate

Before reading any schematic conclusion, open:

- `.chip-netlist/read_integrity.json`
- `.chip-netlist/integrity_audit.json`

Both must say `status: passed`. Check the metrics: `record_count`, `component_count`, `net_count`, `connected_pin_count`, and matching component-index counts. If either file is absent, unreadable, or failed, do not continue to rule findings, datasheets, or claims. Report `read_integrity_failed` and list `failed_required_checks`.

Never infer around missing project evidence. A partial netlist is not weak evidence; it is no evidence.

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
2. Read `.chip-netlist/read_integrity.json` and `.chip-netlist/integrity_audit.json`; if either failed, stop with `read_integrity_failed`.
3. Summarize `.chip-netlist/report.md`.
4. Summarize `.chip-netlist/limitations.json`.
5. Say that chip-level conclusions remain `unknown` unless accepted in `.chip-netlist/verified_claims.json`.
6. Ask which component or net should be analyzed with strict claims.

Do not add unvalidated chip conclusions during the general review.

## Component or Net Deep Review

When the user requests a specific component or net:

1. Ensure the default pipeline has run.
2. Re-check `.chip-netlist/read_integrity.json` and `.chip-netlist/integrity_audit.json`.
3. Build a focused context packet:

```bash
python "<skill-dir>/scripts/parse_project.py" "<project.epro2>" --context "<ref-or-net>" --workdir .chip-netlist
```

4. Read the context packet under `.chip-netlist/context_packets/`.
5. Read the component entry in `.chip-netlist/evidence_ledger.json`.
6. Read the matching file in `.chip-netlist/datasheet_facts/`.
7. Draft claims using the claim schema.
8. Run `strict_claims.py`.
9. Present only accepted claims.

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
