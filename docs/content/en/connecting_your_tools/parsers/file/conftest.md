---
title: "Conftest Scan"
toc_hide: true
---
### File Types
DefectDojo parser accepts Conftest scan data as a .JSON file.

JSON files can be created from the Conftest CLI using the `--output json` flag:
https://www.conftest.dev/

### Acceptable JSON Format

~~~json
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
                    "id": "POLICY-001",
                    "severity": "high"
                }
            }
        ],
        "warnings": [
            {
                "msg": "Resource limits not set",
                "metadata": {
                    "query": "data.main.warn",
                    "id": "POLICY-002",
                    "severity": "low"
                }
            }
        ]
    }
]
~~~

### Sample Scan Data
Sample Conftest scan data can be found
[here](https://github.com/DefectDojo/django-DefectDojo/tree/master/unittests/scans/conftest).
