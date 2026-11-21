# FairShift: Technical Documentation

## 1. Overview
FairShift is a decent-work platform for shift workers (construction, hospitals), aligned with **UN SDG 8**.
It combines an automated 2x overtime engine, fatigue early-warning, multilingual voice + photo hazard
triage (Gemini), a wage-theft checker, tamper-evident safety logs, and portable skill passports.

## 2. Architecture
```mermaid
graph TD
  W[Worker PWA /worker] -->|REST + cookies| API
  A[Admin dashboard /admin] -->|REST + SSE| API
  P[Public Passport /passport/:token] --> API
  subgraph API[FastAPI, Python 3.12]
    MW[Security headers, JSON logs, AI rate limiter]
    R1[/api/v1/worker/*/] --- R2[/api/v1/admin/*/] --- R3[/api/v1/passport/*/]
    SSE[SSE event bus]
  end
  API --> S[Services: rules, payroll, fatigue, wagecheck, impact, integrity, ai]
  S -->|google-genai| G[Gemini 2.5 Flash: text + vision]
  API --> REPO[(In-memory repository)]
  REPO -->|write-through| DB[(SQLite local / Postgres prod)]
```

## 3. Tech stack
| Layer | Choice |
| :--- | :--- |
| Backend | FastAPI, Pydantic v2, Uvicorn, sse-starlette |
| AI | Google Gemini 2.5 Flash via `google-genai` (text triage, vision hazard detection, spoken payslip) |
| Data | In-memory repository + optional write-through persistence (SQLAlchemy 2: SQLite / Postgres via `DATABASE_URL`) |
| Frontend | Vanilla HTML/CSS tokens/ES6, PWA with service worker, IndexedDB offline queue |
| Quality | pytest (backend), `node --test` + jsdom (UI), GitHub Actions CI |
| Deploy | Docker on Render (Cloud Run compatible) |

## 4. Key APIs
| Method | Path | Auth | Purpose |
| :--- | :--- | :--- | :--- |
| POST | `/api/v1/worker/login` | none | Phone + PIN, HttpOnly session |
| POST | `/api/v1/worker/check-in` · `/check-out` | worker | Shift tracking; 2x OT split |
| GET | `/api/v1/worker/payslip` | worker | 14-day payslip (PF 12%, ESI 0.75%) |
| POST | `/api/v1/worker/payslip/explain` | worker | AI spoken explanation (en/hi/ta) |
| POST | `/api/v1/worker/safety-reports` | worker | Voice/text hazard triage |
| POST | `/api/v1/worker/hazard-photo` | worker | **Photo hazard (Gemini Vision)** |
| POST | `/api/v1/worker/wage-check` | worker | **Compare paid vs legal pay** |
| POST | `/api/v1/worker/speak` | worker | **Gemini text-to-speech (WAV) when the device has no voice** |
| GET | `/api/v1/worker/fatigue` · `/passport` | worker | Fatigue alerts, skill passport |
| GET | `/api/v1/admin/overview` · `/fatigue-alerts` · `/safety-kanban` | admin | Dashboards |
| GET | `/api/v1/admin/integrity-check` | admin | **Verify hash chain** |
| GET | `/api/v1/admin/impact?workers=N&theft_rate=r` | admin | **Impact model with stated assumptions** |
| GET | `/api/v1/admin/ai-status` | admin | **Is Gemini configured; ok / error / fallback counters** |
| POST | `/api/v1/admin/ai-selftest` | admin | **One real Gemini call; ok, latency, error** |
| GET | `/api/v1/admin/stream` | admin | SSE live alerts |
| GET | `/api/v1/passport/{token}` | public | Verifiable passport |

## 5. Languages (9)
English, Hindi, Tamil, Bengali, Telugu, Marathi, Kannada, Malayalam, Gujarati. `app/languages.py` is the single source of truth (code, native name, English name for AI prompts, BCP-47 speech tag, offline fallback texts). It drives API validation, Gemini prompts ("write in <language>, native script"), AI-down fallbacks, speech tags and the dropdown. **To add a language:** add it to `app/languages.py`, create `static/i18n/<code>.json`, add an `<option>` in `static/worker.html`, the JSON to `static/sw.js` and the tag to `SPEECH_LANG` in `static/js/worker.js`. `tests/test_languages.py` fails if any step is missed (key parity, placeholders, real native script, dropdown, service-worker cache, speech tags). Translations for the six newer languages are first-pass and should be reviewed by native speakers before a real deployment.

## 5b. Design decisions
- **Tamper-evident log:** each report stores `prev_hash` and `hash = SHA-256(prev_hash | canonical content)`. Workflow fields (status) are excluded so resolving a card never breaks the chain; editing or deleting content does. Verified again after DB restore.
- **Honest AI:** every AI result carries a `source` (`gemini` / `fallback`); fallbacks are never cached, so a transient failure cannot stick; the admin dashboard shows live status. See `AI_TESTING.md`.
- **Resilient AI:** every Gemini call has a 10 s timeout, one retry, a cache and a labelled fallback, so a demo never fails on API errors. Model output is validated against enums before use.
- **Safe uploads:** file type is detected from magic bytes (client content-type is ignored), 5 MB cap, JPEG/PNG/WebP only.
- **Offline-first reporting:** failed or offline photo reports are stored in IndexedDB and auto-synced; permanent rejections (400/413/415/422) are dropped, transient ones (401/429/5xx/network) retried.
- **Privacy:** anonymous feedback stores no worker ID; UI renders server text with `textContent` only (no `innerHTML`).
- **Persistence never blocks a request:** writes go through one ordered background thread (slow remote Postgres cannot stall API/SSE); DB errors are logged, not raised; unreachable DB at startup falls back to in-memory; queued writes finish on shutdown.

## 6. Deployment
1. Render → Docker web service from `main`.
2. Env vars: `GEMINI_API_KEY` (optional `GEMINI_MODEL`, `GEMINI_TTS_MODEL`, `GEMINI_TTS_VOICE`), `ADMIN_PIN`, `SESSION_SECRET`, optional `DATABASE_URL` (Neon/Supabase Postgres, e.g. `postgresql://user:pass@host/db`).
3. Without `DATABASE_URL` the app runs in memory (demo data re-seeded on each start).
4. Health check: `GET /health`.

## 7. Testing
`pytest -q` (127 tests) runs backend tests (rules, payroll, fatigue, security, hash chain, photo, wage check, impact, persistence incl. restart + DB-tamper detection). `cd tests/ui && npm test` (33 tests) runs UI tests (offline queue, i18n for all 9 languages, XSS safety, admin badge).

## 8. Known limitations / future scope
Persistence is a JSON-document mirror (fine for demo scale; a normalised schema is next). Admin uses a shared PIN (role-based JWT planned). Overtime consent capture and quarterly OT cap are planned (see `LABOUR_LAW_MAPPING.md`). Pilot with a contractor/NGO to validate wage-check on real payslips.
