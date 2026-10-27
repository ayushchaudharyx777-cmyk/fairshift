/**
 * FairShift Public Skill Passport - Vanilla JS (UN SDG 8)
 * Strict textContent usage for user-provided data (XSS safe).
 */

(function () {
  'use strict';

  const pathParts = window.location.pathname.split('/');
  const token = pathParts[pathParts.length - 1];

  const loadingState = document.getElementById('passportLoadingState');
  const errorState = document.getElementById('passportErrorState');
  const contentState = document.getElementById('passportContentState');
  const toastContainer = document.getElementById('passportToastContainer');

  function showToast(title, message) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    const textDiv = document.createElement('div');
    const h5 = document.createElement('h5');
    h5.style.fontSize = '0.9rem';
    h5.textContent = title;
    const p = document.createElement('p');
    p.style.fontSize = '0.8rem';
    p.textContent = message;
    textDiv.appendChild(h5);
    textDiv.appendChild(p);
    toast.appendChild(textDiv);
    toastContainer.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
  }

  // Theme Toggle
  const themeToggleBtn = document.getElementById('themeToggleBtn');
  const savedTheme = localStorage.getItem('fairshift_theme') || 'dark';
  document.documentElement.setAttribute('data-theme', savedTheme);

  themeToggleBtn.addEventListener('click', () => {
    const cur = document.documentElement.getAttribute('data-theme');
    const next = cur === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('fairshift_theme', next);
  });

  async function loadPassport() {
    if (!token) {
      showError();
      return;
    }

    try {
      const res = await fetch(`/api/v1/passport/${token}`);
      if (!res.ok) {
        showError();
        return;
      }

      const p = await res.json();
      renderPassport(p);
    } catch (e) {
      showError();
    }
  }

  function showError() {
    loadingState.style.display = 'none';
    errorState.style.display = 'block';
    contentState.style.display = 'none';
  }

  function renderPassport(p) {
    loadingState.style.display = 'none';
    errorState.style.display = 'none';
    contentState.style.display = 'flex';

    document.getElementById('pubAvatar').textContent = p.avatar_initials;
    document.getElementById('pubWorkerName').textContent = p.worker_name;
    document.getElementById('pubRole').textContent = p.role;
    document.getElementById('pubSiteName').textContent = `${p.site_name} • ${p.sector.toUpperCase()} SECTOR`;

    // Badges
    const badgesContainer = document.getElementById('pubBadgesList');
    badgesContainer.textContent = '';
    p.verified_badges.forEach(b => {
      const chip = document.createElement('span');
      chip.className = 'badge badge-success';
      chip.textContent = `✓ ${b}`;
      badgesContainer.appendChild(chip);
    });

    // Skills
    const skillsContainer = document.getElementById('pubSkillsList');
    skillsContainer.textContent = '';
    p.skills.forEach(s => {
      const span = document.createElement('span');
      span.className = 'skill-tag';
      span.textContent = s;
      skillsContainer.appendChild(span);
    });

    // Trainings
    const trainingsContainer = document.getElementById('pubTrainingsList');
    trainingsContainer.textContent = '';
    p.trainings.forEach(t => {
      const div = document.createElement('div');
      div.className = 'line-item-row';
      const left = document.createElement('div');
      left.className = 'line-item-info';
      const h5 = document.createElement('h5');
      h5.textContent = t.title;
      const span = document.createElement('span');
      span.textContent = `Issued by ${t.issued_by} • Valid until ${t.valid_until}`;
      left.appendChild(h5);
      left.appendChild(span);

      const badge = document.createElement('span');
      badge.className = 'badge badge-success';
      badge.textContent = t.status || 'Active';

      div.appendChild(left);
      div.appendChild(badge);
      trainingsContainer.appendChild(div);
    });

    // Employers
    const employersContainer = document.getElementById('pubEmployersList');
    employersContainer.textContent = '';
    p.past_employers.forEach(emp => {
      const div = document.createElement('div');
      div.className = 'line-item-row';
      const left = document.createElement('div');
      left.className = 'line-item-info';
      const h5 = document.createElement('h5');
      h5.textContent = emp.company;
      const span = document.createElement('span');
      span.textContent = `${emp.role} (${emp.period})`;
      left.appendChild(h5);
      left.appendChild(span);

      const badge = document.createElement('span');
      badge.className = 'badge badge-info';
      badge.textContent = emp.verified ? 'Verified Employer' : 'Past Role';

      div.appendChild(left);
      div.appendChild(badge);
      employersContainer.appendChild(div);
    });

    // Timeline
    const timelineContainer = document.getElementById('pubTimelineList');
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

    // Share & Copy Handlers
    const fullUrl = window.location.href;
    document.getElementById('btnPubShare').onclick = async () => {
      if (navigator.share) {
        try {
          await navigator.share({
            title: `Skill Passport - ${p.worker_name}`,
            text: `Verified trade skill credential for ${p.worker_name} under UN SDG 8.`,
            url: fullUrl
          });
        } catch (e) {}
      } else {
        copyUrl(fullUrl);
      }
    };

    document.getElementById('btnPubCopy').onclick = () => {
      copyUrl(fullUrl);
    };
  }

  function copyUrl(url) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(() => {
        showToast('Link Copied', 'Passport URL copied to clipboard.');
      });
    } else {
      showToast('Passport URL', url);
    }
  }

  loadPassport();

})();
