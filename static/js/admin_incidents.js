/* admin_incidents.js — список и поиск оперативных инцидентов

   Этот модуль загружает статистику и список инцидентов
   из API и позволяет фильтровать по статусам и поисковой
   строке. В дальнейшем он может быть расширен для
   отображения таймлайна, назначений и SLA‑индикаторов.
*/

(function(){
  'use strict';

  // DOM элементы
  const elServerTime = document.getElementById('server-time');
  const elQ = document.getElementById('inc-q');
  const elTag = document.getElementById('inc-tag');
  const btnSearch = document.getElementById('inc-btn-search');
  const chkNew = document.getElementById('inc-flt-new');
  const chkAssigned = document.getElementById('inc-flt-assigned');
  const chkEnroute = document.getElementById('inc-flt-enroute');
  const chkOnScene = document.getElementById('inc-flt-on_scene');
  const chkResolved = document.getElementById('inc-flt-resolved');
  const chkClosed = document.getElementById('inc-flt-closed');
  const elRefresh = document.getElementById('inc-refresh');
  const elList = document.getElementById('inc-list');
  const elAlertbar = document.getElementById('inc-alertbar');
  const elKpiTotal = document.getElementById('kpi-inc-total');
  const elKpiNew = document.getElementById('kpi-inc-new');
  const elKpiAssigned = document.getElementById('kpi-inc-assigned');
  const elKpiEnroute = document.getElementById('kpi-inc-enroute');
  const elKpiOnScene = document.getElementById('kpi-inc-on_scene');
  const elKpiResolved = document.getElementById('kpi-inc-resolved');
  const elKpiClosed = document.getElementById('kpi-inc-closed');
  const elToast = document.getElementById('toast');

  // Фильтры по приоритету (P1–P5) и датам создания
  const chkP1 = document.getElementById('inc-pri-1');
  const chkP2 = document.getElementById('inc-pri-2');
  const chkP3 = document.getElementById('inc-pri-3');
  const chkP4 = document.getElementById('inc-pri-4');
  const chkP5 = document.getElementById('inc-pri-5');
  const elFromDate = document.getElementById('inc-from-date');
  const elToDate = document.getElementById('inc-to-date');

  // Показать всплывающее уведомление
  function showToast(msg, type){
    if(!elToast) return;
    elToast.textContent = msg;
    elToast.className = 'adm-toast ' + (type || '');
    elToast.style.display = 'block';
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => { elToast.style.display = 'none'; }, 3200);
  }

  function escapeHtml(s){
    return String(s ?? '')
      .replaceAll('&','&amp;')
      .replaceAll('<','&lt;')
      .replaceAll('>','&gt;')
      .replaceAll('"','&quot;')
      .replaceAll("'", '&#39;');
  }

  /**
   * Отрисовать индикаторы KPI на основе данных stats.
   *
   * @param {Object} stats
   */
  function renderKpi(stats){
    try{
      const byStatus = stats.by_status || {};
      elKpiTotal.textContent = (stats.total != null) ? String(stats.total) : '—';
      elKpiNew.textContent = byStatus['new'] || 0;
      elKpiAssigned.textContent = byStatus['assigned'] || 0;
      elKpiEnroute.textContent = byStatus['enroute'] || 0;
      elKpiOnScene.textContent = byStatus['on_scene'] || 0;
      elKpiResolved.textContent = byStatus['resolved'] || 0;
      elKpiClosed.textContent = byStatus['closed'] || 0;
    }catch(e){ /* noop */ }
  }

  /**
   * Загрузить статистику инцидентов.
   */
  async function loadStats(){
    try{
      const res = await fetch('/api/incidents/stats', { credentials:'same-origin' });
      const txt = await res.text();
      let data = null;
      try { data = txt ? JSON.parse(txt) : null; } catch(e){ data = { _raw: txt }; }
      if(!res.ok) throw { status: res.status, data };
      renderKpi(data);
    }catch(e){ /* ignore KPI errors */ }
  }

  /**
   * Загрузить данные о просроченных SLA и показать предупреждение.
   * Отображает числа нарушений для принятия, выезда и прибытия,
   * если хотя бы один тип нарушения > 0. Иначе скрывает панель.
   */
  async function loadAlerts(){
    if(!elAlertbar) return;
    try{
      const res = await fetch('/api/incidents/sla_overdue', { credentials:'same-origin' });
      if(!res.ok) throw new Error('bad');
      const data = await res.json();
      const a = data.accept_breach_count || 0;
      const e = data.enroute_breach_count || 0;
      const o = data.on_scene_breach_count || 0;
      if(a > 0 || e > 0 || o > 0){
        elAlertbar.style.display = 'block';
        // Формируем текст предупреждения
        const parts = [];
        if(a > 0) parts.push(`Принятие: ${a}`);
        if(e > 0) parts.push(`В пути: ${e}`);
        if(o > 0) parts.push(`На месте: ${o}`);
        elAlertbar.innerHTML = '<strong>Просрочено SLA</strong> — ' + parts.join(' | ');
      }else{
        elAlertbar.style.display = 'none';
        elAlertbar.innerHTML = '';
      }
    }catch(e){
      // скрываем при ошибках
      elAlertbar.style.display = 'none';
      elAlertbar.innerHTML = '';
    }
  }

  /**
   * Собрать параметры фильтров для запроса.
   *
   * @returns {string} строка query‐параметров без ведущего вопроса
   */
  function buildQuery(){
    const params = [];
    const q = (elQ && elQ.value || '').trim();
    if(q) params.push('q=' + encodeURIComponent(q));
    const tag = (elTag && elTag.value || '').trim();
    if(tag) params.push('tag=' + encodeURIComponent(tag));
    const statuses = [];
    if(chkNew && chkNew.checked) statuses.push('new');
    if(chkAssigned && chkAssigned.checked) statuses.push('assigned');
    if(chkEnroute && chkEnroute.checked) statuses.push('enroute');
    if(chkOnScene && chkOnScene.checked) statuses.push('on_scene');
    if(chkResolved && chkResolved.checked) statuses.push('resolved');
    if(chkClosed && chkClosed.checked) statuses.push('closed');
    if(statuses.length) params.push('status=' + statuses.map(encodeURIComponent).join(','));
    // в дальнейшем сюда можно добавить priority, date range, limit/offset
    // Приоритеты
    const priorities = [];
    if(chkP1 && chkP1.checked) priorities.push(1);
    if(chkP2 && chkP2.checked) priorities.push(2);
    if(chkP3 && chkP3.checked) priorities.push(3);
    if(chkP4 && chkP4.checked) priorities.push(4);
    if(chkP5 && chkP5.checked) priorities.push(5);
    if(priorities.length) params.push('priority=' + priorities.join(','));
    // Дата создания (ISO)
    const fromDate = elFromDate && elFromDate.value ? elFromDate.value : '';
    const toDate = elToDate && elToDate.value ? elToDate.value : '';
    if(fromDate) params.push('from=' + encodeURIComponent(fromDate));
    if(toDate) params.push('to=' + encodeURIComponent(toDate));

    params.push('limit=100');
    params.push('offset=0');
    return params.join('&');
  }

  function renderLoading(){
    if(elList) {
      // Скелетон: три серые линии, как в admin_devices
      const s = [];
      for(let i=0;i<6;i++){
        s.push('<div class="skel" style="margin-bottom:10px">'
          + '<div class="skel-line tall" style="width:70%"></div>'
          + '<div class="skel-line" style="width:92%"></div>'
          + '<div class="skel-line small" style="width:58%"></div>'
          + '</div>');
      }
      elList.innerHTML = s.join('');
    }
  }

  /**
   * Отрисовать список инцидентов.
   *
   * @param {Array<Object>} items список инцидентов (to_dict())
   */
  function renderList(items){
    if(!elList) return;
    if(!items || !items.length){
      elList.classList.add('muted');
      elList.innerHTML = 'Нет инцидентов.';
      return;
    }
    elList.classList.remove('muted');
    const out = [];
    items.forEach((it) => {
      const status = String(it.status || '').toLowerCase();
      const pri = it.priority != null ? parseInt(it.priority) : null;
      // формируем CSS классы для тегов
      const statusCls = 'tag-status-' + status.replace(/[^\w]/g, '_');
      const priCls = pri ? 'tag-priority-' + String(pri) : '';
      const addr = it.address || (it.lat != null && it.lon != null ? `${it.lat.toFixed(5)}, ${it.lon.toFixed(5)}` : '—');
      const desc = (it.description || '').trim();
      const descShort = desc.length > 120 ? desc.slice(0,118) + '…' : desc;
      const created = it.created_at ? new Date(it.created_at).toLocaleString() : '—';
      // ссылка на командный центр с фокусом на инцидент можно реализовать позже
      out.push('<div class="inc-card">'
        + '<div class="inc-header"><div class="inc-title">' + escapeHtml(addr) + '</div>'
        + '<div class="inc-tags">'
          + '<span class="tag ' + statusCls + '">' + escapeHtml(status) + '</span>'
          + (pri ? ('<span class="tag ' + priCls + '">P' + pri + '</span>') : '')
        + '</div></div>'
        + (desc ? ('<div class="inc-desc">' + escapeHtml(descShort) + '</div>') : '')
        + '<div class="inc-meta">' + escapeHtml(created) + '</div>'
        + '</div>');
    });
    elList.innerHTML = out.join('');
    // Назначаем data-id элементам карточек и делегируем обработку кликов
    const cards = elList.querySelectorAll('.inc-card');
    cards.forEach((card, idx) => {
      if(items[idx] && items[idx].id != null){
        card.dataset.id = items[idx].id;
      }
    });
    // Делегируем клики на карточках для перехода на страницу инцидента
    elList.addEventListener('click', (ev) => {
      const target = ev.target.closest('.inc-card');
      if(target && target.dataset && target.dataset.id){
        window.location.href = '/admin/incidents/' + encodeURIComponent(String(target.dataset.id));
      }
    });
  }

  /**
   * Загрузить список инцидентов с учётом фильтров.
   */
  async function loadIncidents(){
    renderLoading();
    const qs = buildQuery();
    let url = '/api/incidents';
    if(qs) url += '?' + qs;
    try{
      const res = await fetch(url, { credentials:'same-origin' });
      const txt = await res.text();
      let data = null;
      try { data = txt ? JSON.parse(txt) : null; } catch(e){ data = { _raw: txt }; }
      if(!res.ok) throw { status: res.status, data };
      // API returns array
      renderList(Array.isArray(data) ? data : []);
    }catch(e){
      elList.classList.add('muted');
      elList.innerHTML = 'Ошибка загрузки.';
      if(e && e.status === 403){
        showToast('Нет доступа', 'error');
      }
    }
  }

  function onSearchClick(){
    loadIncidents();
  }
  function onEnterPress(e){ if(e.key === 'Enter'){ e.preventDefault(); loadIncidents(); } }
  function onFilterChange(){ loadIncidents(); }

  function onPriorityChange(){ loadIncidents(); }

  function onDateChange(){ loadIncidents(); }
  function onRefresh(){ loadStats(); loadIncidents(); loadAlerts(); }

  // Навешиваем обработчики
  if(btnSearch) btnSearch.addEventListener('click', onSearchClick);
  if(elQ) elQ.addEventListener('keypress', onEnterPress);
  if(elTag) elTag.addEventListener('keypress', onEnterPress);
  [chkNew, chkAssigned, chkEnroute, chkOnScene, chkResolved, chkClosed].forEach(ch => {
    if(ch) ch.addEventListener('change', onFilterChange);
  });

  // Обработчики для приоритетов и дат
  [chkP1, chkP2, chkP3, chkP4, chkP5].forEach(ch => {
    if(ch) ch.addEventListener('change', onPriorityChange);
  });
  if(elFromDate) elFromDate.addEventListener('change', onDateChange);
  if(elToDate) elToDate.addEventListener('change', onDateChange);
  if(elRefresh) elRefresh.addEventListener('click', onRefresh);

  // начальная загрузка
  loadStats();
  loadIncidents();
  loadAlerts();
})();