from datetime import datetime
from typing import List, Tuple, Dict, Any
from app.models import Shift, Worker, Site, Payslip, PayslipLineItem
from app.services.rules import (
    get_sector_rule,
    PF_PERCENTAGE,
    ESI_PERCENTAGE
)


def calculate_shift_hours(start_iso: str, end_iso: str, sector: str) -> Tuple[float, float, float]:
    """
    Calculate (total_hours, regular_hours, overtime_hours) for a given shift.
    Sector rules:
      - Construction: 8h standard, remainder overtime.
      - Hospital: 12h standard, remainder overtime.
    """
    start_dt = datetime.fromisoformat(start_iso)
    end_dt = datetime.fromisoformat(end_iso)
    total_seconds = max(0.0, (end_dt - start_dt).total_seconds())
    total_hours = round(total_seconds / 3600.0, 2)

    rule = get_sector_rule(sector)
    standard_limit = rule.standard_shift_hours

    if total_hours > standard_limit:
        regular_hours = standard_limit
        overtime_hours = round(total_hours - standard_limit, 2)
    else:
        regular_hours = total_hours
        overtime_hours = 0.0

    return total_hours, regular_hours, overtime_hours


def generate_payslip(worker: Worker, site: Site, shifts: List[Shift], period_start: str, period_end: str) -> Payslip:
    """
    Generate comprehensive payslip aggregating worker shifts with sector rules,
    overtime multipliers (2x), PF, and ESI deductions.
    """
    rule = get_sector_rule(site.sector)
    hourly_rate = worker.hourly_rate or rule.base_hourly_rate

    # Filter completed shifts for this worker
    worker_shifts = [s for s in shifts if s.worker_id == worker.id and s.status == "completed"]
    
    total_shifts = len(worker_shifts)
    regular_hours = round(sum(s.regular_hours for s in worker_shifts), 2)
    overtime_hours = round(sum(s.overtime_hours for s in worker_shifts), 2)
    total_hours = round(regular_hours + overtime_hours, 2)

    base_pay = round(regular_hours * hourly_rate, 2)
    overtime_rate = hourly_rate * rule.overtime_multiplier  # 2x multiplier
    overtime_pay = round(overtime_hours * overtime_rate, 2)
    gross_pay = round(base_pay + overtime_pay, 2)

    pf_deduction = round(base_pay * PF_PERCENTAGE, 2)
    esi_deduction = round(gross_pay * ESI_PERCENTAGE, 2)
    total_deductions = round(pf_deduction + esi_deduction, 2)
    net_pay = round(gross_pay - total_deductions, 2)

    # Donut data for pure-SVG rendering
    # Represent Base Pay, Overtime Pay, and Net Deductions
    donut_total = gross_pay if gross_pay > 0 else 1.0
    base_pct = round((base_pay / donut_total) * 100, 1)
    ot_pct = round((overtime_pay / donut_total) * 100, 1)
    ded_pct = round((total_deductions / donut_total) * 100, 1)

    donut_data = {
        "base_pay": base_pay,
        "base_pct": base_pct,
        "overtime_pay": overtime_pay,
        "overtime_pct": ot_pct,
        "total_deductions": total_deductions,
        "deductions_pct": ded_pct,
        "gross_pay": gross_pay,
        "net_pay": net_pay
    }

    line_items = [
        PayslipLineItem(
            label="Base Regular Earnings",
            rate_or_units=f"{regular_hours} hrs @ ₹{hourly_rate:.0f}/hr",
            amount=base_pay,
            type="earning"
        ),
        PayslipLineItem(
            label=f"Overtime Premium ({rule.overtime_multiplier:.0f}x Fair Wage)",
            rate_or_units=f"{overtime_hours} hrs @ ₹{overtime_rate:.0f}/hr",
            amount=overtime_pay,
            type="earning"
        ),
        PayslipLineItem(
            label="Provident Fund (PF 12%)",
            rate_or_units="Statutory Retirement Savings",
            amount=-pf_deduction,
            type="deduction"
        ),
        PayslipLineItem(
            label="Employee State Insurance (ESI 0.75%)",
            rate_or_units="Statutory Health Coverage",
            amount=-esi_deduction,
            type="deduction"
        ),
        PayslipLineItem(
            label="Net Take-Home Pay",
            rate_or_units="Direct Bank / Cash Disbursal",
            amount=net_pay,
            type="summary"
        )
    ]

    return Payslip(
        worker_id=worker.id,
        worker_name=worker.name,
        site_name=site.name,
        sector=site.sector,
        period_start=period_start,
        period_end=period_end,
        total_shifts=total_shifts,
        regular_hours=regular_hours,
        overtime_hours=overtime_hours,
        total_hours=total_hours,
        hourly_rate=hourly_rate,
        base_pay=base_pay,
        overtime_pay=overtime_pay,
        gross_pay=gross_pay,
        pf_deduction=pf_deduction,
        esi_deduction=esi_deduction,
        total_deductions=total_deductions,
        net_pay=net_pay,
        donut_data=donut_data,
        line_items=line_items
    )
