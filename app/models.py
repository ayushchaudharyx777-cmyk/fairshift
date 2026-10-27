from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# --- Domain Models ---

class Site(BaseModel):
    id: str
    name: str
    sector: str  # "construction" | "hospital"
    location: str


class Worker(BaseModel):
    id: str
    name: str
    phone: str = Field(..., max_length=15)
    pin_hash: str
    site_id: str
    role: str
    hourly_rate: float
    passport_token: str
    created_at: str


class Shift(BaseModel):
    id: str
    worker_id: str
    site_id: str
    start_time: str  # ISO 8601
    end_time: Optional[str] = None  # None if actively clocked in
    total_hours: float = 0.0
    regular_hours: float = 0.0
    overtime_hours: float = 0.0
    status: str = "active"  # "active" | "completed"
    notes: Optional[str] = None


class SafetyReport(BaseModel):
    id: str
    site_id: str
    worker_id: Optional[str] = None
    worker_name: Optional[str] = None
    input_text: str = Field(..., max_length=2000)
    category: str = "hazard"  # "ppe" | "hazard" | "equipment" | "fatigue" | "sanitation" | "other"
    severity: str = "medium"  # "low" | "medium" | "high" | "critical"
    summary_en: str
    summary_local: str
    status: str = "Reported"  # "Reported" | "Acknowledged" | "Resolved"
    created_at: str
    resolved_at: Optional[str] = None


class AnonymousFeedback(BaseModel):
    id: str
    site_id: str
    iso_week: str  # e.g. "2026-W43"
    manager_rating: int = Field(..., ge=1, le=5)
    conditions_rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=1000)
    created_at: str
    # IMPORTANT: worker_id is strictly NOT included!


class TrainingRecord(BaseModel):
    title: str
    issued_by: str
    date: str
    valid_until: str
    status: str = "Active"


class PastEmployer(BaseModel):
    company: str
    role: str
    period: str
    verified: bool = True


class ExperienceItem(BaseModel):
    year: str
    title: str
    description: str


class SkillPassport(BaseModel):
    token: str
    worker_id: str
    worker_name: str
    role: str
    site_name: str
    sector: str
    avatar_initials: str
    verified_badges: List[str]
    skills: List[str]
    trainings: List[TrainingRecord]
    past_employers: List[PastEmployer]
    experience_timeline: List[ExperienceItem]
    qr_data: str


class PayslipLineItem(BaseModel):
    label: str
    rate_or_units: str
    amount: float
    type: str  # "earning" | "deduction" | "summary"


class Payslip(BaseModel):
    worker_id: str
    worker_name: str
    site_name: str
    sector: str
    period_start: str
    period_end: str
    total_shifts: int
    regular_hours: float
    overtime_hours: float
    total_hours: float
    hourly_rate: float
    base_pay: float
    overtime_pay: float
    gross_pay: float
    pf_deduction: float
    esi_deduction: float
    total_deductions: float
    net_pay: float
    donut_data: Dict[str, Any]
    line_items: List[PayslipLineItem]


class FatigueAlert(BaseModel):
    worker_id: str
    worker_name: str
    site_id: str
    site_name: str
    alert_type: str  # "daily_exceeded" | "weekly_exceeded" | "insufficient_rest"
    description: str
    severity: str  # "high" | "critical"
    shift_id: Optional[str] = None
    measured_value: float
    threshold_value: float
    recommended_action: str


# --- Request & Response Schemas ---

class WorkerLoginRequest(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15)
    pin: str = Field(..., min_length=4, max_length=6)


class WorkerLoginResponse(BaseModel):
    worker_id: str
    name: str
    phone: str
    site_id: str
    site_name: str
    sector: str
    role: str
    hourly_rate: float
    passport_token: str


class AdminLoginRequest(BaseModel):
    pin: str = Field(..., min_length=4, max_length=10)


class AdminLoginResponse(BaseModel):
    status: str
    message: str


class CheckInRequest(BaseModel):
    site_id: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=200)


class CheckOutRequest(BaseModel):
    notes: Optional[str] = Field(None, max_length=200)


class SafetyReportCreateRequest(BaseModel):
    input_text: str = Field(..., min_length=3, max_length=2000)
    site_id: Optional[str] = None
    language: Optional[str] = "en"


class SafetyReportUpdateRequest(BaseModel):
    status: str = Field(..., pattern="^(Reported|Acknowledged|Resolved)$")


class AnonymousFeedbackCreateRequest(BaseModel):
    site_id: str
    manager_rating: int = Field(..., ge=1, le=5)
    conditions_rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=1000)


class ExplainPayslipRequest(BaseModel):
    language: str = Field("en", pattern="^(en|hi|ta)$")


class ExplainPayslipResponse(BaseModel):
    explanation: str
    language: str
    speech_lang: str


class KPIStatsResponse(BaseModel):
    today_attendance: int
    total_workers: int
    weekly_overtime_hours: float
    open_safety_reports_count: int
    safety_by_severity: Dict[str, int]
    avg_feedback_score: float
    total_feedback_count: int
