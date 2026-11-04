from dojo.tools.twistlock.parser import TwistlockCSVParser


class CortexParser:
    def get_scan_types(self):
        return ["Cortex Hosts", "Cortex Serverless", "Cortex Images"]

    def get_label_for_scan_types(self, scan_type):
        return scan_type

    def get_description_for_scan_types(self, scan_type):
        return f"CSV vulnerability report generated from Cortex XDR {scan_type.removeprefix('Cortex ')}."

    def get_findings(self, filename, test):
        if filename is None:
            return []
        if not filename.name.lower().endswith(".csv"):
            msg = "Unknown File Format"
            raise ValueError(msg)
        return TwistlockCSVParser().parse(filename, test)
