"""AI health, honest source tagging, no-poisoned-cache, server voice, and the fixes behind the screenshots."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app import config
from app.languages import detect_language
from app.main import app
from app.repository import get_repository
from app.security import create_admin_session_token, create_worker_session_token
from app.seed import seed_database
from app.services import ai, tts
from app.services.integrity import verify_chain


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    seed_database(get_repository())
    config.get_settings.cache_clear()
    monkeypatch.setenv("GEMINI_API_KEY", "")
    ai._AI_CACHE.clear(); tts._CACHE.clear()
    for k in ("ok_count", "error_count", "fallback_count"):
        ai.AI_STATUS[k] = 0
    ai.AI_STATUS.update(last_ok_at=None, last_error=None, last_error_at=None)
    yield
    config.get_settings.cache_clear()


def with_key(monkeypatch, key="AIzaSyDUMMYDUMMYDUMMYDUMMYDUMMY123456"):
    config.get_settings.cache_clear()
    monkeypatch.setenv("GEMINI_API_KEY", key)


def worker(wid="w-1"):
    c = TestClient(app); c.cookies.set("worker_session", create_worker_session_token(wid)); return c


def admin():
    c = TestClient(app); c.cookies.set("admin_session", create_admin_session_token()); return c


PAYSLIP = {"worker_name": "Rajesh", "worker_id": "w-cache", "net_pay": 16000, "regular_hours": 96.0,
           "overtime_hours": 10.5, "base_pay": 15360, "overtime_pay": 3360, "total_deductions": 1984}


# ------------- a failed Gemini call must never poison the cache -------------
def test_payslip_fallback_is_not_cached_so_gemini_recovers():
    boom = AsyncMock(side_effect=RuntimeError("quota"))
    with patch.object(ai, "_execute_gemini_call", boom):
        text1, src1 = asyncio.run(ai.explain_payslip_ex(PAYSLIP, "hi"))
    assert src1 == "fallback"
    good = AsyncMock(return_value="नमस्ते राजेश, आपका वेतन ₹16,000 है।")
    with patch.object(ai, "_execute_gemini_call", good):
        text2, src2 = asyncio.run(ai.explain_payslip_ex(PAYSLIP, "hi"))
    assert src2 == "gemini" and text2.startswith("नमस्ते राजेश") and good.await_count == 1
    with patch.object(ai, "_execute_gemini_call", boom):          # now cached from the REAL answer
        assert asyncio.run(ai.explain_payslip_ex(PAYSLIP, "hi")) == (text2, "gemini")


def test_triage_fallback_not_cached_and_tagged():
    with patch.object(ai, "_execute_gemini_call", AsyncMock(side_effect=RuntimeError("x"))):
        a = asyncio.run(ai.triage_safety_report("exposed wiring near crane", "en"))
    assert a["ai_source"] == "fallback"
    ok = '{"category":"hazard","severity":"critical","summary_en":"Exposed wiring","summary_local":"Exposed wiring"}'
    with patch.object(ai, "_execute_gemini_call", AsyncMock(return_value=ok)):
        b = asyncio.run(ai.triage_safety_report("exposed wiring near crane", "en"))
    assert b["ai_source"] == "gemini" and b["severity"] == "critical"


def test_explain_endpoint_reports_its_source():
    r = worker().post("/api/v1/worker/payslip/explain", json={"language": "mr"}).json()
    assert r["source"] == "fallback"                                      # no key => honest offline label
    with patch.object(ai, "_execute_gemini_call", AsyncMock(return_value="नमस्कार राजेश, तुमचा पगार ठीक आहे.")):
        r2 = worker("w-2").post("/api/v1/worker/payslip/explain", json={"language": "mr"}).json()
    assert r2["source"] == "gemini" and "नमस्कार" in r2["explanation"]


# ------------- AI status + self-test (what the admin 'Test AI now' button uses) -------------
def test_ai_status_reports_unconfigured_without_leaking_anything():
    r = admin().get("/api/v1/admin/ai-status").json()
    assert r["configured"] is False and r["model"] and "key" not in str(r).lower().replace("gemini_api_key", "")


def test_ai_status_counts_real_call_outcomes(monkeypatch):
    with_key(monkeypatch)
    with patch.object(ai, "_call_gemini_with_retry", AsyncMock(return_value="hello")):
        asyncio.run(ai._execute_gemini_call("x"))
    with patch.object(ai, "_call_gemini_with_retry", AsyncMock(side_effect=RuntimeError("429 quota"))):
        with pytest.raises(RuntimeError):
            asyncio.run(ai._execute_gemini_call("x"))
    st = admin().get("/api/v1/admin/ai-status").json()
    assert st["configured"] is True and st["ok_count"] == 1 and st["error_count"] == 1
    assert "429 quota" in st["last_error"]


def test_selftest_ok_failed_and_unconfigured(monkeypatch):
    c = admin()
    r = c.post("/api/v1/admin/ai-selftest").json()
    assert r["ok"] is False and r["configured"] is False and "GEMINI_API_KEY" in r["error"]

    with_key(monkeypatch)
    with patch.object(ai, "_call_gemini_with_retry", AsyncMock(return_value="ready")):
        r = c.post("/api/v1/admin/ai-selftest").json()
    assert r["ok"] is True and r["latency_ms"] >= 0 and r["error"] is None

    leaky = RuntimeError("API key not valid: AIzaSyDUMMYDUMMYDUMMYDUMMYDUMMY123456")
    with patch.object(ai, "_call_gemini_with_retry", AsyncMock(side_effect=leaky)):
        r = c.post("/api/v1/admin/ai-selftest").json()
    assert r["ok"] is False and "AIza" not in r["error"] and "[redacted]" in r["error"]


def test_ai_admin_endpoints_require_admin():
    anon = TestClient(app)
    assert anon.get("/api/v1/admin/ai-status").status_code == 401
    assert anon.post("/api/v1/admin/ai-selftest").status_code == 401
    assert worker().get("/api/v1/admin/ai-status").status_code == 401     # a worker cookie is not an admin


# ------------- server-side voice -------------
PCM = b"\x00\x01" * 2400   # 0.1 s of 24 kHz mono audio


def test_speak_returns_valid_wav_and_caches(monkeypatch):
    with_key(monkeypatch)
    fake = AsyncMock(return_value=PCM)
    with patch.object(tts, "_tts_pcm", fake):
        c = worker()
        r = c.post("/api/v1/worker/speak", json={"text": "तुमचा पगार ठीक आहे", "language": "mr"})
        r2 = c.post("/api/v1/worker/speak", json={"text": "तुमचा पगार ठीक आहे", "language": "mr"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    assert r.content[:4] == b"RIFF" and r.content[8:12] == b"WAVE" and len(r.content) == 44 + len(PCM)
    assert r2.content == r.content and fake.await_count == 1             # second request served from cache


def test_speak_unavailable_validation_and_auth(monkeypatch):
    c = worker()
    assert c.post("/api/v1/worker/speak", json={"text": "hi", "language": "en"}).status_code == 503   # no key
    with_key(monkeypatch)
    with patch.object(tts, "_tts_pcm", AsyncMock(side_effect=RuntimeError("model overloaded"))):
        assert c.post("/api/v1/worker/speak", json={"text": "hi", "language": "en"}).status_code == 503
    assert tts._CACHE == {}                                                                          # failures are not cached
    assert c.post("/api/v1/worker/speak", json={"text": "", "language": "en"}).status_code == 422
    assert c.post("/api/v1/worker/speak", json={"text": "x" * 1501, "language": "en"}).status_code == 422
    assert c.post("/api/v1/worker/speak", json={"text": "hi", "language": "xx"}).status_code == 422
    assert TestClient(app).post("/api/v1/worker/speak", json={"text": "hi", "language": "en"}).status_code == 401


def test_speak_is_rate_limited(monkeypatch):
    with_key(monkeypatch)
    with patch.object(tts, "_tts_pcm", AsyncMock(return_value=PCM)):
        c = worker()
        codes = [c.post("/api/v1/worker/speak", json={"text": f"t{i}", "language": "hi"}).status_code for i in range(32)]
    assert codes[:30] == [200] * 30 and codes[30] == 429


# ------------- safety reports remember their language + source; seed data is classified -------------
def test_new_reports_store_language_and_ai_source():
    c = worker()
    r = c.post("/api/v1/worker/safety-reports", json={"input_text": "wire hanging near scaffold", "language": "ta"}).json()
    assert r["language"] == "ta" and r["ai_source"] == "fallback"
    ok = '{"category":"ppe","severity":"high","summary_en":"No helmet","summary_local":"தலைக்கவசம் இல்லை"}'
    with patch.object(ai, "_execute_gemini_call", AsyncMock(return_value=ok)):
        r2 = c.post("/api/v1/worker/safety-reports", json={"input_text": "no helmet on 3rd floor", "language": "ta"}).json()
    assert r2["ai_source"] == "gemini" and r2["language"] == "ta"


def test_seeded_reports_have_correct_language_and_chain_still_valid():
    reps = get_repository().get_report_chain()
    langs = {r.language for r in reps}
    assert langs <= {"en", "hi", "ta"} and {"hi", "ta"} & langs
    assert all(r.ai_source == "manual" for r in reps)
    assert verify_chain(reps)["valid"] is True
    r = get_repository().get_report_chain()[0]
    r.language = "bn"; r.ai_source = "gemini"                            # provenance fields are not part of the hash
    assert verify_chain(get_repository().get_report_chain())["valid"] is True


def test_detect_language_by_script():
    assert detect_language("நோயாளி") == "ta" and detect_language("मदद") == "hi" and detect_language("ভয়") == "bn"
    assert detect_language("మంచి") == "te" and detect_language("ಕನ್ನಡ") == "kn" and detect_language("മലയാളം") == "ml"
    assert detect_language("ગુજરાતી") == "gu" and detect_language("plain english ₹100") == "en" and detect_language("") == "en"


# ------------- impact card: a percentage can never exceed 100 (screenshot showed 337.5 'per 100') -------------
def test_impact_reports_percent_of_workers_at_risk_not_alerts_per_100():
    r = admin().get("/api/v1/admin/impact?workers=1000").json()
    assert "fatigue_alerts_per_100_workers" not in r
    assert 0 <= r["workers_at_fatigue_risk_percent"] <= 100
