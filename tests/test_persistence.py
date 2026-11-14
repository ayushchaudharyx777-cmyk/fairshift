from datetime import datetime, timezone
import pytest
from app.repository import InMemoryRepository
from app.seed import seed_database
from app.models import SafetyReport, AnonymousFeedback
from app.persistence import Store, normalize_url, restore_or_bootstrap, init_store_from_env
from app.services.integrity import verify_chain


def fresh_repo():
    r = InMemoryRepository()
    seed_database(r)
    return r


def new_report(rid="rep-new1", sev="high"):
    return SafetyReport(id=rid, site_id="site-construction", worker_id="w-1", worker_name="Rajesh Kumar",
                        input_text="crane cable frayed", category="equipment", severity=sev,
                        summary_en="Frayed crane cable", summary_local="x", status="Reported",
                        created_at=datetime.now(timezone.utc).isoformat())


def test_normalize_url_variants():
    assert normalize_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_url("sqlite:///x.db") == "sqlite:///x.db"


def test_first_run_bootstraps_then_restart_restores_everything(tmp_path):
    url = f"sqlite:///{tmp_path/'fs.db'}"
    # --- run 1 ---
    repo1 = fresh_repo()
    assert restore_or_bootstrap(repo1, Store(url)) == "bootstrapped"
    repo1.add_safety_report(new_report())
    rep = repo1.get_safety_report("rep-new1"); rep.status = "Resolved"; repo1.update_safety_report(rep)
    fb = AnonymousFeedback(id="fb-t1", site_id="site-construction", iso_week="2026-W46",
                           manager_rating=4, conditions_rating=3, comment="ok", created_at="2026-11-14T00:00:00+00:00")
    repo1.add_feedback(fb)
    n_reports, n_fb, n_shifts = len(repo1.safety_reports), len(repo1.feedbacks), len(repo1.shifts)
    head = repo1.get_report_chain()[-1].hash

    # --- "restart": brand-new process state, same DB file ---
    repo2 = fresh_repo()
    assert restore_or_bootstrap(repo2, Store(url)) == "restored"
    assert len(repo2.safety_reports) == n_reports and len(repo2.feedbacks) == n_fb and len(repo2.shifts) == n_shifts
    assert repo2.get_safety_report("rep-new1").status == "Resolved"  # update survived
    assert repo2.get_report_chain()[-1].hash == head                 # chain order + hashes preserved
    assert verify_chain(repo2.get_report_chain())["valid"] is True
    # and the restored repo keeps persisting new writes
    repo2.add_safety_report(new_report("rep-new2"))
    repo3 = fresh_repo(); restore_or_bootstrap(repo3, Store(url))
    assert repo3.get_safety_report("rep-new2") is not None
    assert verify_chain(repo3.get_report_chain())["valid"] is True


def test_tampering_in_database_is_detected_after_restore(tmp_path):
    import json
    from sqlalchemy import update
    url = f"sqlite:///{tmp_path/'fs.db'}"
    repo1 = fresh_repo(); st = Store(url); restore_or_bootstrap(repo1, st)
    victim = repo1.get_report_chain()[1]
    d = victim.model_dump(); d["severity"] = "low"           # attacker edits the DB row directly
    with st.engine.begin() as c:
        c.execute(update(st.records).where(st.records.c.id == victim.id).values(data=json.dumps(d)))
    repo2 = fresh_repo(); restore_or_bootstrap(repo2, Store(url))
    res = verify_chain(repo2.get_report_chain())
    assert res["valid"] is False and res["broken_report_id"] == victim.id


def test_db_failure_never_breaks_request_path(tmp_path):
    repo = fresh_repo(); st = Store(f"sqlite:///{tmp_path/'fs.db'}"); restore_or_bootstrap(repo, st)
    st.engine.dispose()
    st.records.drop(st.engine)              # simulate DB losing its table mid-flight
    repo.add_safety_report(new_report())    # must not raise
    assert repo.get_safety_report("rep-new1") is not None


def test_unreachable_database_falls_back_to_memory(monkeypatch):
    from app import config
    config.get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody:x@127.0.0.1:1/nope")
    try:
        assert init_store_from_env() is None
    finally:
        config.get_settings.cache_clear()


def test_no_database_url_means_memory_only(monkeypatch):
    from app import config
    config.get_settings.cache_clear()
    monkeypatch.setenv("DATABASE_URL", "")
    try:
        assert init_store_from_env() is None
    finally:
        config.get_settings.cache_clear()


def test_reset_flag_wipes_saved_data_and_reseeds(tmp_path):
    url = f"sqlite:///{tmp_path/'fs.db'}"
    r1 = fresh_repo(); restore_or_bootstrap(r1, Store(url)); r1.add_safety_report(new_report())
    r2 = fresh_repo(); assert restore_or_bootstrap(r2, Store(url), reset=True) == "reset"
    assert r2.get_safety_report("rep-new1") is None
    r3 = fresh_repo(); assert restore_or_bootstrap(r3, Store(url)) == "restored"
    assert r3.get_safety_report("rep-new1") is None and verify_chain(r3.get_report_chain())["valid"]
