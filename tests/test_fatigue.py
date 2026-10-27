import pytest
from app.services.fatigue import detect_fatigue_alerts
from app.models import Worker, Site, Shift


def test_detect_daily_fatigue_alert():
    worker = Worker(
        id="w-fatigue-1",
        name="Fatigued Worker",
        phone="9999999901",
        pin_hash="dummy",
        site_id="site-1",
        role="Mason",
        hourly_rate=150.0,
        passport_token="p1",
        created_at="2026-10-01T00:00:00Z"
    )
    site = Site(id="site-1", name="Site One", sector="construction", location="Chennai")

    # Shift of 13 hours on a single day (> 10h threshold)
    shifts = [
        Shift(
            id="s-long",
            worker_id="w-fatigue-1",
            site_id="site-1",
            start_time="2026-10-15T06:00:00Z",
            end_time="2026-10-15T19:00:00Z",
            total_hours=13.0,
            regular_hours=8.0,
            overtime_hours=5.0,
            status="completed"
        )
    ]

    alerts = detect_fatigue_alerts([worker], [site], shifts)
    assert len(alerts) >= 1
    daily_alert = [a for a in alerts if a.alert_type == "daily_exceeded"]
    assert len(daily_alert) == 1
    assert daily_alert[0].measured_value == 13.0
    assert daily_alert[0].threshold_value == 10.0
    assert daily_alert[0].severity == "critical"


def test_detect_insufficient_rest_alert():
    worker = Worker(
        id="w-fatigue-2",
        name="Rest Deficit Worker",
        phone="9999999902",
        pin_hash="dummy",
        site_id="site-1",
        role="Nurse",
        hourly_rate=180.0,
        passport_token="p2",
        created_at="2026-10-01T00:00:00Z"
    )
    site = Site(id="site-1", name="Hospital One", sector="hospital", location="Chennai")

    # Shift 1 ends at 2026-10-15 22:00
    # Shift 2 starts at 2026-10-16 04:00 -> Only 6 hours rest (< 8h threshold)
    shifts = [
        Shift(
            id="s-prev",
            worker_id="w-fatigue-2",
            site_id="site-1",
            start_time="2026-10-15T10:00:00Z",
            end_time="2026-10-15T22:00:00Z",
            total_hours=12.0,
            regular_hours=12.0,
            overtime_hours=0.0,
            status="completed"
        ),
        Shift(
            id="s-next",
            worker_id="w-fatigue-2",
            site_id="site-1",
            start_time="2026-10-16T04:00:00Z",
            end_time="2026-10-16T16:00:00Z",
            total_hours=12.0,
            regular_hours=12.0,
            overtime_hours=0.0,
            status="completed"
        )
    ]

    alerts = detect_fatigue_alerts([worker], [site], shifts)
    rest_alerts = [a for a in alerts if a.alert_type == "insufficient_rest"]
    assert len(rest_alerts) == 1
    assert rest_alerts[0].measured_value == 6.0
    assert rest_alerts[0].threshold_value == 8.0
    assert rest_alerts[0].severity == "critical"
