import json
import logging
import asyncio
import re
from typing import Dict, Any, Optional
from google import genai
from app.config import get_settings

logger = logging.getLogger("fairshift.ai")

# In-memory LRU cache for AI results to avoid redundant calls
_AI_CACHE: Dict[str, Any] = {}
_MAX_CACHE_SIZE = 256


def _get_from_cache(cache_key: str) -> Optional[Any]:
    if cache_key in _AI_CACHE:
        return _AI_CACHE[cache_key]
    return None


def _put_in_cache(cache_key: str, value: Any):
    if len(_AI_CACHE) >= _MAX_CACHE_SIZE:
        # Evict oldest entry
        oldest = next(iter(_AI_CACHE))
        _AI_CACHE.pop(oldest, None)
    _AI_CACHE[cache_key] = value


def _clean_json_markdown(text: str) -> str:
    """Clean markdown code fences from JSON output if returned."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


# Fallback intelligent triage for safety reports when AI is offline or without key
def fallback_safety_triage(text: str, language: str = "en") -> Dict[str, Any]:
    text_lower = text.lower()
    
    # Keyword analysis for severity & category
    category = "hazard"
    severity = "medium"

    if any(k in text_lower for k in ["collapse", "fall", "electric", "shock", "fire", "blood", "gas", "explosion", "scaffold loose", "head injury", "oxygen failure"]):
        severity = "critical"
        category = "hazard"
    elif any(k in text_lower for k in ["ppe", "helmet", "boots", "gloves", "mask", "goggles", "shield", "safety harness"]):
        category = "ppe"
        severity = "high" if "missing" in text_lower or "broken" in text_lower or "no" in text_lower else "medium"
    elif any(k in text_lower for k in ["crane", "drill", "machine", "lift", "elevator", "ventilator", "monitor", "equipment"]):
        category = "equipment"
        severity = "high" if "smoke" in text_lower or "spark" in text_lower or "stuck" in text_lower else "medium"
    elif any(k in text_lower for k in ["faint", "tired", "sleep", "dizzy", "fatigue", "exhausted", "continuous", "14 hour", "16 hour"]):
        category = "fatigue"
        severity = "high"
    elif any(k in text_lower for k in ["water", "leak", "slip", "dirty", "trash", "sanitation", "toilet", "washroom"]):
        category = "sanitation"
        severity = "low"

    summary_en = f"Safety observation reported: {text[:140]}..." if len(text) > 140 else f"Safety observation: {text}"
    
    # Local summary based on requested language
    if language == "hi":
        summary_local = f"सुरक्षा रिपोर्ट दर्ज: श्रेणी {category.upper()}, गंभीरता {severity.upper()}। तुरंत ध्यान देने योग्य।"
    elif language == "ta":
        summary_local = f"பாதுகாப்பு அறிக்கை பதிவு செய்யப்பட்டது: பிரிவு {category.upper()}, தீவிரத்தன்மை {severity.upper()}."
    else:
        summary_local = summary_en

    return {
        "category": category,
        "severity": severity,
        "summary_en": summary_en,
        "summary_local": summary_local
    }


# Fallback payslip explanation
def fallback_payslip_explanation(payslip_dict: Dict[str, Any], language: str = "en") -> str:
    worker_name = payslip_dict.get("worker_name", "Worker")
    reg_hrs = payslip_dict.get("regular_hours", 0)
    ot_hrs = payslip_dict.get("overtime_hours", 0)
    base_pay = payslip_dict.get("base_pay", 0)
    ot_pay = payslip_dict.get("overtime_pay", 0)
    deductions = payslip_dict.get("total_deductions", 0)
    net_pay = payslip_dict.get("net_pay", 0)

    if language == "hi":
        return (
            f"नमस्ते {worker_name} जी! आपके वेतन का सरल विवरण: आपने {reg_hrs} घंटे नियमित कार्य किया "
            f"जिसकी मूल कमाई ₹{base_pay:,.0f} बनी। आपने {ot_hrs} घंटे अतिरिक्त (ओवरटाइम) काम किया "
            f"जिसका आपको 2x निष्पक्ष दर से ₹{ot_pay:,.0f} मिला। "
            f"भविष्य की सुरक्षा और इलाज (PF/ESI) के लिए ₹{deductions:,.0f} कटे हैं। "
            f"आपका कुल नकद भुगतान ₹{net_pay:,.0f} है। आपकी निष्ठा और श्रम का सम्मान है!"
        )
    elif language == "ta":
        return (
            f"வணக்கம் {worker_name}! உங்கள் ஊதிய விவரம்: நீங்கள் {reg_hrs} மணிநேரம் வழக்கமான வேலை செய்துள்ளீர்கள், "
            f"அதற்கான தொகை ₹{base_pay:,.0f}. மேலும் {ot_hrs} மணிநேரம் கூடுதல் நேரம் (Overtime) உழைத்துள்ளீர்கள், "
            f"அதற்கு 2 மடங்கு நியாய ஊதியமாக ₹{ot_pay:,.0f} கிடைத்துள்ளது. "
            f"PF மற்றும் ESI பாதுகாப்பு சேமிப்பாக ₹{deductions:,.0f} பிடிக்கப்பட்டுள்ளது. "
            f"உங்கள் வங்கிக் கணக்கில் வரவு வைக்கப்படும் இறுதித் தொகை ₹{net_pay:,.0f} ஆகும். உங்கள் உழைப்புக்கு நன்றி!"
        )
    else:
        return (
            f"Hello {worker_name}! Here is your clear earnings summary: You completed {reg_hrs} standard hours "
            f"earning ₹{base_pay:,.0f} in regular pay. You contributed {ot_hrs} overtime hours, paid at the "
            f"guaranteed 2x FairShift rate amounting to ₹{ot_pay:,.0f}. "
            f"Statutory social security deductions (PF retirement + ESI healthcare) totaled ₹{deductions:,.0f}. "
            f"Your total net take-home pay is ₹{net_pay:,.0f}. Your hard work and safety are our top priority!"
        )


async def _execute_gemini_call(prompt: str) -> str:
    """Execute Gemini call with 10s timeout and 1 retry."""
    settings = get_settings()
    api_key = settings.GEMINI_API_KEY.strip()

    if not api_key or api_key in ["teri_key_yahan", "your_gemini_api_key_here"]:
        raise ValueError("Valid GEMINI_API_KEY is not configured")

    client = genai.Client(api_key=api_key)

    async def _single_attempt():
        response = await client.aio.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt
        )
        return response.text

    # Attempt 1 with 10s timeout
    try:
        return await asyncio.wait_for(_single_attempt(), timeout=10.0)
    except Exception as first_err:
        logger.warning(f"First Gemini attempt failed ({first_err}), retrying once...")
        await asyncio.sleep(1.0)
        # Attempt 2 (1 retry) with 10s timeout
        return await asyncio.wait_for(_single_attempt(), timeout=10.0)


async def triage_safety_report(text: str, language: str = "en") -> Dict[str, Any]:
    """
    Triage safety report with Gemini. Returns strict JSON:
    { "category": "...", "severity": "...", "summary_en": "...", "summary_local": "..." }
    """
    cache_key = f"safety:{language}:{text.strip().lower()}"
    cached = _get_from_cache(cache_key)
    if cached:
        return cached

    prompt = f"""You are the FairShift Safety Officer AI assisting shift workers in construction and hospitals (UN SDG 8 Decent Work & Safety).
Analyze the following worker incident report (which may be in English, Hindi, Tamil, or mixed):
"{text}"

Worker's preferred display language: {language} (en=English, hi=Hindi, ta=Tamil).

Return a STRICT JSON object with these EXACT keys and types:
- "category": one of ["ppe", "hazard", "equipment", "fatigue", "sanitation", "other"]
- "severity": one of ["low", "medium", "high", "critical"]
- "summary_en": a crisp 1-2 sentence factual English summary of what hazard occurred
- "summary_local": a clear, respectful 1-2 sentence summary written in the requested worker language ({language})

CRITICAL: Return ONLY valid JSON, with NO surrounding markdown commentary.
"""

    try:
        raw_text = await _execute_gemini_call(prompt)
        cleaned = _clean_json_markdown(raw_text)
        data = json.loads(cleaned)
        
        # Validate keys
        result = {
            "category": str(data.get("category", "hazard")).lower(),
            "severity": str(data.get("severity", "medium")).lower(),
            "summary_en": str(data.get("summary_en", text[:100])),
            "summary_local": str(data.get("summary_local", text[:100]))
        }
        if result["severity"] not in ["low", "medium", "high", "critical"]:
            result["severity"] = "medium"
        if result["category"] not in ["ppe", "hazard", "equipment", "fatigue", "sanitation", "other"]:
            result["category"] = "hazard"

        _put_in_cache(cache_key, result)
        return result
    except Exception as exc:
        logger.info(f"Using fallback safety triage due to: {exc}")
        result = fallback_safety_triage(text, language)
        _put_in_cache(cache_key, result)
        return result


async def explain_payslip(payslip_dict: Dict[str, Any], language: str = "en") -> str:
    """Generate empathetic multilingual explanation of payslip earnings and deductions."""
    cache_key = f"payslip:{language}:{payslip_dict.get('worker_id')}:{payslip_dict.get('net_pay')}"
    cached = _get_from_cache(cache_key)
    if cached:
        return cached

    worker_name = payslip_dict.get("worker_name", "Worker")
    site_name = payslip_dict.get("site_name", "Site")
    reg_hrs = payslip_dict.get("regular_hours", 0)
    ot_hrs = payslip_dict.get("overtime_hours", 0)
    base_pay = payslip_dict.get("base_pay", 0)
    ot_pay = payslip_dict.get("overtime_pay", 0)
    pf = payslip_dict.get("pf_deduction", 0)
    esi = payslip_dict.get("esi_deduction", 0)
    net_pay = payslip_dict.get("net_pay", 0)

    prompt = f"""You are the FairShift Voice Assistant supporting shift workers under UN SDG 8 (Decent Work & Fair Wages).
Explain this payslip to worker "{worker_name}" in their native language: {language} (en=English, hi=Hindi, ta=Tamil).
Details:
- Workplace: {site_name}
- Regular Hours: {reg_hrs}h, Regular Pay: ₹{base_pay}
- Overtime Hours: {ot_hrs}h, 2x Fair Overtime Pay: ₹{ot_pay}
- Deductions: Provident Fund (PF) ₹{pf}, ESI Healthcare ₹{esi}
- Net Take-Home Pay: ₹{net_pay}

Guidelines:
- Keep it under 4-5 warm, encouraging, conversational sentences.
- Make sure they understand that their overtime was properly paid at the legal 2x rate, and deductions are for their future retirement (PF) and healthcare (ESI).
- If language is hi, write in clear Hindi (Devanagari script).
- If language is ta, write in natural Tamil script.
- If language is en, write in clear simple English.
- Return ONLY the spoken text, no headings or markdown formatting.
"""

    try:
        explanation = await _execute_gemini_call(prompt)
        explanation = explanation.strip()
        _put_in_cache(cache_key, explanation)
        return explanation
    except Exception as exc:
        logger.info(f"Using fallback payslip explanation due to: {exc}")
        explanation = fallback_payslip_explanation(payslip_dict, language)
        _put_in_cache(cache_key, explanation)
        return explanation
