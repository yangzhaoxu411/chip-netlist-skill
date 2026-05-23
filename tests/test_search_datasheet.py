"""Tests for search_datasheet.py."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure the scripts directory is importable
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "chip-netlist" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from search_datasheet import (
    sanitize_filename,
    load_sources,
    save_sources,
    try_download,
    extract_lcsc_pdf_url,
    extract_semiee_pdf_url,
    search_datasheets,
    main,
)

SEARCH_SCRIPT = SCRIPTS_DIR / "search_datasheet.py"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_component_index() -> dict:
    """A minimal component_index.json with a mix of targets and passives."""
    return {
        "schema": "chip-netlist-component-index-v1",
        "component_count": 5,
        "components": {
            "U1": {
                "canonical_name": "LTC4015IUHF#TRPBF",
                "manufacturer_part": "LTC4015IUHF#TRPBF",
                "manufacturer": "ADI",
                "value": None,
                "supplier": "LCSC",
                "supplier_part": "C687160",
                "datasheet": "https://example.com/LTC4015.pdf",
                "supplier_footprint": "QFN-38",
                "datasheet_target": True,
                "priority": "high",
                "reason": "integrated circuit or module",
                "query_terms": ["LTC4015IUHF#TRPBF datasheet"],
            },
            "U5": {
                "canonical_name": "LM74700QDBVRQ1",
                "manufacturer_part": "LM74700QDBVRQ1",
                "manufacturer": "TI",
                "value": None,
                "supplier": "LCSC",
                "supplier_part": "C2941042",
                "datasheet": "https://www.ti.com/lm74700.pdf",
                "supplier_footprint": "SOT-23-6",
                "datasheet_target": True,
                "priority": "high",
                "reason": "integrated circuit",
                "query_terms": ["LM74700QDBVRQ1 datasheet"],
            },
            "C1": {
                "canonical_name": "100nF",
                "manufacturer_part": None,
                "manufacturer": None,
                "value": "100nF",
                "supplier": None,
                "supplier_part": None,
                "datasheet": None,
                "supplier_footprint": "0603",
                "datasheet_target": False,
                "priority": "skip",
                "reason": "ordinary passive component",
                "query_terms": ["100nF datasheet"],
            },
            "D1": {
                "canonical_name": "SS34",
                "manufacturer_part": "SS34",
                "manufacturer": None,
                "value": None,
                "supplier": "LCSC",
                "supplier_part": "C7420365",
                "datasheet": None,
                "supplier_footprint": "SMA",
                "datasheet_target": True,
                "priority": "high",
                "reason": "diode",
                "query_terms": ["SS34 datasheet"],
            },
            "R1": {
                "canonical_name": "10K",
                "manufacturer_part": None,
                "manufacturer": None,
                "value": "10K",
                "supplier": None,
                "supplier_part": None,
                "datasheet": None,
                "supplier_footprint": "0402",
                "datasheet_target": False,
                "priority": "skip",
                "reason": "ordinary passive component",
                "query_terms": [],
            },
        },
    }


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    """Create a temporary workdir with datasheets directory."""
    wd = tmp_path / ".chip-netlist"
    wd.mkdir()
    (wd / "datasheets").mkdir()
    return wd


# ---------------------------------------------------------------------------
# Test sanitize_filename
# ---------------------------------------------------------------------------


class TestSanitizeFilename:
    """Test that special characters in part numbers are replaced."""

    def test_replaces_slash(self):
        assert sanitize_filename("LM5069MM-1/NOPB") == "LM5069MM-1_NOPB"

    def test_replaces_backslash(self):
        assert sanitize_filename("part\\name") == "part_name"

    def test_replaces_colon(self):
        assert sanitize_filename("C:123") == "C_123"

    def test_replaces_asterisk(self):
        assert sanitize_filename("LTC*4015") == "LTC_4015"

    def test_replaces_question_mark(self):
        assert sanitize_filename("what?") == "what_"

    def test_replaces_quotes(self):
        assert sanitize_filename('"quoted"') == "_quoted_"

    def test_replaces_angle_brackets(self):
        assert sanitize_filename("<tag>") == "_tag_"

    def test_replaces_pipe(self):
        assert sanitize_filename("a|b") == "a_b"

    def test_replaces_multiple_special_chars(self):
        assert sanitize_filename('LTC4015IUHF#TRPBF') == 'LTC4015IUHF#TRPBF'
        # The hash # is not in the unsafe set, so it stays
        assert sanitize_filename("LM5069MM-1/NOPB*?") == "LM5069MM-1_NOPB__"

    def test_safe_name_unchanged(self):
        assert sanitize_filename("LTC4015") == "LTC4015"
        assert sanitize_filename("LM74700QDBVRQ1") == "LM74700QDBVRQ1"

    def test_parentheses_preserved(self):
        """Parentheses are not filesystem-unsafe on most systems."""
        assert sanitize_filename("SI7617DN(ES)") == "SI7617DN(ES)"


# ---------------------------------------------------------------------------
# Test load_sources / save_sources
# ---------------------------------------------------------------------------


class TestSourcesIO:
    """Test loading and saving datasheet_sources.json."""

    def test_load_missing_file(self, tmp_path: Path):
        path = tmp_path / "nonexistent.json"
        data = load_sources(path)
        assert data["schema"] == "chip-netlist-datasheet-sources-v1"
        assert data["sources"] == {}

    def test_load_existing_file(self, tmp_path: Path):
        path = tmp_path / "sources.json"
        existing = {
            "schema": "chip-netlist-datasheet-sources-v1",
            "sources": {"U1": {"part": "LTC4015", "status": "downloaded"}},
        }
        path.write_text(json.dumps(existing), encoding="utf-8")
        data = load_sources(path)
        assert data["sources"]["U1"]["status"] == "downloaded"

    def test_save_creates_file(self, tmp_path: Path):
        path = tmp_path / "sources.json"
        data = {"schema": "chip-netlist-datasheet-sources-v1", "sources": {}}
        save_sources(path, data)
        assert path.exists()
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["schema"] == "chip-netlist-datasheet-sources-v1"


# ---------------------------------------------------------------------------
# Test try_download (mocked curl)
# ---------------------------------------------------------------------------


class TestTryDownload:
    """Test the curl download wrapper with mocked subprocess."""

    @patch("search_datasheet.subprocess.run")
    def test_success(self, mock_run, tmp_path: Path):
        mock_run.return_value = MagicMock(returncode=0)
        output = tmp_path / "test.pdf"
        # Simulate a successful download by creating the file
        output.write_bytes(b"%PDF-1.4 fake content")

        # Re-patch to let the file exist check pass
        result = try_download("https://example.com/test.pdf", output, 30)
        assert result is True

    @patch("search_datasheet.subprocess.run")
    def test_curl_failure(self, mock_run, tmp_path: Path):
        mock_run.return_value = MagicMock(returncode=22)  # HTTP error
        output = tmp_path / "test.pdf"
        result = try_download("https://example.com/missing.pdf", output, 30)
        assert result is False

    @patch("search_datasheet.subprocess.run")
    def test_timeout(self, mock_run, tmp_path: Path):
        mock_run.side_effect = subprocess.TimeoutExpired("curl", 30)
        output = tmp_path / "test.pdf"
        result = try_download("https://example.com/slow.pdf", output, 30)
        assert result is False

    @patch("search_datasheet.subprocess.run")
    def test_empty_file(self, mock_run, tmp_path: Path):
        """If curl succeeds but file is empty, treat as failure."""
        mock_run.return_value = MagicMock(returncode=0)
        output = tmp_path / "test.pdf"
        output.write_bytes(b"")  # empty file
        result = try_download("https://example.com/empty.pdf", output, 30)
        assert result is False


# ---------------------------------------------------------------------------
# Test extract_lcsc_pdf_url
# ---------------------------------------------------------------------------


class TestExtractLcscPdfUrl:
    """Test PDF URL extraction from LCSC HTML."""

    def test_extracts_atta_url(self):
        html = '<a href="https://atta.szlcsc.com/upload/public/pdf/source/20210914/C687160.pdf">Download</a>'
        url = extract_lcsc_pdf_url(html, "C687160")
        assert url is not None
        assert "C687160.pdf" in url

    def test_extracts_json_pdf_url(self):
        html = '{"pdfUrl":"https://atta.szlcsc.com/upload/public/pdf/source/test.pdf"}'
        url = extract_lcsc_pdf_url(html, "C123")
        assert url is not None
        assert "test.pdf" in url

    def test_extracts_datasheet_url(self):
        html = '{"datasheetUrl":"https://example.com/ds.pdf"}'
        url = extract_lcsc_pdf_url(html, "C123")
        assert url is not None
        assert "ds.pdf" in url

    def test_no_match(self):
        html = "<html><body>No PDF here</body></html>"
        url = extract_lcsc_pdf_url(html, "C123")
        assert url is None

    def test_json_escaped_slashes(self):
        html = '{"pdfUrl":"https:\\/\\/atta.szlcsc.com\\/pdf\\/test.pdf"}'
        url = extract_lcsc_pdf_url(html, "C123")
        assert url is not None
        assert "https://" in url


# ---------------------------------------------------------------------------
# Test extract_semiee_pdf_url
# ---------------------------------------------------------------------------


class TestExtractSemieePdfUrl:
    """Test PDF URL extraction from semiee.com HTML."""

    def test_extracts_pdf_link(self):
        html = '<a href="https://semiee.com/datasheet/LTC4015.pdf">PDF</a>'
        url = extract_semiee_pdf_url(html)
        assert url is not None
        assert "LTC4015.pdf" in url

    def test_no_match(self):
        html = "<html><body>No PDF</body></html>"
        url = extract_semiee_pdf_url(html)
        assert url is None


# ---------------------------------------------------------------------------
# Test cached files are skipped
# ---------------------------------------------------------------------------


class TestCachedSkip:
    """Test that already-downloaded PDFs are skipped."""

    @patch("search_datasheet.try_download")
    def test_skips_existing_pdf(self, mock_download, sample_component_index, workdir):
        """If a PDF already exists, try_download should not be called."""
        pdf_path = workdir / "datasheets" / "LTC4015IUHF#TRPBF.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 cached content")

        search_datasheets(sample_component_index, workdir=workdir)
        # try_download should not be called for U1 since it's cached
        for call in mock_download.call_args_list:
            url_arg = call[0][0]
            assert "LTC4015" not in url_arg

    @patch("search_datasheet.try_download")
    def test_does_not_skip_empty_file(self, mock_download, sample_component_index, workdir):
        """An empty PDF file should not be considered cached."""
        pdf_path = workdir / "datasheets" / "LTC4015IUHF#TRPBF.pdf"
        pdf_path.write_bytes(b"")  # empty

        mock_download.return_value = True
        search_datasheets(sample_component_index, workdir=workdir)
        # Should have tried to download since file is empty
        assert mock_download.called


# ---------------------------------------------------------------------------
# Test --refs filter
# ---------------------------------------------------------------------------


class TestRefsFilter:
    """Test that --refs limits which components are searched."""

    @patch("search_datasheet.try_download")
    def test_only_requested_refs(self, mock_download, sample_component_index, workdir):
        """Only U5 should be searched when --refs U5 is specified."""
        mock_download.return_value = True

        sources = search_datasheets(
            sample_component_index,
            workdir=workdir,
            refs=["U5"],
        )

        # Only U5 should appear in sources
        assert "U5" in sources["sources"]
        assert "U1" not in sources["sources"]
        assert "D1" not in sources["sources"]

    @patch("search_datasheet.try_download")
    def test_multiple_refs(self, mock_download, sample_component_index, workdir):
        """Specifying multiple refs limits to those."""
        mock_download.return_value = True

        sources = search_datasheets(
            sample_component_index,
            workdir=workdir,
            refs=["U1", "D1"],
        )

        assert "U1" in sources["sources"]
        assert "D1" in sources["sources"]
        assert "U5" not in sources["sources"]

    @patch("search_datasheet.try_download")
    def test_case_insensitive_refs(self, mock_download, sample_component_index, workdir):
        """Ref matching should be case-insensitive."""
        mock_download.return_value = True

        sources = search_datasheets(
            sample_component_index,
            workdir=workdir,
            refs=["u1"],
        )

        assert "U1" in sources["sources"]


# ---------------------------------------------------------------------------
# Test that only high-priority datasheet targets are searched
# ---------------------------------------------------------------------------


class TestPriorityFilter:
    """Test that only datasheet_target=true and priority=high are searched."""

    @patch("search_datasheet.try_download")
    def test_skips_passives(self, mock_download, sample_component_index, workdir):
        """C1 and R1 should be skipped (datasheet_target=false)."""
        mock_download.return_value = True

        sources = search_datasheets(sample_component_index, workdir=workdir)

        assert "C1" not in sources["sources"]
        assert "R1" not in sources["sources"]

    @patch("search_datasheet.try_download")
    def test_includes_high_priority(self, mock_download, sample_component_index, workdir):
        """U1, U5, D1 should be included (high priority)."""
        mock_download.return_value = True

        sources = search_datasheets(sample_component_index, workdir=workdir)

        assert "U1" in sources["sources"]
        assert "U5" in sources["sources"]
        assert "D1" in sources["sources"]


# ---------------------------------------------------------------------------
# Test output schema
# ---------------------------------------------------------------------------


class TestOutputSchema:
    """Test that the output conforms to the expected schema."""

    @patch("search_datasheet.try_download")
    def test_schema_field(self, mock_download, sample_component_index, workdir):
        sources = search_datasheets(sample_component_index, workdir=workdir)
        assert sources["schema"] == "chip-netlist-datasheet-sources-v1"

    @patch("search_datasheet.try_download")
    def test_downloaded_entry_has_required_fields(
        self, mock_download, sample_component_index, workdir
    ):
        mock_download.return_value = True
        sources = search_datasheets(sample_component_index, workdir=workdir)

        for ref, entry in sources["sources"].items():
            assert "part" in entry
            assert "status" in entry
            if entry["status"] == "downloaded":
                assert "url" in entry
                assert "local_path" in entry
            elif entry["status"] == "not_found":
                assert "tried_urls" in entry

    @patch("search_datasheet.try_download")
    def test_datasources_file_written(self, mock_download, sample_component_index, workdir):
        search_datasheets(sample_component_index, workdir=workdir)
        ds_path = workdir / "datasheet_sources.json"
        assert ds_path.exists()
        data = json.loads(ds_path.read_text(encoding="utf-8"))
        assert data["schema"] == "chip-netlist-datasheet-sources-v1"


# ---------------------------------------------------------------------------
# Test CLI interface
# ---------------------------------------------------------------------------


class TestCLI:
    """Tests for the search_datasheet.py CLI."""

    def _write_index(self, tmp_path: Path, index: dict) -> Path:
        fp = tmp_path / "component_index.json"
        fp.write_text(json.dumps(index), encoding="utf-8")
        return fp

    def _run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SEARCH_SCRIPT), *args],
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_missing_file(self, tmp_path: Path):
        result = self._run_cli(str(tmp_path / "missing.json"))
        assert result.returncode != 0

    @patch("search_datasheet.try_download")
    def test_cli_basic(self, mock_download, tmp_path: Path, sample_component_index):
        mock_download.return_value = True
        index_path = self._write_index(tmp_path, sample_component_index)
        workdir = tmp_path / ".chip-netlist"
        workdir.mkdir()
        (workdir / "datasheets").mkdir()

        result = self._run_cli(
            str(index_path),
            "--workdir", str(workdir),
        )
        assert result.returncode == 0
        # stdout should contain valid JSON
        output = json.loads(result.stdout)
        assert output["schema"] == "chip-netlist-datasheet-sources-v1"

    @patch("search_datasheet.try_download")
    def test_cli_refs_filter(self, mock_download, tmp_path: Path, sample_component_index):
        mock_download.return_value = True
        index_path = self._write_index(tmp_path, sample_component_index)
        workdir = tmp_path / ".chip-netlist"
        workdir.mkdir()
        (workdir / "datasheets").mkdir()

        result = self._run_cli(
            str(index_path),
            "--workdir", str(workdir),
            "--refs", "U1",
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert "U1" in output["sources"]
        # U5 should not be in sources since we filtered to U1 only
        assert "U5" not in output["sources"]


# ---------------------------------------------------------------------------
# Test summary output
# ---------------------------------------------------------------------------


class TestSummary:
    """Test the summary statistics in stderr output."""

    @patch("search_datasheet.try_download")
    def test_summary_printed(self, mock_download, sample_component_index, workdir, capsys):
        mock_download.return_value = True
        search_datasheets(sample_component_index, workdir=workdir)
        captured = capsys.readouterr()
        assert "Downloaded:" in captured.err
        assert "Skipped (cached):" in captured.err
        assert "Not found:" in captured.err

    @patch("search_datasheet.try_download")
    def test_cached_count(self, mock_download, sample_component_index, workdir, capsys):
        """Pre-existing PDFs should count as skipped."""
        pdf_path = workdir / "datasheets" / "LTC4015IUHF#TRPBF.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 cached")

        search_datasheets(sample_component_index, workdir=workdir)
        captured = capsys.readouterr()
        assert "Skipped (cached): 1" in captured.err
