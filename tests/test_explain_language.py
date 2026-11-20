"""Payslip explanation must come back in the requested script; an English reply for a native-language
request is rejected and replaced by the native fallback text."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.languages import has_native_script, LANGUAGES
from app.services import ai

PAYSLIP = {
    "worker_name": "Rajesh Kumar", "worker_id": "w-explain-lang", "net_pay": 16736,
    "regular_hours": 96.0, "overtime_hours": 10.5, "base_pay": 15360, "overtime_pay": 3360,
    "total_deductions": 1984, "site_name": "Skyline Construction Site",
}


def test_has_native_script_detects_indic_text_only():
    assert has_native_script("வணக்கம் ராஜேஷ்")
    assert has_native_script("नमस्ते")
    assert has_native_script("নমস্কার")
    assert not has_native_script("Hello Rajesh! You earned ₹15,360.")
    assert not has_native_script("")


@pytest.mark.parametrize("code", [c for c in LANGUAGES if c != "en"])
def test_english_reply_is_replaced_by_native_fallback(code):
    english = "Hello Rajesh! Your overtime was paid at the 2x rate."
    with patch.object(ai, "_execute_gemini_call", AsyncMock(return_value=english)):
        text = asyncio.run(ai.explain_payslip({**PAYSLIP, "worker_id": f"w-{code}"}, code))
    assert text != english
    assert has_native_script(text), (code, text)


def test_native_reply_is_kept_as_is():
    tamil = "வணக்கம் ராஜேஷ்! உங்கள் ஊதியம் சரியாக வழங்கப்பட்டுள்ளது."
    with patch.object(ai, "_execute_gemini_call", AsyncMock(return_value=tamil)):
        text = asyncio.run(ai.explain_payslip({**PAYSLIP, "worker_id": "w-ta-ok"}, "ta"))
    assert text == tamil


def test_english_language_keeps_english_reply():
    english = "Hello Rajesh! Your overtime was paid at the 2x rate."
    with patch.object(ai, "_execute_gemini_call", AsyncMock(return_value=english)):
        text = asyncio.run(ai.explain_payslip({**PAYSLIP, "worker_id": "w-en-ok"}, "en"))
    assert text == english
