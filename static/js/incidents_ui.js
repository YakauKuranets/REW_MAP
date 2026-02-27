/* incidents_ui.js

Минимальный, надёжный CRUD инцидентов прямо на карте:
  - создание из ПКМ или кнопки «Инцидент» (выбор точки кликом по карте)
  - поля: Адрес + Описание (без камеры)
  - Найти: геокод /api/geocode -> обновляет координаты и маркер
  - редактирование: клик по маркеру инцидента (IncidentsOverlay) открывает это же окно
  - удаление: кнопка «Удалить» в режиме редактирования

Экспорт:
  window.IncidentsUI = { startCreate, openModalAt, openEdit, closeModal }
*/

(function(){
  'use strict';

  const API_CREATE = '/api/incidents';
  const API_DETAIL = (id) => `/api/incidents/${encodeURIComponent(id)}`;
  const API_UPDATE = (id) => `/api/incidents/${encodeURIComponent(id)}`;
  const API_DELETE = (id) => `/api/incidents/${encodeURIComponent(id)}`;
  const API_GEOCODE = '/api/geocode';

  // ---------------- utils ----------------
  const $ = (id) => document.getElementById(id);

  function toast(msg, kind){
    try{
      if(window.showToast) return window.showToast(msg, kind);
      if(window.toast) return window.toast(msg, kind);
    }catch(_){ }
    try{ console.log('[toast]', msg); }catch(_){ }
    alert(msg);
  }

  function resolveMap(){
    return window.map || window.dutyMap || null;
  }


function enableIncidentsLayer(){
  try{ localStorage.setItem('incidents_layer_enabled', '1'); }catch(_){ }
  try{
    const btn = document.getElementById('btn-incidents-layer');
    if(btn){
      btn.classList.add('primary','is-on');
      btn.setAttribute('aria-pressed','true');
      btn.title = 'Инциденты: слой включён';
    }
  }catch(_){ }
  try{
    window.dispatchEvent(new CustomEvent('incidents-layer:toggle', { detail: { enabled: true } }));
  }catch(_){ }
  try{
    if(window.IncidentsOverlay && typeof window.IncidentsOverlay.setEnabled === 'function'){
      window.IncidentsOverlay.setEnabled(true);
    }
  }catch(_){ }
}

  function esc(s){
    return String(s ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  }

  async function fetchJson(url, opts){
    const r = await fetch(url, Object.assign({ credentials:'include', cache:'no-store' }, opts || {}));
    const j = await r.json().catch(() => null);
    if(!r.ok){
      const msg = (j && (j.error || j.message)) ? (j.error || j.message) : `HTTP ${r.status}`;
      const e = new Error(msg);
      e.status = r.status;
      e.payload = j;
      throw e;
    }
    return j;
  }

  function dispatchChanged(){
    try{ window.dispatchEvent(new CustomEvent('incidents:changed')); }catch(_){ }
    try{ window.IncidentsOverlay && window.IncidentsOverlay.refresh && window.IncidentsOverlay.refresh(); }catch(_){ }
    try{ window.CC && window.CC.refreshIncidents && window.CC.refreshIncidents(); }catch(_){ }
  }

  // ---------------- state ----------------
  let _placing = false;
  let _mode = 'create'; // create | edit
  let _editId = null;

  let _draftMarker = null;
  let _lat = null;
  let _lon = null;

  // ---------------- modal markup ----------------
  function ensureModalMarkup(){
    if(document.getElementById('incident-modal-backdrop')) return;

    const html = `
      <div id="incident-modal-backdrop" class="backdrop">
        <div id="incident-modal" class="modal" role="dialog" aria-modal="true" aria-labelledby="incident-modal-title">
          <div class="modal-head">
            <div id="incident-modal-title">Добавить инцидент</div>
            <button id="incident-modal-close" class="btn minimal" type="button" title="Закрыть">✕</button>
          </div>

          <div class="modal-body">
            <div class="form-row" style="display:flex; gap:8px; align-items:flex-end">
              <div style="flex:1">
                <label class="lbl">Адрес</label>
                <input id="incident-address" class="input" placeholder="Адрес" autocomplete="off">
              </div>
              <button id="incident-geocode" class="btn" type="button" title="Найти по адресу"><i class="fa-solid fa-magnifying-glass"></i> Найти</button>
            </div>

            <div class="form-row" style="margin-top:10px">
              <label class="lbl">Описание</label>
              <textarea id="incident-description" class="input" rows="3" placeholder="Что произошло?"></textarea>
            </div>

            <input id="incident-lat" type="hidden">
            <input id="incident-lon" type="hidden">

            <div class="muted" style="font-size:12px; margin-top:8px">
              Подсказка: метку инцидента можно перетаскивать мышью.
            </div>
          </div>

          <div class="modal-foot" style="display:flex; gap:8px; justify-content:space-between">
            <div style="display:flex; gap:8px">
              <button id="incident-delete" class="btn" type="button" style="display:none"><i class="fa-solid fa-trash"></i> Удалить</button>
            </div>
            <div style="display:flex; gap:8px">
              <button id="incident-cancel" class="btn" type="button">Отмена</button>
              <button id="incident-save" class="btn primary" type="button">Создать</button>
            </div>
          </div>
        </div>
      </div>
    `;

    const wrap = document.createElement('div');
    wrap.innerHTML = html;
    document.body.appendChild(wrap.firstElementChild);
  }

  const elBackdrop = () => $('incident-modal-backdrop');
  const elTitle = () => $('incident-modal-title');
  const elClose = () => $('incident-modal-close');
  const elCancel = () => $('incident-cancel');
  const elSave = () => $('incident-save');
  const elDelete = () => $('incident-delete');
  const elAddr = () => $('incident-address');
  const elDesc = () => $('incident-description');
  const elGeo = () => $('incident-geocode');
  const elLat = () => $('incident-lat');
  const elLon = () => $('incident-lon');

  function openBackdrop(){
    const b = elBackdrop();
    if(!b) return;
    b.classList.add('open');
  }

  function closeBackdrop(){
    const b = elBackdrop();
    if(!b) return;
    b.classList.remove('open');
  }

  function setMode(mode, id){
    _mode = mode === 'edit' ? 'edit' : 'create';
    _editId = (_mode === 'edit') ? String(id || '').trim() : null;

    const t = elTitle();
    const s = elSave();
    const d = elDelete();

    if(_mode === 'edit'){
      if(t) t.textContent = _editId ? `Инцидент #${_editId}` : 'Инцидент';
      if(s) s.textContent = 'Сохранить';
      if(d) d.style.display = '';
    }else{
      if(t) t.textContent = 'Добавить инцидент';
      if(s) s.textContent = 'Создать';
      if(d) d.style.display = 'none';
    }
  }

  // ---------------- draft marker ----------------
  function clearDraftMarker(){
    try{
      if(_draftMarker){
        const map = resolveMap();
        if(map) map.removeLayer(_draftMarker);
      }
    }catch(_){ }
    _draftMarker = null;
  }

  function setCoords(lat, lon, opts){
    _lat = Number(lat);
    _lon = Number(lon);
    if(!isFinite(_lat) || !isFinite(_lon)) return;

    if(elLat()) elLat().value = String(_lat);
    if(elLon()) elLon().value = String(_lon);

    const map = resolveMap();
    if(!map) return;

    // create/refresh draggable draft marker
    if(!_draftMarker){
      _draftMarker = L.marker([_lat, _lon], { draggable:true, autoPan:true });
      _draftMarker.on('dragend', () => {
        try{
          const ll = _draftMarker.getLatLng();
          setCoords(ll.lat, ll.lng, { keepMarker:true });
        }catch(_){ }
      });
      _draftMarker.addTo(map);
    }else{
      try{ _draftMarker.setLatLng([_lat, _lon]); }catch(_){ }
    }

    if(!(opts && opts.noFit)){
      try{ map.panTo([_lat, _lon], { animate:true }); }catch(_){ }
    }
  }

  // ---------------- open/create/edit ----------------
  function openModalAt(lat, lon){
    ensureModalMarkup();
    enableIncidentsLayer();
    setMode('create');

    // reset fields
    if(elAddr()) elAddr().value = '';
    if(elDesc()) elDesc().value = '';

    openBackdrop();
    clearDraftMarker();
    setCoords(lat, lon);

    // focus
    try{ setTimeout(() => elAddr() && elAddr().focus(), 60); }catch(_){ }
  }

  async function openEdit(id){
    enableIncidentsLayer();
    const incidentId = String(id || '').trim();
    if(!incidentId){ toast('Не указан id инцидента', 'warn'); return; }

    ensureModalMarkup();
    setMode('edit', incidentId);

    openBackdrop();
    clearDraftMarker();

    let data = null;
    try{
      data = await fetchJson(API_DETAIL(incidentId));
    }catch(e){
      toast('Не удалось загрузить инцидент: ' + (e.message || e), 'warn');
      closeModal();
      return;
    }

    if(elAddr()) elAddr().value = (data.address || '');
    if(elDesc()) elDesc().value = (data.description || '');

    setCoords(data.lat, data.lon);
    try{ setTimeout(() => elDesc() && elDesc().focus(), 80); }catch(_){ }
  }

  function closeModal(){
    closeBackdrop();
    clearDraftMarker();
    setMode('create');
  }

  // ---------------- actions ----------------
  async function onGeocode(){
    const addr = (elAddr()?.value || '').trim();
    if(!addr){ toast('Введите адрес', 'warn'); return; }

    try{
      // /api/geocode в бэкенде — GET с параметром q (см. app/geocode/routes.py).
      // Раньше тут был POST {address}, из-за чего кнопка «Найти» молча ломалась.
      // Поддерживаем и ввод координат "lat, lon".

      const mm = addr.match(/^\s*([+-]?\d+(?:[\.,]\d+)?)\s*,\s*([+-]?\d+(?:[\.,]\d+)?)\s*$/);
      if(mm){
        const lat = Number(mm[1].replace(',', '.'));
        const lon = Number(mm[2].replace(',', '.'));
        if(isFinite(lat) && isFinite(lon)){
          setCoords(lat, lon);
          const map = resolveMap();
          if(map){ try{ map.setView([lat, lon], Math.max(map.getZoom(), 15)); }catch(_){ } }
          toast('Координаты обновлены', 'ok');
          return;
        }
      }

      const lang = (navigator.language || 'ru').split('-')[0];
      const url = `${API_GEOCODE}?q=${encodeURIComponent(addr)}&limit=1&lang=${encodeURIComponent(lang)}`;
      const j = await fetchJson(url, { method:'GET' });

      let item = null;
      if(Array.isArray(j) && j.length) item = j[0];
      else if(Array.isArray(j?.items) && j.items.length) item = j.items[0];
      else if(j && (j.lat != null) && (j.lon != null)) item = j;

      const lat = Number(item && (item.lat ?? item.latitude));
      const lon = Number(item && (item.lon ?? item.lng ?? item.longitude));
      if(!isFinite(lat) || !isFinite(lon)){
        toast('Адрес не найден', 'warn');
        return;
      }
      setCoords(lat, lon);
      const map = resolveMap();
      if(map){ try{ map.setView([lat, lon], Math.max(map.getZoom(), 15)); }catch(_){ } }
      toast('Адрес найден', 'ok');
    }catch(e){
      toast('Ошибка геокодирования: ' + (e.message || e), 'warn');
    }
  }

  function buildPayload(){
    const address = (elAddr()?.value || '').trim();
    const description = (elDesc()?.value || '').trim();
    const lat = Number(elLat()?.value || _lat);
    const lon = Number(elLon()?.value || _lon);
    return {
      address: address || null,
      description: description || null,
      lat, lon,
    };
  }

  async function onSave(){
    const payload = buildPayload();
    if(!isFinite(payload.lat) || !isFinite(payload.lon)){
      toast('Не заданы координаты', 'warn');
      return;
    }

    // разрешаем пустой адрес, но описание желательно
    // (не блокируем жёстко, чтобы можно было быстро создавать)

    try{
      if(_mode === 'edit' && _editId){
        await fetchJson(API_UPDATE(_editId), {
          method:'PUT',
          headers:{ 'Content-Type':'application/json' },
          body: JSON.stringify(payload)
        });
        toast('Инцидент сохранён', 'ok');
      }else{
        const j = await fetchJson(API_CREATE, {
          method:'POST',
          headers:{ 'Content-Type':'application/json' },
          body: JSON.stringify(payload)
        });
        const id = (j && (j.id || j.incident_id)) ? String(j.id || j.incident_id) : null;
        toast('Инцидент создан', 'ok');
        if(id){
          try{ setMode('edit', id); }catch(_){ }
        }
      }

      dispatchChanged();
      closeModal();
    }catch(e){
      toast('Не удалось сохранить: ' + (e.message || e), 'warn');
    }
  }

  async function onDelete(){
    if(!_editId){ return; }
    const ok = confirm(`Удалить инцидент #${_editId}?`);
    if(!ok) return;
    try{
      await fetchJson(API_DELETE(_editId), { method:'DELETE' });
      toast('Инцидент удалён', 'ok');
      dispatchChanged();
      closeModal();
    }catch(e){
      toast('Не удалось удалить: ' + (e.message || e), 'warn');
    }
  }

  // ---------------- placing mode ----------------
  function setPlacing(on){
    _placing = !!on;
    try{
      document.body.classList.toggle('incidents-placing', _placing);
    }catch(_){ }
    if(_placing){
      toast('Кликните по карте, чтобы выбрать точку инцидента', 'ok');
    }
  }

  function startCreate(){
    enableIncidentsLayer();
    const map = resolveMap();
    if(!map){ toast('Карта не готова', 'warn'); return; }
    setPlacing(true);
  }

  function bindMapHandlers(){
    const map = resolveMap();
    if(!map) return;

    map.on('click', (e) => {
      try{
        if(!_placing) return;
        setPlacing(false);
        const ll = e && e.latlng;
        if(!ll) return;
        openModalAt(ll.lat, ll.lng);
      }catch(_){ }
    });
  }

  // ---------------- UI handlers ----------------
  function bindUiHandlers(){
    const btn = $('btn-object-add') || $('btn-incident-add');
    if(btn) btn.addEventListener('click', (e) => { e.preventDefault(); startCreate(); });

    if(elClose()) elClose().addEventListener('click', (e) => { e.preventDefault(); closeModal(); });
    if(elCancel()) elCancel().addEventListener('click', (e) => { e.preventDefault(); closeModal(); });
    if(elSave()) elSave().addEventListener('click', (e) => { e.preventDefault(); onSave(); });
    if(elDelete()) elDelete().addEventListener('click', (e) => { e.preventDefault(); onDelete(); });
    if(elGeo()) elGeo().addEventListener('click', (e) => { e.preventDefault(); onGeocode(); });

    if(elAddr()) elAddr().addEventListener('keydown', (e) => {
      if(e.key === 'Enter'){ e.preventDefault(); onGeocode(); }
    });

    document.addEventListener('keydown', (e) => {
      if(e.key === 'Escape'){
        const b = elBackdrop();
        if(b && b.classList.contains('open')) closeModal();
      }
    });

    const b = elBackdrop();
    if(b){
      b.addEventListener('click', (e) => {
        if(e.target === b) closeModal();
      });
    }
  }

  function init(){
    ensureModalMarkup();
    bindUiHandlers();

    // wait for map
    let tries = 0;
    const tick = () => {
      tries += 1;
      const map = resolveMap();
      if(map){ bindMapHandlers(); return; }
      if(tries < 50) setTimeout(tick, 120);
    };
    tick();

    window.IncidentsUI = {
      startCreate,
      openModalAt,
      openEdit,
      closeModal,
    };
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init);
  }else{
    init();
  }
})();
