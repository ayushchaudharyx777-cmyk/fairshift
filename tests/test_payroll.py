import pytest
from app.services.payroll import calculate_shift_hours, generate_payslip
from app.models import Worker, Site, Shift


def test_construction_shift_hours_overtime():
    # Construction standard is 8h
    start = "2026-10-20T08:00:00+00:00"
    end = "2026-10-20T18:30:00+00:00"  # 10.5 hours
    total, regular, overtime = calculate_shift_hours(start, end, "construction")
    assert total == 10.5
    assert regular == 8.0
    assert overtime == 2.5


def test_hospital_shift_hours_overtime():
    # Hospital standard is 12h
    start = "2026-10-20T07:00:00+00:00"
    end = "2026-10-20T21:00:00+00:00"  # 14 hours
    total, regular, overtime = calculate_shift_hours(start, end, "hospital")
    assert total == 14.0
    assert regular == 12.0
    assert overtime == 2.0


def test_standard_shift_without_overtime():
    start = "2026-10-20T08:00:00+00:00"
    end = "2026-10-20T16:00:00+00:00"  # 8 hours
    total, regular, overtime = calculate_shift_hours(start, end, "construction")
    assert total == 8.0
    assert regular == 8.0
    assert overtime == 0.0


def test_payslip_calculation_and_overtime_multiplier():
    worker = Worker(
        id="test-w1",
        name="Test Worker",
        phone="9999999999",
        pin_hash="dummy_hash",
        site_id="site-construction",
        role="Mason",
        hourly_rate=150.0,
        passport_token="pass-test-1",
        created_at="2026-10-01T00:00:00Z"
    )
    site = Site(
        id="site-construction",
        name="Test Construction",
        sector="construction",
        location="Chennai"
    )

    shifts = [
        # Shift 1: 10h -> 8h reg, 2h OT
        Shift(
            id="s1",
            worker_id="test-w1",
            site_id="site-construction",
            start_time="2026-10-10T08:00:00Z",
            end_time="2026-10-10T18:00:00Z",
            total_hours=10.0,
            regular_hours=8.0,
            overtime_hours=2.0,
            status="completed"
        ),
        # Shift 2: 8h -> 8h reg, 0h OT
        Shift(
            id="s2",
            worker_id="test-w1",
            site_id="site-construction",
            start_time="2026-10-11T08:00:00Z",
            end_time="2026-10-11T16:00:00Z",
            total_hours=8.0,
            regular_hours=8.0,
            overtime_hours=0.0,
            status="completed"
        )
    ]

    payslip = generate_payslip(worker, site, shifts, "2026-10-01", "2026-10-14")

    # Regular hours: 8 + 8 = 16h
    # Overtime hours: 2h
    assert payslip.regular_hours == 16.0
    assert payslip.overtime_hours == 2.0
    assert payslip.total_hours == 18.0

    # Base pay: 16h * 150 = 2400
    assert payslip.base_pay == 2400.0

    # Overtime pay: 2h * (150 * 2) = 600 (guaranteed 2x multiplier)
    assert payslip.overtime_pay == 600.0

    # Gross pay: 2400 + 600 = 3000
    assert payslip.gross_pay == 3000.0

    # PF (12% of base pay 2400) = 288.0
    assert payslip.pf_deduction == 288.0

    # ESI (0.75% of gross pay 3000) = 22.5
    assert payslip.esi_deduction == 22.5

    # Total deductions: 288.0 + 22.5 = 310.5
    assert payslip.total_deductions == 310.5

    # Net pay: 3000 - 310.5 = 2689.5
    assert payslip.net_pay == 2689.5
    assert len(payslip.line_items) == 5
    assert payslip.donut_data["gross_pay"] == 3000.0
