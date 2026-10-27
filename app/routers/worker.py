import secrets
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Response
from app.models import (
    WorkerLoginRequest, WorkerLoginResponse, Shift, CheckInRequest, CheckOutRequest,
    SafetyReportCreateRequest, SafetyReport, AnonymousFeedback, AnonymousFeedbackCreateRequest,
    ExplainPayslipRequest, ExplainPayslipResponse, Payslip, SkillPassport, FatigueAlert
)
from app.repository import InMemoryRepository, get_repository
from app.security import (
    verify_pin, create_worker_session_token, get_current_worker_id
)
from app.services.payroll import calculate_shift_hours, generate_payslip
from app.services.fatigue import check_worker_fatigue
from app.services.ai import triage_safety_report, explain_payslip

router = APIRouter(prefix="/api/v1/worker", tags=["Worker API"])


@router.post("/login", response_model=WorkerLoginResponse)
async def worker_login(payload: WorkerLoginRequest, response: Response, repo: InMemoryRepository = Depends(get_repository)) -> WorkerLoginResponse:
    """Authenticate worker via mobile phone and PIN, establishing HttpOnly session."""
    worker = repo.get_worker_by_phone(payload.phone)
    if not worker or not verify_pin(payload.pin, worker.pin_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid phone number or 4-digit PIN"
        )
    
    site = repo.get_site(worker.site_id)
    site_name = site.name if site else "Assigned Site"
    sector = site.sector if site else "construction"

    session_token = create_worker_session_token(worker.id)
    response.set_cookie(
        key="worker_session",
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=86400 * 7,
        secure=False  # Compatible with local dev and Cloud Run reverse proxy
    )

    return WorkerLoginResponse(
        worker_id=worker.id,
        name=worker.name,
        phone=worker.phone,
        site_id=worker.site_id,
        site_name=site_name,
        sector=sector,
        role=worker.role,
        hourly_rate=worker.hourly_rate,
        passport_token=worker.passport_token
    )


@router.post("/logout")
async def worker_logout(response: Response) -> Dict[str, str]:
    """Terminate authenticated worker session and clear cookie."""
    response.delete_cookie("worker_session")
    return {"status": "ok", "message": "Successfully logged out"}


@router.get("/me")
async def get_worker_me(
    worker_id: str = Depends(get_current_worker_id),
    repo: InMemoryRepository = Depends(get_repository)
) -> Dict[str, Any]:
    """Retrieve authenticated worker profile, active shift, and fatigue violations."""
    worker = repo.get_worker(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker profile not found")
    site = repo.get_site(worker.site_id)
    active_shift = repo.get_active_shift(worker.id)
    all_shifts = repo.get_shifts(worker_id=worker.id)
    fatigue_alerts = check_worker_fatigue(worker, site, all_shifts)

    return {
        "worker": worker,
        "site": site,
        "active_shift": active_shift,
        "fatigue_alerts": fatigue_alerts,
        "total_shifts_logged": len([s for s in all_shifts if s.status == "completed"])
    }


@router.post("/check-in", response_model=Shift)
async def check_in(
    payload: CheckInRequest,
    worker_id: str = Depends(get_current_worker_id),
    repo: InMemoryRepository = Depends(get_repository)
) -> Shift:
    """Start a new active work shift for authenticated worker."""
    worker = repo.get_worker(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    existing_active = repo.get_active_shift(worker_id)
    if existing_active:
        return existing_active

    site_id = payload.site_id or worker.site_id
    now_iso = datetime.now(timezone.utc).isoformat()
    shift_id = f"shift-{secrets.token_hex(4)}"

    shift = Shift(
        id=shift_id,
        worker_id=worker.id,
        site_id=site_id,
        start_time=now_iso,
        end_time=None,
        total_hours=0.0,
        regular_hours=0.0,
        overtime_hours=0.0,
        status="active",
        notes=payload.notes
    )
    repo.add_shift(shift)
    return shift


@router.post("/check-out", response_model=Shift)
async def check_out(
    payload: CheckOutRequest,
    worker_id: str = Depends(get_current_worker_id),
    repo: InMemoryRepository = Depends(get_repository)
) -> Shift:
    """End active shift, computing total, regular, and 2x overtime hours."""
    worker = repo.get_worker(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    active_shift = repo.get_active_shift(worker_id)
    if not active_shift:
        raise HTTPException(status_code=400, detail="No active shift found to check out")

    site = repo.get_site(active_shift.site_id)
    sector = site.sector if site else "construction"
    now_iso = datetime.now(timezone.utc).isoformat()

    tot, reg, ot = calculate_shift_hours(active_shift.start_time, now_iso, sector)
    active_shift.end_time = now_iso
    active_shift.total_hours = tot
    active_shift.regular_hours = reg
    active_shift.overtime_hours = ot
    active_shift.status = "completed"
    if payload.notes:
        active_shift.notes = f"{active_shift.notes or ''} | {payload.notes}".strip(" |")

    repo.update_shift(active_shift)
    return active_shift


@router.get("/shifts", response_model=List[Shift])
async def get_worker_shifts(
    worker_id: str = Depends(get_current_worker_id),
    repo: InMemoryRepository = Depends(get_repository)
) -> List[Shift]:
    """Retrieve full shift history for authenticated worker."""
    return repo.get_shifts(worker_id=worker_id)


@router.get("/payslip", response_model=Payslip)
async def get_worker_payslip(
    worker_id: str = Depends(get_current_worker_id),
    repo: InMemoryRepository = Depends(get_repository)
) -> Payslip:
    """Generate 14-day transparent payslip with 2x overtime and statutory deductions."""
    worker = repo.get_worker(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    site = repo.get_site(worker.site_id)
    shifts = repo.get_shifts(worker_id=worker.id)

    # 14 days window
    now = datetime.now(timezone.utc)
    p_start = (now - timedelta(days=14)).strftime("%Y-%m-%d")
    p_end = now.strftime("%Y-%m-%d")

    return generate_payslip(worker, site, shifts, p_start, p_end)


@router.post("/payslip/explain", response_model=ExplainPayslipResponse)
async def explain_worker_payslip(
    payload: ExplainPayslipRequest,
    worker_id: str = Depends(get_current_worker_id),
    repo: InMemoryRepository = Depends(get_repository)
) -> ExplainPayslipResponse:
    """Request AI-generated plain-language voice explanation of worker payslip."""
    worker = repo.get_worker(worker_id)
    site = repo.get_site(worker.site_id)
    shifts = repo.get_shifts(worker_id=worker.id)
    now = datetime.now(timezone.utc)
    payslip = generate_payslip(worker, site, shifts, (now - timedelta(days=14)).strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d"))

    explanation = await explain_payslip(payslip.model_dump(), payload.language)
    speech_lang_map = {"en": "en-IN", "hi": "hi-IN", "ta": "ta-IN"}
    speech_lang = speech_lang_map.get(payload.language, "en-IN")

    return ExplainPayslipResponse(
        explanation=explanation,
        language=payload.language,
        speech_lang=speech_lang
    )


@router.post("/safety-reports", response_model=SafetyReport)
async def submit_safety_report(
    payload: SafetyReportCreateRequest,
    worker_id: str = Depends(get_current_worker_id),
    repo: InMemoryRepository = Depends(get_repository)
) -> SafetyReport:
    """Submit worker safety report with automated multilingual AI hazard triage."""
    worker = repo.get_worker(worker_id)
    site_id = payload.site_id or worker.site_id
    lang = payload.language or "en"

    # AI triage (strict JSON)
    triage = await triage_safety_report(payload.input_text, lang)

    report = SafetyReport(
        id=f"rep-{secrets.token_hex(4)}",
        site_id=site_id,
        worker_id=worker.id,
        worker_name=worker.name,
        input_text=payload.input_text,
        category=triage["category"],
        severity=triage["severity"],
        summary_en=triage["summary_en"],
        summary_local=triage["summary_local"],
        status="Reported",
        created_at=datetime.now(timezone.utc).isoformat()
    )
    repo.add_safety_report(report)
    return report


@router.get("/safety-reports", response_model=List[SafetyReport])
async def list_worker_safety_reports(
    worker_id: str = Depends(get_current_worker_id),
    repo: InMemoryRepository = Depends(get_repository)
) -> List[SafetyReport]:
    """List site safety hazard reports and status updates."""
    worker = repo.get_worker(worker_id)
    return repo.get_safety_reports(site_id=worker.site_id)


@router.post("/feedback")
async def submit_anonymous_feedback(
    payload: AnonymousFeedbackCreateRequest,
    worker_id: str = Depends(get_current_worker_id),
    repo: InMemoryRepository = Depends(get_repository)
) -> Dict[str, str]:
    """Submit anonymized workplace feedback with strict exclusion of worker identity."""
    dt_now = datetime.now(timezone.utc)
    iso_year, iso_week, _ = dt_now.isocalendar()
    current_iso_week = f"{iso_year}-W{iso_week:02d}"

    feedback = AnonymousFeedback(
        id=f"fb-{secrets.token_hex(4)}",
        site_id=payload.site_id,
        iso_week=current_iso_week,
        manager_rating=payload.manager_rating,
        conditions_rating=payload.conditions_rating,
        comment=payload.comment,
        created_at=dt_now.isoformat()
    )
    # Stored with NO worker id
    repo.add_feedback(feedback)
    return {
        "status": "ok",
        "message": "Anonymous feedback recorded securely. Your identity is never stored."
    }


@router.get("/passport", response_model=SkillPassport)
async def get_worker_passport(
    worker_id: str = Depends(get_current_worker_id),
    repo: InMemoryRepository = Depends(get_repository)
) -> SkillPassport:
    """Retrieve verifiable skill passport for authenticated worker."""
    passport = repo.get_passport_by_worker(worker_id)
    if not passport:
        raise HTTPException(status_code=404, detail="Skill passport not found")
    return passport


@router.get("/fatigue", response_model=List[FatigueAlert])
async def get_worker_fatigue_status(
    worker_id: str = Depends(get_current_worker_id),
    repo: InMemoryRepository = Depends(get_repository)
) -> List[FatigueAlert]:
    """Check active fatigue safety violations for authenticated worker."""
    worker = repo.get_worker(worker_id)
    site = repo.get_site(worker.site_id)
    shifts = repo.get_shifts(worker_id=worker.id)
    return check_worker_fatigue(worker, site, shifts)
