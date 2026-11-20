"""Guards against the classic i18n breakages: missing keys, untranslated strings, forgotten dropdown
options, stale service-worker cache lists, and AI/fallback paths that only knew hi/ta."""
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.languages import FALLBACKS, LANGUAGES, LANGUAGE_PATTERN, normalize, prompt_label, speech_tag
from app.main import app
from app.repository import get_repository
from app.security import create_worker_session_token
from app.seed import seed_database

ROOT = Path(__file__).resolve().parent.parent
I18N = {c: json.loads((ROOT / "static/i18n" / f"{c}.json").read_text(encoding="utf-8")) for c in LANGUAGES}
SCRIPT = {  # expected Unicode block per language (English has none)
    "hi": "\u0900-\u097F", "mr": "\u0900-\u097F", "bn": "\u0980-\u09FF", "gu": "\u0A80-\u0AFF",
    "ta": "\u0B80-\u0BFF", "te": "\u0C00-\u0C7F", "kn": "\u0C80-\u0CFF", "ml": "\u0D00-\u0D7F",
}
NON_EN = [c for c in LANGUAGES if c != "en"]
PLACEHOLDER = re.compile(r"\{\w+\}")


@pytest.fixture(autouse=True)
def _db():
    seed_database(get_repository())


@pytest.fixture(autouse=True)
def _no_gemini(monkeypatch):
    """Force the offline-fallback path so tests are deterministic and never call the network."""
    from app import config
    config.get_settings.cache_clear()
    monkeypatch.setenv("GEMINI_API_KEY", "")
    yield
    config.get_settings.cache_clear()


def worker_client(wid="w-1"):
    c = TestClient(app)
    c.cookies.set("worker_session", create_worker_session_token(wid))
    return c


def has_script(text, code):
    return re.search(f"[{SCRIPT[code]}]", text) is not None


# ---------------- registry ----------------
def test_at_least_five_new_languages_beyond_original_three():
    assert len(LANGUAGES) - 3 >= 5
    assert {"en", "hi", "ta"} <= set(LANGUAGES)


def test_registry_helpers():
    assert normalize("bn") == "bn" and normalize("xx") == "en" and normalize("") == "en"
    assert speech_tag("ml") == "ml-IN" and speech_tag("zz") == "en-IN"
    assert prompt_label("te") == "Telugu (te)"
    assert re.match(LANGUAGE_PATTERN, "gu") and not re.match(LANGUAGE_PATTERN, "xx")
    assert not re.match(LANGUAGE_PATTERN, "en|hi")          # pattern must be anchored


# ---------------- UI bundles ----------------
@pytest.mark.parametrize("code", NON_EN)
def test_bundle_has_exactly_the_english_keys(code):
    assert set(I18N[code]) == set(I18N["en"]), set(I18N["en"]) ^ set(I18N[code])


@pytest.mark.parametrize("code", NON_EN)
def test_placeholders_preserved(code):
    for k, v in I18N["en"].items():
        assert sorted(PLACEHOLDER.findall(I18N[code][k])) == sorted(PLACEHOLDER.findall(v)), (code, k)


@pytest.mark.parametrize("code", NON_EN)
def test_bundle_is_really_translated(code):
    """>=95% of strings must contain the language's own script (catches pasted-English bundles)."""
    brand = {"app_name"}
    vals = [v for k, v in I18N[code].items() if k not in brand]
    ok = sum(has_script(v, code) for v in vals)
    assert ok / len(vals) >= 0.95, f"{code}: only {ok}/{len(vals)} strings in native script"
    assert all(v.strip() for v in I18N[code].values()), "empty string found"


def test_trailing_space_keys_kept():
    for code in LANGUAGES:
        assert I18N[code]["r3_photo_fail"].endswith(": ") or I18N[code]["r3_photo_fail"].endswith(" ")
        assert I18N[code]["r3_wage_cause"].endswith(" ")


def test_dropdown_cache_and_speech_in_sync_with_registry():
    html = (ROOT / "static/worker.html").read_text(encoding="utf-8")
    select = re.search(r'<select id="langSelector".*?</select>', html, re.S).group(0)
    options = dict(re.findall(r'<option value="(\w+)">([^<]+)</option>', select))
    assert options == {c: l.native for c, l in LANGUAGES.items()}

    sw = (ROOT / "static/sw.js").read_text(encoding="utf-8")
    for c in LANGUAGES:
        assert f"/static/i18n/{c}.json" in sw, f"service worker does not cache {c}"

    js = (ROOT / "static/js/worker.js").read_text(encoding="utf-8")
    m = re.search(r"const SPEECH_LANG = \{(.*?)\};", js, re.S)
    declared = dict(re.findall(r"(\w+):\s*'([\w-]+)'", m.group(1)))
    assert declared == {c: l.speech for c, l in LANGUAGES.items()}


# ---------------- backend fallbacks (AI down) ----------------
def test_every_new_language_has_all_three_fallbacks():
    for c in NON_EN:
        if c in ("hi", "ta"):
            continue
        assert set(FALLBACKS[c]) == {"triage", "photo", "payslip"}, c
        assert has_script(FALLBACKS[c]["triage"], c) and has_script(FALLBACKS[c]["payslip"], c)


@pytest.mark.parametrize("code", NON_EN)
def test_explain_payslip_in_every_language_without_ai(code):
    r = worker_client().post("/api/v1/worker/payslip/explain", json={"language": code})
    assert r.status_code == 200
    d = r.json()
    assert d["language"] == code and d["speech_lang"] == LANGUAGES[code].speech
    assert has_script(d["explanation"], code), d["explanation"]
    assert "{" not in d["explanation"] and "₹" in d["explanation"]   # template fully filled


@pytest.mark.parametrize("code", NON_EN)
def test_safety_triage_summary_local_per_language(code):
    r = worker_client().post("/api/v1/worker/safety-reports",
                             json={"input_text": "loose scaffolding near the edge", "language": code})
    assert r.status_code == 200
    local = r.json()["summary_local"]
    assert has_script(local, code) and "{" not in local


@pytest.mark.parametrize("code", NON_EN)
def test_photo_fallback_per_language(code):
    jpeg = b"\xff\xd8\xff\xe0" + code.encode() * 8
    r = worker_client().post("/api/v1/worker/hazard-photo", data={"language": code},
                             files={"photo": ("a.jpg", jpeg, "image/jpeg")})
    assert r.status_code == 200 and has_script(r.json()["summary_local"], code)


def test_unknown_language_is_rejected_or_defaults_safely():
    c = worker_client()
    assert c.post("/api/v1/worker/payslip/explain", json={"language": "xx"}).status_code == 422
    assert c.post("/api/v1/worker/payslip/explain", json={"language": "en|hi"}).status_code == 422
    jpeg = b"\xff\xd8\xff\xe0unknown-lang"
    r = c.post("/api/v1/worker/hazard-photo", data={"language": "xx"}, files={"photo": ("a.jpg", jpeg, "image/jpeg")})
    assert r.status_code == 200 and r.json()["summary_local"].isascii()   # unknown code => English


# ---------------- AI prompts name the right language ----------------
@pytest.mark.parametrize("code", NON_EN)
def test_gemini_prompts_name_the_language_and_script(code, monkeypatch):
    seen = []

    async def fake(prompt, image=None):
        seen.append(prompt)
        return '{"category":"hazard","severity":"low","summary_en":"ok","summary_local":"ok"}'

    c = worker_client()
    with patch("app.services.ai._execute_gemini_call", new=AsyncMock(side_effect=fake)):
        c.post("/api/v1/worker/safety-reports", json={"input_text": f"triage-{code}", "language": code})
        c.post("/api/v1/worker/hazard-photo", data={"language": code},
               files={"photo": ("a.jpg", b"\xff\xd8\xff\xe0" + f"p-{code}".encode(), "image/jpeg")})
    assert len(seen) == 2
    label = prompt_label(code)
    for p in seen:
        assert label in p, (code, p[:200])
        assert "{prompt_label" not in p                     # f-string was actually evaluated
        assert "hi=Hindi" not in p and "ta=Tamil" not in p  # old hard-coded 3-language hint is gone
