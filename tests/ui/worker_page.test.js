// Drives the REAL worker.html + worker.js + round3.js in jsdom (network mocked) to reproduce the reported bugs.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const { IDBFactory } = require('fake-indexeddb');

const ROOT = path.join(__dirname, '../..');
const HTML = fs.readFileSync(path.join(ROOT, 'static/worker.html'), 'utf8').replace(/<script[\s\S]*?<\/script>/g, '');
const WORKER_JS = fs.readFileSync(path.join(ROOT, 'static/js/worker.js'), 'utf8');
const ROUND3_JS = fs.readFileSync(path.join(ROOT, 'static/js/round3.js'), 'utf8');
const I18N = (l) => JSON.parse(fs.readFileSync(path.join(ROOT, `static/i18n/${l}.json`), 'utf8'));
const tick = (ms = 30) => new Promise((r) => setTimeout(r, ms));
const res = (status, body, extra = {}) => ({ ok: status >= 200 && status < 300, status, json: async () => body, blob: async () => new Blob(['RIFFxxxxWAVE']), ...extra });

const REPORTS = [
  { id: 'a', category: 'hazard', severity: 'critical', summary_en: 'Loose scaffolding on 4th floor', summary_local: 'தளர்வான சாரக்கட்டு', language: 'ta', status: 'Reported', created_at: '2026-11-21T01:00:00Z', ai_source: 'manual' },
  { id: 'b', category: 'ppe', severity: 'high', summary_en: 'No helmet near the edge', summary_local: 'हेलमेट नहीं है', language: 'hi', status: 'Resolved', created_at: '2026-11-21T02:00:00Z', ai_source: 'gemini' },
];

async function boot({ lang = 'en', voices = [], explain, speak } = {}) {
  const dom = new JSDOM(HTML, { url: 'http://localhost/worker', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.localStorage.setItem('fairshift_lang', lang);
  w.indexedDB = new IDBFactory();
  w.FormData = globalThis.FormData;
  w.matchMedia = w.matchMedia || (() => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
  w.HTMLElement.prototype.scrollIntoView = function () {};
  const calls = [];
  const spoken = [];
  const played = [];
  w.SpeechSynthesisUtterance = function (t) { this.text = t; };
  const synth = { speaking: false, cancel() { spoken.push('cancel'); }, speak(u) { spoken.push(u); }, getVoices: () => voices,
    addEventListener() {}, removeEventListener() {} };
  Object.defineProperty(w, 'speechSynthesis', { value: synth, configurable: true });
  w.Audio = function (url) { this.url = url; this.play = async () => { played.push(url); }; this.pause = () => {}; };
  w.URL.createObjectURL = () => 'blob:fake'; w.URL.revokeObjectURL = () => {};
  w.fetch = async (url, init = {}) => {
    const method = (init.method || 'GET').toUpperCase();
    calls.push({ url, method, body: init.body ? (typeof init.body === 'string' ? JSON.parse(init.body) : init.body) : null });
    if (url.startsWith('/static/i18n/')) return res(200, I18N(url.split('/').pop().replace('.json', '')));
    if (url === '/api/v1/worker/me') return res(401, { detail: 'no' });
    if (url === '/api/v1/worker/safety-reports' && method === 'GET') return res(200, REPORTS);
    if (url === '/api/v1/worker/payslip/explain') return explain ? explain(JSON.parse(init.body)) : res(200, { explanation: 'x', language: 'en', speech_lang: 'en-IN', source: 'gemini' });
    if (url === '/api/v1/worker/speak') return speak ? speak(JSON.parse(init.body)) : res(200, {});
    return res(404, {});
  };
  w.eval(WORKER_JS); w.eval(ROUND3_JS);
  await tick(60);
  const $ = (id) => w.document.getElementById(id);
  const choose = async (code, sel = 'langSelector') => { const s = $(sel); s.value = code; s.dispatchEvent(new w.Event('change')); await tick(80); };
  return { w, $, calls, spoken, played, choose };
}

test('every language picker (header, payslip, safety) shows all 9 languages and stays in sync', async () => {
  const p = await boot();
  for (const id of ['langSelector', 'explainLangSelector', 'safetyLangSelector']) assert.equal(p.$(id).options.length, 9, id);
  await p.choose('mr', 'explainLangSelector');
  assert.equal(p.$('langSelector').value, 'mr'); assert.equal(p.$('safetyLangSelector').value, 'mr');
  assert.equal(p.$('i18n-explain-btn').textContent, I18N('mr').explain_payslip_btn);
});

test('REGRESSION (screenshot 1): explain button label keeps translating after it was clicked once', async () => {
  const p = await boot({ lang: 'hi', explain: () => res(200, { explanation: 'नमस्ते', language: 'hi', speech_lang: 'hi-IN', source: 'gemini' }) });
  p.$('btnExplainPayslip').click(); await tick(60);
  assert.ok(p.$('i18n-explain-btn'), 'the label span must survive the click');
  await p.choose('mr');
  assert.equal(p.$('i18n-explain-btn').textContent, I18N('mr').explain_payslip_btn);
  assert.match(p.$('btnExplainPayslip').textContent, /✨/);
});

test('REGRESSION (screenshot 1): switching language re-generates the explanation in the NEW language', async () => {
  const bodies = [];
  const p = await boot({ lang: 'hi', explain: (b) => { bodies.push(b.language);
    return res(200, { explanation: `text-in-${b.language}`, language: b.language, speech_lang: 'x', source: 'gemini' }); } });
  p.$('btnExplainPayslip').click(); await tick(60);
  assert.equal(p.$('aiExplanationText').textContent, 'text-in-hi');
  await p.choose('mr');
  assert.deepEqual(bodies, ['hi', 'mr']);
  assert.equal(p.$('aiExplanationText').textContent, 'text-in-mr');
  await p.choose('ta');
  assert.equal(p.$('aiExplanationText').textContent, 'text-in-ta');
});

test('no auto-explain if the worker never asked for an explanation', async () => {
  const p = await boot({ lang: 'hi' });
  await p.choose('mr'); await p.choose('ta');
  assert.equal(p.calls.filter((c) => c.url.includes('payslip/explain')).length, 0);
});

test('stale response is dropped when the language changes while a request is in flight', async () => {
  const p = await boot({ lang: 'hi', explain: async (b) => { if (b.language === 'hi') await tick(150);
    return res(200, { explanation: `text-in-${b.language}`, language: b.language, speech_lang: 'x', source: 'gemini' }); } });
  p.$('btnExplainPayslip').click(); await tick(20);       // slow Hindi request starts
  await p.choose('ta');                                    // user switches language mid-request => Tamil is requested automatically
  await tick(260);
  assert.equal(p.$('aiExplanationText').textContent, 'text-in-ta', 'late Hindi reply must not overwrite Tamil');
});

test('AI badge is honest: Gemini vs offline template, and it is translated', async () => {
  const p = await boot({ lang: 'hi', explain: () => res(200, { explanation: 'नमस्ते', language: 'hi', speech_lang: 'hi-IN', source: 'fallback' }) });
  p.$('btnExplainPayslip').click(); await tick(60);
  assert.equal(p.$('aiBadge').textContent, I18N('hi').ai_badge_offline);
  const q = await boot({ lang: 'ta', explain: () => res(200, { explanation: 'வணக்கம்', language: 'ta', speech_lang: 'ta-IN', source: 'gemini' }) });
  q.$('btnExplainPayslip').click(); await tick(60);
  assert.equal(q.$('aiBadge').textContent, I18N('ta').ai_badge_live);
});

test('voice: uses the device voice when one exists for the language (no server call)', async () => {
  const voices = [{ lang: 'en-US', name: 'en' }, { lang: 'mr-IN', name: 'Marathi' }];
  const p = await boot({ lang: 'mr', voices, explain: () => res(200, { explanation: 'नमस्कार', language: 'mr', speech_lang: 'mr-IN', source: 'gemini' }) });
  p.$('btnExplainPayslip').click(); await tick(60);
  p.$('btnListenPayslip').click(); await tick(1400 > 0 ? 80 : 0);
  const u = p.spoken.find((x) => x && x.text);
  assert.ok(u && u.voice.name === 'Marathi' && u.lang === 'mr-IN');
  assert.equal(p.calls.filter((c) => c.url.includes('/speak')).length, 0);
});

test('REGRESSION ("sirf English me bolta h"): no device voice => Gemini server voice is played, not English', async () => {
  const voices = [{ lang: 'en-US', name: 'English only' }];                 // typical Windows machine
  const p = await boot({ lang: 'mr', voices, explain: () => res(200, { explanation: 'नमस्कार राजेश', language: 'mr', speech_lang: 'mr-IN', source: 'gemini' }) });
  p.$('btnExplainPayslip').click(); await tick(60);
  p.$('btnListenPayslip').click();
  await tick(1500);                                                          // waitForVoices() times out, then server voice
  const speakCall = p.calls.find((c) => c.url === '/api/v1/worker/speak');
  assert.ok(speakCall, 'server voice requested');
  assert.deepEqual(speakCall.body, { text: 'नमस्कार राजेश', language: 'mr' });
  assert.equal(p.played.length, 1, 'audio played');
  assert.equal(p.spoken.filter((x) => x && x.text).length, 0, 'must NOT read Marathi with the English voice');
});

test('voice: if the server voice is unavailable the worker gets a clear translated message', async () => {
  const p = await boot({ lang: 'ta', voices: [], explain: () => res(200, { explanation: 'வணக்கம்', language: 'ta', speech_lang: 'ta-IN', source: 'gemini' }),
    speak: () => res(503, { detail: 'down' }) });
  p.$('btnExplainPayslip').click(); await tick(60);
  p.$('btnListenPayslip').click(); await tick(1500);
  assert.match(p.w.document.body.textContent, new RegExp(I18N('ta').voice_unavailable.slice(0, 12)));
  assert.equal(p.played.length, 0);
});

test('static strings the screenshots showed in English are now translated (placeholder, legend, donut label)', async () => {
  const p = await boot({ lang: 'en' });
  await p.choose('hi');
  const b = I18N('hi');
  assert.equal(p.$('safetyTextInput').getAttribute('placeholder'), b.type_safety_placeholder);
  assert.equal(p.$('feedbackCommentInput').getAttribute('placeholder'), b.feedback_comments_placeholder);
  assert.equal(p.$('i18n-total-net').textContent, b.total_earnings);
  assert.equal(p.$('i18n-legend-base').textContent, b.base_pay);
  assert.equal(p.$('i18n-legend-ot').textContent, b.overtime_pay);
});

async function openSafety(p) { p.w.document.getElementById('navBtnSafety').click(); await tick(80); }

test('safety cards: category / severity / status chips are translated and re-render live on language change', async () => {
  const p = await boot({ lang: 'hi' });
  await openSafety(p);
  const card = () => [...p.w.document.querySelectorAll('#safetyReportsContainer .kanban-card')];
  assert.equal(card().length, 2);
  assert.match(card()[0].textContent, new RegExp(I18N('hi').cat_hazard));
  assert.match(card()[0].textContent, new RegExp(I18N('hi').sev_critical));
  assert.match(card()[0].textContent, new RegExp(I18N('hi').status_label + ': ' + I18N('hi').status_reported));
  await p.choose('ta');                                                      // no reload needed
  assert.match(card()[0].textContent, new RegExp(I18N('ta').cat_hazard));
  assert.match(card()[1].textContent, new RegExp(I18N('ta').status_resolved));
  assert.doesNotMatch(card()[0].textContent, /CRITICAL|Reported/);
});

test('safety cards: native line only when the report is in the viewer\'s language, otherwise English', async () => {
  const p = await boot({ lang: 'hi' });
  await openSafety(p);
  const [tamil, hindi] = [...p.w.document.querySelectorAll('#safetyReportsContainer .kanban-card')].map((c) => c.textContent);
  assert.doesNotMatch(tamil, /தளர்வான/); assert.match(tamil, /Loose scaffolding/);   // Tamil report viewed in Hindi => English
  assert.match(hindi, /हेलमेट नहीं है/); assert.match(hindi, /No helmet near the edge/);   // Hindi report in Hindi => native first
  await p.choose('ta');
  const [t2, h2] = [...p.w.document.querySelectorAll('#safetyReportsContainer .kanban-card')].map((c) => c.textContent);
  assert.match(t2, /தளர்வான/); assert.doesNotMatch(h2, /हेलमेट/);
});

test('round3 cards (wage/photo) follow worker.js language switches in the full page (the screenshot-1 bug)', async () => {
  const p = await boot({ lang: 'hi' });
  assert.match(p.w.document.querySelector('#r3WageSlot h4').textContent, /वेतन जांच/);
  await p.choose('mr');
  assert.equal(p.w.document.querySelector('#r3WageSlot h4').textContent, I18N('mr').r3_wage_title);
  assert.equal(p.w.document.querySelector('#r3PhotoSlot button').textContent, I18N('mr').r3_photo_btn);
  await p.choose('hi', 'safetyLangSelector');                                 // changing via another picker works too
  assert.equal(p.w.document.querySelector('#r3WageSlot h4').textContent, I18N('hi').r3_wage_title);
});
