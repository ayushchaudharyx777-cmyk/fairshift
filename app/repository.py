import asyncio
import logging
from typing import Dict, List, Optional
from app.models import (
    Site, Worker, Shift, SafetyReport, AnonymousFeedback, SkillPassport
)

logger = logging.getLogger("fairshift.repository")


class InMemoryRepository:
    def __init__(self):
        self.sites: Dict[str, Site] = {}
        self.workers: Dict[str, Worker] = {}
        self.shifts: Dict[str, Shift] = {}
        self.safety_reports: Dict[str, SafetyReport] = {}
        self.feedbacks: List[AnonymousFeedback] = []
        self.passports: Dict[str, SkillPassport] = {}  # keyed by passport token
        self.worker_to_passport: Dict[str, str] = {}  # worker_id -> token
        self._sse_listeners: List[asyncio.Queue] = []
        self._lock = asyncio.Lock()

    # --- Sites ---
    def get_sites(self) -> List[Site]:
        return list(self.sites.values())

    def get_site(self, site_id: str) -> Optional[Site]:
        return self.sites.get(site_id)

    # --- Workers ---
    def get_workers(self) -> List[Worker]:
        return list(self.workers.values())

    def get_worker(self, worker_id: str) -> Optional[Worker]:
        return self.workers.get(worker_id)

    def get_worker_by_phone(self, phone: str) -> Optional[Worker]:
        cleaned = phone.strip()
        for w in self.workers.values():
            if w.phone == cleaned:
                return w
        return None

    # --- Shifts ---
    def get_shifts(self, site_id: Optional[str] = None, worker_id: Optional[str] = None) -> List[Shift]:
        results = list(self.shifts.values())
        if site_id:
            results = [s for s in results if s.site_id == site_id]
        if worker_id:
            results = [s for s in results if s.worker_id == worker_id]
        return sorted(results, key=lambda s: s.start_time, reverse=True)

    def get_active_shift(self, worker_id: str) -> Optional[Shift]:
        for s in self.shifts.values():
            if s.worker_id == worker_id and s.status == "active":
                return s
        return None

    def add_shift(self, shift: Shift):
        self.shifts[shift.id] = shift

    def update_shift(self, shift: Shift):
        self.shifts[shift.id] = shift

    # --- Safety Reports ---
    def get_safety_reports(self, site_id: Optional[str] = None) -> List[SafetyReport]:
        reports = list(self.safety_reports.values())
        if site_id:
            reports = [r for r in reports if r.site_id == site_id]
        # Sort critical first, then by date desc
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        return sorted(
            reports,
            key=lambda r: (severity_order.get(r.severity, 4), r.created_at),
            reverse=False
        )

    def get_safety_report(self, report_id: str) -> Optional[SafetyReport]:
        return self.safety_reports.get(report_id)

    def add_safety_report(self, report: SafetyReport):
        self.safety_reports[report.id] = report
        # Notify SSE listeners if high or critical
        self.broadcast_event({
            "type": "safety_report_created",
            "report": report.model_dump(),
            "alert": report.severity in ["high", "critical"]
        })

    def update_safety_report(self, report: SafetyReport):
        self.safety_reports[report.id] = report
        self.broadcast_event({
            "type": "safety_report_updated",
            "report": report.model_dump()
        })

    # --- Anonymous Feedback ---
    def add_feedback(self, feedback: AnonymousFeedback):
        # Guarantee no worker_id is ever persisted
        self.feedbacks.append(feedback)
        self.broadcast_event({
            "type": "feedback_created",
            "site_id": feedback.site_id,
            "iso_week": feedback.iso_week,
            "manager_rating": feedback.manager_rating,
            "conditions_rating": feedback.conditions_rating
        })

    def get_feedbacks(self, site_id: Optional[str] = None) -> List[AnonymousFeedback]:
        if site_id:
            return [f for f in self.feedbacks if f.site_id == site_id]
        return list(self.feedbacks)

    # --- Skill Passports ---
    def get_passport_by_token(self, token: str) -> Optional[SkillPassport]:
        return self.passports.get(token)

    def get_passport_by_worker(self, worker_id: str) -> Optional[SkillPassport]:
        token = self.worker_to_passport.get(worker_id)
        if token:
            return self.passports.get(token)
        return None

    def add_passport(self, passport: SkillPassport):
        self.passports[passport.token] = passport
        self.worker_to_passport[passport.worker_id] = passport.token

    # --- SSE Event Broadcaster ---
    def subscribe_events(self) -> asyncio.Queue:
        q = asyncio.Queue()
        self._sse_listeners.append(q)
        return q

    def unsubscribe_events(self, q: asyncio.Queue):
        if q in self._sse_listeners:
            self._sse_listeners.remove(q)

    def broadcast_event(self, data: dict):
        for q in list(self._sse_listeners):
            try:
                q.put_nowait(data)
            except Exception as e:
                logger.warning(f"Failed to enqueue SSE event: {e}")


# Global repository singleton
_repo_instance = InMemoryRepository()


def get_repository() -> InMemoryRepository:
    return _repo_instance
