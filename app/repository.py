import asyncio
import logging
from typing import Dict, List, Optional, Any
from app.models import (
    Site, Worker, Shift, SafetyReport, AnonymousFeedback, SkillPassport
)

logger = logging.getLogger("fairshift.repository")


class InMemoryRepository:
    def __init__(self) -> None:
        """Initialize in-memory data structures and event queues."""
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
        """Return all registered workplace sites."""
        return list(self.sites.values())

    def get_site(self, site_id: str) -> Optional[Site]:
        """Retrieve a specific workplace site by ID."""
        return self.sites.get(site_id)

    # --- Workers ---
    def get_workers(self) -> List[Worker]:
        """Return list of all registered shift workers."""
        return list(self.workers.values())

    def get_worker(self, worker_id: str) -> Optional[Worker]:
        """Retrieve a worker by unique ID."""
        return self.workers.get(worker_id)

    def get_worker_by_phone(self, phone: str) -> Optional[Worker]:
        """Find a worker matching registered mobile phone number."""
        cleaned = phone.strip()
        for w in self.workers.values():
            if w.phone == cleaned:
                return w
        return None

    # --- Shifts ---
    def get_shifts(self, site_id: Optional[str] = None, worker_id: Optional[str] = None) -> List[Shift]:
        """Return filtered shift history sorted chronologically descending."""
        results = list(self.shifts.values())
        if site_id:
            results = [s for s in results if s.site_id == site_id]
        if worker_id:
            results = [s for s in results if s.worker_id == worker_id]
        return sorted(results, key=lambda s: s.start_time, reverse=True)

    def get_active_shift(self, worker_id: str) -> Optional[Shift]:
        """Find currently active shift for worker if clocked in."""
        for s in self.shifts.values():
            if s.worker_id == worker_id and s.status == "active":
                return s
        return None

    def add_shift(self, shift: Shift) -> None:
        """Store newly created shift in repository."""
        self.shifts[shift.id] = shift

    def update_shift(self, shift: Shift) -> None:
        """Persist updated shift state in repository."""
        self.shifts[shift.id] = shift

    # --- Safety Reports ---
    def get_safety_reports(self, site_id: Optional[str] = None) -> List[SafetyReport]:
        """Return safety incident reports prioritizing critical severity."""
        reports = list(self.safety_reports.values())
        if site_id:
            reports = [r for r in reports if r.site_id == site_id]
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        return sorted(
            reports,
            key=lambda r: (severity_order.get(r.severity, 4), r.created_at),
            reverse=False
        )

    def get_safety_report(self, report_id: str) -> Optional[SafetyReport]:
        """Retrieve a single safety report by ID."""
        return self.safety_reports.get(report_id)

    def add_safety_report(self, report: SafetyReport) -> None:
        """Add new safety report and broadcast event to SSE listeners."""
        self.safety_reports[report.id] = report
        self.broadcast_event({
            "type": "safety_report_created",
            "report": report.model_dump(),
            "alert": report.severity in ["high", "critical"]
        })

    def update_safety_report(self, report: SafetyReport) -> None:
        """Update safety report status and broadcast update event."""
        self.safety_reports[report.id] = report
        self.broadcast_event({
            "type": "safety_report_updated",
            "report": report.model_dump()
        })

    # --- Anonymous Feedback ---
    def add_feedback(self, feedback: AnonymousFeedback) -> None:
        """Persist anonymized feedback record without worker identification."""
        self.feedbacks.append(feedback)
        self.broadcast_event({
            "type": "feedback_created",
            "site_id": feedback.site_id,
            "iso_week": feedback.iso_week,
            "manager_rating": feedback.manager_rating,
            "conditions_rating": feedback.conditions_rating
        })

    def get_feedbacks(self, site_id: Optional[str] = None) -> List[AnonymousFeedback]:
        """Return anonymous feedback entries optionally filtered by site."""
        if site_id:
            return [f for f in self.feedbacks if f.site_id == site_id]
        return list(self.feedbacks)

    # --- Skill Passports ---
    def get_passport_by_token(self, token: str) -> Optional[SkillPassport]:
        """Retrieve public skill passport by random verifiable token."""
        return self.passports.get(token)

    def get_passport_by_worker(self, worker_id: str) -> Optional[SkillPassport]:
        """Find skill passport corresponding to internal worker ID."""
        token = self.worker_to_passport.get(worker_id)
        if token:
            return self.passports.get(token)
        return None

    def add_passport(self, passport: SkillPassport) -> None:
        """Store verifiable skill passport mapping."""
        self.passports[passport.token] = passport
        self.worker_to_passport[passport.worker_id] = passport.token

    # --- SSE Event Broadcaster ---
    def subscribe_events(self) -> asyncio.Queue:
        """Register a new asynchronous queue listener for SSE stream."""
        q: asyncio.Queue = asyncio.Queue()
        self._sse_listeners.append(q)
        return q

    def unsubscribe_events(self, q: asyncio.Queue) -> None:
        """Deregister an active SSE queue listener upon disconnect."""
        if q in self._sse_listeners:
            self._sse_listeners.remove(q)

    def broadcast_event(self, data: Dict[str, Any]) -> None:
        """Push real-time event to all connected SSE clients."""
        for q in list(self._sse_listeners):
            try:
                q.put_nowait(data)
            except Exception as e:
                logger.warning(f"Failed to enqueue SSE event: {e}")


# Global repository singleton
_repo_instance = InMemoryRepository()


def get_repository() -> InMemoryRepository:
    """Return application in-memory repository singleton."""
    return _repo_instance
