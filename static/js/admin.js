/**
 * FairShift Admin Dashboard - Vanilla JS Client (UN SDG 8)
 * Strict textContent usage for user-provided data (XSS safe).
 */

(function () {
  'use strict';

  let currentSiteId = '';
  let eventSource = null;

  // DOM Elements
  const adminLoginOverlay = document.getElementById('adminLoginOverlay');
  const adminLoginForm = document.getElementById('adminLoginForm');
  const adminPinInput = document.getElementById('adminPinInput');
  const adminMainLayout = document.getElementById('adminMainLayout');
  const adminSiteFilter = document.getElementById('adminSiteFilter');
  const adminLogoutBtn = document.getElementById('adminLogoutBtn');
  const adminThemeToggle = document.getElementById('adminThemeToggle');
  const btnRefreshDashboard = document.getElementById('btnRefreshDashboard');
  const ssePulseStatus = document.getElementById('ssePulseStatus');
  const navItems = document.querySelectorAll('.admin-nav-item');
  const sections = document.querySelectorAll('.admin-section');
  const toastContainer = document.getElementById('adminToastContainer');

  function showToast(title, message, isCritical = false) {
    const toast = document.createElement('div');
    toast.className = `toast ${isCritical ? 'toast-critical' : ''}`;
    
    const iconSpan = document.createElement('span');
    iconSpan.style.fontSize = '1.4rem';
    iconSpan.textContent = isCritical ? '🚨' : 'ℹ️';

    const textDiv = document.createElement('div');
    const h5 = document.createElement('h5');
    h5.style.fontSize = '0.92rem';
    h5.style.marginBottom = '0.15rem';
    h5.textContent = title;
    const p = document.createElement('p');
    p.style.fontSize = '0.82rem';
    p.textContent = message;

    textDiv.appendChild(h5);
    textDiv.appendChild(p);
    toast.appendChild(iconSpan);
    toast.appendChild(textDiv);
    toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.transition = 'opacity 0.4s ease';
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 400);
    }, 6000);
  }

  // --- 1. Theme Toggle ---
  adminThemeToggle.addEventListener('click', () => {
    const cur = document.documentElement.getAttribute('data-theme') || 'dark';
    const next = cur === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('fairshift_theme', next);
  });

  // --- 2. Authentication ---
  async function checkAdminAuth() {
    try {
      const res = await fetch(`/api/v1/admin/overview?site_id=${currentSiteId}`);
      if (res.ok) {
        adminLoginOverlay.style.display = 'none';
        adminMainLayout.style.display = 'flex';
        initSSE();
        loadAllData();
      } else {
        adminLoginOverlay.style.display = 'flex';
        adminMainLayout.style.display = 'none';
      }
    } catch (e) {
      adminLoginOverlay.style.display = 'flex';
      adminMainLayout.style.display = 'none';
    }
  }

  adminLoginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const pin = adminPinInput.value.trim();
    const btn = document.getElementById('adminLoginBtn');
    btn.disabled = true;
    btn.textContent = 'Verifying PIN...';

    try {
      const res = await fetch('/api/v1/admin/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pin })
      });

      if (res.ok) {
        adminLoginOverlay.style.display = 'none';
        adminMainLayout.style.display = 'flex';
        showToast('Access Granted', 'Authenticated as Safety & Payroll Admin');
        initSSE();
        loadAllData();
      } else {
        const err = await res.json();
        showToast('Login Failed', err.error?.message || 'Invalid PIN', true);
      }
    } catch (e) {
      showToast('Connection Error', 'Could not reach server', true);
    } finally {
      btn.disabled = false;
      btn.textContent = 'Authenticate as Admin';
    }
  });

  adminLogoutBtn.addEventListener('click', async () => {
    try {
      await fetch('/api/v1/admin/logout', { method: 'POST' });
    } catch (e) {}
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    adminLoginOverlay.style.display = 'flex';
    adminMainLayout.style.display = 'none';
    showToast('Logged Out', 'Admin session terminated');
  });

  // --- 3. Navigation ---
  navItems.forEach(item => {
    item.addEventListener('click', () => {
      const target = item.getAttribute('data-section');
      navItems.forEach(n => n.classList.remove('active'));
      item.classList.add('active');

      sections.forEach(s => {
        s.style.display = s.id === target ? 'flex' : 'none';
      });

      if (target === 'sectionOverview') loadOverview();
      if (target === 'sectionSafetyKanban') loadKanban();
      if (target === 'sectionFatigueAlerts') loadFatigueAlerts();
      if (target === 'sectionFeedback') loadFeedback();
    });
  });

  adminSiteFilter.addEventListener('change', (e) => {
    currentSiteId = e.target.value;
    loadAllData();
  });

  btnRefreshDashboard.addEventListener('click', () => {
    loadAllData();
    showToast('Dashboard Refreshed', 'Latest site logs synchronized.');
  });

  function loadAllData() {
    loadOverview();
    loadKanban();
    loadFatigueAlerts();
    loadFeedback();
  }

  // --- 4. Overview & KPIs & Pure SVG Bar Chart ---
  async function loadOverview() {
    try {
      const res = await fetch(`/api/v1/admin/overview?site_id=${currentSiteId}`);
      if (!res.ok) return;
      const data = await res.json();

      // Animated counters
      animateCounter('kpiAttendance', data.kpis.today_attendance);
      document.getElementById('kpiOvertime').textContent = `${data.kpis.weekly_overtime_hours.toFixed(1)}h`;
      animateCounter('kpiSafety', data.kpis.open_safety_reports_count);
      document.getElementById('kpiFeedback').textContent = `${data.kpis.avg_feedback_score.toFixed(1)} / 5`;

      document.getElementById('kpiCritCount').textContent = `${data.kpis.safety_by_severity.critical || 0} Crit`;
      document.getElementById('kpiHighCount').textContent = `${data.kpis.safety_by_severity.high || 0} High`;

      renderSvgChart(data.chart_data);
    } catch (e) {
      console.warn('Overview fetch error:', e);
    }
  }

  function animateCounter(elementId, targetValue) {
    const el = document.getElementById(elementId);
    if (!el) return;
    const start = parseInt(el.textContent, 10) || 0;
    const duration = 600;
    const startTime = performance.now();

    function update(now) {
      const progress = Math.min((now - startTime) / duration, 1);
      const val = Math.floor(start + (targetValue - start) * progress);
      el.textContent = val;
      if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
  }

  // Pure SVG Bar Chart
  function renderSvgChart(chartData) {
    const svg = document.getElementById('workerWeeklyHoursSvg');
    if (!svg || !chartData || !chartData.workers) return;
    svg.textContent = ''; // clear

    const workers = chartData.workers;
    const width = 760;
    const height = 260;
    const paddingLeft = 50;
    const paddingBottom = 45;
    const paddingTop = 30;
    const chartHeight = height - paddingBottom - paddingTop;
    const chartWidth = width - paddingLeft - 20;

    const maxHours = 70.0; // scale up to 70h

    // Background Grid lines
    [0, 20, 40, 48, 60].forEach(val => {
      const y = height - paddingBottom - (val / maxHours) * chartHeight;
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', paddingLeft);
      line.setAttribute('x2', width - 20);
      line.setAttribute('y1', y);
      line.setAttribute('y2', y);
      line.setAttribute('stroke', val === 60 ? '#EF4444' : val === 48 ? '#F59E0B' : 'rgba(255,255,255,0.08)');
      line.setAttribute('stroke-width', val >= 48 ? '1.5' : '1');
      if (val >= 48) {
        line.setAttribute('stroke-dasharray', '4,4');
      }
      svg.appendChild(line);

      // Y-axis label
      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', paddingLeft - 8);
      text.setAttribute('y', y + 4);
      text.setAttribute('text-anchor', 'end');
      text.setAttribute('fill', val === 60 ? '#EF4444' : val === 48 ? '#F59E0B' : '#94A3B8');
      text.setAttribute('font-size', '11');
      text.textContent = `${val}h`;
      svg.appendChild(text);
    });

    // Render Bars
    const barWidth = Math.min(48, Math.max(22, (chartWidth / Math.max(workers.length, 1)) - 14));
    const step = chartWidth / Math.max(workers.length, 1);

    workers.forEach((w, i) => {
      const x = paddingLeft + (i * step) + (step - barWidth) / 2;
      const barH = (Math.min(w.hours, maxHours) / maxHours) * chartHeight;
      const y = height - paddingBottom - barH;

      const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rect.setAttribute('x', x);
      rect.setAttribute('y', y);
      rect.setAttribute('width', barWidth);
      rect.setAttribute('height', Math.max(barH, 2));
      rect.setAttribute('rx', '4');

      // Color coding: Red if > 60h, Amber if > 48h, Teal otherwise
      let barFill = '#14B8A6';
      if (w.hours > 60.0) barFill = '#EF4444';
      else if (w.hours > 48.0) barFill = '#F59E0B';
      rect.setAttribute('fill', barFill);
      svg.appendChild(rect);

      // Value label on top of bar
      const valText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      valText.setAttribute('x', x + barWidth / 2);
      valText.setAttribute('y', y - 6);
      valText.setAttribute('text-anchor', 'middle');
      valText.setAttribute('fill', barFill);
      valText.setAttribute('font-size', '11');
      valText.setAttribute('font-weight', '700');
      valText.textContent = `${w.hours}h`;
      svg.appendChild(valText);

      // Worker name on X axis (truncated)
      const nameText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      nameText.setAttribute('x', x + barWidth / 2);
      nameText.setAttribute('y', height - paddingBottom + 16);
      nameText.setAttribute('text-anchor', 'middle');
      nameText.setAttribute('fill', '#94A3B8');
      nameText.setAttribute('font-size', '11');
      const shortName = w.name.split(' ')[0];
      nameText.textContent = shortName;
      svg.appendChild(nameText);
    });
  }

  // --- 5. Safety Kanban Queue ---
  async function loadKanban() {
    try {
      const res = await fetch(`/api/v1/admin/safety-kanban?site_id=${currentSiteId}`);
      if (!res.ok) return;
      const kanban = await res.json();
      renderKanban(kanban);
    } catch (e) {
      console.warn('Kanban fetch error:', e);
    }
  }

  function renderKanban(kanban) {
    const cols = {
      Reported: document.getElementById('cardsReported'),
      Acknowledged: document.getElementById('cardsAcknowledged'),
      Resolved: document.getElementById('cardsResolved')
    };

    let total = 0;
    Object.keys(cols).forEach(status => {
      const container = cols[status];
      container.textContent = '';
      const list = kanban[status] || [];
      total += list.length;
      document.getElementById(`count${status}`).textContent = list.length;

      if (list.length === 0) {
        const empty = document.createElement('div');
        empty.style.cssText = 'color: var(--text-muted); font-size: 0.8rem; text-align: center; padding: 2rem 0;';
        empty.textContent = 'No cards in this column';
        container.appendChild(empty);
        return;
      }

      list.forEach(item => {
        const card = document.createElement('div');
        card.className = `kanban-card ${item.severity === 'critical' ? 'critical-pulse' : ''}`;

        const top = document.createElement('div');
        top.style.cssText = 'display: flex; justify-content: space-between; align-items: center;';

        const cat = document.createElement('span');
        cat.className = 'badge badge-info';
        cat.textContent = item.category.toUpperCase();

        const sev = document.createElement('span');
        sev.className = `badge ${item.severity === 'critical' ? 'badge-critical' : item.severity === 'high' ? 'badge-warning' : 'badge-info'}`;
        sev.textContent = item.severity.toUpperCase();

        top.appendChild(cat);
        top.appendChild(sev);

        const summary = document.createElement('p');
        summary.style.cssText = 'font-size: 0.88rem; font-weight: 600; color: var(--text-primary);';
        summary.textContent = item.summary_en;

        const original = document.createElement('p');
        original.style.cssText = 'font-size: 0.78rem; color: var(--text-secondary);';
        original.textContent = `"${item.input_text}"`;

        // Action Buttons to shift status
        const actions = document.createElement('div');
        actions.style.cssText = 'display: flex; gap: 0.4rem; margin-top: 0.4rem;';

        if (status === 'Reported') {
          const btnAck = document.createElement('button');
          btnAck.className = 'btn btn-secondary btn-sm';
          btnAck.textContent = 'Acknowledge';
          btnAck.onclick = () => updateReportStatus(item.id, 'Acknowledged');
          actions.appendChild(btnAck);

          const btnRes = document.createElement('button');
          btnRes.className = 'btn btn-primary btn-sm';
          btnRes.textContent = 'Resolve';
          btnRes.onclick = () => updateReportStatus(item.id, 'Resolved');
          actions.appendChild(btnRes);
        } else if (status === 'Acknowledged') {
          const btnRes = document.createElement('button');
          btnRes.className = 'btn btn-primary btn-sm';
          btnRes.textContent = 'Mark Resolved';
          btnRes.onclick = () => updateReportStatus(item.id, 'Resolved');
          actions.appendChild(btnRes);

          const btnBack = document.createElement('button');
          btnBack.className = 'btn btn-secondary btn-sm';
          btnBack.textContent = 'Back to Reported';
          btnBack.onclick = () => updateReportStatus(item.id, 'Reported');
          actions.appendChild(btnBack);
        } else if (status === 'Resolved') {
          const btnReopen = document.createElement('button');
          btnReopen.className = 'btn btn-secondary btn-sm';
          btnReopen.textContent = 'Reopen';
          btnReopen.onclick = () => updateReportStatus(item.id, 'Reported');
          actions.appendChild(btnReopen);
        }

        card.appendChild(top);
        card.appendChild(summary);
        card.appendChild(original);
        card.appendChild(actions);
        container.appendChild(card);
      });
    });

    document.getElementById('kanbanTotalBadge').textContent = `${total} Total Reports`;
  }

  async function updateReportStatus(reportId, newStatus) {
    try {
      const res = await fetch(`/api/v1/admin/safety-reports/${reportId}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus })
      });
      if (res.ok) {
        showToast('Status Updated', `Report moved to ${newStatus}`);
        loadKanban();
        loadOverview();
      }
    } catch (e) {
      showToast('Error', 'Could not update status', true);
    }
  }

  // --- 6. Fatigue Early Warning Table ---
  async function loadFatigueAlerts() {
    try {
      const res = await fetch(`/api/v1/admin/fatigue-alerts?site_id=${currentSiteId}`);
      if (!res.ok) return;
      const alerts = await res.json();
      renderFatigueTable(alerts);
    } catch (e) {
      console.warn('Fatigue alerts fetch error:', e);
    }
  }

  function renderFatigueTable(alerts) {
    const tbody = document.getElementById('fatigueAlertsTableBody');
    tbody.textContent = '';

    if (!alerts || alerts.length === 0) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 7;
      td.style.cssText = 'text-align: center; color: var(--color-success); padding: 2rem; font-weight: 600;';
      td.textContent = '✓ No active fatigue violations detected across selected workforce.';
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    alerts.forEach(a => {
      const tr = document.createElement('tr');

      // Severity chip
      const tdSev = document.createElement('td');
      const chip = document.createElement('span');
      chip.className = `badge ${a.severity === 'critical' ? 'badge-critical' : 'badge-warning'}`;
      chip.textContent = a.severity.toUpperCase();
      tdSev.appendChild(chip);

      // Worker
      const tdWorker = document.createElement('td');
      tdWorker.style.fontWeight = '700';
      tdWorker.textContent = a.worker_name;

      // Site
      const tdSite = document.createElement('td');
      tdSite.textContent = a.site_name;

      // Violation
      const tdType = document.createElement('td');
      tdType.textContent = a.description;

      // Measured
      const tdVal = document.createElement('td');
      tdVal.style.fontWeight = '700';
      tdVal.style.color = a.severity === 'critical' ? 'var(--color-critical)' : 'var(--color-warning)';
      tdVal.textContent = `${a.measured_value}h`;

      // Threshold
      const tdThresh = document.createElement('td');
      tdThresh.textContent = `${a.threshold_value}h`;

      // Recommended Action
      const tdAction = document.createElement('td');
      tdAction.style.cssText = 'color: var(--text-secondary); font-size: 0.8rem;';
      tdAction.textContent = a.recommended_action;

      tr.appendChild(tdSev);
      tr.appendChild(tdWorker);
      tr.appendChild(tdSite);
      tr.appendChild(tdType);
      tr.appendChild(tdVal);
      tr.appendChild(tdThresh);
      tr.appendChild(tdAction);
      tbody.appendChild(tr);
    });
  }

  // --- 7. Anonymous Feedback Summary ---
  async function loadFeedback() {
    try {
      const res = await fetch(`/api/v1/admin/feedback-summary?site_id=${currentSiteId}`);
      if (!res.ok) return;
      const data = await res.json();
      renderFeedbackSummaries(data);
    } catch (e) {
      console.warn('Feedback summary fetch error:', e);
    }
  }

  function renderFeedbackSummaries(sites) {
    const container = document.getElementById('feedbackSummariesContainer');
    container.textContent = '';

    if (!sites || sites.length === 0) {
      const empty = document.createElement('p');
      empty.textContent = 'No feedback recorded yet.';
      container.appendChild(empty);
      return;
    }

    sites.forEach(s => {
      const card = document.createElement('div');
      card.className = 'card';

      const head = document.createElement('div');
      head.style.cssText = 'display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-subtle); padding-bottom: 0.75rem; margin-bottom: 1rem;';

      const title = document.createElement('h4');
      title.style.fontSize = '1.05rem';
      title.textContent = s.site_name;

      const scoreBadge = document.createElement('span');
      scoreBadge.className = 'badge badge-info';
      scoreBadge.textContent = `Overall Score: ${s.overall_avg} / 5 (${s.total_reviews} reviews)`;

      head.appendChild(title);
      head.appendChild(scoreBadge);

      const metrics = document.createElement('div');
      metrics.style.cssText = 'display: flex; gap: 2rem; margin-bottom: 1rem;';

      const m1 = document.createElement('div');
      m1.textContent = `Supervisor Treatment: ${s.avg_manager} / 5`;
      const m2 = document.createElement('div');
      m2.textContent = `Facility Conditions: ${s.avg_conditions} / 5`;
      metrics.appendChild(m1);
      metrics.appendChild(m2);

      // Comments list
      const commList = document.createElement('div');
      commList.style.cssText = 'display: flex; flex-direction: column; gap: 0.5rem;';

      if (s.comments && s.comments.length > 0) {
        s.comments.forEach(c => {
          const block = document.createElement('blockquote');
          block.style.cssText = 'font-style: italic; font-size: 0.85rem; color: var(--text-primary); border-left: 3px solid var(--color-primary); padding-left: 0.75rem;';
          block.textContent = `"${c.comment}"`;
          commList.appendChild(block);
        });
      } else {
        const noComm = document.createElement('p');
        noComm.style.cssText = 'font-size: 0.8rem; color: var(--text-muted);';
        noComm.textContent = 'No worker text comments recorded.';
        commList.appendChild(noComm);
      }

      card.appendChild(head);
      card.appendChild(metrics);
      card.appendChild(commList);
      container.appendChild(card);
    });
  }

  // --- 8. Real-time Server-Sent Events (SSE) Stream ---
  function initSSE() {
    if (eventSource) return;

    eventSource = new EventSource('/api/v1/admin/stream');

    eventSource.onopen = () => {
      ssePulseStatus.style.display = 'flex';
      console.log('SSE Stream connected to FairShift event bus.');
    };

    eventSource.addEventListener('message', (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('SSE Event received:', data);

        if (data.type === 'safety_report_created') {
          // Instant Red Toast for Critical / High Hazards
          if (data.alert) {
            showToast(
              `🚨 HIGH HAZARD REPORTED (${data.report.severity.toUpperCase()})`,
              `${data.report.summary_en}`,
              true
            );
          } else {
            showToast('New Safety Report', data.report.summary_en, false);
          }
          loadKanban();
          loadOverview();
        } else if (data.type === 'feedback_created') {
          showToast('New Anonymous Feedback', 'Worker submitted site review (anonymized).');
          loadFeedback();
          loadOverview();
        } else if (data.type === 'safety_report_updated') {
          loadKanban();
          loadOverview();
        }
      } catch (err) {
        console.warn('Error parsing SSE event data:', err);
      }
    });

    eventSource.onerror = (err) => {
      console.warn('SSE connection interrupted. Reconnecting automatically...');
      // Reconnect handled natively by EventSource
    };
  }

  // Initial Check
  checkAdminAuth();

})();
