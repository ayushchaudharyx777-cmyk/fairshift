import secrets
from datetime import datetime, timedelta, timezone
from app.models import (
    Site, Worker, Shift, SafetyReport, AnonymousFeedback, SkillPassport,
    TrainingRecord, PastEmployer, ExperienceItem
)
from app.repository import InMemoryRepository
from app.security import hash_pin
from app.services.payroll import calculate_shift_hours


def seed_database(repo: InMemoryRepository):
    # Clear existing state
    repo.sites.clear()
    repo.workers.clear()
    repo.shifts.clear()
    repo.safety_reports.clear()
    repo.feedbacks.clear()
    repo.passports.clear()
    repo.worker_to_passport.clear()

    # 1. Sites
    site_const = Site(
        id="site-construction",
        name="Skyline Construction Site, Chennai",
        sector="construction",
        location="OMR IT Corridor, Sholinganallur, Chennai"
    )
    site_hosp = Site(
        id="site-hospital",
        name="City Care Hospital, Chennai",
        sector="hospital",
        location="Anna Salai, Teynampet, Chennai"
    )
    repo.sites[site_const.id] = site_const
    repo.sites[site_hosp.id] = site_hosp

    default_pin_hash = hash_pin("1234")

    # 2. Workers (8 realistic Indian names, 4 per sector)
    workers_data = [
        # Construction
        ("w-1", "Rajesh Kumar", "9876543210", "site-construction", "Master Mason & Scaffolder", 160.0, "pass-rajesh-k892"),
        ("w-2", "Suresh Murugan", "9876543211", "site-construction", "Steel Fixer & Rigger", 155.0, "pass-suresh-m510"),
        ("w-3", "Amit Patel", "9876543212", "site-construction", "Concrete Finisher", 150.0, "pass-amit-p331"),
        ("w-4", "Karthik Subramanian", "9876543213", "site-construction", "Tower Crane Operator", 190.0, "pass-karthik-s742"),
        # Hospital
        ("w-5", "Priya Sharma", "9876543220", "site-hospital", "Emergency Ward Nurse", 185.0, "pass-priya-s419"),
        ("w-6", "Ananya Iyer", "9876543221", "site-hospital", "ICU Specialist Care Assistant", 190.0, "pass-ananya-i628"),
        ("w-7", "Lakshmi Devi", "9876543222", "site-hospital", "Patient Care Attendant", 165.0, "pass-lakshmi-d105"),
        ("w-8", "Deepa Nair", "9876543223", "site-hospital", "Surgical OT Technician", 200.0, "pass-deepa-n984"),
    ]

    for wid, name, phone, site_id, role, rate, token in workers_data:
        worker = Worker(
            id=wid,
            name=name,
            phone=phone,
            pin_hash=default_pin_hash,
            site_id=site_id,
            role=role,
            hourly_rate=rate,
            passport_token=token,
            created_at=datetime.now(timezone.utc).isoformat()
        )
        repo.workers[worker.id] = worker

    # 3. Two weeks of shifts with Overtime and Fatigue cases
    now = datetime.now(timezone.utc)
    shift_counter = 1

    # Base helper to create completed shift
    def add_completed_shift(wid, site_id, sector, start_dt, hours, notes=None):
        nonlocal shift_counter
        end_dt = start_dt + timedelta(hours=hours)
        start_iso = start_dt.isoformat()
        end_iso = end_dt.isoformat()
        tot, reg, ot = calculate_shift_hours(start_iso, end_iso, sector)
        s = Shift(
            id=f"shift-{shift_counter:03d}",
            worker_id=wid,
            site_id=site_id,
            start_time=start_iso,
            end_time=end_iso,
            total_hours=tot,
            regular_hours=reg,
            overtime_hours=ot,
            status="completed",
            notes=notes
        )
        repo.add_shift(s)
        shift_counter += 1

    # Populate 14 days of shifts
    for day_offset in range(13, 0, -1):
        shift_date = (now - timedelta(days=day_offset)).replace(hour=8, minute=0, second=0, microsecond=0)
        
        # Rajesh Kumar (Construction): Standard 8h, but on day 4 had an exhausting 13h shift (FATIGUE: >10h/day)
        if day_offset == 4:
            add_completed_shift("w-1", "site-construction", "construction", shift_date, 13.0, "Emergency slab pouring overtime")
        elif day_offset % 7 != 0:  # 6 days a week
            add_completed_shift("w-1", "site-construction", "construction", shift_date, 8.5, "Standard construction shift + 0.5h OT")

        # Suresh Murugan (Construction): Heavy overtime in week 1 totaling >62h (FATIGUE: >60h/week)
        if day_offset in [13, 12, 11, 10, 9, 8]:
            add_completed_shift("w-2", "site-construction", "construction", shift_date, 10.5, "Fast-track foundation steel reinforcement")
        elif day_offset in [6, 5, 4, 3, 2]:
            add_completed_shift("w-2", "site-construction", "construction", shift_date, 8.0, "Regular rebar assembly")

        # Amit Patel (Construction): Consistent shifts
        if day_offset not in [1, 7]:
            add_completed_shift("w-3", "site-construction", "construction", shift_date, 9.0, "Finishing works")

        # Karthik Subramanian (Construction - Crane):
        if day_offset % 2 == 0:
            add_completed_shift("w-4", "site-construction", "construction", shift_date, 8.0, "Tower crane hoisting")

        # Priya Sharma (Hospital - Nurse): 12h hospital shifts.
        # Fatigue scenario: On day 3 ended shift at 20:00, and next shift on day 2 started at 02:00 (only 6h rest! FATIGUE: <8h rest)
        if day_offset in [12, 10, 8, 6]:
            hosp_start = (now - timedelta(days=day_offset)).replace(hour=7, minute=0, second=0, microsecond=0)
            add_completed_shift("w-5", "site-hospital", "hospital", hosp_start, 12.0, "Emergency daytime rotation")
        elif day_offset == 3:
            hosp_start = (now - timedelta(days=day_offset)).replace(hour=8, minute=0, second=0, microsecond=0)
            add_completed_shift("w-5", "site-hospital", "hospital", hosp_start, 12.0, "Day emergency shift")
        elif day_offset == 2:
            # Starts only 6 hours after previous shift ended!
            hosp_start = (now - timedelta(days=day_offset)).replace(hour=2, minute=0, second=0, microsecond=0)
            add_completed_shift("w-5", "site-hospital", "hospital", hosp_start, 12.5, "Urgent night trauma coverage")

        # Ananya Iyer (Hospital - ICU):
        if day_offset in [11, 9, 7, 5, 3]:
            hosp_start = (now - timedelta(days=day_offset)).replace(hour=19, minute=0, second=0, microsecond=0)
            add_completed_shift("w-6", "site-hospital", "hospital", hosp_start, 13.0, "ICU night shift with 1h critical handover")

        # Lakshmi Devi & Deepa Nair:
        if day_offset in [10, 8, 5, 2]:
            add_completed_shift("w-7", "site-hospital", "hospital", shift_date.replace(hour=8), 12.0, "General ward care")
        if day_offset in [12, 9, 6, 3]:
            add_completed_shift("w-8", "site-hospital", "hospital", shift_date.replace(hour=9), 12.0, "OT surgical support")

    # Add 1 active ongoing shift for Rajesh Kumar started 2.5 hours ago so live check-in is active
    active_start = (now - timedelta(hours=2, minutes=34)).isoformat()
    repo.add_shift(
        Shift(
            id=f"shift-{shift_counter:03d}",
            worker_id="w-1",
            site_id="site-construction",
            start_time=active_start,
            end_time=None,
            total_hours=0.0,
            regular_hours=0.0,
            overtime_hours=0.0,
            status="active",
            notes="Morning structural scaffolding installation"
        )
    )

    # 4. Seeded Safety Reports
    reports_seed = [
        (
            "rep-001", "site-construction", "w-1", "Rajesh Kumar",
            "Scaffolding clamps are loose on 4th floor external lift shaft near Tower B. Vibration causes movement.",
            "hazard", "critical",
            "Loose scaffolding clamps identified on 4th floor external lift shaft causing structural instability.",
            "4வது மாடி வெளிப்புற லிப்ட் ஷாஃப்ட்டில் சாரக்கட்டு கிளாம்புகள் தளர்வாக உள்ளன. உடனடியாக சரிசெய்ய வேண்டும்.",
            "Reported", (now - timedelta(hours=3)).isoformat()
        ),
        (
            "rep-002", "site-hospital", "w-5", "Priya Sharma",
            "Biohazard sharps container overflowing in Emergency Triage Room. Need immediate safe disposal.",
            "hazard", "critical",
            "Overflowing biohazard sharps container poses immediate needle-stick and infection hazard in triage.",
            "அவசர சிகிச்சை பிரிவில் ஊசி மற்றும் கூர்மையான கழிவு பெட்டி நிரம்பி வழிகிறது. உடனடியாக மாற்ற வேண்டும்.",
            "Acknowledged", (now - timedelta(hours=14)).isoformat()
        ),
        (
            "rep-003", "site-construction", "w-2", "Suresh Murugan",
            "Water accumulation and slippery mud near main electrical distribution board on ground level.",
            "hazard", "high",
            "Stagnant water near high-voltage electrical distribution board posing electrocution and slip risk.",
            "मेन इलेक्ट्रिकल बोर्ड के पास पानी भरा हुआ है, जिससे करंट और फिसलने का भारी खतरा है।",
            "Acknowledged", (now - timedelta(days=1, hours=4)).isoformat()
        ),
        (
            "rep-004", "site-hospital", "w-6", "Ananya Iyer",
            "N95 respirator masks and sterile gloves critically low in Isolation Ward 3.",
            "ppe", "high",
            "Depleted inventory of N95 masks and sterile gloves in infectious isolation ward.",
            "ஐசோலேஷன் வார்டு 3-ல் N95 முகக்கவசங்கள் மற்றும் கையுறைகள் கையிருப்பு தீர்ந்துவிட்டது.",
            "Reported", (now - timedelta(hours=6)).isoformat()
        ),
        (
            "rep-005", "site-construction", "w-3", "Amit Patel",
            "Broken handrail on temporary staircase leading to basement parking level.",
            "equipment", "medium",
            "Handrail broken on temporary access staircase leading to lower basement.",
            "बेसमेंट जाने वाली सीढ़ी की रेलिंग टूट गई है।",
            "Resolved", (now - timedelta(days=3)).isoformat()
        ),
        (
            "rep-006", "site-hospital", "w-7", "Lakshmi Devi",
            "Wheelchair brake mechanism slipping on patient transfer ramp.",
            "equipment", "low",
            "Defective brake on transport wheelchair slipping during ramp transfers.",
            "நோயாளி சக்கர நாற்காலியின் பிரேக் சரியாக இயங்கவில்லை.",
            "Resolved", (now - timedelta(days=5)).isoformat()
        ),
    ]

    for rid, sid, wid, wname, inp, cat, sev, sum_en, sum_loc, status, created in reports_seed:
        repo.add_safety_report(
            SafetyReport(
                id=rid,
                site_id=sid,
                worker_id=wid,
                worker_name=wname,
                input_text=inp,
                category=cat,
                severity=sev,
                summary_en=sum_en,
                summary_local=sum_loc,
                status=status,
                created_at=created,
                resolved_at=(now - timedelta(days=1)).isoformat() if status == "Resolved" else None
            )
        )

    # 5. Seeded Anonymous Feedback (CRITICAL: ZERO worker_id stored)
    dt_now = datetime.now(timezone.utc)
    iso_year, iso_week, _ = dt_now.isocalendar()
    current_iso_week = f"{iso_year}-W{iso_week:02d}"

    feedbacks_seed = [
        ("site-construction", current_iso_week, 4, 4, "Supervisor provides adequate drinking water breaks under hot sun. Need better dust masks.", (now - timedelta(days=2)).isoformat()),
        ("site-construction", current_iso_week, 5, 5, "Overtime calculations are transparent and fair under FairShift. Very encouraging.", (now - timedelta(days=1)).isoformat()),
        ("site-construction", current_iso_week, 3, 3, "Scaffolding safety inspections should happen every morning without rush.", (now - timedelta(hours=10)).isoformat()),
        ("site-hospital", current_iso_week, 5, 4, "Manager ensures nursing shift rotations are respected. Great team spirit in emergency.", (now - timedelta(days=2)).isoformat()),
        ("site-hospital", current_iso_week, 4, 5, "Clean sanitization stations and dignified rest areas during 12h shifts.", (now - timedelta(days=1)).isoformat()),
        ("site-hospital", current_iso_week, 3, 2, "Need more staff during night shift handovers to avoid acute fatigue.", (now - timedelta(hours=5)).isoformat()),
    ]

    for sid, iweek, m_rate, c_rate, comm, created in feedbacks_seed:
        repo.add_feedback(
            AnonymousFeedback(
                id=f"fb-{secrets.token_hex(4)}",
                site_id=sid,
                iso_week=iweek,
                manager_rating=m_rate,
                conditions_rating=c_rate,
                comment=comm,
                created_at=created
            )
        )

    # 6. Seeded Skill Passports for all 8 workers
    passports_seed = [
        {
            "worker_id": "w-1",
            "token": "pass-rajesh-k892",
            "name": "Rajesh Kumar",
            "role": "Master Mason & Scaffolder",
            "site": "Skyline Construction Site, Chennai",
            "sector": "construction",
            "badges": ["OSHA 30h Certified", "Safe Working at Heights", "SDG-8 Decent Work Verified", "Zero Incident Record 2025"],
            "skills": ["Heavy Tubular Scaffolding", "Precision Brick & Stone Masonry", "Site Hazard Assessment", "Rigging Safety", "Team Lead"],
            "trainings": [
                TrainingRecord(title="Advanced Scaffolding Safety & Fall Arrest", issued_by="National Safety Council of India", date="2024-03-15", valid_until="2027-03-15"),
                TrainingRecord(title="Emergency First Aid & CPR at Height", issued_by="St. John Ambulance India", date="2024-08-10", valid_until="2026-08-10"),
                TrainingRecord(title="Decent Work & Fair Labor Rights (UN SDG 8)", issued_by="FairShift Foundation", date="2025-01-10", valid_until="2028-01-10")
            ],
            "employers": [
                PastEmployer(company="Skyline Infrastructure Ltd", role="Lead Scaffolder", period="2023 - Present", verified=True),
                PastEmployer(company="L&T Construction Chennai", role="Senior Mason", period="2020 - 2023", verified=True),
                PastEmployer(company="Shapoorji Pallonji EPC", role="Apprentice Mason", period="2018 - 2020", verified=True)
            ],
            "timeline": [
                ExperienceItem(year="2025", title="Master Scaffolder Appointment", description="Promoted to Lead Scaffold Inspector for 40-storey residential tower."),
                ExperienceItem(year="2023", title="Zero Lost-Time Injury Citation", description="Awarded site excellence for completing 500,000 safe worker-hours."),
                ExperienceItem(year="2020", title="Certified Heights Specialist", description="Completed NSCI certification with grade A distinction.")
            ]
        },
        {
            "worker_id": "w-5",
            "token": "pass-priya-s419",
            "name": "Priya Sharma",
            "role": "Emergency Ward Nurse",
            "site": "City Care Hospital, Chennai",
            "sector": "hospital",
            "badges": ["Registered Nurse (INC)", "BLS / ACLS Certified", "Infection Control Specialist", "SDG-8 Decent Work Verified"],
            "skills": ["Triage Rapid Assessment", "Critical IV Cannulation", "Trauma Care Protocols", "Patient Advocacy", "Multilingual Communication"],
            "trainings": [
                TrainingRecord(title="Advanced Cardiac Life Support (ACLS)", issued_by="American Heart Association / Apollo", date="2024-01-20", valid_until="2026-01-20"),
                TrainingRecord(title="Hospital Infection Control & Biohazard Protocol", issued_by="Tamil Nadu Nursing Council", date="2024-06-12", valid_until="2027-06-12"),
                TrainingRecord(title="Fatigue Mitigation & Shift Worker Wellbeing", issued_by="FairShift Health Initiative", date="2025-02-01", valid_until="2028-02-01")
            ],
            "employers": [
                PastEmployer(company="City Care Hospital, Chennai", role="Staff Nurse - Emergency", period="2022 - Present", verified=True),
                PastEmployer(company="Fortis Malar Hospital, Chennai", role="Junior Nurse - Medical Ward", period="2019 - 2022", verified=True)
            ],
            "timeline": [
                ExperienceItem(year="2024", title="Emergency Triage Lead", description="Handled acute trauma coordination during Chennai monsoon relief operations."),
                ExperienceItem(year="2022", title="Joined City Care Trauma Center", description="Deployed as specialized 12h emergency shift lead."),
                ExperienceItem(year="2019", title="Graduated B.Sc Nursing", description="First class with distinction from Madras Medical College.")
            ]
        }
    ]

    # Add passports for remaining workers
    remaining_workers = [
        ("w-2", "pass-suresh-m510", "Suresh Murugan", "Steel Fixer & Rigger", "Skyline Construction Site, Chennai", "construction",
         ["Heavy Rebar Certified", "Welding Level 2"], ["Steel Binding", "Blueprint Interpretation", "Rigging Safety"]),
        ("w-3", "pass-amit-p331", "Amit Patel", "Concrete Finisher", "Skyline Construction Site, Chennai", "construction",
         ["Surface Finishing Expert", "Chemical Admixture Safety"], ["Screeding", "Power Troweling", "Joint Sealing"]),
        ("w-4", "pass-karthik-s742", "Karthik Subramanian", "Tower Crane Operator", "Skyline Construction Site, Chennai", "construction",
         ["Heavy Crane License", "Radio Signal Specialist"], ["High-Rise Hoisting", "Wind Load Calculation", "Equipment Pre-Check"]),
        ("w-6", "pass-ananya-i628", "Ananya Iyer", "ICU Specialist Care Assistant", "City Care Hospital, Chennai", "hospital",
         ["ICU Care Certified", "Ventilator Support"], ["Patient Monitoring", "Arterial Line Assistance", "Vital Tracking"]),
        ("w-7", "pass-lakshmi-d105", "Lakshmi Devi", "Patient Care Attendant", "City Care Hospital, Chennai", "hospital",
         ["Dignified Patient Care", "Mobility Assistance"], ["Bedside Care", "Vital Sign Checks", "Compassionate Support"]),
        ("w-8", "pass-deepa-n984", "Deepa Nair", "Surgical OT Technician", "City Care Hospital, Chennai", "hospital",
         ["Sterile Processing Lead", "Laparoscopy Assistant"], ["Autoclave Operation", "Surgical Tray Prep", "Aseptic Field Maintenance"]),
    ]

    for wid, tok, wname, role, site_name, sec, badges, skills in remaining_workers:
        initials = "".join([part[0] for part in wname.split()[:2]]).upper()
        p = SkillPassport(
            token=tok,
            worker_id=wid,
            worker_name=wname,
            role=role,
            site_name=site_name,
            sector=sec,
            avatar_initials=initials,
            verified_badges=badges + ["FairShift Verified"],
            skills=skills,
            trainings=[
                TrainingRecord(title="Workplace Safety & Ergonomics", issued_by="FairShift Foundation", date="2024-05-10", valid_until="2027-05-10")
            ],
            past_employers=[
                PastEmployer(company=site_name, role=role, period="2023 - Present", verified=True)
            ],
            experience_timeline=[
                ExperienceItem(year="2024", title="Core Competency Endorsement", description=f"Recognized for outstanding adherence to safety in {sec}.")
            ],
            qr_data=f"fairshift://passport/{tok}"
        )
        repo.add_passport(p)

    for item in passports_seed:
        initials = "".join([part[0] for part in item["name"].split()[:2]]).upper()
        p = SkillPassport(
            token=item["token"],
            worker_id=item["worker_id"],
            worker_name=item["name"],
            role=item["role"],
            site_name=item["site"],
            sector=item["sector"],
            avatar_initials=initials,
            verified_badges=item["badges"],
            skills=item["skills"],
            trainings=item["trainings"],
            past_employers=item["employers"],
            experience_timeline=item["timeline"],
            qr_data=f"fairshift://passport/{item['token']}"
        )
        repo.add_passport(p)
