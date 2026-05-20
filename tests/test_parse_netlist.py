import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "chip-netlist" / "scripts" / "parse_tel_netlist.py"
SKILL_DIR = SCRIPT.parents[1]
SPEC = importlib.util.spec_from_file_location("parse_tel_netlist", SCRIPT)
parser = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(parser)


def record(meta, data):
    return json.dumps(meta, separators=(",", ":")) + "||" + json.dumps(data, separators=(",", ":"))


def make_sample_epro2(path: Path):
    records = [
        record({"type": "DOCHEAD", "ticket": 1}, {"docType": "PROJECT"}),
        record({"type": "COMPONENT", "ticket": 2, "id": "sch_u1"}, {"partId": "LM5069MM-1/NOPB.1"}),
        record({"type": "ATTR", "ticket": 3, "id": "a1"}, {"parentId": "sch_u1", "key": "Designator", "value": "U1"}),
        record({"type": "ATTR", "ticket": 4, "id": "a2"}, {"parentId": "sch_u1", "key": "Manufacturer Part", "value": "LM5069MM-1/NOPB"}),
        record({"type": "ATTR", "ticket": 5, "id": "a3"}, {"parentId": "sch_u1", "key": "Supplier Part", "value": "C486026"}),
        record({"type": "ATTR", "ticket": 6, "id": "a4"}, {"parentId": "sch_u1", "key": "Value", "value": "LM5069"}),
        record({"type": "ATTR", "ticket": 7, "id": "a5"}, {"parentId": "sch_u1", "key": "Unique ID", "value": "gge100"}),
        record({"type": "ATTR", "ticket": 8, "id": "a5b"}, {"parentId": "sch_u1", "key": "Datasheet", "value": "https://www.ti.com/lit/gpn/lm5069"}),
        record({"type": "COMPONENT", "ticket": 9, "id": "pcb_u1"}, {"partId": "LM5069MM-1/NOPB.1"}),
        record({"type": "ATTR", "ticket": 10, "id": "a6"}, {"parentId": "pcb_u1", "key": "Designator", "value": "U1"}),
        record({"type": "ATTR", "ticket": 11, "id": "a7"}, {"parentId": "pcb_u1", "key": "Footprint", "value": "TSSOP-10_L3.0-W3.0-P0.50"}),
        record({"type": "ATTR", "ticket": 12, "id": "a8"}, {"parentId": "pcb_u1", "key": "Unique ID", "value": "gge100"}),
        record({"type": "COMPONENT", "ticket": 12, "id": "pcb_r1"}, {"partId": "0402WGF1002TCE.1"}),
        record({"type": "ATTR", "ticket": 13, "id": "a9"}, {"parentId": "pcb_r1", "key": "Designator", "value": "R1"}),
        record({"type": "ATTR", "ticket": 14, "id": "a10"}, {"parentId": "pcb_r1", "key": "Value", "value": "10K"}),
        record({"type": "COMPONENT", "ticket": 15, "id": "pcb_u2"}, {"partId": "TPS7A7001DDAR.1"}),
        record({"type": "ATTR", "ticket": 16, "id": "a11"}, {"parentId": "pcb_u2", "key": "Designator", "value": "U2"}),
        record({"type": "ATTR", "ticket": 17, "id": "a12"}, {"parentId": "pcb_u2", "key": "Manufacturer Part", "value": "TPS7A7001DDAR"}),
        record({"type": "COMPONENT", "ticket": 18, "id": "pcb_r2"}, {"partId": "0402WGF2002TCE.1"}),
        record({"type": "ATTR", "ticket": 19, "id": "a13"}, {"parentId": "pcb_r2", "key": "Designator", "value": "R2"}),
        record({"type": "ATTR", "ticket": 20, "id": "a14"}, {"parentId": "pcb_r2", "key": "Value", "value": "20K"}),
        record({"type": "DOCHEAD", "ticket": 21}, {"docType": "DEVICE", "uuid": "res_dev"}),
        record({"type": "META", "ticket": 22, "id": "META"}, {
            "title": "Res_0402",
            "attributes": {
                "Designator": "R?",
                "Symbol": "res_sym",
                "Footprint": "R0402",
                "Supplier Footprint": "0402",
                "Value": "10K",
                "Name": "={Value}",
            },
        }),
        record({"type": "DOCHEAD", "ticket": 23}, {"docType": "DEVICE", "uuid": "cap_dev"}),
        record({"type": "META", "ticket": 24, "id": "META"}, {
            "title": "CAP_0402",
            "attributes": {
                "Designator": "C?",
                "Symbol": "cap_sym",
                "Footprint": "C0402",
                "Supplier Footprint": "0402",
                "Value": "100nF",
                "Name": "={Value}",
            },
        }),
        record({"type": "COMPONENT", "ticket": 25, "id": "pcb_r3"}, {"partId": "Res_0402.1"}),
        record({"type": "ATTR", "ticket": 26, "id": "a15"}, {"parentId": "pcb_r3", "key": "Designator", "value": "R3"}),
        record({"type": "ATTR", "ticket": 27, "id": "a16"}, {"parentId": "pcb_r3", "key": "Device", "value": "res_dev"}),
        record({"type": "ATTR", "ticket": 28, "id": "a17"}, {"parentId": "pcb_r3", "key": "Value", "value": None}),
        record({"type": "COMPONENT", "ticket": 29, "id": "pcb_c1"}, {"partId": "CAP_0402.1"}),
        record({"type": "ATTR", "ticket": 30, "id": "a18"}, {"parentId": "pcb_c1", "key": "Designator", "value": "C1"}),
        record({"type": "ATTR", "ticket": 31, "id": "a19"}, {"parentId": "pcb_c1", "key": "Device", "value": "cap_dev"}),
        record({"type": "ATTR", "ticket": 32, "id": "a20"}, {"parentId": "pcb_c1", "key": "Value", "value": None}),
        record({"type": "NET", "ticket": 33, "id": json.dumps(["NET", "VIN"])}, {}),
        record({"type": "NET", "ticket": 34, "id": json.dumps(["NET", "GND"])}, {}),
        record({"type": "NET", "ticket": 35, "id": json.dumps(["NET", "VOUT"])}, {}),
        record({"type": "PAD_NET", "ticket": 36, "id": json.dumps(["PAD_NET", "pcb_u1", "1", "e1"])}, {"padNet": "VIN"}),
        record({"type": "PAD_NET", "ticket": 37, "id": json.dumps(["PAD_NET", "pcb_u1", "2", "e2"])}, {"padNet": "GND"}),
        record({"type": "PAD_NET", "ticket": 38, "id": json.dumps(["PAD_NET", "pcb_u1", "3", "e3"])}, {"padNet": ""}),
        record({"type": "PAD_NET", "ticket": 39, "id": json.dumps(["PAD_NET", "pcb_r1", "1", "e4"])}, {"padNet": "VIN"}),
        record({"type": "PAD_NET", "ticket": 40, "id": json.dumps(["PAD_NET", "pcb_r1", "2", "e5"])}, {"padNet": "GND"}),
        record({"type": "PAD_NET", "ticket": 41, "id": json.dumps(["PAD_NET", "pcb_u2", "1", "e6"])}, {"padNet": "VOUT"}),
        record({"type": "PAD_NET", "ticket": 42, "id": json.dumps(["PAD_NET", "pcb_u2", "2", "e7"])}, {"padNet": "GND"}),
        record({"type": "PAD_NET", "ticket": 43, "id": json.dumps(["PAD_NET", "pcb_r2", "1", "e8"])}, {"padNet": "VOUT"}),
        record({"type": "PAD_NET", "ticket": 44, "id": json.dumps(["PAD_NET", "pcb_r2", "2", "e9"])}, {"padNet": "GND"}),
    ]
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("project2.json", json.dumps({"title": "sample"}))
        zf.writestr("sample.epru", "|\n".join(records) + "|\n")


class ParseNetlistTests(unittest.TestCase):
    def test_version_file_and_cli_report_current_version(self):
        expected_version = (SKILL_DIR / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(parser.load_version(), expected_version)

        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--version"],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.stdout.strip(), f"chip-netlist {expected_version}")

    def test_epro2_parser_extracts_ai_ready_components_and_connections(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "board.epro2"
            make_sample_epro2(project)

            result = parser.analyze(project, "U1")

        self.assertEqual(result["source_type"], "epro2")
        self.assertEqual(result["schema"], "chip-netlist-ai-json-v1")
        self.assertEqual(result["generated_by"]["tool"], "chip-netlist")
        self.assertEqual(result["generated_by"]["version"], parser.load_version())
        self.assertIn("datasheet_lookup", result)
        self.assertEqual(result["components"]["U1"]["manufacturer_part"], "LM5069MM-1/NOPB")
        self.assertEqual(result["components"]["U1"]["supplier_part"], "C486026")
        self.assertEqual(result["components"]["U1"]["datasheet"], "https://www.ti.com/lit/gpn/lm5069")
        self.assertIn("pcb_u1", result["components"]["U1"]["source_component_ids"])
        self.assertEqual(result["pins"]["U1.1"][0]["net"], "VIN")
        self.assertEqual(set(result["pins"]["U1.1"][0]["peers"]), {"R1.1"})
        self.assertEqual(result["pins"]["U1.2"][0]["net"], "GND")
        u1_pin3 = next(pin for pin in result["ref_report"]["pins"] if pin["pin"] == "U1.3")
        self.assertFalse(u1_pin3["connected"])
        self.assertIn("U1.3", result["warnings"]["no_net_pins"])

        candidates = result["datasheet_lookup"]["candidates"]
        self.assertEqual(candidates[0]["ref"], "U1")
        self.assertEqual(candidates[0]["datasheet"], "https://www.ti.com/lit/gpn/lm5069")
        self.assertIn("LM5069MM-1/NOPB datasheet", candidates[0]["query_terms"])
        self.assertIn("LM5069MM-1/NOPB 半导小芯 数据手册", candidates[0]["query_terms"])
        self.assertIn("LM5069MM-1/NOPB 立创商城 数据手册", candidates[0]["query_terms"])
        self.assertTrue(any("半导小芯" in item for item in result["datasheet_lookup"]["source_priority"]))
        self.assertTrue(any("立创商城" in item for item in result["datasheet_lookup"]["source_priority"]))
        self.assertTrue(any("WebFetch" in item and "curl" in item for item in result["datasheet_lookup"]["search_rules"]))
        self.assertNotIn("R1", {candidate["ref"] for candidate in candidates})

    def test_parser_falls_back_to_library_meta_when_instance_value_is_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "board.epro2"
            make_sample_epro2(project)

            result = parser.analyze(project)

        self.assertEqual(result["components"]["R3"]["value"], "10K")
        self.assertEqual(result["components"]["R3"]["canonical_name"], "10K")
        self.assertEqual(result["components"]["R3"]["supplier_footprint"], "0402")
        self.assertEqual(result["components"]["C1"]["value"], "100nF")
        self.assertEqual(result["components"]["C1"]["canonical_name"], "100nF")
        self.assertEqual(result["components"]["C1"]["supplier_footprint"], "0402")

    def test_context_packet_keeps_only_selected_area_and_relevant_datasheet_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "board.epro2"
            make_sample_epro2(project)

            result = parser.analyze(project, "U1")
            packet = parser.build_context_packet(result, "U1")

        self.assertEqual(packet["schema"], "chip-netlist-context-packet-v1")
        self.assertEqual(packet["selection"]["query"], "U1")
        self.assertEqual(packet["selection"]["matched_refs"], ["U1"])
        self.assertEqual(set(packet["components"]), {"U1", "R1"})
        self.assertNotIn("U2", packet["components"])
        self.assertEqual({net["net"] for net in packet["nets"]}, {"GND", "VIN"})
        self.assertEqual([target["ref"] for target in packet["datasheet_lookup"]["targets"]], ["U1"])
        self.assertEqual(packet["datasheet_lookup"]["targets"][0]["context_role"], "primary")
        self.assertIn("R1", packet["support_components"])
        self.assertNotIn("U2.2", packet["pins"]["U1.2"][0]["peers"])
        self.assertEqual(packet["pins"]["U1.2"][0]["omitted_peer_count"], 2)

    def test_workbench_writes_persistent_files_without_overwriting_report_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "board.epro2"
            workbench = Path(tmp) / ".chip-netlist"
            make_sample_epro2(project)

            result = parser.analyze(project, "U1")
            packet = parser.build_context_packet(result, "U1")
            paths = parser.write_workbench(result, workbench, packet)

            report = workbench / "analysis_report.md"
            report.write_text("keep this human note\n", encoding="utf-8")
            state = workbench / "analysis_state.json"
            state.write_text('{"schema":"keep-state"}\n', encoding="utf-8")
            parser.write_workbench(result, workbench, packet)

            self.assertTrue((workbench / "chip_netlist.json").exists())
            self.assertTrue((workbench / "component_index.json").exists())
            self.assertTrue((workbench / "datasheet_sources.json").exists())
            self.assertTrue((workbench / "datasheets").is_dir())
            self.assertTrue((workbench / "datasheet_facts").is_dir())
            self.assertTrue((workbench / "context_packets" / "U1.json").exists())
            self.assertEqual(report.read_text(encoding="utf-8"), "keep this human note\n")
            self.assertEqual(json.loads(state.read_text(encoding="utf-8"))["schema"], "keep-state")
            self.assertIn("context_packet", paths)


if __name__ == "__main__":
    unittest.main()
