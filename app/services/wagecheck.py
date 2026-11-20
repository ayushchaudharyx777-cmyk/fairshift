"""Wage Theft Detective: compare what a worker was actually paid with the legal payslip."""
from typing import Optional
from app.models import Payslip, WageCheckResponse
from app.services.rules import ESI_PERCENTAGE, get_sector_rule

TOLERANCE_INR = 1.0  # ignore rounding differences

LEGAL_NOTE = (
    "Indicative check against FairShift sector rules (OT at 2x, PF 12%, ESI 0.75%). "
    "Not legal advice; raise any shortfall with your supervisor or a labour office."
)


def _likely_cause(payslip: Payslip, shortfall: float, multiplier: float) -> Optional[str]:
    """Heuristic: does the gap match a common wage-theft pattern?"""
    if shortfall <= TOLERANCE_INR:
        return None
    if payslip.overtime_hours > 0:
        # OT paid at 1x instead of the legal multiplier loses (m-1)/m of the OT pay
        ot_premium_lost = payslip.overtime_pay * (multiplier - 1) / multiplier
        ot_premium_lost_net = ot_premium_lost * (1 - ESI_PERCENTAGE)  # ESI is on gross
        if abs(shortfall - ot_premium_lost_net) <= max(50.0, 0.05 * shortfall):
            return f"Overtime looks paid at 1x instead of {multiplier:.0f}x"
        if abs(shortfall - payslip.overtime_pay * (1 - ESI_PERCENTAGE)) <= max(50.0, 0.05 * shortfall):
            return "Overtime hours look unpaid"
    if payslip.pf_deduction > 0 and abs(shortfall - payslip.pf_deduction) <= 50.0:
        return "PF may have been deducted twice or not credited"
    if shortfall > 0.5 * payslip.net_pay:
        return "More than half of earnings missing; check hours recorded"
    return "Unexplained deduction; ask for an itemised payslip"


def check_wage_theft(payslip: Payslip, paid_amount: float) -> WageCheckResponse:
    rule = get_sector_rule(payslip.sector)
    expected = round(payslip.net_pay, 2)
    paid = round(paid_amount, 2)
    diff = round(expected - paid, 2)

    if diff > TOLERANCE_INR:
        verdict, shortfall = "underpaid", diff
    elif diff < -TOLERANCE_INR:
        verdict, shortfall = "overpaid", 0.0
    else:
        verdict, shortfall = "fair", 0.0

    pct = round((shortfall / expected) * 100, 1) if expected > 0 else 0.0
    return WageCheckResponse(
        verdict=verdict,
        expected_net=expected,
        paid_amount=paid,
        shortfall=shortfall,
        shortfall_percent=pct,
        likely_cause=_likely_cause(payslip, shortfall, rule.overtime_multiplier),
        legal_note=LEGAL_NOTE,
        breakdown={
            "regular_hours": payslip.regular_hours,
            "overtime_hours": payslip.overtime_hours,
            "hourly_rate": payslip.hourly_rate,
            "overtime_multiplier": rule.overtime_multiplier,
            "gross_pay": payslip.gross_pay,
            "total_deductions": payslip.total_deductions,
        },
    )
