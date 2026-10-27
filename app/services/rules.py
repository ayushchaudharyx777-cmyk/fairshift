from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class SectorRule:
    sector_id: str
    name: str
    standard_shift_hours: float
    overtime_multiplier: float
    base_hourly_rate: float
    description: str


SECTOR_RULES: Dict[str, SectorRule] = {
    "construction": SectorRule(
        sector_id="construction",
        name="Construction Sector",
        standard_shift_hours=8.0,
        overtime_multiplier=2.0,
        base_hourly_rate=150.0,  # INR/hr
        description="Standard 8-hour daily limit. All hours exceeding 8h paid at 2x overtime rate."
    ),
    "hospital": SectorRule(
        sector_id="hospital",
        name="Healthcare / Hospital Sector",
        standard_shift_hours=12.0,
        overtime_multiplier=2.0,
        base_hourly_rate=180.0,  # INR/hr
        description="Standard 12-hour rotational shift. All hours exceeding 12h paid at 2x overtime rate."
    )
}

# Fatigue Violation Thresholds (aligned with ILO & UN SDG 8 Decent Work Guidelines)
FATIGUE_DAILY_MAX_HOURS = 10.0      # > 10h per day
FATIGUE_WEEKLY_MAX_HOURS = 60.0     # > 60h per week
FATIGUE_MIN_REST_HOURS = 8.0        # < 8h rest between consecutive shifts

# Deductions
PF_PERCENTAGE = 0.12                # 12% Employee Provident Fund on base earnings
ESI_PERCENTAGE = 0.0075             # 0.75% Employee State Insurance on gross earnings


def get_sector_rule(sector: str) -> SectorRule:
    sector_key = sector.lower().strip()
    if sector_key in SECTOR_RULES:
        return SECTOR_RULES[sector_key]
    # Default to construction if unknown
    return SECTOR_RULES["construction"]
