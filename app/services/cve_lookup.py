from __future__ import annotations

from typing import Any

from app.vulnerabilities.models import CVE


def find_cves_for_product(product_hint: str, limit: int = 20) -> list[dict[str, Any]]:
    """Find CVE entries by product/vendor hint in affected_products JSON or description."""
    needle = (product_hint or "").strip().lower()
    if not needle:
        return []

    # JSON filtering is backend-dependent; do broad filter then in-Python match for portability.
    rows = CVE.query.order_by(CVE.last_updated.desc().nullslast()).limit(1000).all()
    matched: list[dict[str, Any]] = []
    for row in rows:
        products = row.affected_products or []
        found = needle in (row.description or "").lower()
        if not found:
            for item in products:
                if not isinstance(item, dict):
                    continue
                joined = " ".join(str(item.get(k, "")) for k in ("vendor", "product", "version")).lower()
                if needle in joined:
                    found = True
                    break
        if found:
            matched.append(
                {
                    "id": row.id,
                    "description": row.description,
                    "cvss_score": row.cvss_score,
                    "exploit_available": bool(row.exploit_available),
                    "affected_products": products,
                    "last_updated": row.last_updated.isoformat() if row.last_updated else None,
                }
            )
        if len(matched) >= max(1, int(limit)):
            break
    return matched
