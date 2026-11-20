"""Single source of truth for supported languages.

Everything language-related (request validation, AI prompts, offline fallbacks, text-to-speech tags)
reads from here. To add a language: add a Language entry + FALLBACKS entry, add static/i18n/<code>.json,
add an <option> in static/worker.html and the JSON to static/sw.js. tests/test_languages.py fails if any
of those is forgotten.
"""
from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class Language:
    code: str
    native: str    # shown in the language dropdown
    english: str   # used in AI prompts
    speech: str    # BCP-47 tag for browser speech recognition / synthesis


LANGUAGES: Dict[str, Language] = {l.code: l for l in (
    Language("en", "English", "English", "en-IN"),
    Language("hi", "हिंदी", "Hindi", "hi-IN"),
    Language("ta", "தமிழ்", "Tamil", "ta-IN"),
    Language("bn", "বাংলা", "Bengali", "bn-IN"),
    Language("te", "తెలుగు", "Telugu", "te-IN"),
    Language("mr", "मराठी", "Marathi", "mr-IN"),
    Language("kn", "ಕನ್ನಡ", "Kannada", "kn-IN"),
    Language("ml", "മലയാളം", "Malayalam", "ml-IN"),
    Language("gu", "ગુજરાતી", "Gujarati", "gu-IN"),
)}

DEFAULT_LANGUAGE = "en"
LANGUAGE_PATTERN = "^(" + "|".join(LANGUAGES) + ")$"


def normalize(code: str) -> str:
    """Return a supported language code, falling back to English."""
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


def speech_tag(code: str) -> str:
    return LANGUAGES[normalize(code)].speech


def prompt_label(code: str) -> str:
    """e.g. 'Bengali (bn)' for use inside LLM prompts."""
    lang = LANGUAGES[normalize(code)]
    return f"{lang.english} ({lang.code})"


# Offline / AI-down fallback texts for languages that have no hand-written branch in ai.py (hi, ta, en keep theirs).
# Placeholders: triage -> {category} {severity}; payslip -> {name} {reg} {base} {ot_h} {ot_pay} {ded} {net}
FALLBACKS: Dict[str, Dict[str, str]] = {
    "bn": {
        "triage": "নিরাপত্তা রিপোর্ট নথিভুক্ত: বিভাগ {category}, গুরুত্ব {severity}। তাৎক্ষণিক নজর দরকার।",
        "photo": "ফটোতে সম্ভাব্য নিরাপত্তা ঝুঁকি। অনুগ্রহ করে এখনই সাইট ইঞ্জিনিয়ারকে দিয়ে পরীক্ষা করান।",
        "payslip": "নমস্কার {name}! আপনার বেতনের সহজ বিবরণ: আপনি {reg} ঘণ্টা নিয়মিত কাজ করেছেন, মূল আয় ₹{base}। আপনি {ot_h} ঘণ্টা ওভারটাইম করেছেন, ২ গুণ ন্যায্য হারে পেয়েছেন ₹{ot_pay}। ভবিষ্যৎ নিরাপত্তা ও চিকিৎসার (PF/ESI) জন্য ₹{ded} কাটা হয়েছে। আপনার মোট হাতে পাওয়া অর্থ ₹{net}। আপনার পরিশ্রমকে সম্মান!",
    },
    "te": {
        "triage": "భద్రతా నివేదిక నమోదైంది: వర్గం {category}, తీవ్రత {severity}. వెంటనే శ్రద్ధ అవసరం.",
        "photo": "ఫోటోలో సాధ్యమైన భద్రతా ప్రమాదం. దయచేసి వెంటనే సైట్ ఇంజనీర్‌తో తనిఖీ చేయించండి.",
        "payslip": "నమస్కారం {name}! మీ వేతన వివరాలు: మీరు {reg} గంటలు సాధారణ పని చేశారు, ప్రాథమిక సంపాదన ₹{base}. {ot_h} గంటలు ఓవర్‌టైమ్ చేశారు, 2 రెట్లు న్యాయమైన రేటుతో ₹{ot_pay} వచ్చింది. భవిష్యత్ భద్రత, వైద్యం (PF/ESI) కోసం ₹{ded} మినహాయించారు. మీ మొత్తం చేతికి వచ్చే వేతనం ₹{net}. మీ శ్రమకు గౌరవం!",
    },
    "mr": {
        "triage": "सुरक्षा अहवाल नोंदवला: श्रेणी {category}, तीव्रता {severity}. त्वरित लक्ष देणे आवश्यक.",
        "photo": "फोटोत संभाव्य सुरक्षा धोका. कृपया त्वरित साइट अभियंत्याकडून तपासणी करवा.",
        "payslip": "नमस्कार {name}! तुमच्या पगाराचा सोपा तपशील: तुम्ही {reg} तास नियमित काम केले, मूळ कमाई ₹{base}. तुम्ही {ot_h} तास ओव्हरटाइम केला, २ पट न्याय्य दराने ₹{ot_pay} मिळाले. भविष्यातील सुरक्षा व उपचारांसाठी (PF/ESI) ₹{ded} कापले गेले. तुमचा एकूण हातात येणारा पगार ₹{net}. तुमच्या कष्टाचा सन्मान!",
    },
    "kn": {
        "triage": "ಸುರಕ್ಷತಾ ವರದಿ ದಾಖಲಾಗಿದೆ: ವರ್ಗ {category}, ತೀವ್ರತೆ {severity}. ತಕ್ಷಣ ಗಮನ ಅಗತ್ಯ.",
        "photo": "ಫೋಟೋದಲ್ಲಿ ಸಂಭವನೀಯ ಸುರಕ್ಷತಾ ಅಪಾಯ. ದಯವಿಟ್ಟು ತಕ್ಷಣ ಸೈಟ್ ಎಂಜಿನಿಯರ್‌ರಿಂದ ಪರಿಶೀಲಿಸಿ.",
        "payslip": "ನಮಸ್ಕಾರ {name}! ನಿಮ್ಮ ವೇತನದ ಸರಳ ವಿವರ: ನೀವು {reg} ಗಂಟೆ ನಿಯಮಿತ ಕೆಲಸ ಮಾಡಿದ್ದೀರಿ, ಮೂಲ ಗಳಿಕೆ ₹{base}. {ot_h} ಗಂಟೆ ಓವರ್‌ಟೈಮ್ ಮಾಡಿದ್ದೀರಿ, 2 ಪಟ್ಟು ನ್ಯಾಯಯುತ ದರದಲ್ಲಿ ₹{ot_pay} ಸಿಕ್ಕಿದೆ. ಭವಿಷ್ಯದ ಭದ್ರತೆ ಮತ್ತು ಚಿಕಿತ್ಸೆಗಾಗಿ (PF/ESI) ₹{ded} ಕಡಿತವಾಗಿದೆ. ನಿಮ್ಮ ಒಟ್ಟು ಕೈಗೆ ಬರುವ ವೇತನ ₹{net}. ನಿಮ್ಮ ಶ್ರಮಕ್ಕೆ ಗೌರವ!",
    },
    "ml": {
        "triage": "സുരക്ഷാ റിപ്പോർട്ട് രേഖപ്പെടുത്തി: വിഭാഗം {category}, തീവ്രത {severity}. ഉടൻ ശ്രദ്ധ ആവശ്യം.",
        "photo": "ഫോട്ടോയിൽ സാധ്യമായ സുരക്ഷാ അപകടം. ദയവായി ഉടൻ സൈറ്റ് എൻജിനീയറെ കൊണ്ട് പരിശോധിപ്പിക്കുക.",
        "payslip": "നമസ്കാരം {name}! നിങ്ങളുടെ ശമ്പളത്തിന്റെ ലളിത വിവരം: നിങ്ങൾ {reg} മണിക്കൂർ സാധാരണ ജോലി ചെയ്തു, അടിസ്ഥാന വരുമാനം ₹{base}. {ot_h} മണിക്കൂർ ഓവർടൈം ചെയ്തു, 2 മടങ്ങ് ന്യായ നിരക്കിൽ ₹{ot_pay} ലഭിച്ചു. ഭാവി സുരക്ഷയ്ക്കും ചികിത്സയ്ക്കുമായി (PF/ESI) ₹{ded} കിഴിച്ചു. നിങ്ങളുടെ ആകെ കൈയിൽ കിട്ടുന്ന ശമ്പളം ₹{net}. നിങ്ങളുടെ അധ്വാനത്തിന് ആദരം!",
    },
    "gu": {
        "triage": "સુરક્ષા રિપોર્ટ નોંધાયો: શ્રેણી {category}, ગંભીરતા {severity}. તાત્કાલિક ધ્યાન જરૂરી.",
        "photo": "ફોટામાં સંભવિત સુરક્ષા જોખમ. કૃપા કરીને તરત સાઇટ એન્જિનિયર પાસે તપાસ કરાવો.",
        "payslip": "નમસ્તે {name}! તમારા પગારની સરળ વિગત: તમે {reg} કલાક નિયમિત કામ કર્યું, મૂળ કમાણી ₹{base}. તમે {ot_h} કલાક ઓવરટાઇમ કર્યો, 2 ગણા ન્યાયી દરે ₹{ot_pay} મળ્યા. ભવિષ્યની સુરક્ષા અને સારવાર (PF/ESI) માટે ₹{ded} કપાયા. તમારો કુલ હાથમાં આવતો પગાર ₹{net}. તમારી મહેનતનું સન્માન!",
    },
}
