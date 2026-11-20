"""Optional write-through persistence (SQLite locally, Postgres in production).

The in-memory repository stays the working store, so every existing code path and test is
unchanged. When DATABASE_URL is set, mutable collections (shifts, safety reports incl. their
hash chain, anonymous feedback) are mirrored to the database and restored on startup.
Persistence failures are logged and never break a request.
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, Integer, MetaData, String, Table, Text, create_engine, delete, func, select, update
from sqlalchemy.engine import Engine

from app.models import AnonymousFeedback, SafetyReport, Shift

logger = logging.getLogger("fairshift.persistence")

COLLECTIONS = ("shifts", "safety_reports", "feedbacks")

# All DB writes run on ONE background thread: request handlers never wait on (possibly remote) database
# latency, and a single worker keeps writes strictly ordered (hash-chain order is preserved).
# At interpreter exit Python joins this pool, so already-queued writes still complete.
_WRITER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fs-persist")


def flush(timeout: float = 30.0) -> None:
    """Block until every queued write has been executed (used before reads, tests and shutdown)."""
    _WRITER.submit(lambda: None).result(timeout=timeout)



def normalize_url(url: str) -> str:
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


class Store:
    def __init__(self, url: str) -> None:
        self.engine: Engine = create_engine(normalize_url(url), pool_pre_ping=True, future=True)
        md = MetaData()
        self.records = Table(
            "records", md,
            Column("collection", String(40), primary_key=True),
            Column("id", String(80), primary_key=True),
            Column("seq", Integer, nullable=False, default=0),
            Column("data", Text, nullable=False),
        )
        md.create_all(self.engine)

    def upsert(self, collection: str, rec_id: str, data: Dict[str, Any], seq: int = 0) -> bool:
        """Queue a write; returns immediately. Failures are logged by the writer thread."""
        _WRITER.submit(self._upsert_now, collection, rec_id, data, seq)
        return True

    def _upsert_now(self, collection: str, rec_id: str, data: Dict[str, Any], seq: int = 0) -> bool:
        payload = json.dumps(data, ensure_ascii=False, default=str)
        try:
            with self.engine.begin() as conn:
                res = conn.execute(
                    update(self.records)
                    .where(self.records.c.collection == collection, self.records.c.id == rec_id)
                    .values(seq=seq, data=payload)
                )
                if res.rowcount == 0:
                    conn.execute(self.records.insert().values(collection=collection, id=rec_id, seq=seq, data=payload))
            return True
        except Exception as exc:  # never break a request because the DB hiccuped
            logger.error("persist failed for %s/%s: %s", collection, rec_id, exc)
            return False

    def load(self, collection: str) -> List[Dict[str, Any]]:
        flush()
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(self.records.c.data).where(self.records.c.collection == collection).order_by(self.records.c.seq)
            ).all()
        return [json.loads(r[0]) for r in rows]

    def count(self, collection: Optional[str] = None) -> int:
        flush()
        with self.engine.connect() as conn:
            q = select(func.count()).select_from(self.records)
            if collection:
                q = q.where(self.records.c.collection == collection)
            return int(conn.execute(q).scalar() or 0)

    def wipe(self) -> None:
        flush()
        with self.engine.begin() as conn:
            conn.execute(delete(self.records))


def init_store_from_env() -> Optional[Store]:
    from app.config import get_settings
    url = get_settings().DATABASE_URL.strip()
    if not url:
        return None
    try:
        return Store(url)
    except Exception as exc:
        logger.error("DATABASE_URL set but database unreachable (%s); running in-memory only", exc)
        return None


def persist_all(repo: Any, store: Store) -> None:
    for i, rid in enumerate(repo.report_chain):
        r = repo.safety_reports.get(rid)
        if r:
            store.upsert("safety_reports", r.id, r.model_dump(), i)
    for s in repo.shifts.values():
        store.upsert("shifts", s.id, s.model_dump())
    for i, f in enumerate(repo.feedbacks):
        store.upsert("feedbacks", f.id, f.model_dump(), i)


def restore_or_bootstrap(repo: Any, store: Store, reset: bool = False) -> str:
    """Call AFTER seeding. Returns 'restored' (DB had data), 'bootstrapped' (first run) or 'reset'."""
    if reset:
        store.wipe()
        repo.store = store
        persist_all(repo, store)
        return "reset"
    if store.count() > 0:
        repo.shifts.clear()
        repo.safety_reports.clear()
        repo.report_chain.clear()
        repo.feedbacks.clear()
        for d in store.load("shifts"):
            s = Shift(**d); repo.shifts[s.id] = s
        for d in store.load("safety_reports"):
            r = SafetyReport(**d); repo.safety_reports[r.id] = r; repo.report_chain.append(r.id)
        for d in store.load("feedbacks"):
            repo.feedbacks.append(AnonymousFeedback(**d))
        repo.store = store
        return "restored"
    repo.store = store
    persist_all(repo, store)
    return "bootstrapped"
