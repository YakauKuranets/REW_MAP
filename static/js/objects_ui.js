/* objects_ui.js

Этап 2: «Метки/Объекты» как ядро сценария.

Функции:
  - Кнопка «+ Объект» открывает модалку создания
  - Модалка поддерживает координаты, описание, теги и список камер
  - Сохранение в /api/objects (POST/PUT)
  - Быстрое создание инцидента из объекта (/api/incidents)

Глобальный API:
  window.ObjectsUI.openCreate()
  window.ObjectsUI.openEdit(id)
  window.ObjectsUI.createIncidentFromObject(id)
*/

(function(){
  'use strict';

  function $(id){ return document.getElementById(id); }

  function resolveMap(){
    return window.map || window.dutyMap || null;
  }

  function toast(msg){
    try{
      if(typeof window.showToast === 'function') return window.showToast(msg);
    }catch(_){ }
    try{ console.log('[toast]', msg); }catch(_){ }
  }

  function num(v){
    const n = Number(v);
    return isFinite(n) ? n : null;
  }

  function setVisible(el, show){
    if(!el) return;
    el.style.display = show ? '' : 'none';
  }

  // --- Modal state ---
  let _draftMarker = null;
  let _editingId = null;
  let _coordsTouched = false;
  let _modalOpen = false;

  function clearDraftMarker(){
    try{
      const map = resolveMap();
      if(_draftMarker && map){ map.removeLayer(_draftMarker); }
    }catch(_){ }
    _draftMarker = null;
  }

  function addCameraRow(cam){
    const root = $('obj-cameras');
    if(!root) return;

    const row = document.createElement('div');
    row.className = 'obj-cam-row';
    row.style.display = 'grid';
    row.style.gridTemplateColumns = '1fr 2fr 120px auto';
    row.style.gap = '6px';
    row.style.alignItems = 'center';

    const inpLabel = document.createElement('input');
    inpLabel.className = 'input cam-label';
    inpLabel.placeholder = 'Label';
    inpLabel.value = (cam && cam.label) ? String(cam.label) : '';

    const inpUrl = document.createElement('input');
    inpUrl.className = 'input cam-url';
    inpUrl.placeholder = 'URL';
    inpUrl.value = (cam && cam.url) ? String(cam.url) : '';

    const selType = document.createElement('select');
    selType.className = 'input cam-type';
    const types = ['web','hls','rtsp','other'];
    for(const t of types){
      const o = document.createElement('option');
      o.value = t;
      o.textContent = t;
      selType.appendChild(o);
    }
    const ctype = (cam && cam.type) ? String(cam.type).toLowerCase() : 'web';
    selType.value = types.includes(ctype) ? ctype : 'other';

    const btnDel = document.createElement('button');
    btnDel.className = 'btn minimal';
    btnDel.type = 'button';
    btnDel.title = 'Удалить камеру';
    btnDel.textContent = '✕';
    btnDel.addEventListener('click', (ev) => {
      ev.preventDefault();
      try{ row.remove(); }catch(_){ }
    });

    row.appendChild(inpLabel);
    row.appendChild(inpUrl);
    row.appendChild(selType);
    row.appendChild(btnDel);

    root.appendChild(row);
  }

  function readCameras(){
    const root = $('obj-cameras');
    if(!root) return [];
    const rows = Array.from(root.querySelectorAll('.obj-cam-row'));
    const out = [];
    for(const row of rows){
      const label = (row.querySelector('.cam-label')?.value || '').trim();
      const url = (row.querySelector('.cam-url')?.value || '').trim();
      const type = (row.querySelector('.cam-type')?.value || '').trim();
      if(!url) continue;
      out.push({ label: label || null, url, type: type || null });
    }
    return out;
  }

  function clearCameras(){
    const root = $('obj-cameras');
    if(!root) return;
    root.innerHTML = '';
  }



  async function geocodeOnce(q){
    const qq = String(q || '').trim();
    if(!qq) return null;

    // Поддержка ввода "lat, lon" напрямую
    const mm = qq.match(/^\s*([+-]?\d+(?:[\.,]\d+)?)\s*,\s*([+-]?\d+(?:[\.,]\d+)?)\s*$/);
    if(mm){
      const lat = Number(mm[1].replace(',', '.'));
      const lon = Number(mm[2].replace(',', '.'));
      if(isFinite(lat) && isFinite(lon)) return { lat, lon, label: qq };
    }

    const lang = (navigator.language || 'ru').split('-')[0];
    const url = `/api/geocode?q=${encodeURIComponent(qq)}&limit=1&lang=${encodeURIComponent(lang)}`;
    const res = await fetch(url, { credentials: 'same-origin' });
    const data = await res.json().catch(() => ({}));
    if(!res.ok) throw new Error(data?.detail || ('geocode_' + res.status));

    let item = null;
    if(Array.isArray(data) && data.length) item = data[0];
    else if(Array.isArray(data?.items) && data.items.length) item = data.items[0];
    else if(data && (data.lat != null) && (data.lon != null)) item = data;

    if(!item) return null;
    return item;
  }

  async function onObjGeocode(){{
    const nameEl = $('obj-name');
    const q = nameEl ? String(nameEl.value || '').trim() : '';
    if(!q){ toast('Введите адрес/название'); return; }
    try{
      toast('Поиск адреса…');
      const r = await geocodeOnce(q);
      if(!r){ toast('Адрес не найден'); return; }
      const lat = Number(r.lat);
      const lon = Number(r.lon);
      if(!isFinite(lat) || !isFinite(lon)) { toast('Геокодер вернул некорректные координаты'); return; }
      const latEl = $('obj-lat');
      const lonEl = $('obj-lon');
      if(latEl) latEl.value = lat.toFixed(6);
      if(lonEl) lonEl.value = lon.toFixed(6);
      syncMarkerFromInputs();
      // Подровняем карту, но не дергаем сильно
      const map = resolveMap();
      if(map){ try{ map.setView([lat, lon], Math.max(map.getZoom(), 15)); }catch(_){ } }
      toast('Координаты обновлены');
    }catch(e){
      toast('Ошибка геокодинга');
      try{ console.warn(e); }catch(_){ }
    }
  }
  function syncMarkerFromInputs(){
    const map = resolveMap();
    if(!map || !_draftMarker) return;
    const lat = num($('obj-lat')?.value);
    const lon = num($('obj-lon')?.value);
    if(lat === null || lon === null) return;
    try{ _draftMarker.setLatLng([lat, lon]); }catch(_){ }
  }

  function syncInputsFromMarker(){
    _coordsTouched = true;
    if(!_draftMarker) return;
    const ll = _draftMarker.getLatLng();
    const latEl = $('obj-lat');
    const lonEl = $('obj-lon');
    if(latEl) latEl.value = Number(ll.lat).toFixed(6);
    if(lonEl) lonEl.value = Number(ll.lng).toFixed(6);
  }

  function openModal(modeTitle){
    const bd = $('object-backdrop');
    if(!bd) return;
    bd.classList.add('open');
    const ttl = $('object-modal-title');
    if(ttl) ttl.textContent = modeTitle || 'Объект';
    _modalOpen = true;
  }

  function closeModal(){
    const bd = $('object-backdrop');
    if(bd) bd.classList.remove('open');
    _modalOpen = false;
    _editingId = null;
    clearDraftMarker();
  }

  async function saveObject(){
    const name = ($('obj-name')?.value || '').trim();
    const description = ($('obj-desc')?.value || '').trim();
    const tags = ($('obj-tags')?.value || '').trim();
    const lat = num($('obj-lat')?.value);
    const lon = num($('obj-lon')?.value);
    const cameras = readCameras();

    if(!name){
      toast('Укажи адрес/название объекта');
      return;
    }

    const payload = { name, description, tags, lat, lon, cameras };
    const isEdit = _editingId !== null && _editingId !== undefined;
    const url = isEdit ? `/api/objects/${encodeURIComponent(_editingId)}` : '/api/objects';
    const method = isEdit ? 'PUT' : 'POST';

    let resp = null;
    try{
      resp = await fetch(url, {
        method,
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify(payload),
      });
    }catch(e){
      toast('Сеть умерла в процессе сохранения');
      return;
    }
    if(!resp || !resp.ok){
      toast('Не удалось сохранить объект (проверь права/сессию)');
      return;
    }
    let js = null;
    try{ js = await resp.json(); }catch(_){ js = null; }
    const id = js && js.id ? js.id : _editingId;

    // Обновим слой на карте (если включён)
    try{
      if(window.ObjectsOverlay && typeof window.ObjectsOverlay.refresh === 'function'){
        window.ObjectsOverlay.refresh();
      }
    }catch(_){ }

    // Сигнал для панелей/списков
    try{ window.dispatchEvent(new CustomEvent('objects:changed', { detail: { id } })); }catch(_){ }

    toast(isEdit ? 'Объект обновлён' : 'Объект создан');
    closeModal();

    // Плавно покажем на карте
    try{
      const map = resolveMap();
      if(map && lat !== null && lon !== null){ map.setView([lat, lon], Math.max(map.getZoom(), 16)); }
    }catch(_){ }

    return id;
  }

  async function deleteObject(){
    if(!_editingId) return;
    if(!confirm('Удалить объект?')) return;
    let resp = null;
    try{
      resp = await fetch(`/api/objects/${encodeURIComponent(_editingId)}`, {
        method: 'DELETE',
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json' }
      });
    }catch(_){
      toast('Удаление не удалось (сеть/сервер)');
      return;
    }
    if(!resp.ok){
      toast('Удаление не удалось (права?)');
      return;
    }
    try{ if(window.ObjectsOverlay && typeof window.ObjectsOverlay.refresh === 'function') window.ObjectsOverlay.refresh(); }catch(_){ }
    try{ window.dispatchEvent(new CustomEvent('objects:changed', { detail: { id: _editingId, deleted: true } })); }catch(_){ }
    toast('Объект удалён');
    closeModal();
  }

  function ensureDraftMarker(lat, lon){
    const map = resolveMap();
    if(!map) return;
    clearDraftMarker();
    try{
      _draftMarker = L.marker([lat, lon], { draggable: true, opacity: 0.85 });
      _draftMarker.addTo(map);
      _draftMarker.on('dragend', () => syncInputsFromMarker());
    }catch(_){ }
  }

  async function openCreate(){
    const map = resolveMap();
    if(!map){ toast('Карта ещё не готова'); return; }
    _editingId = null;

    const c = map.getCenter();
    const lat = Number(c.lat);
    const lon = Number(c.lng);

    // заполнение
    if($('obj-name')) $('obj-name').value = '';
    if($('obj-desc')) $('obj-desc').value = '';
    if($('obj-tags')) $('obj-tags').value = '';
    if($('obj-lat')) $('obj-lat').value = lat.toFixed(6);
    if($('obj-lon')) $('obj-lon').value = lon.toFixed(6);
    clearCameras();
    addCameraRow({ type: 'web' });

    ensureDraftMarker(lat, lon);
    openModal('Новый объект');

    setVisible($('obj-delete'), false);
  }


  async function openCreateAt(lat, lon){
    const map = resolveMap();
    if(!map){ toast('Карта ещё не готова'); return; }

    _editingId = null;
    _coordsTouched = false;

    const clat = Number(lat);
    const clon = Number(lon);
    const ll = (isFinite(clat) && isFinite(clon)) ? [clat, clon] : [map.getCenter().lat, map.getCenter().lng];

    // пустая форма
    elName().value = '';
    elLat().value = Number(ll[0]).toFixed(6);
    elLon().value = Number(ll[1]).toFixed(6);
    elDesc().value = '';
    setCameras([]);

    syncMarkerFromInputs();
    showModal(true);
  }

  async function openEdit(id){
    const map = resolveMap();
    if(!map){ toast('Карта ещё не готова'); return; }

    let obj = null;
    try{
      const resp = await fetch(`/api/objects/${encodeURIComponent(id)}`, {
        method: 'GET',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: { 'Accept': 'application/json' },
      });
      if(resp.ok) obj = await resp.json();
    }catch(_){ obj = null; }
    if(!obj){ toast('Не удалось загрузить объект'); return; }

    _editingId = obj.id;

    if($('obj-name')) $('obj-name').value = obj.name || '';
    if($('obj-desc')) $('obj-desc').value = obj.description || '';
    if($('obj-tags')) $('obj-tags').value = obj.tags || '';
    if($('obj-lat')) $('obj-lat').value = (obj.lat !== null && obj.lat !== undefined) ? Number(obj.lat).toFixed(6) : '';
    if($('obj-lon')) $('obj-lon').value = (obj.lon !== null && obj.lon !== undefined) ? Number(obj.lon).toFixed(6) : '';

    clearCameras();
    if(Array.isArray(obj.cameras) && obj.cameras.length){
      for(const c of obj.cameras) addCameraRow(c);
    }else{
      addCameraRow({ type: 'web' });
    }

    const lat = num($('obj-lat')?.value) ?? map.getCenter().lat;
    const lon = num($('obj-lon')?.value) ?? map.getCenter().lng;
    ensureDraftMarker(lat, lon);
    openModal(`Объект #${obj.id}`);

    setVisible($('obj-delete'), true);
  }

  async function createIncidentFromObject(id, opts){
    opts = opts || {};
    const interactive = !!opts.interactive;

    let obj = null;
    try{
      const resp = await fetch(`/api/objects/${encodeURIComponent(id)}`, {
        method: 'GET',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: { 'Accept': 'application/json' },
      });
      if(resp.ok) obj = await resp.json();
    }catch(_){ obj = null; }
    if(!obj){ toast('Не удалось загрузить объект'); return; }

    // Быстрый режим (по умолчанию): берём описание из объекта, приоритет = 3
    let description = String((obj.description || obj.name || '')).trim();
    let priority = 3;

    // Интерактивный режим: Shift‑клик (или вызов с opts.interactive=true)
    if(interactive){
      const desc = prompt('Описание инцидента (можно коротко):', description || obj.name || '');
      if(desc === null) return;
      description = String(desc || '').trim() || description || String(obj.name || '').trim();
      const pr = prompt('Приоритет 1-4 (1=критично, 4=низкий):', String(priority));
      priority = Math.min(4, Math.max(1, parseInt(pr || String(priority), 10) || priority));
    }

    if(!description) description = String(obj.name || `Объект #${obj.id}`);

    const payload = {
      object_id: obj.id,
      lat: obj.lat,
      lon: obj.lon,
      address: obj.name,
      description,
      priority,
      status: 'new'
    };

    let resp2 = null;
    let inc = null;
    try{
      resp2 = await fetch('/api/incidents', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify(payload)
      });
      if(resp2.ok) inc = await resp2.json();
    }catch(_){ inc = null; }

    if(!inc || !inc.id){
      toast('Инцидент не создался (права/сессия?)');
      return;
    }

    toast(`Инцидент создан #${inc.id}`);

    // Обновим слой/панели
    try{ if(window.IncidentsOverlay && typeof window.IncidentsOverlay.refresh === 'function') window.IncidentsOverlay.refresh(); }catch(_){ }
    try{ window.dispatchEvent(new CustomEvent('incidents:changed', { detail: { id: inc.id, object_id: obj.id } })); }catch(_){ }

    // Попытаемся открыть в drawer (Command Center), иначе — новая вкладка
    const preferDrawer = !opts.openInNewTab;
    if(preferDrawer && window.CC && typeof window.CC.openIncidentCard === 'function'){
      // включим слой инцидентов, если кнопка доступна
      try{
        const btn = document.getElementById('btn-incidents-layer');
        const pressed = btn && (btn.getAttribute('aria-pressed') || '').toLowerCase() === 'true';
        if(btn && !pressed) btn.click();
      }catch(_){ }
      try{
        await window.CC.openIncidentCard(String(inc.id), { tab: 'overview', fit: false });
      }catch(_){ }
      try{
        if(window.IncidentsOverlay && typeof window.IncidentsOverlay.focus === 'function'){
          window.IncidentsOverlay.focus(String(inc.id), { openPopup: false, zoom: 17 });
        }
      }catch(_){ }
      return inc;
    }

    try{ window.open(`/admin/incidents/${encodeURIComponent(inc.id)}`, '_blank'); }catch(_){ }
    return inc;
  }


  function bind(){
    const btnAdd = $('btn-object-add');
    if(btnAdd && btnAdd.getAttribute('data-mode') !== 'incident'){
      btnAdd.addEventListener('click', (ev) => {
        ev.preventDefault();
        openCreate();
      });
    }

    const close = $('object-modal-close');
    if(close) close.addEventListener('click', (ev) => { ev.preventDefault(); closeModal(); });
    const bd = $('object-backdrop');
    if(bd){
      bd.addEventListener('click', (ev) => {
        if(ev.target === bd) closeModal();
      });
    }

    const btnGeo = $('obj-geocode');
    if(btnGeo) btnGeo.addEventListener('click', (ev) => { ev.preventDefault(); onObjGeocode(); });

    const btnSave = $('obj-save');
    if(btnSave) btnSave.addEventListener('click', (ev) => { ev.preventDefault(); saveObject(); });

    const btnDel = $('obj-delete');
    if(btnDel) btnDel.addEventListener('click', (ev) => { ev.preventDefault(); deleteObject(); });

    const addCam = $('obj-add-cam');
    if(addCam) addCam.addEventListener('click', (ev) => { ev.preventDefault(); addCameraRow({ type: 'web' }); });

    const latEl = $('obj-lat');
    const lonEl = $('obj-lon');
    if(latEl) latEl.addEventListener('change', syncMarkerFromInputs);
    if(lonEl) lonEl.addEventListener('change', syncMarkerFromInputs);
  }

  function init(){
    // Экспортируем API
    window.ObjectsUI = {
      openCreate,
      openCreateAt,
      openEdit,
      createIncidentFromObject,
    };
    bind();
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init);
  }else{
    init();
  }
})();
