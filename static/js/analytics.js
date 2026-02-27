// analytics.js — упрощённая «текстовая» аналитика (без графиков)
//
// Цель: максимум стабильности и минимум зависимостей.
// - никаких Chart.js
// - никакой авто‑подгрузки по wheel/scroll
// - аналитика грузится ТОЛЬКО по нажатию кнопок периода

(function () {
  'use strict';

  const PERIOD_LABELS = {
    1: '1 день',
    7: 'Неделя',
    30: 'Месяц',
    90: 'Квартал',
    182: 'Полгода',
    365: 'Год',
  };

  function $(id) { return document.getElementById(id); }

  function fmtPct(x) {
    if (x === null || x === undefined) return '0%';
    const n = Number(x);
    if (!isFinite(n)) return '0%';
    // 0.0–100.0
    return (Math.round(n * 10) / 10).toFixed(1).replace(/\.0$/, '') + '%';
  }

  function safeInt(x) {
    const n = parseInt(String(x || '0'), 10);
    return Number.isFinite(n) ? n : 0;
  }

  function setActive(btns, activeDays) {
    btns.forEach((b) => {
      const d = safeInt(b.dataset.days);
      b.classList.toggle('active', d === activeDays);
    });
  }

  async function fetchText(days) {
    const resp = await fetch(`/api/analytics/text?days=${encodeURIComponent(days)}`, {
      headers: { 'Accept': 'application/json' },
      cache: 'no-store',
    });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    return await resp.json();
  }

  function renderText(target, days, data) {
    const label = PERIOD_LABELS[days] || `${days} дней`;

    const a = data.addresses || {};
    const r = data.requests || {};

    const totalAddr = safeInt(a.total);
    const addedAddr = safeInt(a.added);
    const addedAddrPct = fmtPct(a.added_percent);

    const totalReq = safeInt(r.total);
    const createdReq = safeInt(r.created);
    const createdReqPct = fmtPct(r.created_percent);

    const approvedTotal = safeInt(r.approved_total);
    const approved = safeInt(r.approved);
    const approvedPct = fmtPct(r.approved_percent);

    const rejectedTotal = safeInt(r.rejected_total);
    const rejected = safeInt(r.rejected);
    const rejectedPct = fmtPct(r.rejected_percent);

    const since = (data.since || '').toString();

    target.innerHTML = `
      <div class="analytics-text__card">
        <div class="analytics-text__title">Период: <b>${label}</b> <span class="muted">(${days} дн.)</span></div>
        <div class="analytics-text__meta muted">Срез от: ${since || '—'}</div>

        <div class="analytics-text__block">
          <div class="analytics-text__row"><b>Адреса</b></div>
          <div class="analytics-text__row">Добавлено: <b>${addedAddr}</b> <span class="muted">(${addedAddrPct} от всех ${totalAddr})</span></div>
        </div>

        <div class="analytics-text__block">
          <div class="analytics-text__row"><b>Заявки</b></div>
          <div class="analytics-text__row">Создано: <b>${createdReq}</b> <span class="muted">(${createdReqPct} от всех ${totalReq})</span></div>
          <div class="analytics-text__row">Одобрено: <b>${approved}</b> <span class="muted">(${approvedPct} от всех ${approvedTotal})</span></div>
          <div class="analytics-text__row">Отклонено: <b>${rejected}</b> <span class="muted">(${rejectedPct} от всех ${rejectedTotal})</span></div>
        </div>

        <div class="analytics-text__hint muted">Подсказка: данные обновляются только когда вы нажимаете кнопку периода.</div>
      </div>
    `;
  }

  function init() {
    const btnAnalytics = $('btn-analytics');
    const backdrop = $('analytics-backdrop');
    const closeBtn = $('analytics-close');
    const out = $('analytics-text');

    if (!backdrop || !out) return;

    const periodBtns = Array.from(backdrop.querySelectorAll('.analytics-period-btn'));

    async function load(days) {
      out.textContent = 'Загрузка…';
      try {
        const data = await fetchText(days);
        renderText(out, days, data);
      } catch (e) {
        console.warn('analytics load failed', e);
        out.innerHTML = '<div class="analytics-text__card"><b>Не удалось загрузить аналитику</b><div class="muted">Проверь консоль и /api/analytics/text</div></div>';
      }
    }

    function open() {
      backdrop.classList.add('open');
      // По умолчанию показываем неделю — это самый понятный период.
      const defaultDays = 7;
      setActive(periodBtns, defaultDays);
      load(defaultDays);
    }

    function close() {
      backdrop.classList.remove('open');
    }

    if (btnAnalytics) {
      btnAnalytics.addEventListener('click', open);
    }
    if (closeBtn) {
      closeBtn.addEventListener('click', close);
    }

    // Клик по подложке закрывает модалку
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) close();
    });

    periodBtns.forEach((b) => {
      b.addEventListener('click', () => {
        const days = Math.max(1, Math.min(365, safeInt(b.dataset.days)));
        setActive(periodBtns, days);
        load(days);
      });
    });
  }

  document.addEventListener('DOMContentLoaded', init);
})();
