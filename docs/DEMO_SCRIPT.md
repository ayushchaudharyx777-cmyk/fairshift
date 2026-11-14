# FairShift Demo Video Script (target 4:00, limit 3–5 min)

**Story:** *Ramesh, a scaffolder in Chennai, works 11 hours, spots a loose clamp, and suspects he was underpaid.*

| Time | Screen | Say (suggested) |
| :--- | :--- | :--- |
| 0:00–0:20 | Landing page | "Shift workers lose pay, safety and credentials. FairShift protects all three, aligned to UN SDG 8." |
| 0:20–0:55 | Worker app → check in / out | "Ramesh checks in. After 11 hours, FairShift automatically splits regular and 2x overtime hours. Fatigue warning appears." |
| 0:55–1:30 | Payslip tab | "Transparent payslip: base, 2x overtime, PF, ESI. Tamil/Hindi voice explanation for low-literacy workers." |
| 1:30–2:10 | **Wage Theft Check** | "His employer paid ₹X. He enters it. FairShift shows he is short by ₹Y and flags *overtime paid at 1x instead of 2x*." |
| 2:10–2:50 | **Photo hazard** | "He photographs the loose clamp. Gemini Vision classifies severity and the site engineer is alerted instantly." (show a pre-tested photo) |
| 2:50–3:15 | Offline demo (airplane mode) | "No signal on site? The report is saved on the phone and sent automatically when network returns." |
| 3:15–3:50 | Admin dashboard | "Live alert, Kanban, fatigue table, **Integrity: Verified**: reports are hash-chained, so a contractor cannot quietly delete or downgrade them. Impact calculator shows scale." |
| 3:50–4:00 | Closing slide | "Open source, tested, deployed. Next: pilot with a contractor/NGO." |

## Recording checklist
- Wake Render 2 minutes before (open `/health`); UptimeRobot keeps it warm.
- Pre-test 2–3 hazard photos with the real `GEMINI_API_KEY`; keep the best one.
- Log in as **Rajesh (9876543210 / 1234)**; admin PIN **4821** in a second tab.
- Record at 1080p; mention the live URL and GitHub repo on the last frame.
- Do **not** show API keys or env vars.
