"""Illustrative impact model. Every assumption is returned so judges can audit the numbers."""
from datetime import datetime
from typing import Any, Dict, List
from app.models import Worker, Site, Shift
from app.services.rules import get_sector_rule


def estimate_impact(workers: List[Worker], sites: List[Site], shifts: List[Shift],
                    fatigue_alert_count: int, scale_workers: int, theft_rate: float) -> Dict[str, Any]:
    site_by_id = {s.id: s for s in sites}
    done = [s for s in shifts if s.status == "completed" and s.end_time]
    n_workers = max(1, len(workers))

    if done:
        starts = [datetime.fromisoformat(s.start_time) for s in done]
        weeks = max(1.0, (max(starts) - min(starts)).days / 7.0)
    else:
        weeks = 1.0

    ot_hours_per_worker_week = sum(s.overtime_hours for s in done) / n_workers / weeks

    # Premium at risk: if OT is paid at 1x instead of m-x, the worker loses (m-1) * rate per OT hour
    premium_loss_per_ot_hour = 0.0
    counted = 0
    for w in workers:
        site = site_by_id.get(w.site_id)
        mult = get_sector_rule(site.sector).overtime_multiplier if site else 2.0
        premium_loss_per_ot_hour += w.hourly_rate * (mult - 1.0)
        counted += 1
    premium_loss_per_ot_hour = premium_loss_per_ot_hour / counted if counted else 0.0

    annual_loss_per_underpaid_worker = ot_hours_per_worker_week * 52 * premium_loss_per_ot_hour
    affected = scale_workers * theft_rate
    wage_protected = annual_loss_per_underpaid_worker * affected

    return {
        "scale_workers": scale_workers,
        "estimated_annual_wage_protected_inr": round(wage_protected, 0),
        "annual_loss_per_underpaid_worker_inr": round(annual_loss_per_underpaid_worker, 0),
        "workers_affected": round(affected),
        "fatigue_alerts_per_100_workers": round(fatigue_alert_count / n_workers * 100, 1),
        "assumptions": {
            "basis": f"Seeded demo data: {len(done)} completed shifts across {n_workers} workers, ~{weeks:.1f} weeks",
            "ot_hours_per_worker_per_week": round(ot_hours_per_worker_week, 2),
            "avg_overtime_premium_per_hour_inr": round(premium_loss_per_ot_hour, 2),
            "theft_rate_assumed": theft_rate,
            "model": "Share of workers whose OT is paid at 1x instead of 2x. An assumption, not a measured statistic.",
        },
    }
