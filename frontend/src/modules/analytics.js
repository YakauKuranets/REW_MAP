/* ========= Аналитика (дашборд) ========= */
/**
 * Модуль аналитики. Использует:
 *  - /api/analytics/summary
 *  - функции refresh(), renderQuickCounters(), updateCurrentFilterLabel()
 */
(function() {
  function openAnalytics() {
    const ab = document.getElementById('analytics-backdrop');
    if (ab) {
      ab.classList.add('open');
      loadAnalyticsSummary();
    }
  }
  function closeAnalytics() {
    const ab = document.getElementById('analytics-backdrop');
    if (ab) {
      ab.classList.remove('open');
    }
  }

  async function loadAnalyticsSummary() {
    const root = document.getElementById('analytics-backdrop');
    if (!root) return;
    const overview = root.querySelector('#analytics-overview');
    const catWrap = root.querySelector('#analytics-categories');
    const statusWrap = root.querySelector('#analytics-statuses');
    const rangeSel = root.querySelector('#analytics-range');
    const range = rangeSel ? rangeSel.value : 'all';
    if (overview) {
      overview.textContent = 'Загрузка…';
    }
    if (catWrap) catWrap.innerHTML = '';
    if (statusWrap) statusWrap.innerHTML = '';
    try {
      const resp = await fetch('/api/analytics/summary');
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      const total = data.total || 0;
      const pending = data.pending || 0;
      const approved = data.approved || 0;
      const rejected = data.rejected || 0;
      const added7d = data.added_last_7d || 0;

      if (overview) {
        if (range === '7d') {
          overview.innerHTML =
            '<div class="section">' +
            '<div>Новых адресов за 7 дней: <b>' + added7d + '</b></div>' +
            '<div class="muted">Заявки ниже показаны в общем разрезе по всем данным.</div>' +
            '<div style="margin-top:0.5rem;">Всего адресов в системе: <b>' + total + '</b></div>' +
            '<div>Активных заявок (всего): <b>' + pending + '</b></div>' +
            '<div>Одобренных заявок (всего): <b>' + approved + '</b></div>' +
            '<div>Отклонённых заявок (всего): <b>' + rejected + '</b></div>' +
            '</div>';
        } else {
          overview.innerHTML =
            '<div class="section">' +
            '<div>Всего адресов: <b>' + total + '</b></div>' +
            '<div>Активных заявок: <b>' + pending + '</b></div>' +
            '<div>Одобренных заявок: <b>' + approved + '</b></div>' +
            '<div>Отклонённых заявок: <b>' + rejected + '</b></div>' +
            '<div>Добавлено за 7 дней: <b>' + added7d + '</b></div>' +
            '</div>';
        }
      }

      const byCat = data.by_category || {};
      const byStatus = data.by_status || {};


  function renderDict(container, dict) {
        if (!container) return;
        const entries = Object.entries(dict);
        if (!entries.length) {
          container.innerHTML = '<div class="muted">Нет данных</div>';
          return;
        }
        const maxVal = entries.reduce((m, [, v]) => Math.max(m, v || 0), 0) || 1;
        container.innerHTML = '';
        for (const [label, countRaw] of entries) {
          const count = countRaw || 0;
          const pct = Math.round((count / maxVal) * 100);
          const wrap = document.createElement('div');
          wrap.className = 'progress-wrap';
          const bar = document.createElement('div');
          bar.className = 'progress';
          bar.style.setProperty('--progress', pct + '%');
          bar.innerHTML = '<span>' + count + '</span>';
          const lbl = document.createElement('span');
          lbl.className = 'muted';
          lbl.textContent = label || '(пусто)';
          wrap.appendChild(bar);
          wrap.appendChild(lbl);

          // Клик по строке аналитики — применить фильтр и обновить карту/список
          wrap.addEventListener('click', async () => {
            const key = (label || '').trim();
            if (!key) return;

            // Аналитика по категориям
            if (container.id === 'analytics-categories') {
              const catSel = document.getElementById('filter-category');
              if (catSel) {
                catSel.value = key;
              }
              const l = document.getElementById('opt-local');  if (l) l.checked = false;
              const r = document.getElementById('opt-remote'); if (r) r.checked = false;
            }

            // Аналитика по статусам (локальный / удалённый доступ)
            if (container.id === 'analytics-statuses') {
              const l = document.getElementById('opt-local');
              const r = document.getElementById('opt-remote');
              const lower = key.toLowerCase();
              if (l && r) {
                const isLocal = lower.includes('локал');
                l.checked = isLocal;
                r.checked = !isLocal;
              }
            }

            if (typeof refresh === 'function') {
              await refresh();
            }
            if (typeof renderQuickCounters === 'function') {
              renderQuickCounters();
            }
            closeAnalytics();
          });

          container.appendChild(wrap);
        }
      }

  catWrap, byCat);
      renderDict(statusWrap, byStatus);
    } catch (err) {

  document.addEventListener('DOMContentLoaded', () => {
    // Кнопка аналитики (дашборд)

    const btnAnalytics = document.getElementById('btn-analytics');
    const analyticsBackdrop = document.getElementById('analytics-backdrop');
    const analyticsClose = document.getElementById('analytics-close');
    const analyticsRange = document.getElementById('analytics-range');
    const analyticsReset = document.getElementById('analytics-reset-filters');

    if (btnAnalytics) {
      btnAnalytics.addEventListener('click', () => {
        openAnalytics();
      });
    }
    if (analyticsClose) {
      analyticsClose.addEventListener('click', () => {
        closeAnalytics();
      });
    }
    if (analyticsBackdrop) {
      analyticsBackdrop.addEventListener('click', (e) => {
        if (e.target === analyticsBackdrop) {
          closeAnalytics();
        }
      });
    }
    if (analyticsRange) {
      analyticsRange.addEventListener('change', () => {
        loadAnalyticsSummary();
      });
    }
    if (analyticsReset) {
      analyticsReset.addEventListener('click', async () => {
        const catSel = document.getElementById('filter-category');
        if (catSel) catSel.value = '';
        const optLocal = document.getElementById('opt-local');
        const optRemote = document.getElementById('opt-remote');
        if (optLocal) optLocal.checked = false;
        if (optRemote) optRemote.checked = false;
        if (typeof refresh === 'function') {
          await refresh();
        }
        if (typeof renderQuickCounters === 'function') {
          renderQuickCounters();
        }
        if (typeof updateCurrentFilterLabel === 'function') {
          updateCurrentFilterLabel();
        }
        closeAnalytics();
      });
    }
  });
})();
