import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "chip-netlist" / "scripts" / "parse_tel_netlist.py"
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
        record({"type": "COMPONENT", "ticket": 8, "id": "pcb_u1"}, {"partId": "LM5069MM-1/NOPB.1"}),
        record({"type": "ATTR", "ticket": 9, "id": "a6"}, {"parentId": "pcb_u1", "key": "Designator", "value": "U1"}),
        record({"type": "ATTR", "ticket": 10, "id": "a7"}, {"parentId": "pcb_u1", "key": "Footprint", "value": "TSSOP-10_L3.0-W3.0-P0.50"}),
        record({"type": "ATTR", "ticket": 11, "id": "a8"}, {"parentId": "pcb_u1", "key": "Unique ID", "value": "gge100"}),
        record({"type": "COMPONENT", "ticket": 12, "id": "pcb_r1"}, {"partId": "0402WGF1002TCE.1"}),
        record({"type": "ATTR", "ticket": 13, "id": "a9"}, {"parentId": "pcb_r1", "key": "Designator", "value": "R1"}),
        record({"type": "ATTR", "ticket": 14, "id": "a10"}, {"parentId": "pcb_r1", "key": "Value", "value": "10K"}),
        record({"type": "NET", "ticket": 15, "id": json.dumps(["NET", "VIN"])}, {}),
        record({"type": "NET", "ticket": 16, "id": json.dumps(["NET", "GND"])}, {}),
        record({"type": "PAD_NET", "ticket": 17, "id": json.dumps(["PAD_NET", "pcb_u1", "1", "e1"])}, {"padNet": "VIN"}),
        record({"type": "PAD_NET", "ticket": 18, "id": json.dumps(["PAD_NET", "pcb_u1", "2", "e2"])}, {"padNet": "GND"}),
        record({"type": "PAD_NET", "ticket": 19, "id": json.dumps(["PAD_NET", "pcb_u1", "3", "e3"])}, {"padNet": ""}),
        record({"type": "PAD_NET", "ticket": 20, "id": json.dumps(["PAD_NET", "pcb_r1", "1", "e4"])}, {"padNet": "VIN"}),
        record({"type": "PAD_NET", "ticket": 21, "id": json.dumps(["PAD_NET", "pcb_r1", "2", "e5"])}, {"padNet": "GND"}),
    ]
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("project2.json", json.dumps({"title": "sample"}))
        zf.writestr("sample.epru", "|\n".join(records) + "|\n")


class ParseNetlistTests(unittest.TestCase):
    def test_version_file_and_cli_report_current_version(self):
        self.assertEqual(parser.load_version(), "0.1.4")

        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--version"],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.stdout.strip(), "chip-netlist 0.1.4")

    def test_epro2_parser_extracts_ai_ready_components_and_connections(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "board.epro2"
            make_sample_epro2(project)

            result = parser.analyze(project, "U1")

        self.assertEqual(result["source_type"], "epro2")
        self.assertEqual(result["components"]["U1"]["manufacturer_part"], "LM5069MM-1/NOPB")
        self.assertEqual(result["components"]["U1"]["supplier_part"], "C486026")
        self.assertIn("pcb_u1", result["components"]["U1"]["source_component_ids"])
        self.assertEqual(result["pins"]["U1.1"][0]["net"], "VIN")
        self.assertEqual(set(result["pins"]["U1.1"][0]["peers"]), {"R1.1"})
        self.assertEqual(result["pins"]["U1.2"][0]["net"], "GND")
        u1_pin3 = next(pin for pin in result["ref_report"]["pins"] if pin["pin"] == "U1.3")
        self.assertFalse(u1_pin3["connected"])
        self.assertIn("U1.3", result["warnings"]["no_net_pins"])


if __name__ == "__main__":
    unittest.main()
