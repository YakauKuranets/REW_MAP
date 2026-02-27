
/*
 * js/main.js — основной клиентский код для проекта Map v12
 *
 * Этот файл реализует работу с картой (Leaflet), рисование зон,
 * загрузку и отображение списка адресов, работу с модальными окнами,
 * а также управление темой.
 *
 * Обновлено: аккуратный вывод заявок в колокольчике (по строкам: Описание, Инициатор,
 * Категория, Доступ, Координаты, Ссылка).
 * + Микро-анимации и UX: ripple, bump у метки, контекст-меню по правому клику,
 *   быстрые чипы‑счётчики, инъекция стилей (шестерёнка крутится на hover).
 */

/* ========= Утилиты ========= */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
function escapeAttr(s) { return String(s || '').replace(/"/g, '&quot;'); }

function escapeHTML(str) {
  return String(str || '').replace(/[&<>\"']/g, s => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[s]));
}
function linkify(text) {
  const esc = escapeHTML(text || '');
  const urlRegex = /(https?:\/\/[^\s<]+)/g;
  return esc.replace(urlRegex, url => `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`);
}
function setProgress(el, pct){
  if(!el) return;
  pct = Math.max(0, Math.min(100, Math.round(Number(pct) || 0)));
  const pctStr = pct + '%';
  try {
    el.style.setProperty('--progress', pctStr);
  } catch (err) {
    try {
      const bar = el.querySelector && el.querySelector('span') ? el : null;
      if (bar && bar.style) bar.style.width = pctStr;
    } catch (_) {}
  }
  const t = el.querySelector('span');
  if(t) t.textContent = pct + '%';
}

// Формат размера
function formatSize(bytes) {
  const units = ['байт', 'КБ', 'МБ', 'ГБ', 'ТБ'];
  let n = Number(bytes);
  if (!n || n < 0) return '';
  let u = 0;
  while (n >= 1024 && u < units.length - 1) { n /= 1024; u++; }
  return (u === 0 ? n.toFixed(0) : n.toFixed(1)) + ' ' + units[u];
}

/* ========= Инъекция минимальных стилей UX ========= */
function injectStyleOnce(id, cssText) {
  if (document.getElementById(id)) return;
  const s = document.createElement('style');
  s.id = id;
  s.textContent = cssText;
  document.head.appendChild(s);
}

const zonePolygonMap = {};
const zoneMarkerMap = {};
let editingZoneLayer = null;
let routeLayer = null;

let CURRENT_ROLE = null;

/* ==== Notifications (incoming requests) ==== */
let CURRENT_REQUEST_ID = null;
let _notifOpen = false;


/* ========= Доп. утилиты ========= */
function haversineDistance(lat1, lon1, lat2, lon2) {
  const R = 6371;
  const toRad = deg => (deg * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

/**
 * Показать push‑уведомление через API Notification. Если разрешения нет,
 * попытка не предпринимается. В случае ошибки уведомление выводится
 * через всплывающее toast‑сообщение.
 * @param {string} title Заголовок уведомления
 * @param {string} body  Текст уведомления
 */
function pushNotify(title, body) {
  if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
    try {
      new Notification(title, { body });
    } catch (err) {
      // Если не получилось создать notification, используем toast
      showToast(`${title}: ${body}`, 'info');
    }
  }
}

/* ========= Тайлы / карта ========= */
function setTileSource(mode = 'online') {
  if (tileLayer) { try { tileLayer.remove(); } catch (_) {} }
  if (mode === 'local') {
    tileLayer = L.tileLayer('/tiles/{z}/{x}/{y}.png', { maxZoom: 19 });
  } else {
    tileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OSM' });
  }
  tileLayer.addTo(map);
}


/* ========= Тема ========= */

/* ========= Список / маркеры ========= */
let ITEMS = [];
let radiusFiltered = null;
async function fetchList() {
  const qEl = $('#search');
  const q = qEl ? qEl.value.trim() : '';
  let url = '/api/addresses?q=' + encodeURIComponent(q);

  const catEl = $('#filter-category');
  if (catEl) {
    const category = (catEl.value || '').trim();
    if (category) url += '&category=' + encodeURIComponent(category);
  }
  const localEl = $('#opt-local'), remoteEl = $('#opt-remote');
  const local = localEl ? localEl.checked : false;
  const remote = remoteEl ? remoteEl.checked : false;
  if (local && !remote) url += '&status=' + encodeURIComponent('Локальный доступ');
  else if (remote && !local) url += '&status=' + encodeURIComponent('Удаленный доступ');

  try {
    const r = await fetch(url);
    if (!r.ok) { console.error('fetchList error', r.status, r.statusText); ITEMS = []; return; }
    ITEMS = await r.json();
  } catch (e) {
    console.error('fetchList exception', e);
    ITEMS = [];
  }
}

const greenIcon = L.icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
  iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41]
});
const blueIcon = L.icon({
  iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-blue.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
  iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41]
});

const el = document.getElementById('mode-status');
    if (el) el.textContent = modeText;
  }
}


    console.error('loadAnalyticsSummary failed', err);
    if (overview) {
      overview.innerHTML = '<div class="muted">Не удалось загрузить аналитику</div>';
    }
  }
}
/* ========= Оффлайн: загрузки карт и геокодера ========= */
function openSettings() { const sb = $('#settings-backdrop'); if (sb) sb.classList.add('open'); }
function closeSettings() {
  const sb = $('#settings-backdrop'); if (sb) sb.classList.remove('open');
  const mf = document.getElementById('map-files-list'); if (mf) mf.style.display = 'none';
  const gf = document.getElementById('geocode-files-list'); if (gf) gf.style.display = 'none';
}
async function loadCities() {
  try {
    const r = await fetch('/api/offline/cities'); const arr = await r.json();
    const sel = $('#offline-city'); if (!sel) return;
    sel.innerHTML = '';
    for (const c of arr) { const o = document.createElement('option'); o.value = c.code; o.textContent = c.name; sel.appendChild(o); }
  } catch (e) { console.error(e); }
}
function startMapDownload(setName = '') {
  const code = $('#offline-city')?.value || 'minsk';
  const status = $('#map-status');
  const bar = $('#map-progress');
  setProgress(bar, 0);
  if (status) status.textContent = 'Старт...';
  try { window.__mapSSE?.close(); } catch (_) { }
  const zmaxInput = document.getElementById('offline-zmax');
  let zmaxVal = 14;
  if (zmaxInput) { const v = parseInt(zmaxInput.value); if (!isNaN(v)) zmaxVal = v; }
  zmaxVal = Math.max(0, Math.min(19, zmaxVal));
  let url = `/api/offline/map/stream?city=${encodeURIComponent(code)}&zmin=6&zmax=${zmaxVal}`;
  if (setName && setName.trim() && setName.toLowerCase() !== 'download') url += `&set=${encodeURIComponent(setName.trim())}`;
  mapDownloadStart = Date.now();
  const es = new EventSource(url);
  window.__mapSSE = es;
  es.onmessage = ev => {
    const d = JSON.parse(ev.data);
    if (d.type === 'progress') {
      setProgress(bar, d.pct);
      if (status) {
        const elapsed = (Date.now() - mapDownloadStart) / 1000;
        const pct = (d.total && d.total > 0) ? (d.done / d.total) : 0;
        if (pct > 0) {
          const remaining = elapsed * (1 / pct - 1);
          const mins = Math.floor(remaining / 60);
          const secs = Math.floor(remaining % 60).toString().padStart(2, '0');
          status.textContent = `${d.done}/${d.total} — осталось ${mins}:${secs}`;
        } else status.textContent = `${d.done}/${d.total}`;
      }
    }
    if (d.type === 'done') {
      setProgress(bar, 100);
      if (status) status.textContent = 'Готово';
      es.close();
      setTileSource('local');
      try { loadOfflineSets(); } catch (_) {}
      try { updateOfflineStatus(); } catch (_) {}
      const btn = document.getElementById('btn-download-map');
      if (btn) btn.disabled = false;
    }
    if (d.type === 'error') { if (status) status.textContent = d.message || 'Ошибка'; es.close(); const btn = document.getElementById('btn-download-map'); if (btn) btn.disabled = false; }
  };
  es.onerror = () => { if (status) status.textContent = 'Ошибка соединения'; es.close(); const btn = document.getElementById('btn-download-map'); if (btn) btn.disabled = false; };
}
async function deleteMap() {
  if (!confirm('Вы уверены, что хотите удалить скачанные тайлы карты?')) return;
  await fetch('/api/offline/map:delete', { method: 'POST' });
  const s = $('#map-status'); if (s) s.textContent = 'Удалено';
  setTileSource('online');
  try { updateOfflineStatus(); } catch (_) {}
}
function startGeocodeDownload() {
  const code = $('#offline-city').value || 'minsk';
  const status = $('#geo-status');
  const bar = $('#geo-progress');
  setProgress(bar, 0);
  if (status) status.textContent = 'Старт...';
  try { window.__geoSSE?.close(); } catch (_) { }
  geocodeDownloadStart = Date.now();
  const es = new EventSource(`/api/offline/geocode/stream?city=${encodeURIComponent(code)}`);
  window.__geoSSE = es;
  es.onmessage = ev => {
    const d = JSON.parse(ev.data);
    if (d.type === 'progress') {
      setProgress(bar, d.pct);
      if (status) {
        const pct = d.pct || 0;
        let msg = d.step || '';
        if (pct > 0) {
          const elapsed = (Date.now() - geocodeDownloadStart) / 1000;
          const remaining = elapsed * (100 / pct - 1);
          const mins = Math.floor(remaining / 60);
          const secs = Math.floor(remaining % 60).toString().padStart(2, '0');
          msg = (msg ? msg + ' — ' : '') + `осталось ${mins}:${secs}`;
        }
        status.textContent = msg;
      }
    }
    if (d.type === 'done') { setProgress(bar, 100); if (status) status.textContent = 'Готово'; es.close(); }
    if (d.type === 'error') { if (status) status.textContent = d.message || 'Ошибка'; es.close(); }
  };
  es.onerror = () => { if (status) status.textContent = 'Ошибка соединения'; es.close(); };
}
async function deleteGeocode() {
  if (!confirm('Вы уверены, что хотите удалить базу геокодирования?')) return;
  await fetch('/api/offline/geocode:delete', { method: 'POST' });
  const s = $('#geo-status'); if (s) s.textContent = 'Удалено';
}


/* ========= Записи геокодера ========= */
async function viewGeocodeEntries() {
  const listEl = document.getElementById('geocode-entries-list');
  if (!listEl) return;
  if (listEl.style.display === 'block') { listEl.style.display = 'none'; listEl.innerHTML = ''; return; }
  try {
    const r = await fetch('/api/offline/geocode/entries');
    if (!r.ok) { showToast('Не удалось загрузить записи', 'error'); return; }
    const data = await r.json();
    listEl.innerHTML = '';
    if (data.entries && Array.isArray(data.entries)) {
      data.entries.forEach(entry => {
        const row = document.createElement('div');
        row.className = 'entry';
        const info = document.createElement('div');
        info.className = 'info';
        const title = document.createElement('b');
        title.textContent = entry.display_name || '';
        info.appendChild(title);
        const coord = document.createElement('span');
        coord.textContent = `${entry.lat != null ? entry.lat : ''}, ${entry.lon != null ? entry.lon : ''}`;
        info.appendChild(coord);
        row.appendChild(info);
        const btn = document.createElement('button');
        btn.className = 'warn';
        btn.textContent = 'Удалить';
        btn.onclick = async () => {
          if (!confirm('Удалить эту запись?')) return;
          try {
            const resp = await fetch(`/api/offline/geocode/entries/${entry.id}`, { method: 'DELETE' });
            if (!resp.ok) { showToast('Не удалось удалить запись', 'error'); return; }
            showToast('Запись удалена', 'success');
            viewGeocodeEntries();
          } catch (e) { console.error(e); }
        };
        row.appendChild(btn);
        listEl.appendChild(row);
      });
    }
    listEl.style.display = 'block';
  } catch (err) { console.error('viewGeocodeEntries failed', err); }
}

}






/* ========= Обновление списка/карты ========= */
async function refresh() { await fetchList(); renderList(); }

/* ========= Привязка UI ========= */
function bindUI() {
  const btnToggle = $('#btn-toggle-sidebar'); if (btnToggle) btnToggle.onclick = toggleSidebar;
  const btnTheme = $('#btn-theme'); if (btnTheme) btnTheme.onclick = toggleTheme;
  const btnAdd = $('#btn-add'); if (btnAdd) btnAdd.onclick = openAdd;
  const modalClose = $('#modal-close'); if (modalClose) modalClose.onclick = closeAdd;
  const modalBackdrop = $('#modal-backdrop'); if (modalBackdrop) modalBackdrop.addEventListener('click', e => { if (e.target.id === 'modal-backdrop') closeAdd(); });
  const btnGeocode = $('#btn-geocode'); if (btnGeocode) btnGeocode.onclick = geocodeAddress;
  const modalSave = $('#modal-save'); if (modalSave) modalSave.onclick = saveAdd;



  const btnFile = $('#btn-file');
  const fileMenu = $('#file-menu');
  if (btnFile) {
    btnFile.onclick = (e) => {
      e.stopPropagation();
      if (!fileMenu) return;
      // если меню уже открыто — закрываем
      if (fileMenu.style.display === 'block') {
        fileMenu.style.display = 'none';
        // восстановление родителя, если нужно
        if (fileMenu._restore) {
          const { parent, next } = fileMenu._restore;
          next ? parent.insertBefore(fileMenu, next) : parent.appendChild(fileMenu);
          fileMenu._restore = null;
        }
        return;
      }
      // определяем положение кнопки
      const rect = btnFile.getBoundingClientRect();
      try {
        if (fileMenu.parentElement !== document.body) {
          fileMenu._restore = { parent: fileMenu.parentElement, next: fileMenu.nextSibling };
          document.body.appendChild(fileMenu);
        }
      } catch (_) {}
      fileMenu.style.position = 'fixed';
      fileMenu.style.left = Math.round(rect.left) + 'px';
      fileMenu.style.top = Math.round(rect.bottom + 6) + 'px';
      // сбрасываем выравнивание по правому краю, иначе меню растягивается до края
      fileMenu.style.right = 'auto';
      fileMenu.style.zIndex = '9999';
      fileMenu.style.display = 'block';
    };
  }
  if (fileMenu) {
    const expCsv = $('#menu-export-csv'); if (expCsv) expCsv.onclick = doExport;
    const expJson = $('#menu-export-json'); if (expJson) expJson.onclick = exportGeoJSON;
    const impCsv = $('#menu-import-csv'); if (impCsv) impCsv.onclick = openImportFile;
    const impJson = $('#menu-import-json'); if (impJson) impJson.onclick = openImportJson;
  }
  document.addEventListener('click', (e) => {
    if (!fileMenu) return;
    const target = e.target;
    if (btnFile && (btnFile.contains(target) || fileMenu.contains(target))) return;
    fileMenu.style.display = 'none';
    // возвращаем меню на место, если перемещали
    if (fileMenu._restore) {
      const { parent, next } = fileMenu._restore;
      next ? parent.insertBefore(fileMenu, next) : parent.appendChild(fileMenu);
      fileMenu._restore = null;
    }
  });
  const hiddenFile = $('#hidden-file'); if (hiddenFile) hiddenFile.addEventListener('change', handleImportFile);
  const hiddenJson = $('#hidden-json'); if (hiddenJson) hiddenJson.addEventListener('change', handleImportJson);

  function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn.apply(this, a), ms); } }
  const searchEl = $('#search'); if (searchEl) searchEl.addEventListener('input', debounce(refresh, 250));

  bindDragDrop();

  const btnSettings = $('#btn-settings');
  if (btnSettings) btnSettings.onclick = async () => {
    openSettings();
    await loadCities();
    await loadOfflineSets();
    await updateOfflineStatus();
  };
  const settingsClose = $('#settings-close'); if (settingsClose) settingsClose.onclick = closeSettings;
  const settingsBackdrop = $('#settings-backdrop'); if (settingsBackdrop) settingsBackdrop.addEventListener('click', e => { if (e.target.id === 'settings-backdrop') closeSettings(); });

  const btnDownloadMap = $('#btn-download-map');
  if (btnDownloadMap) btnDownloadMap.onclick = () => {
    const nameInput = document.getElementById('offline-set-name');
    const setName = (nameInput && nameInput.value || '').trim();
    btnDownloadMap.disabled = true;
    startMapDownload(setName);
  };
  const btnDeleteMap = $('#btn-delete-map'); if (btnDeleteMap) btnDeleteMap.onclick = deleteMap;
  const btnDownloadGeo = $('#btn-download-geocode'); if (btnDownloadGeo) btnDownloadGeo.onclick = startGeocodeDownload;
  const btnDeleteGeo = $('#btn-delete-geocode'); if (btnDeleteGeo) btnDeleteGeo.onclick = deleteGeocode;

  const btnActivateSet = document.getElementById('btn-activate-set');
  if (btnActivateSet) {
    btnActivateSet.onclick = async () => {
      btnActivateSet.disabled = true;
      try {
        await activateOfflineSet();
        await updateOfflineStatus();
      } finally {
        btnActivateSet.disabled = false;
      }
    };
  }
  const btnDeleteSet = document.getElementById('btn-delete-set');
  if (btnDeleteSet) {
    btnDeleteSet.onclick = async () => {
      btnDeleteSet.disabled = true;
      try {
        await deleteOfflineSet();
        await loadOfflineSets();
        await updateOfflineStatus();
      } finally {
        btnDeleteSet.disabled = false;
      }
    };
  }

  const btnViewMap = $('#btn-view-map-files');
  if (btnViewMap) {
    btnViewMap.onclick = async () => {
      try {
        const resp = await fetch('/api/offline/map/files');
        if (!resp.ok) { showToast('Не удалось получить список файлов карты', 'error'); return; }
        const data = await resp.json();
        const listEl = document.getElementById('map-files-list');
        if (listEl) {
          if (data.levels && data.levels.length) {
            let html = '<ul>';
            data.levels.forEach(l => {
              const sz = (l.size != null) ? formatSize(l.size) : '';
              html += `<li>Зум ${l.z}: ${l.tiles} тайлов${sz ? ', ' + sz : ''}</li>`;
            });
            html += '</ul>';
            if (data.size_bytes != null) html += `<div style="margin-top:4px;"><b>Всего:</b> ${formatSize(data.size_bytes)}, ${data.total_tiles} тайлов</div>`;
            listEl.innerHTML = html;
          } else listEl.innerHTML = '<em>Нет загруженных тайлов</em>';
          listEl.style.display = 'block';
        }
      } catch (err) { showToast('Ошибка при загрузке файлов карты', 'error'); }
    };
  }
  const btnViewGeo = $('#btn-view-geocode-files');
  if (btnViewGeo) {
    btnViewGeo.onclick = async () => {
      try {
        const resp = await fetch('/api/offline/geocode/files');
        if (!resp.ok) { showToast('Не удалось получить данные геокодирования', 'error'); return; }
        const data = await resp.json();
        const listEl = document.getElementById('geocode-files-list');
        if (listEl) {
          if (data.files && data.files.length) {
            let html = '<ul>';
            data.files.forEach(f => {
              html += `<li>${f}`;
              const parts = [];
              if (data.entries != null) parts.push(`${data.entries} записей`);
              if (data.size_bytes != null) parts.push(formatSize(data.size_bytes));
              if (data.modified) parts.push(`от ${data.modified}`);
              if (parts.length) html += ` — ${parts.join(', ')}`;
              html += '</li>';
            });
            html += '</ul>';
            listEl.innerHTML = html;
          } else listEl.innerHTML = '<em>Файл геокодирования отсутствует</em>';
          listEl.style.display = 'block';
        }
      } catch (err) { showToast('Ошибка при загрузке данных геокодирования', 'error'); }
    };
  }

  const mapModeSelect = $('#map-mode');
  if (mapModeSelect) {
    mapModeSelect.addEventListener('change', async (ev) => {
      const val = ev.target.value;
      if (val === 'offline') setTileSource('local'); else setTileSource('online');
      const modeStatus = document.getElementById('mode-status');
      if (modeStatus) modeStatus.textContent = val === 'offline' ? 'Режим: Офлайн' : 'Режим: Онлайн';
      await updateOfflineStatus();
    });
  }

  const themeSel = document.getElementById('theme-select');
  if (themeSel) {
    try { const savedAccent = localStorage.getItem('accent') || ''; themeSel.value = savedAccent; } catch (_) {}
    themeSel.addEventListener('change', (ev) => { const val = ev.target.value || ''; applyAccent(val); });
  }

  const filterCat = $('#filter-category'); if (filterCat) filterCat.addEventListener('change', refresh);
  const optLocal = $('#opt-local'), optRemote = $('#opt-remote');
  if (optLocal) optLocal.addEventListener('change', refresh);
  if (optRemote) optRemote.addEventListener('change', refresh);

  const bulkBtn = $('#btn-bulk-del');
  if (bulkBtn) {
    bulkBtn.disabled = true;
    bulkBtn.onclick = async () => {
      const ids = Array.from(document.querySelectorAll('#list input[type=checkbox][data-id]:checked')).map(el => el.dataset.id);
      if (!ids.length) return;
      try {
        await fetch('/api/addresses:batchDelete', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids })
        });
      } catch (e) { console.error('bulk delete failed', e); }
      await refresh();
    };
  }

  const btnDrawZone = $('#btnDrawZone');
  if (btnDrawZone) {
    btnDrawZone.onclick = () => {
      try { map.closePopup(); } catch (_) {}
      try { new L.Draw.Polygon(map, drawControl.options.draw.polygon).enable(); }
      catch (e) { new L.Draw.Polygon(map, { showArea: true, allowIntersection: false, shapeOptions: { color: '#000', weight: 2, fillOpacity: 0.15 } }).enable(); }
    };
  }
  const btnChooseIcon = $('#btnChooseIcon');
  if (btnChooseIcon) {
    btnChooseIcon.onclick = () => { try { map.closePopup(); } catch (_) {} openZoneModalForDefaults(); };
  }

    });
    window.__notifOutsideBound = true;
  }

  const btnAccess = $('#btn-access');
  const accessMenu = $('#access-menu');
  if (btnAccess) {
    btnAccess.onclick = (e) => {
      e.stopPropagation();
      if (!accessMenu) return;
      // если меню открыто — закрываем
      if (accessMenu.style.display === 'block') {
        accessMenu.style.display = 'none';
        // восстановить родителя, если меню было перемещено
        if (accessMenu._restore) {
          const { parent, next } = accessMenu._restore;
          next ? parent.insertBefore(accessMenu, next) : parent.appendChild(accessMenu);
          accessMenu._restore = null;
        }
        return;
      }
      // вычисляем позицию кнопки и переносим меню в body
      const rect = btnAccess.getBoundingClientRect();
      try {
        if (accessMenu.parentElement !== document.body) {
          accessMenu._restore = { parent: accessMenu.parentElement, next: accessMenu.nextSibling };
          document.body.appendChild(accessMenu);
        }
      } catch (_) {}
      accessMenu.style.position = 'fixed';
      accessMenu.style.left = Math.round(rect.left) + 'px';
      accessMenu.style.top = Math.round(rect.bottom + 6) + 'px';
      // сбрасываем выравнивание по правому краю (установленное в CSS)
      accessMenu.style.right = 'auto';
      accessMenu.style.zIndex = '9999';
      accessMenu.style.display = 'block';
    };
  }
  if (accessMenu) {
    document.addEventListener('click', (e) => {
      if (!btnAccess || !accessMenu) return;
      const target = e.target;
      if (btnAccess.contains(target) || accessMenu.contains(target)) return;
      accessMenu.style.display = 'none';
      // восстановить родителя, если нужно
      if (accessMenu._restore) {
        const { parent, next } = accessMenu._restore;
        next ? parent.insertBefore(accessMenu, next) : parent.appendChild(accessMenu);
        accessMenu._restore = null;
      }
    });
  }

  // --- Фото: кнопка в сайдбаре и модалка ---
  const btnViewPhoto = document.getElementById('btn-view-photo');
  if (btnViewPhoto) {
    btnViewPhoto.addEventListener('click', () => {
      const it = getSelectedItem();
      if (!it) {
        showToast('Сначала выберите метку в списке', 'error');
        return;
      }

      // Пытаемся взять URL фото
      let url = '';
      if (it.photo) {
        // Бэкенд отдаёт имя файла, как мы уже используем в списке и попапе
        url = '/uploads/' + it.photo;
      } else if (Array.isArray(it.photos) && it.photos[0] && it.photos[0].url) {
        // Альтернативный вариант структуры данных
        url = it.photos[0].url;
      }

      if (!url) {
        showToast('У этой метки нет прикреплённой фотографии', 'error');
        return;
      }

      openPhotoModal(url);
    });
  }

    // --- Кнопка "Удалить фото" в модалке редактирования ---
  const btnDeletePhoto = document.getElementById('btn-delete-photo');
  if (btnDeletePhoto) {
    btnDeletePhoto.addEventListener('click', () => {
      const removePhotoInput = document.getElementById('f-remove-photo');
      const fileInput = document.getElementById('f-photo');

      if (removePhotoInput) removePhotoInput.value = '1';
      if (fileInput) fileInput.value = ''; // на всякий случай, чтобы не отправить новый файл

      showToast('Фото будет удалено после сохранения', 'warn');
    });
  }


  const photoClose = document.getElementById('photo-close');
  const photoBackdrop = document.getElementById('photo-backdrop');

  if (photoClose) {
    photoClose.addEventListener('click', () => {
      closePhotoModal();
    });
  }

  if (photoBackdrop) {
    photoBackdrop.addEventListener('click', (e) => {
      if (e.target.id === 'photo-backdrop') {
        closePhotoModal();
      }
    });
  }


  const topActions = document.querySelector('.top-actions');
  const scrollLeftBtn = $('#scroll-left');
  const scrollRightBtn = $('#scroll-right');
  if (scrollLeftBtn && topActions) scrollLeftBtn.onclick  = () => topActions.scrollBy({ left: -200, behavior: 'smooth' });
  if (scrollRightBtn && topActions) scrollRightBtn.onclick = () => topActions.scrollBy({ left: 200, behavior: 'smooth' });
}

/* ========= Поиск по радиусу ========= */
/* startRadiusSearch: либо режим "кликните на карте", либо сразу считаем от centerLL */
async function startRadiusSearch(kmParam, centerLL) {
  // Сброс
  if (radiusSearchActive && !kmParam && !centerLL) {
    radiusSearchActive = false;
    radiusFiltered = null;
    if (radiusCircle) { try { map.removeLayer(radiusCircle); } catch(_) {} radiusCircle = null; }
    await refresh();
    showToast('Фильтр радиуса очищен', 'success');
    return;
  }

  // Ветка: сразу посчитать от переданного центра
  if (kmParam && centerLL) {
    const km = Math.max(0, parseFloat(kmParam)) || 0;
    if (!km) { showToast('Введите радиус в километрах', 'error'); return; }
    const center = centerLL;
    radiusFiltered = ITEMS.filter(it => {
      if (it.lat != null && it.lon != null) {
        const dist = haversineDistance(center.lat, center.lng, parseFloat(it.lat), parseFloat(it.lon));
        return dist <= km;
      }
      return false;
    });
    if (radiusCircle) { try { map.removeLayer(radiusCircle); } catch(_) {} }
    radiusCircle = L.circle(center, { radius: km * 1000, color: '#4f46e5', weight: 2, fillOpacity: 0.1 });
    radiusCircle.addTo(map);
    try { map.fitBounds(radiusCircle.getBounds()); } catch(_) {}
    renderList();
    showToast(`Найдено ${radiusFiltered.length} объектов в пределах ${km} км`, 'success');
    return;
  }

  // Старый сценарий: спросить радиус и дождаться клика по карте
  const radiusInput = document.getElementById('radius-km');
  const km = parseFloat(radiusInput && radiusInput.value);
  if (!km || km <= 0) { showToast('Введите радиус в километрах', 'error'); return; }
  showToast('Кликните на карте для выбора центра', 'default', 4000);
  radiusSearchActive = true;
  map.once('click', async (e) => {
    radiusSearchActive = false;
    const center = e.latlng;
    radiusFiltered = ITEMS.filter(it => {
      if (it.lat != null && it.lon != null) {
        const dist = haversineDistance(center.lat, center.lng, parseFloat(it.lat), parseFloat(it.lon));
        return dist <= km;
      }
      return false;
    });
    if (radiusCircle) { try { map.removeLayer(radiusCircle); } catch(_) {} }
    radiusCircle = L.circle(center, { radius: km * 1000, color: '#4f46e5', weight: 2, fillOpacity: 0.1 });
    radiusCircle.addTo(map);
    try { map.fitBounds(radiusCircle.getBounds()); } catch (_) {}
    renderList();
    showToast(`Найдено ${radiusFiltered.length} объектов в пределах ${km} км`, 'success');
  });
}


/* ========= ЗОНЫ ========= */
let DEFAULT_ZONE_ICON = 'beer';
let DEFAULT_ZONE_COLOR = '#ffcc00';

function openZoneModalForNew() {
  const m = document.getElementById('zone-backdrop');
  if (!m) { alert('Окно зоны не найдено'); return; }
  m.style.display = 'block'; m.classList.add('open');

  const descEl = $('#zoneDesc'); if (descEl) descEl.value = '';
  const colorEl = $('#zoneColor'); if (colorEl) colorEl.value = DEFAULT_ZONE_COLOR;
  const iconInput = $('#zoneIcon'); if (iconInput) iconInput.value = DEFAULT_ZONE_ICON;

  const icons = document.querySelectorAll('#zoneIcons .zicon');
  icons.forEach(ic => ic.classList.toggle('active', ic.dataset.icon === DEFAULT_ZONE_ICON));

  const saveBtn = $('#saveZoneBtn');
  const newSave = saveBtn.cloneNode(true);
  saveBtn.parentNode.replaceChild(newSave, saveBtn);
  newSave.onclick = async () => {
    const desc = (document.getElementById('zoneDesc').value || '').trim();
    const color = (document.getElementById('zoneColor').value || DEFAULT_ZONE_COLOR);
    const icon = (document.getElementById('zoneIcon').value || DEFAULT_ZONE_ICON);
    if (!_pendingZoneLayer) { closeZoneModal(); return; }
    try {
      _pendingZoneLayer.setStyle({ color: '#000000', weight: 2, fillColor: color, fillOpacity: 0.15 });
      if (desc) _pendingZoneLayer.bindPopup(escapeHTML(desc));
      _pendingZoneLayer.iconName = icon;
    } catch (e) { console.warn(e); }
    let marker = null;
    let latlngs = [];
    try {
      const arr = _pendingZoneLayer.getLatLngs()[0] || [];
      latlngs = arr.map(p => ({ lat: p.lat, lng: p.lng }));
      let clat = 0, clon = 0;
      for (const p of arr) { clat += p.lat; clon += p.lng; }
      clat = clat / (arr.length || 1); clon = clon / (arr.length || 1);
      const emoji = iconToEmoji(icon);
      marker = L.marker([clat, clon], {
        icon: L.divIcon({
          html: `<div style="font-size:22px; line-height:22px;">${emoji}</div>`,
          className: 'zone-icon', iconSize: [22, 22], iconAnchor: [11, 11]
        })
      });

      marker.iconName = icon;
      zonesLayer.addLayer(marker);
    } catch (e) { console.warn('centroid error', e); }
    const id = await saveZoneToServer(desc, color, icon, latlngs);
    if (id) {
      _pendingZoneLayer.zoneId = id;
      _pendingZoneLayer.iconName = icon;
      if (marker) marker.zoneId = id;
      zonePolygonMap[id] = _pendingZoneLayer;
      if (marker) zoneMarkerMap[id] = marker;
    }
    _pendingZoneLayer = null;
    saveZonesToLocal();
    closeZoneModal();
  };
  m.addEventListener('click', zoneBackdropCloser);
}
function openZoneModalForDefaults() {
  const m = document.getElementById('zone-backdrop');
  if (!m) { alert('Окно зоны не найдено'); return; }
  m.style.display = 'block'; m.classList.add('open');
  document.getElementById('zoneDesc').value = '';
  document.getElementById('zoneColor').value = DEFAULT_ZONE_COLOR;
  document.getElementById('zoneIcon').value = DEFAULT_ZONE_ICON;
  const icons = document.querySelectorAll('#zoneIcons .zicon');
  icons.forEach(ic => ic.classList.toggle('active', ic.dataset.icon === DEFAULT_ZONE_ICON));
  const saveBtn = $('#saveZoneBtn');
  const newSave = saveBtn.cloneNode(true);
  saveBtn.parentNode.replaceChild(newSave, saveBtn);
  newSave.onclick = () => {
    DEFAULT_ZONE_COLOR = document.getElementById('zoneColor').value || DEFAULT_ZONE_COLOR;
    DEFAULT_ZONE_ICON = document.getElementById('zoneIcon').value || DEFAULT_ZONE_ICON;
    closeZoneModal();
  };
  m.addEventListener('click', zoneBackdropCloser);
}
function closeZoneModal() {
  const m = document.getElementById('zone-backdrop'); if (!m) return;
  m.classList.remove('open'); m.style.display = 'none';
  m.removeEventListener('click', zoneBackdropCloser);
  editingZoneLayer = null;
}
function zoneBackdropCloser(e) { if (e.target && e.target.id === 'zone-backdrop') closeZoneModal(); }

function cancelNewZone() {
  if (_pendingZoneLayer) { try { zonesLayer.removeLayer(_pendingZoneLayer); } catch (e) { console.warn(e); } _pendingZoneLayer = null; }
  closeZoneModal();
}
function iconToEmoji(v) {
  switch (v) {
    case 'beer': return '🍺';
    case 'car-crash': return '🚗💥';
    case 'user-secret': return '🕵️';
    case 'gavel': return '⚖️';
    case 'exclamation-triangle': return '⚠️';
    default: return '📍';
  }
}

/* ========= Выделение элементов ========= */
function selectItem(itemId) {
  if (currentSelectedId && listMap[currentSelectedId]) listMap[currentSelectedId].classList.remove('selected');
  currentSelectedId = itemId;
  const li = listMap[itemId]; if (li) li.classList.add('selected');
  const marker = markerMap[itemId];
  if (marker) {
    try {
      const currentZoom = map.getZoom();
      const targetZoom = Math.max(currentZoom, 16);
      map.setView(marker.getLatLng(), targetZoom);
      marker.openPopup();
      // bump анимация
      const el = marker._icon;
      if (el) {
        el.classList.remove('marker--bump');
        void el.offsetWidth; // reflow
        el.classList.add('marker--bump');
      }
    } catch (_) { }
  }
}

function getSelectedItem() {
  if (currentSelectedId == null) return null;
  const items = radiusFiltered || ITEMS;
  return items.find(it => String(it.id) === String(currentSelectedId)) || null;
}

function openPhotoModal(url) {
  const backdrop = document.getElementById('photo-backdrop');
  const img = document.getElementById('photo-img');
  if (!backdrop || !img) return;
  img.src = url;
  backdrop.style.display = 'block';
  backdrop.classList.add('open');
}

function closePhotoModal() {
  const backdrop = document.getElementById('photo-backdrop');
  const img = document.getElementById('photo-img');
  if (!backdrop || !img) return;
  img.src = '';
  backdrop.classList.remove('open');
  backdrop.style.display = 'none';
}


/* ========= Зоны: сервер ========= */
async function loadZonesFromServer() {
  try {
    const res = await fetch('/zones');
    if (!res.ok) return;
    const arr = await res.json();
    arr.forEach(z => {
      const geom = z.geometry;
      let latlngs = [];
      if (geom && Array.isArray(geom.latlngs)) {
        latlngs = geom.latlngs.map(p => [p.lat, p.lng]);
      } else if (geom && Array.isArray(geom.coordinates)) {
        latlngs = geom.coordinates[0].map(c => [c[1], c[0]]);
      }
      if (!latlngs.length) return;
      const poly = L.polygon(latlngs, {
        color: '#000', weight: 2, fillColor: z.color || DEFAULT_ZONE_COLOR, fillOpacity: 0.15,
      }).bindPopup(escapeHTML(z.description || ''));
      poly.zoneId = z.id;
      poly.iconName = z.icon || 'beer';
      zonesLayer.addLayer(poly);
      zonePolygonMap[z.id] = poly;
      try {
        const sum = latlngs.reduce((acc, p) => [acc[0] + p[0], acc[1] + p[1]], [0, 0]);
        const clat = sum[0] / latlngs.length;
        const clon = sum[1] / latlngs.length;
        const emoji = iconToEmoji(poly.iconName);
        const marker = L.marker([clat, clon], {
          icon: L.divIcon({
            html: `<div style="font-size:22px; line-height:22px;">${emoji}</div>`,
            className: 'zone-icon', iconSize: [22, 22], iconAnchor: [11, 11],
          }),
        });
        marker.zoneId = z.id;
        marker.iconName = poly.iconName;
        zonesLayer.addLayer(marker);
        zoneMarkerMap[z.id] = marker;
      } catch (err) { console.warn('centroid error', err); }
    });
  } catch (err) { console.error('loadZonesFromServer failed', err); }
}
async function saveZoneToServer(description, color, icon, latlngs) {
  try {
    const resp = await fetch('/zones', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description, color, icon, geometry: { latlngs } }),
    });
    if (!resp.ok) throw new Error('Server error');
    const data = await resp.json();
    return data.id;
  } catch (e) { console.error('saveZoneToServer failed', e); showToast('Ошибка сохранения зоны', 'error'); return null; }
}
async function updateZoneToServer(layer) {
  try {
    const id = layer.zoneId; if (!id) return;
    const latlngs = layer.getLatLngs()[0].map(p => ({ lat: p.lat, lng: p.lng }));
    const desc = (layer.getPopup() && layer.getPopup().getContent()) || '';
    const color = layer.options.fillColor || DEFAULT_ZONE_COLOR;
    const icon = layer.iconName || 'beer';
    await fetch(`/zones/${id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description: desc, color, icon, geometry: { latlngs } }),
    });
    showToast('Зона обновлена', 'success');
  } catch (err) { console.error('updateZoneToServer failed', err); showToast('Ошибка обновления зоны', 'error'); }
}
async function deleteZoneFromServer(id) {
  try { if (!id) return; await fetch(`/zones/${id}`, { method: 'DELETE' }); showToast('Зона удалена', 'success'); }
  catch (err) { console.error('deleteZoneFromServer failed', err); showToast('Ошибка удаления зоны', 'error'); }
}
async function updateZonesToServer() {
  const layers = [];
  zonesLayer.eachLayer(l => { if (l instanceof L.Polygon && l.zoneId) layers.push(l); });
  for (const l of layers) await updateZoneToServer(l);
}

/* ========= LocalStorage зон ========= */
const ZONES_KEY = 'map_v12_zones_v1';
function saveZonesToLocal() {
  try {
    const arr = [];
    zonesLayer.eachLayer(l => {
      if (l instanceof L.Polygon) {
        const latlngs = l.getLatLngs()[0].map(p => ({ lat: p.lat, lng: p.lng }));
        arr.push({ type: 'polygon', latlngs, options: l.options, popup: (l.getPopup() && l.getPopup().getContent()) || '' });
      }
    });
    localStorage.setItem(ZONES_KEY, JSON.stringify(arr));
  } catch (e) { console.warn('saveZonesToLocal failed', e); }
}
function loadZonesFromLocal() {
  try {
    const raw = localStorage.getItem(ZONES_KEY);
    if (!raw) return;
    const arr = JSON.parse(raw);
    for (const it of arr) {
      if (it.type === 'polygon' && Array.isArray(it.latlngs)) {
        const p = L.polygon(it.latlngs, it.options || { color: '#000', weight: 2, fillOpacity: 0.15 }).bindPopup(it.popup || '');
        zonesLayer.addLayer(p);
      }
    }
  } catch (e) { console.warn('loadZonesFromLocal failed', e); }
}

/* ========= Иконки зоны ========= */
function setupZoneIconEvents() {
  const icons = document.querySelectorAll('#zoneIcons .zicon');
  icons.forEach(ic => {
    ic.addEventListener('click', () => {
      icons.forEach(i => i.classList.remove('active'));
      ic.classList.add('active');
      const input = document.getElementById('zoneIcon');
      if (input) input.value = ic.dataset.icon || '';
    });
  });
}

/* ========= Роли ========= */

function applyRole(role) {
  const isAdmin = (role === 'admin');
  const addBtn = document.getElementById('btn-add'); if (addBtn) addBtn.disabled = !isAdmin;
  const bulkBtn = document.getElementById('btn-bulk-del'); if (bulkBtn) bulkBtn.disabled = !isAdmin;
  document.querySelectorAll('[data-act="edit"]').forEach(btn => { btn.style.display = isAdmin ? '' : 'none'; });
  document.querySelectorAll('[data-act="del"]').forEach(btn  => { btn.style.display = isAdmin ? '' : 'none'; });
  try {
    if (!isAdmin && drawControl) map.removeControl(drawControl);
    else if (isAdmin && drawControl) map.addControl(drawControl);
  } catch (_) {}

  // Показываем кнопку чата и аналитику только администратору
  const btnChat = document.getElementById('btn-chat');
  if (btnChat) btnChat.style.display = isAdmin ? '' : 'none';

  const btnAnalytics = document.getElementById('btn-analytics');
  if (btnAnalytics) btnAnalytics.style.display = isAdmin ? '' : 'none';
}

/* ========= Запуск ========= */
document.addEventListener('DOMContentLoaded', async () => {
  ensureInjectedStyles();
  applyTheme(localStorage.getItem('theme') || 'light');
  try { const savedAccent = localStorage.getItem('accent') || ''; applyAccent(savedAccent); } catch (_) {}
  initMap();
  bindUI();
  setupZoneIconEvents();
  loadZonesFromLocal();
  try { await loadZonesFromServer(); } catch (e) { console.warn('loadZonesFromServer failed', e); }
  await refresh();
  try { await updateOfflineStatus(); } catch (_) {}

  initShortcuts();
  initGeolocateControl();

  // Запрашиваем разрешение на уведомления, если пользователь ещё не давал его
  if ('Notification' in window && Notification.permission === 'default') {
    try {
      Notification.requestPermission();
    } catch (err) {
      console.warn('Notification permission request failed', err);
    }
  }



const roleModal = document.getElementById('role-modal');
const btnAdminRole = document.getElementById('btn-admin-role');
const btnGuestRole = document.getElementById('btn-guest-role');
const roleChoice = document.getElementById('role-choice');
const loginArea = document.getElementById('login-area');
const loginSubmit = document.getElementById('login-submit');
const loginBack = document.getElementById('login-back');
const loginError = document.getElementById('login-error');
 {
      const resp = await fetch('/setrole/guest', { method: 'POST' });
      if (!resp.ok) { showToast('Ошибка выбора роли', 'error'); return; }
      CURRENT_ROLE = 'guest';
      if (roleModal) roleModal.style.display = 'none';
      applyRole('guest');
    } catch (err) { console.error(err); showToast('Ошибка выбора роли', 'error'); }
  });
  if (loginBack) loginBack.addEventListener('click', () => {
    if (loginArea) loginArea.style.display = 'none';
    if (loginError) { loginError.style.display = 'none'; loginError.textContent = ''; }
    if (roleChoice) roleChoice.style.display = 'block';
  });
  if (loginSubmit) loginSubmit.addEventListener('click', async () => {
    const username = (document.getElementById('login-username')?.value || '').trim();
    const password = (document.getElementById('login-password')?.value || '');
    try {
      const resp = await fetch('/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      if (resp.ok) {
        CURRENT_ROLE = 'admin';
        if (roleModal) roleModal.style.display = 'none';
        applyRole('admin');
      } else {
        const data = await resp.json().catch(() => ({}));
        const msg = data && data.error ? data.error : 'Ошибка входа';
        if (loginError) { loginError.textContent = msg; loginError.style.display = 'block'; }
        else { showToast(msg, 'error'); }
      }
    } catch (err) { console.error(err); showToast('Ошибка входа', 'error'); }

    refreshNotifCount();
    setInterval(refreshNotifCount, 15000);
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') refreshNotifCount(); });
  });
});

/* Ripple on .btn / .icon */
function attachRipple(root = document) {
  root.addEventListener('pointerdown', (e) => {
    const t = e.target.closest('.btn, .icon');
    if (!t) return;
    const rect = t.getBoundingClientRect();
    const span = document.createElement('span');
    span.className = 'ripple';
    span.style.left = (e.clientX - rect.left) + 'px';
    span.style.top  = (e.clientY - rect.top) + 'px';
    t.appendChild(span);
    span.addEventListener('animationend', () => span.remove(), { once: true });
  });
}
attachRipple();


/* NOTIF_FIX_OUTSIDE */
document.addEventListener('click', (ev) => {
  const menu = document.getElementById('notif-menu');
  const btn  = document.getElementById('btn-bell');
  if (!menu || !btn) return;
  const t = ev.target;
  if (t === menu || (menu.contains && menu.contains(t)) || t === btn || (btn.contains && btn.contains(t))) return;
  if (menu.style.display === 'block') {
    menu.style.display = 'none';
    if (menu._restore) {
      const { parent, next } = menu._restore;
      next ? parent.insertBefore(menu, next) : parent.appendChild(menu);
      menu._restore = null;
    }
  }
}, true);

function __repositionNotifMenu() {
  const menu = document.getElementById('notif-menu');
  const btn  = document.getElementById('btn-bell');
  if (!menu || !btn) return;
  if (menu.style.display === 'block') {
    const r = btn.getBoundingClientRect();
    menu.style.left = Math.round(r.left) + 'px';
    menu.style.top  = Math.round(r.bottom + 6) + 'px';
  }
}
window.addEventListener('resize', __repositionNotifMenu, { passive: true });
window.addEventListener('scroll', __repositionNotifMenu, { passive: true });
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  const menu = document.getElementById('notif-menu');
  if (!menu || menu.style.display !== 'block') return;
  menu.style.display = 'none';
  if (menu._restore) {
    const { parent, next } = menu._restore;
    next ? parent.insertBefore(menu, next) : parent.appendChild(menu);
    menu._restore = null;
  }

});


/* ========= Keyboard shortcuts =========
  / : focus search
  t : toggle theme
  s : toggle sidebar
  a : open "add"
  ? : show help
  Esc : close any open modal/menus
*/
