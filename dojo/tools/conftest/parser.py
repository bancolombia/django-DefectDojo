import json
import logging

from django.conf import settings

from dojo.models import Finding

logger = logging.getLogger(__name__)

SEVERITY_MAP = {
    "critical": "Critical",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
    "info": "Info",
}

DEFAULT_SEVERITY = "Low"


class ConftestParser:
    """Parser for Conftest IaC policy scanning output (JSON format).

    Conftest output is a JSON array where each element represents a scanned file:
    [
        {
            "filename": "deploy.yaml",
            "namespace": "main",
            "successes": 1,
            "failures": [
                {
                    "msg": "Containers must not run as root",
                    "metadata": {
                        "query": "data.main.deny",
                        "id": "CONF_N8N_BC_3",
                        "node_type": "n8n-nodes-base.executeCommand",
                        "node_id": "8a77aa44-0f57-4f6b-985a-4b5989138621",
                        "severity": "high"
                    }
                }
            ],
            "warnings": []
        }
    ]
    """

    def get_scan_types(self):
        return ["Conftest Scan"]

    def get_label_for_scan_types(self, scan_type):
        return scan_type

    def get_description_for_scan_types(self, scan_type):
        return "Import Conftest IaC policy scan findings in JSON format."

    def get_findings(self, file, test):
        try:
            data = json.load(file)
        except (json.JSONDecodeError, ValueError) as e:
            msg = f"Invalid JSON format: {e}"
            raise ValueError(msg)

        if not isinstance(data, list):
            msg = "Conftest output must be a JSON array"
            raise ValueError(msg)

        findings = []
        for file_result in data:
            if not isinstance(file_result, dict):
                continue

            filename = file_result.get("filename", "")
            namespace = file_result.get("namespace", "")

            for failure in file_result.get("failures", []):
                finding = self._parse_violation(failure, filename, namespace, test)
                if finding:
                    findings.append(finding)

            for warning in file_result.get("warnings", []):
                finding = self._parse_violation(warning, filename, namespace, test, is_warning=True)
                if finding:
                    findings.append(finding)

        return findings

    def _parse_violation(self, violation, filename, namespace, test, is_warning=False):
        if not isinstance(violation, dict):
            return None

        msg = violation.get("msg", "").strip()
        if not msg:
            return None

        metadata = violation.get("metadata", {}) or {}

        rule_id = metadata.get("id") or metadata.get("query") or ""
        severity_raw = metadata.get("severity", "").lower()
        severity = SEVERITY_MAP.get(severity_raw, DEFAULT_SEVERITY)

        if is_warning and severity_raw not in SEVERITY_MAP:
            severity = "Info"

        node_type = metadata.get("node_type", "")
        node_id = metadata.get("node_id", "")

        # Build a descriptive title — only the message, no rule ID in the title
        title = msg

        # Limit title length per Finding model constraint (max 255)
        if len(title) > 255:
            title = title[:252] + "..."

        # Build description with all available context
        description_parts = [msg]
        if namespace:
            description_parts.append(f"**Namespace:** {namespace}")
        if rule_id:
            description_parts.append(f"**Rule ID:** {rule_id}")
        if node_type:
            description_parts.append(f"**node_type:** {node_type}")
        if node_id:
            description_parts.append(f"**node_id:** {node_id}")
        if metadata.get("query"):
            description_parts.append(f"**Query:** {metadata['query']}")

        description = "\n\n".join(description_parts)

        # Build a composite unique_id_from_tool that is truly unique per finding
        # instance: rule + file + node (if present).
        # The rule_id alone is NOT unique — the same rule can fire on many files/nodes.
        unique_id_parts = [p for p in [rule_id, filename, node_id] if p]
        unique_id = "|".join(unique_id_parts) if unique_id_parts else None

        finding = Finding(
            title=title,
            severity=severity,
            description=description,
            file_path=filename if filename else None,
            vuln_id_from_tool=rule_id if rule_id else None,
            unique_id_from_tool=unique_id,
            active=True,
            verified=False,
            static_finding=True,
            dynamic_finding=False,
        )
        finding.unsaved_tags = [settings.DD_CUSTOM_TAG_PARSER.get("conftest")]

        return finding
