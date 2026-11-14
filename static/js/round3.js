/* FairShift Round 3 UI: photo hazard, wage-theft check, integrity badge, impact calculator.
   Self-contained; uses textContent only (no innerHTML) so server data can never inject markup. */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const inr = (n) => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });

  function el(tag, props, children) {
    const node = document.createElement(tag);
    Object.entries(props || {}).forEach(([k, v]) => {
      if (k === 'style') node.style.cssText = v;
      else if (k === 'text') node.textContent = v;
      else if (k === 'class') node.className = v;
      else node.setAttribute(k, v);
    });
    (children || []).forEach((c) => node.appendChild(c));
    return node;
  }

  async function api(url, opts) {
    const res = await fetch(url, opts);
    let body = null;
    try { body = await res.json(); } catch (_) { /* non-JSON */ }
    if (!res.ok) {
      const msg = (body && (body.error && body.error.message || body.detail)) || ('Request failed (' + res.status + ')');
      throw new Error(typeof msg === 'string' ? msg : 'Request failed');
    }
    return body;
  }

  // ---------------- Worker: photo hazard ----------------
  function initPhoto(slot) {
    const input = el('input', { type: 'file', accept: 'image/*', capture: 'environment', style: 'display:none' });
    const btn = el('button', { class: 'btn btn-secondary', style: 'width:100%; margin-top:0.6rem;', text: '📷 Report with Photo (AI)' });
    const result = el('div', { style: 'margin-top:0.6rem; font-size:0.85rem;' });
    btn.addEventListener('click', () => input.click());
    input.addEventListener('change', async () => {
      const file = input.files && input.files[0];
      if (!file) return;
      if (file.size > 5 * 1024 * 1024) { result.textContent = 'Photo too large (max 5 MB).'; return; }
      btn.disabled = true; btn.textContent = 'Analyzing photo with AI...'; result.textContent = '';
      try {
        const fd = new FormData();
        fd.append('photo', file);
        fd.append('language', localStorage.getItem('fairshift_lang') || 'en');
        const r = await api('/api/v1/worker/hazard-photo', { method: 'POST', body: fd });
        const lang = localStorage.getItem('fairshift_lang') || 'en';
        result.textContent = '';
        result.appendChild(el('strong', { text: r.severity.toUpperCase() + ' · ' + r.category.toUpperCase() }));
        result.appendChild(el('div', { text: lang === 'en' ? r.summary_en : r.summary_local, style: 'margin-top:0.25rem;' }));
        result.appendChild(el('div', { text: 'Sent to site engineer and logged tamper-proof.', style: 'color:var(--text-secondary); margin-top:0.25rem;' }));
      } catch (e) {
        result.textContent = 'Could not analyze photo: ' + e.message;
      } finally {
        btn.disabled = false; btn.textContent = '📷 Report with Photo (AI)'; input.value = '';
      }
    });
    slot.append(input, btn, result);
  }

  // ---------------- Worker: wage check ----------------
  function initWage(slot) {
    const amount = el('input', { type: 'number', min: '0', step: '1', inputmode: 'numeric', class: 'input-field', placeholder: 'Amount you actually received (₹)' });
    const btn = el('button', { class: 'btn btn-primary', style: 'width:100%; margin-top:0.6rem;', text: 'Check my pay' });
    const out = el('div', { style: 'margin-top:0.75rem;' });
    const card = el('div', { class: 'card' }, [
      el('h4', { style: 'font-size:0.95rem; margin-bottom:0.25rem;', text: '🔍 Wage Theft Check' }),
      el('p', { style: 'font-size:0.8rem; color:var(--text-secondary); margin-bottom:0.6rem;', text: 'Compare what you were paid with what the law says you should get.' }),
      amount, btn, out,
    ]);
    btn.addEventListener('click', async () => {
      const v = parseFloat(amount.value);
      if (!isFinite(v) || v < 0) { out.textContent = 'Enter a valid amount.'; return; }
      btn.disabled = true; out.textContent = 'Checking...';
      try {
        const r = await api('/api/v1/worker/wage-check', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ paid_amount: v }),
        });
        const colors = { fair: '#10B981', underpaid: '#EF4444', overpaid: '#F59E0B' };
        const headline = r.verdict === 'underpaid' ? 'Underpaid by ' + inr(r.shortfall) + ' (' + r.shortfall_percent + '%)'
          : r.verdict === 'fair' ? 'Your pay is fair ✓' : 'Paid more than expected';
        out.textContent = '';
        out.appendChild(el('div', { style: 'font-weight:700; font-size:1.05rem; color:' + colors[r.verdict], text: headline }));
        out.appendChild(el('div', { style: 'font-size:0.85rem; margin-top:0.25rem;', text: 'Expected take-home: ' + inr(r.expected_net) + ' · You received: ' + inr(r.paid_amount) }));
        if (r.likely_cause) out.appendChild(el('div', { style: 'font-size:0.85rem; margin-top:0.25rem; color:#F59E0B;', text: 'Likely cause: ' + r.likely_cause }));
        out.appendChild(el('div', { style: 'font-size:0.72rem; margin-top:0.4rem; color:var(--text-secondary);', text: r.legal_note }));
      } catch (e) { out.textContent = 'Could not check: ' + e.message; }
      finally { btn.disabled = false; }
    });
    slot.appendChild(card);
  }

  // ---------------- Admin: integrity + impact ----------------
  function initAdmin(slot) {
    const badge = el('span', { class: 'badge badge-info', text: 'Integrity: checking...' });
    const detail = el('div', { style: 'font-size:0.75rem; color:var(--text-secondary); margin-top:0.35rem;' });
    const refresh = el('button', { class: 'btn btn-secondary btn-sm', text: 'Verify now' });

    async function verify() {
      try {
        const r = await api('/api/v1/admin/integrity-check');
        badge.className = 'badge ' + (r.valid ? 'badge-success' : 'badge-critical');
        badge.textContent = r.valid ? 'Integrity: Verified ✓ (' + r.checked + ' reports)' : 'Integrity: TAMPERING DETECTED';
        detail.textContent = r.valid ? 'Head hash ' + r.head_hash.slice(0, 16) + '…' : (r.reason + ' · report ' + r.broken_report_id);
      } catch (e) { badge.textContent = 'Integrity: unavailable'; }
    }
    refresh.addEventListener('click', verify);

    const slider = el('input', { type: 'range', min: '100', max: '100000', step: '100', value: '1000', style: 'width:100%;' });
    const rate = el('input', { type: 'range', min: '0', max: '100', step: '5', value: '30', style: 'width:100%;' });
    const big = el('div', { style: 'font-size:1.8rem; font-weight:800; color:var(--color-primary);' });
    const sub = el('div', { style: 'font-size:0.82rem; color:var(--text-secondary);' });
    const assume = el('div', { style: 'font-size:0.72rem; color:var(--text-secondary); margin-top:0.4rem;' });
    const lbl1 = el('label', { style: 'font-size:0.8rem;' });
    const lbl2 = el('label', { style: 'font-size:0.8rem;' });

    let timer = null;
    async function impact() {
      lbl1.textContent = 'Workers covered: ' + Number(slider.value).toLocaleString('en-IN');
      lbl2.textContent = 'Assumed share underpaid: ' + rate.value + '%';
      try {
        const r = await api('/api/v1/admin/impact?workers=' + slider.value + '&theft_rate=' + (rate.value / 100));
        big.textContent = inr(r.estimated_annual_wage_protected_inr) + ' / year';
        sub.textContent = 'overtime premium protected for ' + r.workers_affected.toLocaleString('en-IN') + ' workers · ' + r.fatigue_alerts_per_100_workers + ' fatigue alerts per 100 workers today';
        assume.textContent = 'Illustrative model. ' + r.assumptions.basis + '. ' + r.assumptions.model;
      } catch (e) { big.textContent = 'Unavailable'; }
    }
    [slider, rate].forEach((s) => s.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(impact, 150); }));

    slot.appendChild(el('div', { class: 'card' }, [
      el('div', { style: 'display:flex; justify-content:space-between; align-items:center; gap:0.5rem; flex-wrap:wrap;' }, [
        el('div', {}, [el('h3', { style: 'font-size:1.05rem;', text: '🔒 Tamper-Proof Safety Log' }), detail]), badge, refresh]),
      el('hr', { style: 'border:none; border-top:1px solid var(--border-strong); margin:1rem 0;' }),
      el('h3', { style: 'font-size:1.05rem; margin-bottom:0.5rem;', text: '📈 Impact Calculator' }),
      lbl1, slider, lbl2, rate, big, sub, assume,
    ]));
    verify(); impact();
  }

  document.addEventListener('DOMContentLoaded', () => {
    const p = $('r3PhotoSlot'); if (p) initPhoto(p);
    const w = $('r3WageSlot'); if (w) initWage(w);
    const a = $('r3AdminSlot'); if (a) initAdmin(a);
  });
})();
