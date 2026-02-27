/* incidents_panel_cc.js

Command Center: левая панель «Инциденты».

Минимальный функционал (этап 3.1):
  - список инцидентов (активные по умолчанию)
  - фильтр по статусу + поиск по строке
  - пустое состояние
  - действия: Показать (фокус + включить слой), Открыть карточку
*/

(() => {
  const elList = () => document.getElementById('list-incidents');
  const elCount = () => document.getElementById('count-incidents');
  const elQ = () => document.getElementById('ap-incidents-q');
  const elStatus = () => document.getElementById('ap-incidents-status');
  const elRefresh = () => document.getElementById('ap-incidents-refresh');

  const API = (params) => `/api/incidents${params ? `?${params}` : ''}`;

  // Держим последний список, чтобы обновлять unread без полной перезагрузки
  let lastItems = [];
  let _unreadRefreshTimer = null;


  function esc(s){
    return String(s ?? '').replace(/[&<>\"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[ch]));
  }

  function debounce(fn, ms){
    let t = null;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), ms);
    };
  }

  function ensureIncidentsLayer(){
    const btn = document.getElementById('btn-incidents-layer');
    if(!btn) return;
    const pressed = btn.getAttribute('aria-pressed') === 'true';
    if(!pressed) btn.click();
  }

  async function fetchJson(url){
    const resp = await fetch(url, { credentials: 'include' });
    if(!resp.ok){
      const txt = await resp.text().catch(() => '');
      throw new Error(`HTTP ${resp.status}: ${txt}`);
    }
    return await resp.json();
  }

  function statusLabel(s){
    const v = String(s || '').toLowerCase();
    if(v === 'new') return 'new';
    if(v === 'assigned') return 'assigned';
    if(v === 'enroute') return 'enroute';
    if(v === 'on_scene') return 'on_scene';
    if(v === 'resolved') return 'resolved';
    if(v === 'closed') return 'closed';
    return v || '—';
  }

  function buildParams(){
    const q = (elQ()?.value || '').trim();
    const st = (elStatus()?.value || 'active').trim();
    const p = new URLSearchParams();
    p.set('limit', '200');
    // Поиск (сервер поддерживает q)
    if(q) p.set('q', q);
    // Статусы
    if(st === 'active'){
      // активные = все, кроме closed
      // бэкенд фильтрует одним status, поэтому делаем client‑filter
      p.set('status', ''); // пусто, возьмём все и отфильтруем
    }else if(st === 'all'){
      p.set('status', '');
    }else{
      p.set('status', st);
    }
    return { params: p.toString(), statusMode: st };
  }

  function renderEmpty(){
    const list = elList();
    if(!list) return;
    list.innerHTML = `
      <div class="ap-empty-mini">
        <div class="ap-empty-mini__title">Нет инцидентов</div>
        <div class="ap-empty-mini__text muted">Попробуйте сменить фильтр статуса или создайте инцидент из метки.</div>
      </div>
    `;
  }

  function renderError(err){
    const list = elList();
    if(!list) return;
    list.innerHTML = `<div class="muted">Ошибка загрузки: ${esc(err?.message || err)}</div>`;
  }

  function renderList(items){
    lastItems = Array.isArray(items) ? items : [];
    const list = elList();
    if(!list) return;
    if(!items.length){
      renderEmpty();
      return;
    }
    list.innerHTML = items.map(i => {
      const id = i.id;
      const addr = (i.address || '').trim() || '—';
      const descr = (i.description || '').trim();
      const pr = i.priority ?? '';
      const st = statusLabel(i.status);
      const ts = (i.updated_at || i.created_at || '').replace('T',' ').slice(0,19);
      return `
        <div class="ap-item" data-incident-id="${esc(id)}">
          <div class="ap-item__main">
            <div class="ap-item__title">#${esc(id)} <span class="ap-badge red ap-unread-badge" data-incident-id="${esc(id)}" style="display:none"></span> &bull; ${esc(addr)}</div>
            <div class="ap-item__meta muted">${esc(st)}${pr ? ` • p${esc(pr)}` : ''}${ts ? ` • ${esc(ts)}` : ''}</div>
            ${descr ? `<div class="ap-item__meta muted">${esc(descr).slice(0,120)}</div>` : ''}
          </div>
          <div class="ap-item__actions">
            <button class="btn" type="button" data-act="show" title="Показать на карте"><i class="fa-solid fa-location-crosshairs"></i></button>
            <button class="btn" type="button" data-act="edit" title="Редактировать"><i class="fa-solid fa-pen"></i></button>
            <button class="btn" type="button" data-act="chat" title="Чат инцидента"><i class="fa-solid fa-comment-dots"></i></button>
            <a class="btn" data-act="open" href="/admin/incidents/${encodeURIComponent(id)}" title="Открыть карточку"><i class="fa-solid fa-arrow-up-right-from-square"></i></a>
          </div>
        </div>
      `;
    }).join('');

    list.querySelectorAll('[data-act="show"]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const row = btn.closest('[data-incident-id]');
        const id = row?.getAttribute('data-incident-id');
        if(!id) return;
        ensureIncidentsLayer();
        if(window.IncidentsOverlay && typeof window.IncidentsOverlay.focus === 'function'){
          window.IncidentsOverlay.focus(id, { openPopup: true, zoom: 17 });
        }
      });
    });

// Редактирование инцидента прямо на карте
list.querySelectorAll('[data-act="edit"]').forEach(btn => {
  btn.addEventListener('click', (e) => {
    e.preventDefault();
    const row = btn.closest('[data-incident-id]');
    const id = row?.getAttribute('data-incident-id');
    if(!id) return;
    ensureIncidentsLayer();
    try{
      if(window.IncidentsUI && typeof window.IncidentsUI.openEdit === 'function'){
        window.IncidentsUI.openEdit(id);
        return;
      }
    }catch(_){ }
    // fallback: карточка
    window.location.href = `/admin/incidents/${encodeURIComponent(id)}`;
  });
});


    list.querySelectorAll('[data-act="open"]').forEach(a => {
      a.addEventListener('click', (e) => {
        // если есть модификатор (ctrl/shift/meta) — пусть браузер откроет ссылку как обычно
        const openNew = e && (e.ctrlKey || e.metaKey || e.shiftKey);
        if(openNew) return;

        const row = a.closest('[data-incident-id]');
        const id = row?.getAttribute('data-incident-id');
        if(!id) return;

        if(window.CC && typeof window.CC.openIncidentCard === 'function'){
          e.preventDefault();
          ensureIncidentsLayer();
          window.CC.openIncidentCard(id, { tab:'overview', fit:false });
        }
      });
    });

    // Быстрый доступ: открыть чат инцидента прямо из списка
    list.querySelectorAll('[data-act="chat"]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const row = btn.closest('[data-incident-id]');
        const id = row?.getAttribute('data-incident-id');
        if(!id) return;

        try{
          if(typeof window.chat2OpenForIncident === 'function'){
            window.chat2OpenForIncident(id);
            return;
          }
          if(typeof window.chat2OpenChannel === 'function'){
            // fallback: ensure + open
            fetch('/api/chat2/ensure_incident_channel', {
              method: 'POST',
              headers: { 'Content-Type':'application/json' },
              body: JSON.stringify({ marker_id: id })
            }).then(r => r.json().then(j => ({ok:r.ok, j}))).then(({ok,j}) => {
              if(!ok) throw new Error(j && j.error ? j.error : 'ensure failed');
              const chId = (j && (j.channel_id || j.id)) ? (j.channel_id || j.id) : null;
              if(chId) window.chat2OpenChannel(chId, 'Инцидент #' + id);
            }).catch(_ => {});
            return;
          }
        }catch(_e){ /* ignore */ }
      });
    });
  }


  async function updateUnreadBadges(items){
    try{
      const ids = (items || []).map(x => x && x.id).filter(Boolean);
      if(!ids.length) return;

      const url = `/api/chat2/unread_for_incidents?ids=${encodeURIComponent(ids.join(','))}`;
      const r = await fetch(url);
      if(!r.ok) return;
      const data = await r.json();

      document.querySelectorAll('.ap-unread-badge[data-incident-id]').forEach(el => {
        const id = el.getAttribute('data-incident-id');
        const n = Number((data && (data[id] ?? data[String(id)])) || 0);
        if(n > 0){
          el.style.display = 'inline-flex';
          el.textContent = (n > 99) ? '99+' : String(n);
        }else{
          el.style.display = 'none';
          el.textContent = '';
        }
      });
    }catch(_){
      // ignore
    }
  }
  async function load(){
    const list = elList();
    const count = elCount();
    if(!list || !count) return;
    list.innerHTML = '<span class="muted">Загрузка…</span>';

    const { params, statusMode } = buildParams();
    let data = [];
    try{
      // если params содержит пустой status, уберём его
      const url = API(params);
      data = await fetchJson(url);
    }catch(err){
      count.textContent = '0';
      renderError(err);
      return;
    }

    let items = Array.isArray(data) ? data : [];
    if(statusMode === 'active'){
      items = items.filter(i => String(i.status || '').toLowerCase() !== 'closed');
    }

    count.textContent = String(items.length);
    renderList(items);
    updateUnreadBadges(items);
  }

  function scheduleUnreadRefresh(){
    try{
      if(_unreadRefreshTimer) return;
      _unreadRefreshTimer = setTimeout(() => {
        _unreadRefreshTimer = null;
        if(Array.isArray(lastItems) && lastItems.length) updateUnreadBadges(lastItems);
      }, 650);
    }catch(_e){}
  }

  function bindRealtimeUnread(){
    if(!window.Realtime || typeof window.Realtime.on !== 'function') return;
    try{ window.Realtime.connect(); }catch(_e){}
    try{
      window.Realtime.on('chat2_message', () => scheduleUnreadRefresh());
      window.Realtime.on('chat2_receipt', () => scheduleUnreadRefresh());
    }catch(_e){}
  }

  function init(){
    if(!elList()) return;
    const deb = debounce(load, 250);
    elQ()?.addEventListener('input', deb);
    elStatus()?.addEventListener('change', load);
    elRefresh()?.addEventListener('click', load);

    bindRealtimeUnread();

    // Мгновенное обновление при создании/изменении инцидента (без ожидания таймера)
    window.addEventListener('incidents:changed', () => {
      try{
        const pane = document.querySelector('.ap-sidebar-pane.active[data-spane="incidents"]');
        if(pane) load();
      }catch(_e){}
    });

    // авто‑обновление редко, чтобы не бесить сервер
    setInterval(() => {
      // обновляем только если вкладка «Инциденты» открыта
      const pane = document.querySelector('.ap-sidebar-pane.active[data-spane="incidents"]');
      if(pane) load();
    }, 15000);

    load();
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init);
  }else{
    init();
  }
})();
