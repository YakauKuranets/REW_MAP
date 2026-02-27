/* ========= Адреса / CRUD + геокодинг ========= */
/**
 * Модуль отвечает за:
 *  - модалку добавления/редактирования адреса (openAdd/closeAdd/saveAdd)
 *  - геокодинг адреса (geocodeAddress)
 *
 * Функции экспортируются в window.*, т.к. биндинги происходят в bindUI() из main.js.
 */
(function() {

  function t(key, vars){
    try{ if(window.i18n && typeof window.i18n.t==='function') return window.i18n.t(key, vars); }catch(_){ }
    const base = String(key||'');
    if(!vars) return base;
    return base.replace(/\{(\w+)\}/g, (m,k)=> (vars[k]!=null ? String(vars[k]) : m));
  }

  let CURRENT_EDIT_ID = null;

  // Флаг, чтобы предотвратить повторные клики по кнопке «Сохранить»
  // Пока выполняется запрос на сервер, повторный вызов saveAdd будет игнорироваться.
  let _isSaving = false;

  function clearFieldErrors() {
    ['f-address', 'f-lat', 'f-lon', 'f-desc', 'f-link'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.classList.remove('field-error');
    });
  }

  function markError(id) {
    const el = document.getElementById(id);
    if (el) el.classList.add('field-error');
  }

  function validateAddressPayload(d) {
    clearFieldErrors();
    const problems = [];

    if (!d.name || !d.name.trim()) {
      problems.push(t('map_err_need_address'));
      markError('f-address');
    }
    if (isNaN(d.lat) || isNaN(d.lon)) {
      problems.push(t('map_err_coords_nums'));
      markError('f-lat');
      markError('f-lon');
    }
    if (d.notes && d.notes.length > 500) {
      problems.push(t('map_err_desc_long'));
      markError('f-desc');
    }
    if (d.link && d.link.length > 255) {
      problems.push(t('map_err_link_long'));
      markError('f-link');
    }

    if (!problems.length) return true;

    // Используем unified уведомления для вывода ошибок
    if (window.notify && typeof window.notify.error === 'function') {
      window.notify.error(problems.join('\n'));
    } else if (window.showToast) {
      window.showToast(problems.join('\n'), 'error');
    } else {
      alert(problems.join('\n'));
    }
    return false;
  }

  function openAdd(it = null) {
    const mb = $('#modal-backdrop'); if (mb) mb.classList.add('open');

    const photoActions = document.getElementById('photo-edit-actions');
    const removePhotoInput = document.getElementById('f-remove-photo');
    if (removePhotoInput) removePhotoInput.value = '0'; // при каждом открытии сбрасываем флаг

    if (it) {
      CURRENT_EDIT_ID = it.id;
      const mt = $('#modal-title'); if (mt) mt.textContent = t('map_modal_edit');
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
      const mt = $('#modal-title'); if (mt) mt.textContent = t('map_modal_add');
      $('#f-address').value = ''; $('#f-lat').value = ''; $('#f-lon').value = '';
      $('#f-desc').value = ''; $('#f-status').value = ''; $('#f-link').value = ''; $('#f-category').value = '';
      const fp = $('#f-photo'); if (fp) fp.value = '';

      // при создании новой метки блока удаления фото быть не должно
      if (photoActions) photoActions.style.display = 'none';
    }
  }

  // Убираем дублирование: определяем closeAdd только один раз.
  function closeAdd() {
    const mb = $('#modal-backdrop');
    if (mb) mb.classList.remove('open');
  }

  async function saveAdd() {
    // Если уже идёт сохранение, не запускаем его повторно
    if (_isSaving) return;
    _isSaving = true;

    // Захватываем кнопку сохранения, чтобы изменить её состояние
    const btnSave = document.getElementById('modal-save');
    let oldSaveContent;
    if (btnSave) {
      oldSaveContent = btnSave.innerHTML;
      btnSave.disabled = true;
      // Меняем текст на «Сохранение…», можно добавить спиннер по необходимости
      btnSave.innerHTML = t('map_modal_saving');
    }

    const d = {
      name: $('#f-address').value.trim(),
      lat: parseFloat($('#f-lat').value || 0),
      lon: parseFloat($('#f-lon').value || 0),
      notes: $('#f-desc').value.trim(),
      status: $('#f-status').value,
      link: $('#f-link').value.trim(),
      category: $('#f-category').value
    };

    if (!validateAddressPayload(d)) {
      // Валидация не прошла — восстанавливаем состояние кнопки и выходим
      if (btnSave) {
        btnSave.disabled = false;
        btnSave.innerHTML = oldSaveContent || t('map_modal_save');
      }
      _isSaving = false;
      return;
    }

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
      if (window.notify && typeof window.notify.success === 'function') {
        window.notify.success(t('map_modal_saved'));
      } else {
        showToast(t('map_modal_saved'), 'success');
      }
    } catch (e) {
      console.error('saveAdd failed', e);
      if (window.notify && typeof window.notify.error === 'function') {
        window.notify.error(t('map_modal_save_err'));
      } else {
        showToast(t('map_modal_save_err'), 'error');
      }
    } finally {
      // Всегда восстанавливаем состояние кнопки и сбрасываем флаг
      if (btnSave) {
        btnSave.disabled = false;
        btnSave.innerHTML = oldSaveContent || t('map_modal_save');
      }
      _isSaving = false;
    }
  }


  /* ========= Геокодинг ========= */
  async function geocodeAddress() {
    try {
      const btn = $('#btn-geocode');
      const addressInput = $('#f-address'); const latInput = $('#f-lat'); const lonInput = $('#f-lon');
      if (!addressInput || !latInput || !lonInput) {
        if (window.notify && typeof window.notify.error === 'function') {
          window.notify.error(t('map_err_fields_not_found'));
        } else if (window.showToast) {
          window.showToast(t('map_err_fields_not_found'), 'error');
        } else {
          alert(t('map_err_fields_not_found'));
        }
        return;
      }
      const q = (addressInput.value || '').trim();
      if (!q) {
        if (window.notify && typeof window.notify.error === 'function') {
          window.notify.error(t('map_err_enter_address'));
        } else if (window.showToast) {
          window.showToast(t('map_err_enter_address'), 'error');
        } else {
          alert(t('map_err_enter_address'));
        }
        return;
      }
      const m = q.match(/^\\s*([+-]?\\d+(?:[\\.,]\\d+)?)\\s*,\\s*([+-]?\\d+(?:[\\.,]\\d+)?)\\s*$/);
      if (m) {
        const la = m[1].replace(',', '.'); const lo = m[2].replace(',', '.');
        latInput.value = la; lonInput.value = lo;
        try { map.setView([parseFloat(la), parseFloat(lo)], 16); } catch (_) { }
        return;
      }
      if (btn) { btn.disabled = true; var old = btn.textContent; btn.textContent = t('map_geocode_searching'); }
      const lang = (navigator.language || 'ru').split('-')[0];
      const resp = await fetch(`/api/geocode?q=${encodeURIComponent(q)}&limit=1&lang=${encodeURIComponent(lang)}`);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      if (Array.isArray(data) && data.length) {
        const item = data[0];
        latInput.value = item.lat; lonInput.value = item.lon;
        try { map.setView([parseFloat(item.lat), parseFloat(item.lon)], 16); } catch (_) { }
      } else {
        if (window.notify && typeof window.notify.error === 'function') {
          window.notify.error(t('map_err_coords_not_found'));
        } else if (window.showToast) {
          window.showToast(t('map_err_coords_not_found'), 'error');
        } else {
          alert(t('map_err_coords_not_found'));
        }
      }
      if (btn) { btn.textContent = old; btn.disabled = false; }
    } catch (err) {
      console.error(err);
      if (window.notify && typeof window.notify.error === 'function') {
        window.notify.error(t('map_err_geocode_failed_fmt', { err: (err.message || err) }));
      } else if (window.showToast) {
        window.showToast(t('map_err_geocode_failed_fmt', { err: (err.message || err) }), 'error');
      } else {
        alert(t('map_err_geocode_failed_fmt', { err: (err.message || err) }));
      }
      try { const btn2 = $('#btn-geocode'); if (btn2) { btn2.textContent = t('map_geocode_btn'); btn2.disabled = false; } } catch (_) { }
    }
  }

  // Экспорт в глобальную область видимости
  window.openAdd = openAdd;
  window.closeAdd = closeAdd;
  window.saveAdd = saveAdd;
  window.geocodeAddress = geocodeAddress;
})();
