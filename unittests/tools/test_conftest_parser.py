from dojo.models import Test
from dojo.tools.conftest.parser import ConftestParser
from unittests.dojo_test_case import DojoTestCase, get_unit_tests_scans_path


class TestConftestParser(DojoTestCase):

    def setUp(self):
        self.parser = ConftestParser()
        self.scans_path = get_unit_tests_scans_path("conftest")

    # --- Metadata ---

    def test_get_scan_types(self):
        self.assertEqual(["Conftest Scan"], self.parser.get_scan_types())

    def test_get_label_for_scan_types(self):
        self.assertEqual("Conftest Scan", self.parser.get_label_for_scan_types("Conftest Scan"))

    def test_get_description_for_scan_types(self):
        desc = self.parser.get_description_for_scan_types("Conftest Scan")
        self.assertIn("Conftest", desc)

    # --- Empty / no findings ---

    def test_parse_empty_array(self):
        """An empty JSON array should return no findings."""
        with open(self.scans_path / "no_findings.json") as f:
            findings = self.parser.get_findings(f, Test())
        self.assertEqual(0, len(findings))

    def test_parse_file_with_successes_only(self):
        """A file with only successes and no failures/warnings returns no findings."""
        with open(self.scans_path / "no_violations.json") as f:
            findings = self.parser.get_findings(f, Test())
        self.assertEqual(0, len(findings))

    # --- Multiple findings ---

    def test_parse_many_findings(self):
        """Should parse failures and warnings from multiple files."""
        with open(self.scans_path / "many_findings.json") as f:
            findings = self.parser.get_findings(f, Test())
        # 2 failures (deploy.yaml) + 1 warning (deploy.yaml) + 1 failure (service.yaml)
        self.assertEqual(4, len(findings))

    def test_severity_mapping(self):
        """Severity values from metadata should map correctly to DefectDojo severities."""
        with open(self.scans_path / "many_findings.json") as f:
            findings = self.parser.get_findings(f, Test())

        severity_map = {f.title: f.severity for f in findings}

        # unique_id is composite: rule_id|filename — same rule_id can appear on different files
        # POLICY-001 on deploy.yaml → high
        self.assertEqual("High", next(f.severity for f in findings if (f.unique_id_from_tool or "") == "POLICY-001|deploy.yaml"))
        # POLICY-002 on deploy.yaml → medium
        self.assertEqual("Medium", next(f.severity for f in findings if (f.unique_id_from_tool or "") == "POLICY-002|deploy.yaml"))
        # POLICY-004 on service.yaml → critical
        self.assertEqual("Critical", next(f.severity for f in findings if (f.unique_id_from_tool or "") == "POLICY-004|service.yaml"))

    def test_warning_severity_low(self):
        """Warning with severity=low in metadata should map to Low."""
        with open(self.scans_path / "many_findings.json") as f:
            findings = self.parser.get_findings(f, Test())
        warning = next(f for f in findings if (f.unique_id_from_tool or "") == "POLICY-003|deploy.yaml")
        self.assertEqual("Low", warning.severity)

    def test_file_path_populated(self):
        """file_path should be set to the scanned filename."""
        with open(self.scans_path / "many_findings.json") as f:
            findings = self.parser.get_findings(f, Test())
        deploy_findings = [f for f in findings if f.file_path == "deploy.yaml"]
        self.assertGreater(len(deploy_findings), 0)
        service_findings = [f for f in findings if f.file_path == "service.yaml"]
        self.assertGreater(len(service_findings), 0)

    def test_unique_id_from_tool(self):
        """unique_id_from_tool must be a composite of rule_id|filename[|node_id].
        The same rule can fire on different files, so the composite ensures uniqueness per instance."""
        with open(self.scans_path / "many_findings.json") as f:
            findings = self.parser.get_findings(f, Test())
        ids = {f.unique_id_from_tool for f in findings}
        self.assertIn("POLICY-001|deploy.yaml", ids)
        self.assertIn("POLICY-002|deploy.yaml", ids)
        self.assertIn("POLICY-004|service.yaml", ids)
        # All IDs must be distinct
        self.assertEqual(len(ids), len(findings))

    def test_vuln_id_from_tool(self):
        """vuln_id_from_tool should contain the rule ID; title should NOT."""
        with open(self.scans_path / "many_findings.json") as f:
            findings = self.parser.get_findings(f, Test())
        for finding in findings:
            if finding.vuln_id_from_tool:
                self.assertNotIn(finding.vuln_id_from_tool, finding.title)
        vuln_ids = {f.vuln_id_from_tool for f in findings}
        self.assertIn("POLICY-001", vuln_ids)
        self.assertIn("POLICY-002", vuln_ids)
        self.assertIn("POLICY-004", vuln_ids)

    # --- n8n workflow findings ---

    def test_parse_n8n_findings(self):
        """Should parse findings with node_type and node_id in metadata."""
        with open(self.scans_path / "n8n_findings.json") as f:
            findings = self.parser.get_findings(f, Test())
        self.assertEqual(1, len(findings))
        finding = findings[0]
        self.assertEqual("High", finding.severity)
        # composite: rule_id|filename|node_id
        node_id = "8a77aa44-0f57-4f6b-985a-4b5989138621"
        self.assertEqual(f"POLICY-005|workflow.json|{node_id}", finding.unique_id_from_tool)
        self.assertEqual("POLICY-005", finding.vuln_id_from_tool)
        self.assertEqual("workflow.json", finding.file_path)
        # title is only the message, rule_id must NOT appear in title
        self.assertNotIn("POLICY-005", finding.title)
        self.assertIn("node_type", finding.description.lower())

    # --- Minimal metadata (edge cases) ---

    def test_parse_minimal_metadata(self):
        """Findings with empty or missing metadata should still parse."""
        with open(self.scans_path / "minimal_metadata.json") as f:
            findings = self.parser.get_findings(f, Test())
        self.assertEqual(2, len(findings))
        for finding in findings:
            self.assertIsNotNone(finding.title)
            self.assertIsNotNone(finding.severity)

    def test_minimal_metadata_default_severity(self):
        """Findings with unknown/missing severity should default to Low."""
        with open(self.scans_path / "minimal_metadata.json") as f:
            findings = self.parser.get_findings(f, Test())
        for finding in findings:
            self.assertEqual("Low", finding.severity)

    # --- Invalid input ---

    def test_invalid_json(self):
        """Invalid JSON should raise ValueError."""
        import io
        bad_input = io.BytesIO(b"this is not json")
        with self.assertRaises(ValueError):
            self.parser.get_findings(bad_input, Test())

    def test_non_array_json(self):
        """JSON that is not an array should raise ValueError."""
        import io
        bad_input = io.BytesIO(b'{"filename": "deploy.yaml"}')
        with self.assertRaises(ValueError):
            self.parser.get_findings(bad_input, Test())
