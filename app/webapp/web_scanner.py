# -*- coding: utf-8 -*-
"""Web application scanner wrappers for authorized security assessment."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from typing import Dict, List

logger = logging.getLogger(__name__)


class WebAppScanner:
    """Wrapper around Nuclei and Nikto binaries with result parsing."""

    def __init__(self, nuclei_path: str = "/usr/local/bin/nuclei", nikto_path: str = "/usr/bin/nikto"):
        self.nuclei_path = nuclei_path
        self.nikto_path = nikto_path

    def scan_with_nuclei(self, target_url: str, template_type: str = "cves") -> List[Dict]:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            output_file = tmp.name

        try:
            cmd = [
                self.nuclei_path,
                "-u",
                target_url,
                "-t",
                f"/root/nuclei-templates/{template_type}/",
                "-json",
                "-o",
                output_file,
            ]
            subprocess.run(cmd, capture_output=True, timeout=300, check=False)

            findings: list[dict] = []
            if not os.path.exists(output_file):
                return findings

            with open(output_file, "r", encoding="utf-8", errors="ignore") as stream:
                for line in stream:
                    try:
                        vuln = json.loads(line)
                    except Exception:
                        continue
                    findings.append(
                        {
                            "template": vuln.get("template-id"),
                            "name": (vuln.get("info") or {}).get("name"),
                            "severity": (vuln.get("info") or {}).get("severity"),
                            "url": vuln.get("matched-at"),
                            "extracted_results": vuln.get("extracted-results", []),
                        }
                    )
            return findings
        except subprocess.TimeoutExpired:
            logger.error("Nuclei scan timeout")
            return []
        finally:
            if os.path.exists(output_file):
                os.unlink(output_file)

    def scan_with_nikto(self, target_url: str) -> List[Dict]:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
            output_file = tmp.name

        try:
            cmd = ["perl", self.nikto_path, "-h", target_url, "-Format", "txt", "-o", output_file]
            subprocess.run(cmd, capture_output=True, timeout=180, check=False)

            findings: list[dict] = []
            if not os.path.exists(output_file):
                return findings

            with open(output_file, "r", encoding="utf-8", errors="ignore") as stream:
                for line in stream:
                    if "+ " in line and ("OSVDB" in line or "CVE" in line):
                        findings.append({"raw": line.strip(), "type": "nikto_finding"})
            return findings
        except subprocess.TimeoutExpired:
            logger.error("Nikto scan timeout")
            return []
        finally:
            if os.path.exists(output_file):
                os.unlink(output_file)
