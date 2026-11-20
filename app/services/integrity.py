"""Tamper-evident hash chain for safety reports.

Each report stores prev_hash and hash = sha256(prev_hash | canonical payload).
Mutable workflow fields (status, resolved_at) are deliberately excluded, so an
admin moving a card to "Resolved" never breaks the chain, while editing or
deleting the report content itself does.
"""
import hashlib
import json
from typing import Any, Dict, List

GENESIS_HASH = "0" * 64


def _payload(report: Any) -> str:
    data: Dict[str, Any] = {
        "id": report.id,
        "site_id": report.site_id,
        "worker_id": report.worker_id,
        "input_text": report.input_text,
        "category": report.category,
        "severity": report.severity,
        "summary_en": report.summary_en,
        "source": getattr(report, "source", "text"),
        "created_at": report.created_at,
    }
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compute_report_hash(report: Any, prev_hash: str) -> str:
    return hashlib.sha256(f"{prev_hash}|{_payload(report)}".encode("utf-8")).hexdigest()


def verify_chain(reports_in_order: List[Any]) -> Dict[str, Any]:
    """Return {valid, checked, broken_index, broken_report_id, reason}."""
    prev = GENESIS_HASH
    for i, r in enumerate(reports_in_order):
        if r.prev_hash != prev:
            return {"valid": False, "checked": i, "broken_index": i,
                    "broken_report_id": r.id, "reason": "prev_hash mismatch (report removed or reordered)"}
        if r.hash != compute_report_hash(r, prev):
            return {"valid": False, "checked": i, "broken_index": i,
                    "broken_report_id": r.id, "reason": "content hash mismatch (report was modified)"}
        prev = r.hash
    return {"valid": True, "checked": len(reports_in_order), "broken_index": None,
            "broken_report_id": None, "reason": None, "head_hash": prev}
