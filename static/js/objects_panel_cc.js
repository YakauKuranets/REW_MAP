/* objects_panel_cc.js

Command Center: левая панель «Объекты».

Цели (минимальный, но рабочий прод‑уровень для этапа 2):
  - список объектов (lite) с фильтрами q/tag
  - пустое состояние: «Нет объектов, нажмите +»
  - клик по объекту: фокус на карте + попап
  - быстрые действия: Редактировать / Инцидент

Требует:
  - /api/objects?lite=1&limit=...&q=...&tag=...
  - window.ObjectsOverlay.focus (добавлено в objects_overlay.js)
  - window.ObjectsUI.openCreate/openEdit/createIncidentFromObject
*/

(function(){
  'use strict';

  const API_LIST = '/api/objects';

  function $(id){ return document.getElementById(id); }

  function escapeHtml(s){
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[c]));
  }

  function debounce(fn, ms){
    let t = null;
    return function(){
      const args = arguments;
      if(t) clearTimeout(t);
      t = setTimeout(() => { t = null; fn.apply(null, args); }, ms);
    };
  }

  async function fetchJson(url){
    const res = await fetch(url, {
      method: 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { 'Accept': 'application/json' }
    });
    if(!res.ok) throw new Error('HTTP ' + res.status);
    return await res.json();
  }

  function showToast(msg){
    try{ if(typeof window.showToast === 'function') return window.showToast(msg); }catch(_){ }
    try{ console.log('[objects_panel]', msg); }catch(_){ }
  }

  function ensureObjectsLayerEnabled(){
    // Чтобы кнопка и localStorage были консистентны: используем click().
    const btn = document.getElementById('btn-objects-layer');
    if(!btn) return;
    const pressed = (btn.getAttribute('aria-pressed') || '').toLowerCase() === 'true';
    if(!pressed){
      try{ btn.click(); }catch(_){ }
    }
  }

  async function focusObject(id){
    const oid = String(id ?? '').trim();
    if(!oid) return;

    ensureObjectsLayerEnabled();

    // лучший путь: через overlay, чтобы сразу открыть попап
    if(window.ObjectsOverlay && typeof window.ObjectsOverlay.focus === 'function'){
      try{ await window.ObjectsOverlay.focus(oid, { openPopup: true }); return; }catch(_){ }
    }

    // fallback: просто открыть страницу админки
    try{ window.open('/admin/objects?highlight=' + encodeURIComponent(oid), '_blank'); }catch(_){ }
  }

  function renderEmpty(listEl){
    if(!listEl) return;
    listEl.innerHTML = `
      <div class="ap-empty" style="padding:10px">
        <b>Нет объектов</b>
        <div class="muted" style="margin-top:6px">Нажмите <b>+</b>, чтобы добавить объект.</div>
        <div style="margin-top:10px">
          <button id="ap-objects-empty-add" class="btn primary" type="button"><i class="fa-solid fa-plus"></i> Добавить объект</button>
        </div>
      </div>
    `;
    const b = $('ap-objects-empty-add');
    if(b){
      b.addEventListener('click', (ev) => {
        ev.preventDefault();
        if(window.ObjectsUI && typeof window.ObjectsUI.openCreate === 'function') window.ObjectsUI.openCreate();
      });
    }
  }

  function renderError(listEl, msg){
    if(!listEl) return;
    listEl.innerHTML = `
      <div class="ap-empty" style="padding:10px">
        <b>Не удалось загрузить объекты</b>
        <div class="muted" style="margin-top:6px">${escapeHtml(msg || 'Ошибка сети/сервера')}</div>
      </div>
    `;
  }

  function renderList(listEl, items){
    if(!listEl) return;

    const rows = [];
    for(const it of items){
      if(!it || it.id == null) continue;
      const id = String(it.id);
      const name = escapeHtml(it.name || ('Объект #' + id));
      const tags = escapeHtml(it.tags || '');
      const cams = (it.camera_count != null) ? Number(it.camera_count) : null;
      const camsText = (cams != null && isFinite(cams)) ? `${cams} кам.` : '';
      const meta = [tags, camsText].filter(Boolean).join(' · ');

      rows.push(`
        <div class="ap-item" data-oid="${escapeHtml(id)}" style="cursor:pointer">
          <div class="ap-item__row">
            <div style="min-width:0">
              <div class="ap-item__title" style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis">${name}</div>
              <div class="ap-item__meta">${meta || '<span class="muted">без тегов</span>'}</div>
            </div>
          </div>
          <div class="ap-item__actions">
            <button class="btn" type="button" data-act="focus" data-id="${escapeHtml(id)}">Показать</button>
            <button class="btn" type="button" data-act="edit" data-id="${escapeHtml(id)}">Редактировать</button>
            <button class="btn primary" type="button" data-act="incident" data-id="${escapeHtml(id)}">Инцидент</button>
          </div>
        </div>
      `);
    }

    listEl.innerHTML = rows.join('') || '';

    // делегирование событий
    listEl.querySelectorAll('[data-act="focus"]').forEach((b) => {
      b.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        focusObject(b.getAttribute('data-id'));
      });
    });
    listEl.querySelectorAll('[data-act="edit"]').forEach((b) => {
      b.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        const id = b.getAttribute('data-id');
        if(window.ObjectsUI && typeof window.ObjectsUI.openEdit === 'function') window.ObjectsUI.openEdit(id);
      });
    });
    listEl.querySelectorAll('[data-act="incident"]').forEach((b) => {
      b.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        const id = b.getAttribute('data-id');
        if(window.ObjectsUI && typeof window.ObjectsUI.createIncidentFromObject === 'function') window.ObjectsUI.createIncidentFromObject(id, { interactive: !!(ev && ev.shiftKey) });
      });
    });

    listEl.querySelectorAll('.ap-item[data-oid]').forEach((row) => {
      row.addEventListener('click', (ev) => {
        ev.preventDefault();
        const id = row.getAttribute('data-oid');
        if(!id) return;
        const openNew = ev && (ev.ctrlKey || ev.metaKey || ev.shiftKey);
        if(openNew){
          window.open(`/admin/objects?highlight=${encodeURIComponent(id)}`, '_blank');
          return;
        }
        // сначала фокус на карте
        focusObject(id);
        // затем drawer (если доступен)
        if(window.CC && typeof window.CC.openObjectCard === 'function'){
          window.CC.openObjectCard(id, { tab:'overview', fit:false });
        }
      });
    });
  }

  function init(){
    const listEl = $('list-objects');
    const countEl = $('count-objects');
    const qEl = $('ap-objects-q');
    const tagEl = $('ap-objects-tag');
    const refreshBtn = $('ap-objects-refresh');
    const addBtn = $('ap-objects-add');

    if(!listEl) return;

    const load = async () => {
      listEl.innerHTML = '<div class="muted" style="padding:10px">Загрузка…</div>';
      const q = (qEl?.value || '').trim();
      const tag = (tagEl?.value || '').trim();
      const url = API_LIST
        + '?lite=1&limit=500'
        + (q ? '&q=' + encodeURIComponent(q) : '')
        + (tag ? '&tag=' + encodeURIComponent(tag) : '');

      let data = null;
      try{
        data = await fetchJson(url);
      }catch(e){
        renderError(listEl, e && e.message ? e.message : '');
        if(countEl) countEl.textContent = '0';
        return;
      }
      const items = Array.isArray(data) ? data : [];
      if(countEl) countEl.textContent = String(items.length);
      if(items.length === 0){
        renderEmpty(listEl);
      }else{
        renderList(listEl, items);
      }
    };

    const loadDebounced = debounce(load, 250);

    if(qEl) qEl.addEventListener('input', loadDebounced);
    if(tagEl) tagEl.addEventListener('input', loadDebounced);
    if(refreshBtn) refreshBtn.addEventListener('click', (ev) => { ev.preventDefault(); load(); });
    if(addBtn) addBtn.addEventListener('click', (ev) => {
      ev.preventDefault();
      if(window.ObjectsUI && typeof window.ObjectsUI.openCreate === 'function') window.ObjectsUI.openCreate();
      else showToast('UI объектов ещё не инициализировался');
    });

    // Авто‑обновление списка после сохранения/удаления объекта
    window.addEventListener('objects:changed', () => {
      try{ load(); }catch(_){ }
    });

    load();
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init);
  }else{
    init();
  }
})();
