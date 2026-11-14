# FairShift: Labour Law Mapping (Indicative)

> **Indicative, not legal advice.** Verified against public summaries of the Labour Codes (in force since
> **21 November 2025**). Central/State rules are still being finalised, so confirm section numbers and
> thresholds with a labour-law professional before relying on them commercially.

| FairShift rule / feature | What it implements | Legal anchor (indicative) |
| :--- | :--- | :--- |
| **2x overtime** (`app/services/rules.py`, payslip, Wage Theft Detective) | Hours beyond normal working hours are paid at **not less than twice** the normal wage rate | **Code on Wages, 2019, Section 14** (overtime wages) |
| **Wage Theft Detective** | Detects when amount paid is below the legally expected pay, e.g. OT paid at 1x | Code on Wages, 2019: Section 14 (OT), Section 17 (timely payment), Section 18 (permitted deductions) |
| **Itemised, transparent payslip** | Shows regular pay, OT, PF and ESI separately | Code on Wages, 2019 (records and wage payment provisions); Code on Social Security, 2020 (PF / ESI contributions) |
| **Fatigue engine** (>10h/day, >60h/week, <8h rest) | Prevents unsafe long shifts and short rest gaps | Occupational Safety, Health and Working Conditions (OSH) Code, 2020 (working hours, rest, safety). **The numeric limits are FairShift safety thresholds aligned with ILO guidance, not quotations of statute.** |
| **Voice / photo hazard reports + Kanban** | Gives workers a low-literacy channel to report unsafe conditions; tracks resolution | OSH Code, 2020 (safe working environment, employer duty to address hazards) |
| **Tamper-proof safety log** | Evidence of a report cannot be silently edited or deleted | Supports employer accountability and inspections under the OSH Code |
| **Anonymous feedback** | Workers can raise concerns without identity stored | Supports retaliation protection and fair workplace principles |

## Gaps and honest notes
- **Sector shift lengths (8h construction, 12h hospital)** are FairShift's configurable sector defaults, not a single statutory number. Actual normal hours depend on the applicable Act/Rules, notification and state.
- **Overtime consent:** under the new Codes, overtime is reported to be allowed only with the worker's consent. FairShift does not yet record that consent. Planned future scope: an explicit "I agree to this overtime" step at check-out.
- **Quarterly overtime cap:** some commentary mentions a cap (e.g. 144 hours per quarter) coming from rules. Not enforced here; verify against the final notified rules before adding.
- **PF 12% / ESI 0.75%** are the employee-side rates used in the demo; real contributions depend on wage ceilings, establishment coverage and state rules.
- **Statutes subsumed:** the Codes consolidate earlier laws (e.g. Payment of Wages Act 1936, Minimum Wages Act 1948 under the Wage Code). Older references to those Acts are superseded.
