import asyncio
import json
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sse_starlette.sse import EventSourceResponse
from app.config import get_settings
from app.models import (
    AdminLoginRequest, AdminLoginResponse, KPIStatsResponse,
    SafetyReport, SafetyReportUpdateRequest, FatigueAlert, AnonymousFeedback
)
from app.repository import InMemoryRepository, get_repository
from app.security import (
    create_admin_session_token, require_admin_auth, verify_admin_session_token
)
from app.services.fatigue import detect_fatigue_alerts

router = APIRouter(prefix="/api/v1/admin", tags=["Admin API"])


@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(payload: AdminLoginRequest, response: Response):
    settings = get_settings()
    if payload.pin != settings.ADMIN_PIN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Admin PIN"
        )
    token = create_admin_session_token()
    response.set_cookie(
        key="admin_session",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=86400 * 2,
        secure=False
    )
    return AdminLoginResponse(status="ok", message="Admin authentication successful")


@router.post("/logout")
async def admin_logout(response: Response):
    response.delete_cookie("admin_session")
    return {"status": "ok", "message": "Admin logged out"}


@router.get("/overview")
async def get_admin_overview(
    site_id: Optional[str] = None,
    authorized: bool = Depends(require_admin_auth),
    repo: InMemoryRepository = Depends(get_repository)
):
    """Return comprehensive dashboard KPIs, chart data, and site summaries."""
    sites = repo.get_sites()
    workers = repo.get_workers()
    all_shifts = repo.get_shifts()
    all_safety = repo.get_safety_reports()
    all_feedback = repo.get_feedbacks()

    if site_id:
        workers = [w for w in workers if w.site_id == site_id]
        all_shifts = [s for s in all_shifts if s.site_id == site_id]
        all_safety = [r for r in all_safety if r.site_id == site_id]
        all_feedback = [f for f in all_feedback if f.site_id == site_id]

    # 1. Today's Attendance
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_active_worker_ids = set()
    for s in all_shifts:
        if s.start_time.startswith(today_str) or s.status == "active":
            today_active_worker_ids.add(s.worker_id)
    today_attendance = len(today_active_worker_ids)

    # 2. Weekly Overtime Hours (current week)
    now_dt = datetime.now(timezone.utc)
    week_start = (now_dt - timedelta(days=7)).isoformat()
    weekly_shifts = [s for s in all_shifts if s.start_time >= week_start and s.status == "completed"]
    weekly_overtime_hours = round(sum(s.overtime_hours for s in weekly_shifts), 1)

    # 3. Safety Reports by Severity (Open = Reported or Acknowledged)
    open_safety = [r for r in all_safety if r.status in ["Reported", "Acknowledged"]]
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for r in open_safety:
        sev = r.severity.lower()
        if sev in severity_counts:
            severity_counts[sev] += 1
        else:
            severity_counts["medium"] += 1

    # 4. Feedback Average Score
    total_feedback_count = len(all_feedback)
    if total_feedback_count > 0:
        avg_feedback_score = round(
            sum((f.manager_rating + f.conditions_rating) / 2.0 for f in all_feedback) / total_feedback_count,
            1
        )
    else:
        avg_feedback_score = 5.0

    # 5. Worker Weekly Hours for SVG Bar Chart
    worker_weekly_hours = []
    worker_map = {w.id: w for w in repo.get_workers()}
    shifts_by_worker = defaultdict(float)
    for s in weekly_shifts:
        shifts_by_worker[s.worker_id] += s.total_hours

    for w in workers:
        total_h = round(shifts_by_worker.get(w.id, 0.0), 1)
        worker_weekly_hours.append({
            "worker_id": w.id,
            "name": w.name,
            "site_id": w.site_id,
            "hours": total_h,
            "is_overtime": total_h > 48.0,
            "is_fatigued": total_h > 60.0
        })

    # Sort workers by hours desc
    worker_weekly_hours.sort(key=lambda x: x["hours"], reverse=True)

    return {
        "kpis": {
            "today_attendance": today_attendance,
            "total_workers": len(workers),
            "weekly_overtime_hours": weekly_overtime_hours,
            "open_safety_reports_count": len(open_safety),
            "safety_by_severity": severity_counts,
            "avg_feedback_score": avg_feedback_score,
            "total_feedback_count": total_feedback_count
        },
        "chart_data": {
            "threshold_warning": 48.0,
            "threshold_fatigue": 60.0,
            "workers": worker_weekly_hours[:10]
        },
        "sites": [s.model_dump() for s in sites]
    }


@router.get("/fatigue-alerts", response_model=List[FatigueAlert])
async def get_fatigue_alerts(
    site_id: Optional[str] = None,
    authorized: bool = Depends(require_admin_auth),
    repo: InMemoryRepository = Depends(get_repository)
):
    """Detect and return all active fatigue violations across all sites/workers."""
    workers = repo.get_workers()
    sites = repo.get_sites()
    shifts = repo.get_shifts(site_id=site_id)
    alerts = detect_fatigue_alerts(workers, sites, shifts)
    if site_id:
        alerts = [a for a in alerts if a.site_id == site_id]
    # Sort critical first
    sev_order = {"critical": 0, "high": 1}
    alerts.sort(key=lambda a: sev_order.get(a.severity, 2))
    return alerts


@router.get("/safety-kanban")
async def get_safety_kanban(
    site_id: Optional[str] = None,
    authorized: bool = Depends(require_admin_auth),
    repo: InMemoryRepository = Depends(get_repository)
):
    """Kanban board grouped into Reported, Acknowledged, and Resolved columns."""
    reports = repo.get_safety_reports(site_id=site_id)
    kanban: Dict[str, List[Dict[str, Any]]] = {
        "Reported": [],
        "Acknowledged": [],
        "Resolved": []
    }
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    for r in reports:
        col = r.status if r.status in kanban else "Reported"
        kanban[col].append(r.model_dump())

    # Sort each column so critical reports are strictly on top
    for col in kanban:
        kanban[col].sort(key=lambda item: (sev_order.get(item["severity"], 4), item["created_at"]))

    return kanban


@router.patch("/safety-reports/{report_id}/status")
async def update_safety_report_status(
    report_id: str,
    payload: SafetyReportUpdateRequest,
    authorized: bool = Depends(require_admin_auth),
    repo: InMemoryRepository = Depends(get_repository)
):
    """Transition safety report status (Reported -> Acknowledged -> Resolved)."""
    report = repo.get_safety_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Safety report not found")
    
    report.status = payload.status
    if payload.status == "Resolved":
        report.resolved_at = datetime.now(timezone.utc).isoformat()
    repo.update_safety_report(report)
    return report


@router.get("/feedback-summary")
async def get_feedback_summary(
    site_id: Optional[str] = None,
    authorized: bool = Depends(require_admin_auth),
    repo: InMemoryRepository = Depends(get_repository)
):
    """Anonymous feedback aggregated by site with zero worker identification."""
    feedbacks = repo.get_feedbacks(site_id=site_id)
    sites = repo.get_sites()
    site_map = {s.id: s.name for s in sites}

    by_site: Dict[str, Dict[str, Any]] = {}
    for s in sites:
        if site_id and s.id != site_id:
            continue
        by_site[s.id] = {
            "site_id": s.id,
            "site_name": s.name,
            "total_reviews": 0,
            "avg_manager": 0.0,
            "avg_conditions": 0.0,
            "overall_avg": 0.0,
            "comments": []
        }

    for f in feedbacks:
        if f.site_id in by_site:
            entry = by_site[f.site_id]
            entry["total_reviews"] += 1
            entry["avg_manager"] += f.manager_rating
            entry["avg_conditions"] += f.conditions_rating
            if f.comment:
                entry["comments"].append({
                    "iso_week": f.iso_week,
                    "manager_rating": f.manager_rating,
                    "conditions_rating": f.conditions_rating,
                    "comment": f.comment,
                    "created_at": f.created_at
                })

    results = []
    for sid, data in by_site.items():
        count = data["total_reviews"]
        if count > 0:
            data["avg_manager"] = round(data["avg_manager"] / count, 1)
            data["avg_conditions"] = round(data["avg_conditions"] / count, 1)
            data["overall_avg"] = round((data["avg_manager"] + data["avg_conditions"]) / 2.0, 1)
        else:
            data["avg_manager"] = 5.0
            data["avg_conditions"] = 5.0
            data["overall_avg"] = 5.0
        results.append(data)

    return results


@router.get("/stream")
async def sse_event_stream(
    request: Request,
    repo: InMemoryRepository = Depends(get_repository)
):
    """
    Server-Sent Events endpoint.
    Live notifies admin of new critical/high safety reports and status updates.
    """
    # Verify auth via cookie or query param or header
    cookie_token = request.cookies.get("admin_session")
    auth_header = request.headers.get("Authorization")
    token = cookie_token
    if not token and auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
    if not token and "token" in request.query_params:
        token = request.query_params.get("token")

    if not token or not verify_admin_session_token(token):
        raise HTTPException(status_code=401, detail="Admin auth required for SSE stream")

    event_queue = repo.subscribe_events()

    async def event_generator():
        try:
            # Send initial keepalive
            yield {
                "event": "connected",
                "data": json.dumps({"status": "connected", "time": datetime.now(timezone.utc).isoformat()})
            }
            while True:
                # Check client disconnect
                if await request.is_disconnected():
                    break
                try:
                    event_data = await asyncio.wait_for(event_queue.get(), timeout=15.0)
                    yield {
                        "event": "message",
                        "data": json.dumps(event_data)
                    }
                except asyncio.TimeoutError:
                    # Send heartbeat ping every 15s to keep connection alive
                    yield {
                        "event": "ping",
                        "data": json.dumps({"ping": True})
                    }
        finally:
            repo.unsubscribe_events(event_queue)

    return EventSourceResponse(event_generator())
