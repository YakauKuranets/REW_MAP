/* ========= Offline map: status & tile sets ========= */
/**
 * Модуль работы с оффлайн-наборами карт:
 *  - updateOfflineStatus
 *  - loadOfflineSets / activateOfflineSet / deleteOfflineSet
 *
 * Функции экспортируются в window.*, т.к. вызываются из main.js.
 */
(function() {
  async function updateOfflineStatus() {
    const modeSel = document.getElementById('map-mode');
    const modeText = (modeSel && modeSel.value === 'offline') ? 'Режим: Офлайн' : 'Режим: Онлайн';
    try {
      const res = await fetch('/api/offline/map/sets');
      if (!res.ok) {
        const el = document.getElementById('mode-status');
        if (el) el.textContent = modeText;
        return;
      }
      const data = await res.json(); // {active, sets:[{name,total_tiles,size_bytes}]}
      const active = data.active || 'download';
      const el = document.getElementById('mode-status');
      if (el) el.textContent = (active && active.toLowerCase() !== 'download')
        ? `${modeText}; Активный набор: ${active}`
        : modeText;

      const sel = document.getElementById('offline-set-select');
      if (sel && data.sets) {
        sel.innerHTML = '';
        data.sets.forEach(s => {
          const o = document.createElement('option');
          o.value = s.name;
          o.textContent = s.total_tiles ? `${s.name} (${s.total_tiles})` : s.name;
          sel.appendChild(o);
        });
        sel.value = data.active || 'download';
      }
        } catch (_) {
      // игнорируем, статус оффлайна необязателен
    }
  }

  async function loadOfflineSets() {

    try {
      const r = await fetch('/api/offline/map/sets');
      if (!r.ok) return;
      const data = await r.json();
      const sel = document.getElementById('offline-set-select');
      if (!sel) return;
      sel.innerHTML = '';
      if (data.sets && Array.isArray(data.sets)) {
        data.sets.forEach(setInfo => {
          const opt = document.createElement('option');
          opt.value = setInfo.name;
          const count = setInfo.total_tiles || 0;
          opt.textContent = `${setInfo.name} (${count})`;
          sel.appendChild(opt);
        });
        sel.value = data.active || 'download';
      }
    } catch (err) { console.error('loadOfflineSets failed', err); }
  }
  async function activateOfflineSet() {
    const sel = document.getElementById('offline-set-select');
    if (!sel) return;
    const val = sel.value || '';
    try {
      const res = await fetch('/api/offline/map/activate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ set: val })
      });
      if (!res.ok) { showToast('Не удалось активировать набор', 'error'); return; }
      await res.json();
      showToast('Набор активирован', 'success');
      if (val && val.toLowerCase() !== 'download') setTileSource('local'); else setTileSource('online');
    } catch (err) { console.error('activateOfflineSet failed', err); }
  }
  async function deleteOfflineSet() {
    const sel = document.getElementById('offline-set-select');
    if (!sel) return;
    const val = sel.value || '';
    if (!val || val.toLowerCase() === 'download') {
      if (!confirm('Удалить скачанные тайлы по умолчанию?')) return;
      await deleteMap();
      await loadOfflineSets();
      return;
    }
    if (!confirm(`Удалить набор карт "${val}"?`)) return;
    try {
      const res = await fetch(`/api/offline/map/sets/${encodeURIComponent(val)}`, { method: 'DELETE' });
      if (!res.ok) { showToast('Не удалось удалить набор', 'error'); return; }
      showToast('Набор удалён', 'success');
      await loadOfflineSets();
    } catch (err) { console.error('deleteOfflineSet failed', err); }
  }

  

  /* ========= Оффлайн: настройки, скачивание карт и геокодера ========= */
  const $ = (s, r = document) => r.querySelector(s);

  /**
   * Обновляет прогресс‑бар.
   *
   * В некоторых местах проекта (например, в main.js) прогресс‑бар реализован через
   * CSS‑переменную --progress, которая применяется к псевдоэлементу ::after.
   * В исходной реализации offline.js ширина задавалась напрямую через el.style.width,
   * что не срабатывало для такого вида прогресс‑баров, и скачивание геокодирования
   * отображалось без визуального прогресса.  Для единообразия используем тот же
   * подход, что и в main.js: устанавливаем CSS‑переменную и обновляем текст внутри span.
   * @param {HTMLElement} el – элемент progress (div.progress) или тег <progress>
   * @param {number} pct – процент (0..100)
   */
  function setProgress(el, pct) {
    if (!el) return;
    let v = Number(pct);
    if (isNaN(v)) v = 0;
    v = Math.max(0, Math.min(100, Math.round(v)));
    const pctStr = v + '%';
    // Если это нативный тег <progress>, используем value
    if (el.tagName && el.tagName.toLowerCase() === 'progress') {
      el.value = v;
    } else {
      try {
        // Устанавливаем CSS‑переменную для ::after
        el.style.setProperty('--progress', pctStr);
      } catch (err) {
        // Fallback: меняем ширину элемента или span
        try {
          const bar = (el.querySelector && el.querySelector('span')) ? el : null;
          if (bar && bar.style) bar.style.width = pctStr;
        } catch (_) {}
      }
      // Обновляем текстовое отображение процента, если есть
      const t = (el.querySelector) ? el.querySelector('span') : null;
      if (t) t.textContent = pctStr;
    }
  }

  function formatSize(bytes) {
    const units = ['байт', 'КБ', 'МБ', 'ГБ', 'ТБ'];
    let n = Number(bytes);
    if (!n || n < 0) return '';
    let u = 0;
    while (n >= 1024 && u < units.length - 1) { n /= 1024; u++; }
    return (u === 0 ? n.toFixed(0) : n.toFixed(1)) + ' ' + units[u];
  }

  let mapDownloadStart = 0;
  let geocodeDownloadStart = 0;

  function openSettings() {
    const sb = $('#settings-backdrop');
    if (sb) sb.classList.add('open');
  }

  function closeSettings() {
    const sb = $('#settings-backdrop');
    if (sb) sb.classList.remove('open');
    const mf = document.getElementById('map-files-list'); if (mf) { mf.style.display = 'none'; mf.innerHTML = ''; }
    const gf = document.getElementById('geocode-files-list'); if (gf) { gf.style.display = 'none'; gf.innerHTML = ''; }
  }

  async function loadCities() {
    try {
      const r = await fetch('/api/offline/cities');
      if (!r.ok) return;
      const arr = await r.json();
      const sel = $('#offline-city');
      if (!sel) return;
      sel.innerHTML = '';
      for (const c of arr) {
        const o = document.createElement('option');
        o.value = c.code;
        o.textContent = c.name;
        sel.appendChild(o);
      }
    } catch (e) { console.error('loadCities failed', e); }
  }

  function startMapDownload(setName = '') {
    const code = $('#offline-city')?.value || 'minsk';
    const status = $('#map-status');
    const bar = $('#map-progress');
    const btn = document.getElementById('btn-download-map');

    setProgress(bar, 0);
    if (status) status.textContent = 'Старт...';
    if (btn) btn.disabled = true;

    try { window.__mapSSE?.close(); } catch (_) { }
    const zmaxInput = document.getElementById('offline-zmax');
    let zmaxVal = 14;
    if (zmaxInput) { const v = parseInt(zmaxInput.value); if (!isNaN(v)) zmaxVal = v; }
    zmaxVal = Math.max(0, Math.min(19, zmaxVal));

    let url = `/api/offline/map/stream?city=${encodeURIComponent(code)}&zmin=6&zmax=${zmaxVal}`;
    if (setName && setName.trim() && setName.trim().toLowerCase() !== 'download') {
      url += `&set=${encodeURIComponent(setName.trim())}`;
    }

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
        try { setTileSource('local'); } catch (_) {}
        try { loadOfflineSets(); } catch (_) {}
        try { updateOfflineStatus(); } catch (_) {}
        if (btn) btn.disabled = false;
      }
      if (d.type === 'error') {
        if (status) status.textContent = d.message || 'Ошибка';
        try { es.close(); } catch (_) {}
        if (btn) btn.disabled = false;
        if (typeof showToast === 'function') showToast(d.message || 'Ошибка при скачивании карты', 'error');
      }
    };

    es.onerror = () => {
      if (status) status.textContent = 'Ошибка соединения';
      try { es.close(); } catch (_) {}
      if (btn) btn.disabled = false;
      if (typeof showToast === 'function') showToast('Ошибка соединения при скачивании карты', 'error');
    };
  }

  async function deleteMap() {
    if (!confirm('Вы уверены, что хотите удалить скачанные тайлы карты?')) return;
    try {
      const resp = await fetch('/api/offline/map:delete', { method: 'POST' });
      if (!resp.ok) throw new Error(String(resp.status));
    } catch (e) {
      console.warn('deleteMap failed', e);
      if (typeof showToast === 'function') showToast('Не удалось удалить тайлы карты', 'error');
      return;
    }
    const s = $('#map-status'); if (s) s.textContent = 'Удалено';
    try { setTileSource('online'); } catch (_) {}
    try { updateOfflineStatus(); } catch (_) {}
  }

  function startGeocodeDownload() {
    const code = $('#offline-city')?.value || 'minsk';
    const status = $('#geo-status');
    const bar = $('#geo-progress');
    const btn = document.getElementById('btn-download-geocode');

    setProgress(bar, 0);
    if (status) status.textContent = 'Старт...';
    if (btn) btn.disabled = true;

    try { window.__geoSSE?.close(); } catch (_) { }
    geocodeDownloadStart = Date.now();

    let es;
    try {
      es = new EventSource(`/api/offline/geocode/stream?city=${encodeURIComponent(code)}`);
    } catch (err) {
      console.warn('startGeocodeDownload failed', err);
      if (status) status.textContent = 'Ошибка соединения';
      if (btn) btn.disabled = false;
      if (typeof showToast === 'function') showToast('Ошибка соединения при скачивании геокодирования', 'error');
      return;
    }

    window.__geoSSE = es;
    es.onmessage = ev => {
      const d = JSON.parse(ev.data);
      if (d.type === 'progress') {
        setProgress(bar, d.pct);
        if (status) {
          const elapsed = (Date.now() - geocodeDownloadStart) / 1000;
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
        try { es.close(); } catch (_) {}
        if (btn) btn.disabled = false;
      }
      if (d.type === 'error') {
        if (status) status.textContent = d.message || 'Ошибка';
        try { es.close(); } catch (_) {}
        if (btn) btn.disabled = false;
        if (typeof showToast === 'function') showToast(d.message || 'Ошибка при скачивании геокодирования', 'error');
      }
    };
    es.onerror = () => {
      if (status) status.textContent = 'Ошибка соединения';
      try { es.close(); } catch (_) {}
      if (btn) btn.disabled = false;
      if (typeof showToast === 'function') showToast('Ошибка соединения при скачивании геокодирования', 'error');
    };
  }

  async function deleteGeocode() {
    if (!confirm('Вы уверены, что хотите удалить базу геокодирования?')) return;
    try {
      const resp = await fetch('/api/offline/geocode:delete', { method: 'POST' });
      if (!resp.ok) throw new Error(String(resp.status));
    } catch (e) {
      console.warn('deleteGeocode failed', e);
      if (typeof showToast === 'function') showToast('Не удалось удалить базу геокодирования', 'error');
      return;
    }
    const s = $('#geo-status'); if (s) s.textContent = 'Удалено';
  }

  async function viewMapFiles() {
    try {
      const resp = await fetch('/api/offline/map/files');
      if (!resp.ok) { if (typeof showToast === 'function') showToast('Не удалось получить список файлов карты', 'error'); return; }
      const data = await resp.json();
      const listEl = document.getElementById('map-files-list');
      if (!listEl) return;

      if (listEl.style.display === 'block') { listEl.style.display = 'none'; listEl.innerHTML = ''; return; }

      if (data.levels && data.levels.length) {
        let html = '<ul>';
        data.levels.forEach(l => {
          const sz = (l.size != null) ? formatSize(l.size) : '';
          html += `<li>Зум ${l.z}: ${l.tiles} тайлов${sz ? ', ' + sz : ''}</li>`;
        });
        html += '</ul>';
        listEl.innerHTML = html;
      } else listEl.innerHTML = '<em>Нет загруженных тайлов</em>';

      listEl.style.display = 'block';
    } catch (err) { if (typeof showToast === 'function') showToast('Ошибка при загрузке файлов карты', 'error'); }
  }

  async function viewGeocodeFiles() {
    try {
      const resp = await fetch('/api/offline/geocode/files');
      if (!resp.ok) { if (typeof showToast === 'function') showToast('Не удалось получить данные геокодирования', 'error'); return; }
      const data = await resp.json();
      const listEl = document.getElementById('geocode-files-list');
      if (!listEl) return;

      // повторный клик — свернуть список
      if (listEl.style.display === 'block') { listEl.style.display = 'none'; listEl.innerHTML = ''; return; }

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
      } else {
        listEl.innerHTML = '<em>Файл геокодирования отсутствует</em>';
      }
      listEl.style.display = 'block';
    } catch (err) {
      if (typeof showToast === 'function') showToast('Ошибка при загрузке данных геокодирования', 'error');
    }
  }

  function bindOfflineSettingsUI() {
    const backdrop = document.getElementById('settings-backdrop');
    if (backdrop && backdrop.dataset.boundOffline) return;
    if (backdrop) backdrop.dataset.boundOffline = '1';

    const btnSettings = document.getElementById('btn-settings');
    if (btnSettings) {
      btnSettings.addEventListener('click', async () => {
        openSettings();
        try { await loadCities(); } catch (e) { console.warn('loadCities failed', e); }
        try { await loadOfflineSets(); } catch (e) { console.warn('loadOfflineSets failed', e); }
        try { await updateOfflineStatus(); } catch (e) { console.warn('updateOfflineStatus failed', e); }
      });
    }

    const settingsClose = document.getElementById('settings-close');
    if (settingsClose) settingsClose.addEventListener('click', closeSettings);

    if (backdrop) {
      backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) closeSettings();
      });
    }

    const btnDownloadMap = document.getElementById('btn-download-map');
    if (btnDownloadMap) {
      btnDownloadMap.addEventListener('click', () => {
        const nameInput = document.getElementById('offline-set-name');
        const setName = (nameInput && nameInput.value || '').trim();
        try { startMapDownload(setName); } catch (e) {
          console.warn('startMapDownload failed', e);
          if (typeof showToast === 'function') showToast('Не удалось запустить скачивание карты', 'error');
          btnDownloadMap.disabled = false;
        }
      });
    }

    const btnDeleteMap = document.getElementById('btn-delete-map');
    if (btnDeleteMap) btnDeleteMap.addEventListener('click', deleteMap);

    const btnDownloadGeo = document.getElementById('btn-download-geocode');
    if (btnDownloadGeo) btnDownloadGeo.addEventListener('click', startGeocodeDownload);

    const btnDeleteGeo = document.getElementById('btn-delete-geocode');
    if (btnDeleteGeo) btnDeleteGeo.addEventListener('click', deleteGeocode);

    const btnActivateSet = document.getElementById('btn-activate-set');
    if (btnActivateSet) {
      btnActivateSet.addEventListener('click', async () => {
        btnActivateSet.disabled = true;
        try {
          await activateOfflineSet();
          await updateOfflineStatus();
        } finally {
          btnActivateSet.disabled = false;
        }
      });
    }

    const btnDeleteSet = document.getElementById('btn-delete-set');
    if (btnDeleteSet) {
      btnDeleteSet.addEventListener('click', async () => {
        btnDeleteSet.disabled = true;
        try { await deleteOfflineSet(); } finally { btnDeleteSet.disabled = false; }
      });
    }

    const btnViewMap = document.getElementById('btn-view-map-files');
    if (btnViewMap) btnViewMap.addEventListener('click', viewMapFiles);

    const btnViewGeo = document.getElementById('btn-view-geocode-files');
    if (btnViewGeo) btnViewGeo.addEventListener('click', viewGeocodeFiles);

    const mapModeSelect = document.getElementById('map-mode');
    if (mapModeSelect) {
      mapModeSelect.addEventListener('change', async (ev) => {
        const val = ev.target.value;
        try { if (val === 'offline') setTileSource('local'); else setTileSource('online'); } catch (_) {}
        const modeStatus = document.getElementById('mode-status');
        if (modeStatus) modeStatus.textContent = val === 'offline' ? 'Режим: Офлайн' : 'Режим: Онлайн';
        try { await updateOfflineStatus(); } catch (_) {}
      });
    }
  }

  // Запускаем привязку после готовности DOM
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindOfflineSettingsUI);
  } else {
    bindOfflineSettingsUI();
  }
// Экспортируем в глобальную область для совместимости со старым кодом
  window.updateOfflineStatus = updateOfflineStatus;
  window.loadOfflineSets = loadOfflineSets;
  window.activateOfflineSet = activateOfflineSet;
  window.deleteOfflineSet = deleteOfflineSet;
})();
