import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.repository import get_repository
from app.seed import seed_database
from app.security import create_worker_session_token, create_admin_session_token
from app.services.integrity import verify_chain
from app.services.wagecheck import check_wage_theft
from app.services.payroll import generate_payslip

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture(autouse=True)
def init_db():
    seed_database(get_repository())


def worker_client(wid="w-1"):
    c = TestClient(app)
    c.cookies.set("worker_session", create_worker_session_token(wid))
    return c


def admin_client():
    c = TestClient(app)
    c.cookies.set("admin_session", create_admin_session_token())
    return c


# ---------- hash chain ----------
def test_seed_chain_is_valid():
    res = admin_client().get("/api/v1/admin/integrity-check").json()
    assert res["valid"] is True and res["checked"] >= 5


def test_status_change_does_not_break_chain():
    c = admin_client()
    rid = get_repository().get_safety_reports()[0].id
    c.patch(f"/api/v1/admin/safety-reports/{rid}/status", json={"status": "Resolved"})
    assert c.get("/api/v1/admin/integrity-check").json()["valid"] is True


def test_tampering_content_is_detected():
    repo = get_repository()
    victim = repo.get_report_chain()[2]
    victim.severity = "low"  # contractor quietly downgrades a critical report
    res = admin_client().get("/api/v1/admin/integrity-check").json()
    assert res["valid"] is False
    assert res["broken_report_id"] == victim.id


def test_deleting_a_report_is_detected():
    repo = get_repository()
    gone = repo.report_chain[1]
    repo.safety_reports.pop(gone)
    assert verify_chain(repo.get_report_chain())["valid"] is False


def test_integrity_requires_admin():
    assert TestClient(app).get("/api/v1/admin/integrity-check").status_code == 401


# ---------- photo hazard ----------
def test_photo_hazard_with_mocked_vision():
    c = worker_client()
    fake = '{"category":"ppe","severity":"high","summary_en":"Worker without helmet near edge","summary_local":"x"}'
    with patch("app.services.ai._execute_gemini_call", new_callable=AsyncMock) as m:
        m.return_value = fake
        r = c.post("/api/v1/worker/hazard-photo", files={"photo": ("a.jpg", JPEG, "image/jpeg")},
                   data={"language": "en"})
    assert r.status_code == 200
    d = r.json()
    assert d["source"] == "photo" and d["category"] == "ppe" and d["severity"] == "high"
    assert d["hash"] and admin_client().get("/api/v1/admin/integrity-check").json()["valid"]


def test_photo_ai_failure_falls_back_not_crashes():
    c = worker_client()
    with patch("app.services.ai._execute_gemini_call", new_callable=AsyncMock) as m:
        m.side_effect = RuntimeError("API down")
        r = c.post("/api/v1/worker/hazard-photo", files={"photo": ("a.png", PNG, "image/png")})
    assert r.status_code == 200 and r.json()["severity"] == "medium"


def test_photo_rejects_non_image_even_with_image_content_type():
    r = worker_client().post("/api/v1/worker/hazard-photo",
                             files={"photo": ("evil.jpg", b"<script>alert(1)</script>", "image/jpeg")})
    assert r.status_code == 415


def test_photo_rejects_oversize_and_requires_auth():
    big = JPEG + b"\x00" * (5 * 1024 * 1024)
    assert worker_client().post("/api/v1/worker/hazard-photo",
                                files={"photo": ("a.jpg", big, "image/jpeg")}).status_code == 413
    assert TestClient(app).post("/api/v1/worker/hazard-photo",
                                files={"photo": ("a.jpg", JPEG, "image/jpeg")}).status_code == 401


def test_prompt_injection_in_model_output_is_sanitised():
    bad = '{"category":"DROP TABLE","severity":"apocalyptic","summary_en":"ok","summary_local":"ok"}'
    with patch("app.services.ai._execute_gemini_call", new_callable=AsyncMock) as m:
        m.return_value = bad
        unique = JPEG + b"injection-test"  # distinct bytes => bypass the image-hash cache
        r = worker_client().post("/api/v1/worker/hazard-photo", files={"photo": ("a.jpg", unique, "image/jpeg")})
    assert r.json()["category"] == "hazard" and r.json()["severity"] == "medium"


# ---------- wage theft ----------
def _payslip(wid="w-1"):
    repo = get_repository()
    w = repo.get_worker(wid)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return generate_payslip(w, repo.get_site(w.site_id), repo.get_shifts(worker_id=wid), now, now)


def test_wage_check_fair():
    ps = _payslip()
    r = check_wage_theft(ps, ps.net_pay)
    assert r.verdict == "fair" and r.shortfall == 0


def test_wage_check_detects_ot_paid_at_1x():
    ps = _payslip()
    assert ps.overtime_hours > 0, "seed must contain OT for this scenario"
    paid = ps.net_pay - (ps.overtime_pay / 2) * (1 - 0.0075)
    r = check_wage_theft(ps, paid)
    assert r.verdict == "underpaid" and r.shortfall > 0
    assert "1x" in r.likely_cause


def test_wage_check_endpoint_and_validation():
    c = worker_client()
    ps = _payslip()
    r = c.post("/api/v1/worker/wage-check", json={"paid_amount": ps.net_pay - 500})
    assert r.status_code == 200 and r.json()["shortfall"] == pytest.approx(500, abs=1)
    assert c.post("/api/v1/worker/wage-check", json={"paid_amount": -5}).status_code == 422
    assert TestClient(app).post("/api/v1/worker/wage-check", json={"paid_amount": 1}).status_code == 401


# ---------- impact ----------
def test_impact_scales_linearly_and_exposes_assumptions():
    c = admin_client()
    a = c.get("/api/v1/admin/impact?workers=1000&theft_rate=0.3").json()
    b = c.get("/api/v1/admin/impact?workers=2000&theft_rate=0.3").json()
    assert b["estimated_annual_wage_protected_inr"] == pytest.approx(2 * a["estimated_annual_wage_protected_inr"], rel=0.01)
    assert "theft_rate_assumed" in a["assumptions"]
    assert c.get("/api/v1/admin/impact?workers=-5&theft_rate=9").status_code == 200  # clamped, no crash


def test_photo_endpoint_is_rate_limited_like_other_ai_endpoints(monkeypatch):
    # The limiter is a 60s rolling window. Stub Gemini so every request returns instantly; a real call
    # with an invalid or slow key (401 + retry) lets early requests age out of the window before the 31st.
    from app.services import ai

    async def offline(prompt, image=None):
        raise RuntimeError("offline test stub")

    monkeypatch.setattr(ai, "_execute_gemini_call", offline)
    c = worker_client()
    codes = []
    for i in range(32):
        r = c.post("/api/v1/worker/hazard-photo",
                   files={"photo": ("a.jpg", JPEG + str(i).encode(), "image/jpeg")})
        codes.append(r.status_code)
    assert codes[:30] == [200] * 30 and codes[30] == 429
