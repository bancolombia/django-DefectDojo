from dojo.models import Test
from dojo.tools.cortex.parser import CortexParser
from unittests.dojo_test_case import DojoTestCase, get_unit_tests_scans_path


class TestCortexParser(DojoTestCase):
    def test_registers_separate_scan_types(self):
        parser = CortexParser()

        self.assertEqual(
            ["Cortex Hosts", "Cortex Serverless", "Cortex Images"],
            parser.get_scan_types(),
        )

    def test_parses_cortex_csv_and_preserves_cortex_tags(self):
        testfile = (get_unit_tests_scans_path("cortex") / "cortex_hosts.csv").open(encoding="utf-8")
        findings = CortexParser().get_findings(testfile, Test())
        testfile.close()

        self.assertEqual(1, len(findings))
        finding = findings[0]
        self.assertEqual("CVE-2025-1234", finding.vuln_id_from_tool)
        self.assertEqual(["CVE-2025-1234"], finding.unsaved_vulnerability_ids)
        self.assertEqual(["Cortex", "Hosts"], finding.unsaved_tags)
