from datetime import datetime
from collections import defaultdict
from typing import List, Dict
from app.models import Shift, Worker, Site, FatigueAlert
from app.services.rules import (
    FATIGUE_DAILY_MAX_HOURS,
    FATIGUE_WEEKLY_MAX_HOURS,
    FATIGUE_MIN_REST_HOURS
)


def detect_fatigue_alerts(workers: List[Worker], sites: List[Site], shifts: List[Shift]) -> List[FatigueAlert]:
    """
    Scans shifts across all workers to find fatigue violations:
      1. Daily hours > 10h
      2. Weekly hours > 60h (in ISO week)
      3. Rest interval between consecutive shifts < 8h
    """
    site_map: Dict[str, Site] = {s.id: s for s in sites}
    worker_map: Dict[str, Worker] = {w.id: w for w in workers}
    alerts: List[FatigueAlert] = []

    # Group shifts by worker
    worker_shifts: Dict[str, List[Shift]] = defaultdict(list)
    for shift in shifts:
        if shift.status == "completed" and shift.end_time:
            worker_shifts[shift.worker_id].append(shift)

    for worker_id, s_list in worker_shifts.items():
        worker = worker_map.get(worker_id)
        if not worker:
            continue
        site = site_map.get(worker.site_id)
        site_name = site.name if site else "Unknown Site"

        # Sort chronologically by start_time
        sorted_shifts = sorted(s_list, key=lambda s: s.start_time)

        # 1. Daily shift hours
        # Group by date (YYYY-MM-DD)
        daily_hours: Dict[str, float] = defaultdict(float)
        daily_shifts: Dict[str, List[Shift]] = defaultdict(list)
        for s in sorted_shifts:
            date_str = s.start_time[:10]
            daily_hours[date_str] += s.total_hours
            daily_shifts[date_str].append(s)

        for date_str, hours in daily_hours.items():
            if hours > FATIGUE_DAILY_MAX_HOURS:
                severity = "critical" if hours >= 12.0 else "high"
                alerts.append(
                    FatigueAlert(
                        worker_id=worker.id,
                        worker_name=worker.name,
                        site_id=worker.site_id,
                        site_name=site_name,
                        alert_type="daily_exceeded",
                        description=f"Shift duration exceeded safe limit: {hours:.1f}h logged on {date_str} (Limit: {FATIGUE_DAILY_MAX_HOURS}h).",
                        severity=severity,
                        shift_id=daily_shifts[date_str][-1].id if daily_shifts[date_str] else None,
                        measured_value=round(hours, 1),
                        threshold_value=FATIGUE_DAILY_MAX_HOURS,
                        recommended_action="Enforce immediate rest break and halt further overtime."
                    )
                )

        # 2. Weekly hours (group by ISO calendar year and week)
        weekly_hours: Dict[str, float] = defaultdict(float)
        for s in sorted_shifts:
            dt = datetime.fromisoformat(s.start_time)
            iso_year, iso_week, _ = dt.isocalendar()
            week_key = f"{iso_year}-W{iso_week:02d}"
            weekly_hours[week_key] += s.total_hours

        for week_key, hours in weekly_hours.items():
            if hours > FATIGUE_WEEKLY_MAX_HOURS:
                alerts.append(
                    FatigueAlert(
                        worker_id=worker.id,
                        worker_name=worker.name,
                        site_id=worker.site_id,
                        site_name=site_name,
                        alert_type="weekly_exceeded",
                        description=f"Weekly cumulative hours ({hours:.1f}h) exceeded safe cap in {week_key} (Max: {FATIGUE_WEEKLY_MAX_HOURS}h).",
                        severity="critical",
                        measured_value=round(hours, 1),
                        threshold_value=FATIGUE_WEEKLY_MAX_HOURS,
                        recommended_action="Cap weekly shift assignment. Mandate 24h rest before next rotation."
                    )
                )

        # 3. Rest intervals between consecutive shifts (< 8h)
        for i in range(len(sorted_shifts) - 1):
            prev_shift = sorted_shifts[i]
            next_shift = sorted_shifts[i + 1]
            if prev_shift.end_time and next_shift.start_time:
                prev_end = datetime.fromisoformat(prev_shift.end_time)
                next_start = datetime.fromisoformat(next_shift.start_time)
                rest_seconds = (next_start - prev_end).total_seconds()
                rest_hours = rest_seconds / 3600.0

                if 0 <= rest_hours < FATIGUE_MIN_REST_HOURS:
                    severity = "critical" if rest_hours <= 6.0 else "high"
                    alerts.append(
                        FatigueAlert(
                            worker_id=worker.id,
                            worker_name=worker.name,
                            site_id=worker.site_id,
                            site_name=site_name,
                            alert_type="insufficient_rest",
                            description=f"Insufficient recovery rest between shifts: only {rest_hours:.1f}h rest before shift on {next_shift.start_time[:10]} (Min: {FATIGUE_MIN_REST_HOURS}h).",
                            severity=severity,
                            shift_id=next_shift.id,
                            measured_value=round(rest_hours, 1),
                            threshold_value=FATIGUE_MIN_REST_HOURS,
                            recommended_action="Reschedule start time to allow a minimum of 8 continuous rest hours."
                        )
                    )

    return alerts


def check_worker_fatigue(worker: Worker, site: Site, worker_shifts: List[Shift]) -> List[FatigueAlert]:
    """Check fatigue alerts specifically for one worker."""
    return detect_fatigue_alerts([worker], [site], worker_shifts)
