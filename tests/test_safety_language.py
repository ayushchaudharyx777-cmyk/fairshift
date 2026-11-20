"""Safety reports: the local-language summary must come back in the requested script (English-only
Gemini replies are replaced by the native fallback), and the Safety tab must offer a language picker."""
import asyncio
import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.languages import has_native_script
from app.services import ai

ROOT = Path(__file__).resolve().parent.parent


def test_english_local_summary_is_replaced_for_tamil():
    reply = ('{"category":"ppe","severity":"high","summary_en":"Helmet missing on site.",'
             '"summary_local":"Helmet missing on site."}')
    with patch.object(ai, "_execute_gemini_call", AsyncMock(return_value=reply)):
        result = asyncio.run(ai.triage_safety_report("helmet missing on site", "ta"))
    assert result["category"] == "ppe" and result["severity"] == "high"  # Gemini's classification is kept
    assert result["summary_en"] == "Helmet missing on site."
    assert has_native_script(result["summary_local"]), result["summary_local"]


def test_native_local_summary_is_kept():
    native = "ஹெல்மெட் இல்லை."
    reply = ('{"category":"ppe","severity":"high","summary_en":"Helmet missing.",'
             f'"summary_local":"{native}"}}')
    with patch.object(ai, "_execute_gemini_call", AsyncMock(return_value=reply)):
        result = asyncio.run(ai.triage_safety_report("helmet missing for tamil", "ta"))
    assert result["summary_local"] == native


def test_safety_tab_has_language_picker_wired_up():
    html = (ROOT / "static/worker.html").read_text(encoding="utf-8")
    js = (ROOT / "static/js/worker.js").read_text(encoding="utf-8")
    safety = re.search(r'<section id="tabSafety".*?</section>', html, re.S)
    assert safety and 'id="safetyLangSelector"' in safety.group(0)
    assert "safetyLangSelector" in js and "[explainLangSelector, safetyLangSelector]" in js
