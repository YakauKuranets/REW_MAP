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

  // Экспортируем в глобальную область для совместимости со старым кодом
  window.updateOfflineStatus = updateOfflineStatus;
  window.loadOfflineSets = loadOfflineSets;
  window.activateOfflineSet = activateOfflineSet;
  window.deleteOfflineSet = deleteOfflineSet;
})();
