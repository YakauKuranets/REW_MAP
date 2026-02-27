from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime

import requests
from celery import shared_task

from app.extensions import db
from app.vulnerabilities.models import CVE
from app.tasks.reports_delivery import send_vulnerability_alerts

NVD_FEED_URL = "https://nvd.nist.gov/feeds/json/cve/1.1/nvdcve-1.1-recent.json.zip"


def _extract_products(item: dict) -> list[dict]:
    products: list[dict] = []
    for node in (item.get("configurations", {}) or {}).get("nodes", []) or []:
        for cpe in node.get("cpe_match", []) or []:
            cpe_uri = cpe.get("cpe23Uri") or ""
            # cpe:2.3:a:vendor:product:version:...
            parts = cpe_uri.split(":")
            if len(parts) >= 6:
                products.append({"vendor": parts[3], "product": parts[4], "version": parts[5]})
    return products


@shared_task(name="app.tasks.cve_updater.update_nvd_cve")
def update_nvd_cve() -> dict[str, int]:
    resp = requests.get(NVD_FEED_URL, timeout=60)
    resp.raise_for_status()

    archive = zipfile.ZipFile(io.BytesIO(resp.content))
    with archive.open(archive.namelist()[0]) as handle:
        data = json.load(handle)

    created = 0
    updated = 0
    for item in data.get("CVE_Items", []) or []:
        cve_id = (((item.get("cve") or {}).get("CVE_data_meta") or {}).get("ID") or "").strip()
        if not cve_id:
            continue

        desc_data = (((item.get("cve") or {}).get("description") or {}).get("description_data") or [])
        description = (desc_data[0].get("value") if desc_data else "") or ""

        cvss = None
        impact = item.get("impact") or {}
        if (impact.get("baseMetricV3") or {}).get("cvssV3"):
            cvss = (impact["baseMetricV3"]["cvssV3"]).get("baseScore")

        products = _extract_products(item)

        record = CVE.query.get(cve_id)
        if record is None:
            record = CVE(id=cve_id)
            created += 1
        else:
            updated += 1

        record.description = description
        record.cvss_score = cvss
        record.affected_products = products
        record.last_updated = datetime.utcnow()
        db.session.add(record)

        if cvss is not None and float(cvss) >= 7.0:
            affected = ", ".join(
                sorted({f"{(p.get('vendor') or '').strip()}:{(p.get('product') or '').strip()}" for p in (products or []) if (p.get('vendor') or p.get('product'))})
            ) or "unknown"
            send_vulnerability_alerts.delay(cve_id, description[:500], float(cvss), affected)

    db.session.commit()
    return {"created": created, "updated": updated}
