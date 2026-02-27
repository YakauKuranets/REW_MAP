/* ========= Импорт / Экспорт (CSV + GeoJSON) ========= */
/**
 * Модуль:
 *  - doExport / openImportFile / handleImportFile / bindDragDrop
 *  - exportGeoJSON / openImportJson / handleImportJson
 *
 * Использует:
 *  - refresh(), showToast(), radiusFiltered, ITEMS
 */
(function() {
  async function doExport() {
    const a = document.createElement('a');
    a.href = '/api/export'; a.download = 'addresses.csv';
    document.body.appendChild(a); a.click(); a.remove();
  }
  function openImportFile() { const hf = $('#hidden-file'); if (hf) hf.click(); }
  async function handleImportFile(e) {
    const f = e.target.files[0]; if (!f) return;
    const fd = new FormData(); fd.append('file', f);
    await fetch('/api/import', { method: 'POST', body: fd });
    e.target.value = ''; await refresh();
  }
  function bindDragDrop() {
    const box = $('#sidebar'); if (!box) return;
    box.addEventListener('dragover', e => { e.preventDefault(); });
    box.addEventListener('drop', async e => {
      e.preventDefault();
      const f = Array.from(e.dataTransfer.files).find(x => x.name.endsWith('.csv')); if (!f) return;
      const fd = new FormData(); fd.append('file', f);
      await fetch('/api/import', { method: 'POST', body: fd });
      await refresh();
    });
  }

  /* ========= GeoJSON экспорт/импорт ========= */
  function exportGeoJSON() {
    try {
      const items = radiusFiltered || ITEMS;
      const features = [];
      for (const item of items) {
        const lat = item.lat; const lon = item.lon;
        if (lat == null || lon == null) continue;
        features.push({
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [parseFloat(lon), parseFloat(lat)] },
          properties: {
            id: item.id, address: item.address || '', description: item.description || '',
            status: item.status || '', link: item.link || '', category: item.category || ''
          }
        });
      }
      const geojson = { type: 'FeatureCollection', features };
      const blob = new Blob([JSON.stringify(geojson, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'addresses.geojson';
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      if (window.notify && typeof window.notify.success === 'function') {
        window.notify.success('Экспорт завершён');
      } else {
        showToast('Экспорт завершён', 'success');
      }
    } catch (e) {
      console.error(e);
      if (window.notify && typeof window.notify.error === 'function') {
        window.notify.error('Ошибка экспорта');
      } else {
        showToast('Ошибка экспорта', 'error');
      }
    }
  }
     function openImportJson() {
    const hf = document.getElementById('hidden-json');
    if (hf) hf.click();
  }

  async function handleImportJson(e) {
    const file = e.target.files[0];
    if (!file) return;

    try {
      const text = await file.text();
      const data = JSON.parse(text);

      if (!data || !Array.isArray(data.features)) {
        if (window.notify && typeof window.notify.error === 'function') {
          window.notify.error('Файл не содержит корректный файл GeoJSON');
        } else {
          showToast('Файл не содержит корректный файл GeoJSON', 'error');
        }
        e.target.value = '';
        return;
      }

      for (const feat of data.features) {
        if (!feat || feat.type !== 'Feature' || !feat.geometry || feat.geometry.type !== 'Point') continue;
        const coords = feat.geometry.coordinates || [];
        const lat = coords[1];
        const lon = coords[0];
        const props = feat.properties || {};

        const payload = {
          address: props.address || '',
          lat: lat || null,
          lon: lon || null,
          description: props.description || '',
          status: props.status || '',
          link: props.link || '',
          category: props.category || '',
        };

        await fetch('/api/addresses', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      }

      if (window.notify && typeof window.notify.success === 'function') {
        window.notify.success('Импорт завершён');
      } else {
        showToast('Импорт завершён', 'success');
      }
      e.target.value = '';
      await refresh();
    } catch (err) {
      console.error(err);
      if (window.notify && typeof window.notify.error === 'function') {
        window.notify.error('Ошибка импорта');
      } else {
        showToast('Ошибка импорта', 'error');
      }
      e.target.value = '';
    }
  }


  // Экспортируем функции в глобальную область, т.к. они дергаются из main.js и HTML
  window.doExport = doExport;
  window.openImportFile = openImportFile;
  window.handleImportFile = handleImportFile;
  window.bindDragDrop = bindDragDrop;
  window.exportGeoJSON = exportGeoJSON;
  window.openImportJson = openImportJson;
  window.handleImportJson = handleImportJson;
})();
