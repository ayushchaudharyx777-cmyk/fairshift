/**
 * FairShift Worker Portal - Vanilla JS Client (UN SDG 8)
 * Strict textContent usage for user-provided data (XSS safe).
 */

(function () {
  'use strict';

  // State
  let currentLang = localStorage.getItem('fairshift_lang') || 'en';
  let i18nStrings = {};
  let currentWorker = null;
  let currentSite = null;
  let activeShift = null;
  let timerInterval = null;
  let currentSpeechUtterance = null;
  let speechRecognition = null;
  let isListening = false;
  let currentFeedbackRatings = { manager: 5, conditions: 5 };

  // DOM Elements
  const langSelector = document.getElementById('langSelector');
  const workerThemeToggle = document.getElementById('workerThemeToggle');
  const workerLogoutBtn = document.getElementById('workerLogoutBtn');
  const viewLogin = document.getElementById('viewLogin');
  const workerLoginForm = document.getElementById('workerLoginForm');
  const loginPhone = document.getElementById('loginPhone');
  const loginPin = document.getElementById('loginPin');
  const btnFillConstruction = document.getElementById('btnFillConstruction');
  const btnFillHospital = document.getElementById('btnFillHospital');
  const workerBottomNav = document.getElementById('workerBottomNav');

  // Tabs
  const tabHome = document.getElementById('tabHome');
  const tabShift = document.getElementById('tabShift');
  const tabPayslip = document.getElementById('tabPayslip');
  const tabSafety = document.getElementById('tabSafety');
  const tabPassport = document.getElementById('tabPassport');
  const navBtns = document.querySelectorAll('.nav-tab-btn');

  // Voice Orb
  const voiceOrbBtn = document.getElementById('voiceOrbBtn');
  const voiceOrbStatusText = document.getElementById('voiceOrbStatusText');
  const safetyTextInput = document.getElementById('safetyTextInput');
  const btnSubmitSafetyReport = document.getElementById('btnSubmitSafetyReport');
  const safetyReportsContainer = document.getElementById('safetyReportsContainer');

  // Toast
  const toastContainer = document.getElementById('workerToastContainer');

  function showToast(title, message, isCritical = false) {
    const toast = document.createElement('div');
    toast.className = `toast ${isCritical ? 'toast-critical' : ''}`;
    
    const iconSpan = document.createElement('span');
    iconSpan.style.fontSize = '1.3rem';
    iconSpan.textContent = isCritical ? '⚠️' : '✅';

    const textDiv = document.createElement('div');
    const h5 = document.createElement('h5');
    h5.style.fontSize = '0.9rem';
    h5.style.marginBottom = '0.15rem';
    h5.textContent = title;
    const p = document.createElement('p');
    p.style.fontSize = '0.8rem';
    p.textContent = message;

    textDiv.appendChild(h5);
    textDiv.appendChild(p);
    toast.appendChild(iconSpan);
    toast.appendChild(textDiv);
    toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.transition = 'opacity 0.3s ease';
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  // --- 1. i18n Localization ---
  async function loadTranslations(lang) {
    try {
      const res = await fetch(`/static/i18n/${lang}.json`);
      if (res.ok) {
        i18nStrings = await res.json();
        currentLang = lang;
        document.documentElement.lang = lang;
        localStorage.setItem('fairshift_lang', lang);
        applyTranslations();
      }
    } catch (e) {
      console.warn('Could not load i18n bundle:', e);
    }
  }

  function applyTranslations() {
    const s = i18nStrings;
    if (!s) return;

    const setText = (id, key) => {
      const el = document.getElementById(id);
      if (el && s[key]) el.textContent = s[key];
    };

    setText('i18n-app-name', 'app_name');
    setText('i18n-login-title', 'login_title');
    setText('i18n-login-subtitle', 'login_subtitle');
    setText('i18n-phone-label', 'phone_placeholder');
    setText('i18n-pin-label', 'pin_placeholder');
    setText('i18n-sign-in-btn', 'sign_in_btn');
    setText('i18n-quick-demo', 'quick_demo_worker');
    setText('i18n-nav-home', 'nav_home');
    setText('i18n-nav-shift', 'nav_shift');
    setText('i18n-nav-payslip', 'nav_payslip');
    setText('i18n-nav-safety', 'nav_safety');
    setText('i18n-nav-passport', 'nav_passport');
    setText('i18n-recent-shifts', 'recent_shifts');
    setText('i18n-payslip-title', 'payslip_title');
    setText('i18n-explain-btn', 'explain_payslip_btn');
    setText('i18n-listen-btn', 'listen_btn');
    setText('i18n-safety-title', 'safety_title');
    setText('i18n-safety-subtitle', 'safety_subtitle');
    setText('i18n-submit-safety', 'submit_report_btn');
    setText('i18n-recent-safety', 'recent_safety_reports');
    setText('i18n-share-passport', 'share_passport_btn');
    setText('i18n-copy-link', 'copy_link_btn');

    if (langSelector) langSelector.value = currentLang;
  }

  langSelector.addEventListener('change', (e) => {
    loadTranslations(e.target.value);
  });

  // --- 2. Theme Toggle ---
  workerThemeToggle.addEventListener('click', () => {
    const cur = document.documentElement.getAttribute('data-theme') || 'dark';
    const next = cur === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('fairshift_theme', next);
  });

  // --- 3. Authentication & Profile ---
  async function checkSession() {
    try {
      const res = await fetch('/api/v1/worker/me');
      if (res.ok) {
        const data = await res.json();
        currentWorker = data.worker;
        currentSite = data.site;
        activeShift = data.active_shift;
        setupLoggedInView(data);
      } else {
        setupLoggedOutView();
      }
    } catch (e) {
      setupLoggedOutView();
    }
  }

  function setupLoggedOutView() {
    currentWorker = null;
    viewLogin.style.display = 'block';
    workerBottomNav.style.display = 'none';
    workerLogoutBtn.style.display = 'none';
    [tabHome, tabShift, tabPayslip, tabSafety, tabPassport].forEach(t => t.style.display = 'none');
    document.getElementById('headerSiteRole').textContent = 'UN SDG 8 Worker Portal';
  }

  function setupLoggedInView(data) {
    viewLogin.style.display = 'none';
    workerBottomNav.style.display = 'flex';
    workerLogoutBtn.style.display = 'flex';

    // Header info
    document.getElementById('headerSiteRole').textContent = `${data.site.name} • ${data.worker.role}`;

    // Home Tab Info
    document.getElementById('homeWorkerName').textContent = data.worker.name;
    document.getElementById('homeSiteBadge').textContent = `${data.site.name} (${data.site.sector.toUpperCase()})`;
    const initials = data.worker.name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
    document.getElementById('homeInitialsAvatar').textContent = initials;

    // Fatigue alert check
    const fatigueBanner = document.getElementById('homeFatigueBanner');
    if (data.fatigue_alerts && data.fatigue_alerts.length > 0) {
      const highest = data.fatigue_alerts[0];
      fatigueBanner.style.display = 'flex';
      document.getElementById('fatigueBannerTitle').textContent = `⚠️ Safety Fatigue Alert (${highest.severity.toUpperCase()})`;
      document.getElementById('fatigueBannerDesc').textContent = highest.description;
    } else {
      fatigueBanner.style.display = 'none';
    }

    // Initialize Active Shift Tracker
    updateShiftUI(data.active_shift);

    // Switch to Home tab by default
    switchTab('tabHome');
  }

  // Login Form Submission
  workerLoginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const phone = loginPhone.value.trim();
    const pin = loginPin.value.trim();
    const submitBtn = document.getElementById('loginSubmitBtn');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Authenticating...';

    try {
      const res = await fetch('/api/v1/worker/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone, pin })
      });

      if (res.ok) {
        showToast('Welcome!', 'Signed in successfully');
        await checkSession();
      } else {
        const err = await res.json();
        showToast('Login Failed', err.error?.message || 'Invalid credentials', true);
      }
    } catch (err) {
      showToast('Connection Error', 'Could not reach server', true);
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = i18nStrings.sign_in_btn || 'Sign In to FairShift';
    }
  });

  // Quick Demo Buttons
  btnFillConstruction.addEventListener('click', () => {
    loginPhone.value = '9876543210';
    loginPin.value = '1234';
  });

  btnFillHospital.addEventListener('click', () => {
    loginPhone.value = '9876543220';
    loginPin.value = '1234';
  });

  // Logout
  workerLogoutBtn.addEventListener('click', async () => {
    try {
      await fetch('/api/v1/worker/logout', { method: 'POST' });
    } catch (e) {}
    if (timerInterval) clearInterval(timerInterval);
    showToast('Signed Out', 'You have been safely logged out');
    setupLoggedOutView();
  });

  // --- 4. Navigation & Tabs ---
  function switchTab(tabId) {
    const tabs = {
      tabHome: tabHome,
      tabShift: tabShift,
      tabPayslip: tabPayslip,
      tabSafety: tabSafety,
      tabPassport: tabPassport
    };

    Object.keys(tabs).forEach(id => {
      tabs[id].style.display = id === tabId ? 'flex' : 'none';
    });

    navBtns.forEach(btn => {
      btn.classList.toggle('active', btn.getAttribute('data-tab') === tabId);
    });

    // Refresh content for selected tab
    if (tabId === 'tabShift') loadShiftData();
    if (tabId === 'tabPayslip') loadPayslipData();
    if (tabId === 'tabSafety') loadSafetyData();
    if (tabId === 'tabPassport') loadPassportData();
  }

  navBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.getAttribute('data-tab');
      switchTab(target);
    });
  });

  // Action Tiles on Home Screen
  document.getElementById('tileShift').addEventListener('click', () => switchTab('tabShift'));
  document.getElementById('tilePayslip').addEventListener('click', () => switchTab('tabPayslip'));
  document.getElementById('tileSafety').addEventListener('click', () => switchTab('tabSafety'));
  document.getElementById('tilePassport').addEventListener('click', () => switchTab('tabPassport'));

  // Keyboard navigation for action tiles
  ['tileShift', 'tilePayslip', 'tileSafety', 'tilePassport'].forEach(id => {
    const tile = document.getElementById(id);
    if (tile) {
      tile.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          tile.click();
        }
      });
    }
  });

  // --- 5. Shift Tracking & Live Timer ---
  function updateShiftUI(shift) {
    activeShift = shift;
    const homeBtn = document.getElementById('homeShiftActionBtn');
    const bigBtn = document.getElementById('btnBigShiftToggle');
    const homeTimer = document.getElementById('homeTimerDisplay');
    const shiftTimer = document.getElementById('shiftTimerDisplay');
    const homeBadge = document.getElementById('homeShiftStatusBadge');
    const shiftStatusText = document.getElementById('shiftStatusText');
    const shiftIndicator = document.getElementById('shiftStatusIndicator');
    const shiftPolicy = document.getElementById('shiftSectorPolicy');

    if (timerInterval) clearInterval(timerInterval);

    if (currentSite) {
      if (currentSite.sector === 'hospital') {
        shiftPolicy.textContent = 'Hospital Sector: 12h standard, 2x Overtime Rate';
      } else {
        shiftPolicy.textContent = 'Construction Sector: 8h standard, 2x Overtime Rate';
      }
    }

    if (shift && shift.status === 'active') {
      homeBadge.textContent = 'Shift Active';
      homeBadge.className = 'badge badge-success';
      shiftStatusText.textContent = 'Clocked In (Active Duty)';
      shiftIndicator.style.background = 'var(--color-success)';

      homeBtn.textContent = 'Clock Out (End Shift)';
      homeBtn.className = 'btn btn-critical';
      bigBtn.textContent = 'End Shift (Check-Out)';
      bigBtn.className = 'btn btn-critical big-shift-btn active';

      const startMs = new Date(shift.start_time).getTime();
      const standardLimitHours = currentSite?.sector === 'hospital' ? 12 : 8;

      const runTimer = () => {
        const diffMs = Math.max(0, Date.now() - startMs);
        const totalSec = Math.floor(diffMs / 1000);
        const hours = Math.floor(totalSec / 3600);
        const minutes = Math.floor((totalSec % 3600) / 60);
        const seconds = totalSec % 60;
        const timeFormatted = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        
        homeTimer.textContent = timeFormatted;
        shiftTimer.textContent = timeFormatted;

        const totalHours = (diffMs / 3600000);
        let regH = totalHours > standardLimitHours ? standardLimitHours : totalHours;
        let otH = totalHours > standardLimitHours ? totalHours - standardLimitHours : 0;
        document.getElementById('shiftHoursCalculated').textContent = 
          `${regH.toFixed(2)} Regular hrs | ${otH.toFixed(2)} OT hrs (2x)`;
      };

      runTimer();
      timerInterval = setInterval(runTimer, 1000);
    } else {
      homeBadge.textContent = 'Off Duty';
      homeBadge.className = 'badge badge-info';
      shiftStatusText.textContent = 'Not Clocked In';
      shiftIndicator.style.background = 'var(--text-muted)';
      homeTimer.textContent = '00:00:00';
      shiftTimer.textContent = '00:00:00';
      document.getElementById('shiftHoursCalculated').textContent = '0.0 Regular hrs | 0.0 OT hrs';

      homeBtn.textContent = 'Start Shift (Check-In)';
      homeBtn.className = 'btn btn-primary';
      bigBtn.textContent = 'Start Shift (Check-In)';
      bigBtn.className = 'btn btn-primary big-shift-btn';
    }
  }

  async function toggleShift() {
    const isClockIn = !activeShift || activeShift.status !== 'active';
    const endpoint = isClockIn ? '/api/v1/worker/check-in' : '/api/v1/worker/check-out';
    const notesInput = document.getElementById('shiftNotesInput');
    const notes = notesInput ? notesInput.value.trim() : '';

    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes: notes || null })
      });

      if (res.ok) {
        const shiftData = await res.json();
        if (isClockIn) {
          showToast('Shift Started', 'Live duty hours and overtime tracking enabled.');
          updateShiftUI(shiftData);
        } else {
          showToast('Shift Completed', `Logged ${shiftData.total_hours}h (${shiftData.overtime_hours}h OT). Great job!`);
          updateShiftUI(null);
          loadShiftData();
        }
        if (notesInput) notesInput.value = '';
      } else {
        const err = await res.json();
        showToast('Shift Error', err.error?.message || 'Operation failed', true);
      }
    } catch (e) {
      showToast('Network Error', 'Could not record shift', true);
    }
  }

  document.getElementById('homeShiftActionBtn').addEventListener('click', toggleShift);
  document.getElementById('btnBigShiftToggle').addEventListener('click', toggleShift);

  async function loadShiftData() {
    try {
      const res = await fetch('/api/v1/worker/shifts');
      if (res.ok) {
        const shifts = await res.json();
        renderShiftsList(shifts);
      }
    } catch (e) {
      console.warn('Failed to load shifts:', e);
    }
  }

  function renderShiftsList(shifts) {
    const container = document.getElementById('shiftsListContainer');
    container.textContent = '';
    const completed = shifts.filter(s => s.status === 'completed');
    document.getElementById('shiftHistoryCount').textContent = `${completed.length} shifts`;

    if (completed.length === 0) {
      const p = document.createElement('p');
      p.style.cssText = 'font-size: 0.85rem; color: var(--text-muted); text-align: center; padding: 1rem;';
      p.textContent = 'No completed shifts logged yet.';
      container.appendChild(p);
      return;
    }

    completed.slice(0, 10).forEach(s => {
      const card = document.createElement('div');
      card.className = 'line-item-row';

      const left = document.createElement('div');
      left.className = 'line-item-info';
      const h5 = document.createElement('h5');
      const startDt = new Date(s.start_time);
      h5.textContent = `${startDt.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })} • ${s.total_hours} hrs`;
      const span = document.createElement('span');
      span.textContent = s.notes || (s.overtime_hours > 0 ? `${s.overtime_hours}h Overtime @ 2x Fair Wage` : 'Standard Shift');
      left.appendChild(h5);
      left.appendChild(span);

      const right = document.createElement('div');
      if (s.overtime_hours > 0) {
        const badge = document.createElement('span');
        badge.className = 'badge badge-success';
        badge.textContent = `+${s.overtime_hours}h OT`;
        right.appendChild(badge);
      } else {
        const badge = document.createElement('span');
        badge.className = 'badge badge-info';
        badge.textContent = 'Standard';
        right.appendChild(badge);
      }

      card.appendChild(left);
      card.appendChild(right);
      container.appendChild(card);
    });
  }

  // --- 6. Payslip & AI Speech Explanation ---
  let lastLoadedPayslip = null;

  async function loadPayslipData() {
    try {
      const res = await fetch('/api/v1/worker/payslip');
      if (res.ok) {
        const p = await res.json();
        lastLoadedPayslip = p;
        renderPayslip(p);
      }
    } catch (e) {
      console.warn('Failed to load payslip:', e);
    }
  }

  function renderPayslip(p) {
    document.getElementById('payslipDateRange').textContent = `${p.period_start} to ${p.period_end}`;
    document.getElementById('payslipNetTotal').textContent = `₹${p.net_pay.toLocaleString('en-IN')}`;
    document.getElementById('legendBasePay').textContent = `₹${p.base_pay.toLocaleString('en-IN')}`;
    document.getElementById('legendOtPay').textContent = `₹${p.overtime_pay.toLocaleString('en-IN')}`;
    document.getElementById('legendDedPay').textContent = `₹${p.total_deductions.toLocaleString('en-IN')}`;

    // Pure SVG Donut Math
    // Total circumference for r=15.915 is 100
    const totalEarnings = p.gross_pay || 1;
    const basePct = Math.max(0, Math.min(100, (p.base_pay / totalEarnings) * 100));
    const otPct = Math.max(0, Math.min(100, (p.overtime_pay / totalEarnings) * 100));
    const dedPct = Math.max(0, Math.min(100, (p.total_deductions / totalEarnings) * 100));

    const segBase = document.getElementById('donutBaseSeg');
    const segOt = document.getElementById('donutOtSeg');
    const segDed = document.getElementById('donutDedSeg');

    segBase.setAttribute('stroke-dasharray', `${basePct} 100`);
    segBase.setAttribute('stroke-dashoffset', '0');

    segOt.setAttribute('stroke-dasharray', `${otPct} 100`);
    segOt.setAttribute('stroke-dashoffset', `-${basePct}`);

    segDed.setAttribute('stroke-dasharray', `${dedPct} 100`);
    segDed.setAttribute('stroke-dashoffset', `-${basePct + otPct}`);

    // Render Line Items
    const list = document.getElementById('payslipLineItemsList');
    list.textContent = '';
    p.line_items.forEach(item => {
      const row = document.createElement('div');
      row.className = `line-item-row ${item.type === 'summary' ? 'summary' : ''}`;

      const info = document.createElement('div');
      info.className = 'line-item-info';
      const h5 = document.createElement('h5');
      h5.textContent = item.label;
      const span = document.createElement('span');
      span.textContent = item.rate_or_units;
      info.appendChild(h5);
      info.appendChild(span);

      const amt = document.createElement('div');
      amt.className = `line-item-amount ${item.amount < 0 ? 'amount-deduction' : 'amount-earning'}`;
      amt.textContent = `${item.amount < 0 ? '-' : ''}₹${Math.abs(item.amount).toLocaleString('en-IN')}`;

      row.appendChild(info);
      row.appendChild(amt);
      list.appendChild(row);
    });
  }

  // Gemini AI Payslip Explanation
  document.getElementById('btnExplainPayslip').addEventListener('click', async () => {
    const btn = document.getElementById('btnExplainPayslip');
    const container = document.getElementById('aiExplanationContainer');
    const textEl = document.getElementById('aiExplanationText');
    const listenBtn = document.getElementById('btnListenPayslip');

    btn.disabled = true;
    btn.textContent = 'Generating explanation...';
    container.style.display = 'flex';
    textEl.textContent = 'Connecting to Gemini AI assistant...';

    try {
      const res = await fetch('/api/v1/worker/payslip/explain', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language: currentLang })
      });

      if (res.ok) {
        const data = await res.json();
        textEl.textContent = data.explanation;
        listenBtn.style.display = 'inline-flex';
        // Auto trigger or offer speech
      } else {
        textEl.textContent = 'Could not generate explanation at this moment. Please check connection.';
      }
    } catch (e) {
      textEl.textContent = 'Error connecting to explanation service.';
    } finally {
      btn.disabled = false;
      btn.textContent = i18nStrings.explain_payslip_btn || 'Explain in My Language';
    }
  });

  // Web Speech API Voice Readout
  document.getElementById('btnListenPayslip').addEventListener('click', () => {
    const text = document.getElementById('aiExplanationText').textContent;
    if (!text || !('speechSynthesis' in window)) {
      showToast('Speech Error', 'Voice synthesis is not supported on this browser.', true);
      return;
    }

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    const langMap = { en: 'en-IN', hi: 'hi-IN', ta: 'ta-IN' };
    utterance.lang = langMap[currentLang] || 'en-IN';
    utterance.rate = 0.95;

    const stopBtn = document.getElementById('btnStopSpeech');
    stopBtn.style.display = 'inline-block';

    utterance.onend = () => { stopBtn.style.display = 'none'; };
    utterance.onerror = () => { stopBtn.style.display = 'none'; };

    stopBtn.onclick = () => {
      window.speechSynthesis.cancel();
      stopBtn.style.display = 'none';
    };

    window.speechSynthesis.speak(utterance);
  });

  // --- 7. Glowing Voice Orb & Safety Reporting ---
  function initSpeechRecognition() {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRec) {
      console.warn('Web Speech Recognition not supported in this browser.');
      return null;
    }
    const rec = new SpeechRec();
    rec.continuous = false;
    rec.interimResults = true;
    const langMap = { en: 'en-IN', hi: 'hi-IN', ta: 'ta-IN' };
    rec.lang = langMap[currentLang] || 'en-IN';

    rec.onstart = () => {
      isListening = true;
      voiceOrbBtn.className = 'voice-orb listening';
      voiceOrbStatusText.textContent = i18nStrings.orb_listening || 'Listening... Speak clearly';
    };

    rec.onresult = (event) => {
      let transcript = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      safetyTextInput.value = transcript;
    };

    rec.onerror = (e) => {
      console.warn('Speech recognition error:', e.error);
      resetVoiceOrb();
      showToast('Microphone Notice', 'Could not record audio. You can type your report.', false);
    };

    rec.onend = () => {
      isListening = false;
      resetVoiceOrb();
    };

    return rec;
  }

  function resetVoiceOrb() {
    isListening = false;
    voiceOrbBtn.className = 'voice-orb idle';
    voiceOrbStatusText.textContent = i18nStrings.orb_idle || 'Tap Orb to Speak';
  }

  voiceOrbBtn.addEventListener('click', () => {
    if (isListening) {
      if (speechRecognition) speechRecognition.stop();
      resetVoiceOrb();
      return;
    }

    speechRecognition = initSpeechRecognition();
    if (!speechRecognition) {
      showToast('Voice Notice', 'Speech recognition unavailable. Please type your safety observation.', false);
      safetyTextInput.focus();
      return;
    }

    try {
      speechRecognition.start();
    } catch (e) {
      resetVoiceOrb();
    }
  });

  btnSubmitSafetyReport.addEventListener('click', async () => {
    const text = safetyTextInput.value.trim();
    if (!text) {
      showToast('Input Required', 'Please speak into the orb or type safety report details', true);
      return;
    }

    btnSubmitSafetyReport.disabled = true;
    voiceOrbBtn.className = 'voice-orb processing';
    voiceOrbStatusText.textContent = i18nStrings.orb_processing || 'Analyzing hazard with AI...';

    try {
      const res = await fetch('/api/v1/worker/safety-reports', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          input_text: text,
          language: currentLang
        })
      });

      if (res.ok) {
        const report = await res.json();
        showToast('Report Submitted!', `Category: ${report.category.toUpperCase()} | Severity: ${report.severity.toUpperCase()}`);
        safetyTextInput.value = '';
        loadSafetyData();
      } else {
        showToast('Submission Error', 'Failed to record report', true);
      }
    } catch (e) {
      showToast('Network Error', 'Could not submit report', true);
    } finally {
      btnSubmitSafetyReport.disabled = false;
      resetVoiceOrb();
    }
  });

  async function loadSafetyData() {
    try {
      const res = await fetch('/api/v1/worker/safety-reports');
      if (res.ok) {
        const reports = await res.json();
        renderSafetyReports(reports);
      }
    } catch (e) {
      console.warn('Failed to load safety reports:', e);
    }
  }

  function renderSafetyReports(reports) {
    safetyReportsContainer.textContent = '';
    if (!reports || reports.length === 0) {
      const p = document.createElement('p');
      p.style.cssText = 'font-size: 0.85rem; color: var(--text-muted); text-align: center; padding: 1rem;';
      p.textContent = 'No active safety hazards logged for your site.';
      safetyReportsContainer.appendChild(p);
      return;
    }

    reports.forEach(r => {
      const card = document.createElement('div');
      card.className = 'kanban-card';

      const top = document.createElement('div');
      top.style.cssText = 'display: flex; justify-content: space-between; align-items: center;';

      const catBadge = document.createElement('span');
      catBadge.className = 'badge badge-info';
      catBadge.textContent = r.category.toUpperCase();

      const sevBadge = document.createElement('span');
      sevBadge.className = `badge ${r.severity === 'critical' ? 'badge-critical' : r.severity === 'high' ? 'badge-warning' : 'badge-info'}`;
      sevBadge.textContent = r.severity.toUpperCase();

      top.appendChild(catBadge);
      top.appendChild(sevBadge);

      const pEn = document.createElement('p');
      pEn.style.cssText = 'font-size: 0.88rem; color: var(--text-primary); font-weight: 600;';
      pEn.textContent = r.summary_en;

      const pLoc = document.createElement('p');
      pLoc.style.cssText = 'font-size: 0.8rem; color: var(--text-secondary);';
      pLoc.textContent = r.summary_local;

      const foot = document.createElement('div');
      foot.style.cssText = 'display: flex; justify-content: space-between; align-items: center; font-size: 0.75rem; color: var(--text-muted); margin-top: 0.25rem;';
      
      const statusSpan = document.createElement('span');
      statusSpan.style.fontWeight = '700';
      statusSpan.style.color = r.status === 'Resolved' ? 'var(--color-success)' : r.status === 'Acknowledged' ? 'var(--color-info)' : 'var(--color-warning)';
      statusSpan.textContent = `Status: ${r.status}`;

      const timeSpan = document.createElement('span');
      timeSpan.textContent = new Date(r.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

      foot.appendChild(statusSpan);
      foot.appendChild(timeSpan);

      card.appendChild(top);
      card.appendChild(pEn);
      card.appendChild(pLoc);
      card.appendChild(foot);
      safetyReportsContainer.appendChild(card);
    });
  }

  // --- 8. Anonymous Feedback ---
  const feedbackModal = document.getElementById('feedbackModal');
  document.getElementById('btnOpenFeedbackModal').addEventListener('click', () => {
    feedbackModal.style.display = 'flex';
  });

  document.getElementById('btnCloseFeedbackModal').addEventListener('click', () => {
    feedbackModal.style.display = 'none';
  });

  // Emoji Rating handlers
  function setupEmojiGroup(groupId, stateKey) {
    const group = document.getElementById(groupId);
    const buttons = group.querySelectorAll('.emoji-btn');
    buttons.forEach(btn => {
      btn.addEventListener('click', () => {
        buttons.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentFeedbackRatings[stateKey] = parseInt(btn.getAttribute('data-val'), 10);
      });
    });
  }

  setupEmojiGroup('managerEmojiGroup', 'manager');
  setupEmojiGroup('conditionsEmojiGroup', 'conditions');

  document.getElementById('feedbackForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!currentWorker) return;

    const comment = document.getElementById('feedbackCommentInput').value.trim();
    const btn = document.getElementById('btnSubmitFeedback');
    btn.disabled = true;

    try {
      const res = await fetch('/api/v1/worker/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          site_id: currentWorker.site_id,
          manager_rating: currentFeedbackRatings.manager,
          conditions_rating: currentFeedbackRatings.conditions,
          comment: comment || null
        })
      });

      if (res.ok) {
        showToast('Anonymous Feedback Sent', 'Your identity was NOT stored. Thank you for making work safer!');
        feedbackModal.style.display = 'none';
        document.getElementById('feedbackCommentInput').value = '';
      } else {
        showToast('Feedback Error', 'Could not record feedback', true);
      }
    } catch (err) {
      showToast('Network Error', 'Could not submit feedback', true);
    } finally {
      btn.disabled = false;
    }
  });

  // --- 9. Skill Passport ---
  let currentPassportToken = null;

  async function loadPassportData() {
    try {
      const res = await fetch('/api/v1/worker/passport');
      if (res.ok) {
        const p = await res.json();
        currentPassportToken = p.token;
        renderPassport(p);
      }
    } catch (e) {
      console.warn('Failed to load passport:', e);
    }
  }

  function renderPassport(p) {
    document.getElementById('passportAvatar').textContent = p.avatar_initials;
    document.getElementById('passportWorkerName').textContent = p.worker_name;
    document.getElementById('passportRole').textContent = p.role;
    document.getElementById('passportSite').textContent = `${p.site_name} (${p.sector.toUpperCase()})`;

    // Badges
    const badgesContainer = document.getElementById('passportBadgesList');
    badgesContainer.textContent = '';
    p.verified_badges.forEach(b => {
      const chip = document.createElement('span');
      chip.className = 'badge badge-success';
      chip.textContent = `✓ ${b}`;
      badgesContainer.appendChild(chip);
    });

    // Skills
    const skillsContainer = document.getElementById('passportSkillsList');
    skillsContainer.textContent = '';
    p.skills.forEach(s => {
      const span = document.createElement('span');
      span.className = 'skill-tag';
      span.textContent = s;
      skillsContainer.appendChild(span);
    });

    // Timeline
    const timelineContainer = document.getElementById('passportTimelineList');
    timelineContainer.textContent = '';
    p.experience_timeline.forEach(item => {
      const entry = document.createElement('div');
      entry.className = 'timeline-entry';
      const h6 = document.createElement('h6');
      h6.textContent = `${item.year} — ${item.title}`;
      const pText = document.createElement('p');
      pText.textContent = item.description;
      entry.appendChild(h6);
      entry.appendChild(pText);
      timelineContainer.appendChild(entry);
    });
  }

  // Share & Copy link
  document.getElementById('btnSharePassport').addEventListener('click', async () => {
    if (!currentPassportToken) return;
    const passportUrl = `${window.location.origin}/passport/${currentPassportToken}`;
    if (navigator.share) {
      try {
        await navigator.share({
          title: `FairShift Digital Skill Passport - ${currentWorker?.name || 'Worker'}`,
          text: 'Verified skill credentials and safe duty history under UN SDG 8.',
          url: passportUrl
        });
      } catch (e) {}
    } else {
      copyPassportLink(passportUrl);
    }
  });

  document.getElementById('btnCopyPassportLink').addEventListener('click', () => {
    if (!currentPassportToken) return;
    const passportUrl = `${window.location.origin}/passport/${currentPassportToken}`;
    copyPassportLink(passportUrl);
  });

  function copyPassportLink(url) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(() => {
        showToast('Link Copied!', i18nStrings.link_copied || 'Passport link copied to clipboard.');
      });
    } else {
      showToast('Passport URL', url);
    }
  }

  // Register PWA Service Worker
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/static/sw.js').catch(err => {
        console.warn('SW registration skipped:', err);
      });
    });
  }

  // Initialize
  loadTranslations(currentLang).then(() => {
    checkSession();
  });

})();
