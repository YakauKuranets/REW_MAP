/* ========= Адреса / CRUD + геокодинг ========= */
/**
 * Модуль отвечает за:
 *  - модалку добавления/редактирования адреса (openAdd/closeAdd/saveAdd)
 *  - геокодинг адреса (geocodeAddress)
 *
 * Функции экспортируются в window.*, т.к. биндинги происходят в bindUI() из main.js.
 */
(function() {
  let CURRENT_EDIT_ID = null;
  function openAdd(it = null) {
    const mb = $('#modal-backdrop'); if (mb) mb.classList.add('open');

    const photoActions = document.getElementById('photo-edit-actions');
    const removePhotoInput = document.getElementById('f-remove-photo');
    if (removePhotoInput) removePhotoInput.value = '0'; // при каждом открытии сбрасываем флаг

    if (it) {
      CURRENT_EDIT_ID = it.id;
      const mt = $('#modal-title'); if (mt) mt.textContent = 'Редактирование';
      $('#f-address').value = it.name || it.address || '';
      $('#f-lat').value = it.lat || '';
      $('#f-lon').value = it.lon || '';
      $('#f-desc').value = it.notes || it.description || '';
      $('#f-status').value = it.status || '';
      $('#f-link').value = it.link || '';
      $('#f-category').value = it.category || '';
      const fp = $('#f-photo');
      if (fp) fp.value = '';

      // если у записи есть фото — показываем блок действий
      if (photoActions) photoActions.style.display = it.photo ? 'flex' : 'none';
    } else {
      CURRENT_EDIT_ID = null;
      const mt = $('#modal-title'); if (mt) mt.textContent = 'Добавить';
      $('#f-address').value = ''; $('#f-lat').value = ''; $('#f-lon').value = '';
      $('#f-desc').value = ''; $('#f-status').value = ''; $('#f-link').value = ''; $('#f-category').value = '';
      const fp = $('#f-photo'); if (fp) fp.value = '';

      // при создании новой метки блока удаления фото быть не должно
      if (photoActions) photoActions.style.display = 'none';
    }
  }

  function closeAdd() { const mb = $('#modal-backdrop'); if (mb) mb.classList.remove('open'); }
  function closeAdd() {
    const mb = $('#modal-backdrop');
    if (mb) mb.classList.remove('open');
  }

  async function saveAdd() {
    const d = {
      name: $('#f-address').value.trim(),
      lat: parseFloat($('#f-lat').value || 0),
      lon: parseFloat($('#f-lon').value || 0),
      notes: $('#f-desc').value.trim(),
      status: $('#f-status').value,
      link: $('#f-link').value.trim(),
      category: $('#f-category').value
    };

    const removePhotoInput = document.getElementById('f-remove-photo');
    const removePhoto = removePhotoInput && removePhotoInput.value === '1';
    if (removePhoto) {
      d.remove_photo = true; // флаг для JSON-запроса
    }

    try {
      const fp = $('#f-photo');
      const hasFile = fp && fp.files && fp.files.length > 0;

      let url, method;
      if (CURRENT_EDIT_ID) {
        url = '/api/addresses/' + CURRENT_EDIT_ID;
        method = 'PUT';
      } else {
        url = '/api/addresses';
        method = 'POST';
      }

      if (hasFile) {
        // multipart/form-data (новое фото)
        const fd = new FormData();
        fd.append('name', d.name);
        fd.append('lat', String(d.lat));
        fd.append('lon', String(d.lon));
        fd.append('notes', d.notes);
        fd.append('status', d.status);
        fd.append('link', d.link);
        fd.append('category', d.category);
        // по желанию можно тоже передавать remove_photo в multipart:
        if (removePhoto) fd.append('remove_photo', '1');
        fd.append('photo', fp.files[0]);

        await fetch(url, { method, body: fd });
      } else {
        // обычный JSON (в т.ч. remove_photo:true)
        await fetch(url, {
          method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(d)
        });
      }

      // если сохраняли заявку из колокольчика
      if (CURRENT_REQUEST_ID) {
        try {
          await fetch(`/api/requests/${encodeURIComponent(CURRENT_REQUEST_ID)}`, { method: 'DELETE' });
          CURRENT_REQUEST_ID = null;
          const list = await fetchPendingRequests();
          if (_notifOpen) renderNotifList(list);
          updateNotifBadge(list.length);
        } catch (e) {
          console.warn('Не удалось убрать запрос из очереди после сохранения', e);
        }
      }

      // сбрасываем состояние формы
      if (fp) fp.value = '';
      if (removePhotoInput) removePhotoInput.value = '0';

      closeAdd();
      await refresh();
      showToast('Сохранено', 'success');
    } catch (e) {
      console.error('saveAdd failed', e);
      showToast('Ошибка сохранения', 'error');
    }
  }


  /* ========= Геокодинг ========= */
  async function geocodeAddress() {
    try {
      const btn = $('#btn-geocode');
      const addressInput = $('#f-address'); const latInput = $('#f-lat'); const lonInput = $('#f-lon');
      if (!addressInput || !latInput || !lonInput) { alert('Поля формы не найдены'); return; }
      const q = (addressInput.value || '').trim();
      if (!q) { alert('Введите адрес'); return; }
      const m = q.match(/^\\s*([+-]?\\d+(?:[\\.,]\\d+)?)\\s*,\\s*([+-]?\\d+(?:[\\.,]\\d+)?)\\s*$/);
      if (m) {
        const la = m[1].replace(',', '.'); const lo = m[2].replace(',', '.');
        latInput.value = la; lonInput.value = lo;
        try { map.setView([parseFloat(la), parseFloat(lo)], 16); } catch (_) { }
        return;
      }
      if (btn) { btn.disabled = true; var old = btn.textContent; btn.textContent = 'Поиск…'; }
      const lang = (navigator.language || 'ru').split('-')[0];
      const resp = await fetch(`/api/geocode?q=${encodeURIComponent(q)}&limit=1&lang=${encodeURIComponent(lang)}`);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      if (Array.isArray(data) && data.length) {
        const item = data[0];
        latInput.value = item.lat; lonInput.value = item.lon;
        try { map.setView([parseFloat(item.lat), parseFloat(item.lon)], 16); } catch (_) { }
      } else alert('Координаты не найдены для этого адреса');
      if (btn) { btn.textContent = old; btn.disabled = false; }
    } catch (err) {
      console.error(err);
      alert('Ошибка геокодинга: ' + (err.message || err));
      try { const btn = $('#btn-geocode'); if (btn) { btn.textContent = 'Геокодинг'; btn.disabled = false; } } catch (_) { }
    }
  }

  // Экспорт в глобальную область видимости
  window.openAdd = openAdd;
  window.closeAdd = closeAdd;
  window.saveAdd = saveAdd;
  window.geocodeAddress = geocodeAddress;
})();
