/* ========= Zones Admin UI (superadmin only) ========= */
/**
 * Модуль UI для управления зонами:
 *  - показывает список зон (id, описание, цвет, значок, привязанные админы);
 *  - позволяет супер-админу фокусировать карту на зоне;
 *  - позволяет редактировать описание/цвет/значок зоны;
 *  - позволяет удалять зоны.
 *
 * Геометрию зоны (полигон) по-прежнему создаём и редактируем через существующий
 * механизм рисования на карте и модалку «Зона». Здесь мы не трогаем координаты,
 * а только метаданные.
 *
 * Зависимости:
 *  - endpoint GET /zones            — список зон (как уже используется в main.js)
 *  - endpoint PUT /zones/<id>       — обновление зоны
 *  - endpoint DELETE /zones/<id>    — удаление зоны
 *  - endpoint GET /api/admin/users/ — список админов (для отображения привязок)
 *  - глобальные переменные: map, zonePolygonMap, zoneMarkerMap, zonesLayer (если есть)
 *  - функция showToast(msg, type)
 */

(function() {
  const API_ZONES = '/zones';
  const API_ADMINS = '/api/admin/users/';

  let zones = [];
  let admins = [];
  let isLoading = false;

  /**
   * Показать уведомление. Использует глобальный объект notify, если он определён,
   * затем fallback на showToast, затем на alert/console. Такая унификация
   * позволяет централизованно контролировать стиль уведомлений.
   *
   * @param {string} msg  Сообщение
   * @param {string} type Тип: 'success', 'error' или 'info'
   */
  function toast(msg, type) {
    if (window.notify && typeof window.notify[type] === 'function') {
      window.notify[type](msg);
      return;
    }
    if (typeof window.showToast === 'function') {
      window.showToast(msg, type);
      return;
    }
    console[type === 'error' ? 'error' : 'log'](msg);
    if (type === 'error') {
      alert(msg);
    }
  }

  function esc(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function getAdminsForZone(zoneId) {
    const res = [];
    admins.forEach(a => {
      if (Array.isArray(a.zones) && a.zones.includes(zoneId)) {
        res.push(a.username);
      }
    });
    return res;
  }

  function renderZones() {
    const root = document.getElementById('zones-root');
    if (!root) return;

    if (isLoading) {
      root.innerHTML = '<div class="muted">Загрузка зон...</div>';
      return;
    }

    const rows = zones.map(z => {
      const adminList = getAdminsForZone(z.id);
      const adminsText = adminList.length
        ? adminList.join(', ')
        : '—';

      const colorSwatch = z.color || '#ffcc00';
      const iconName = z.icon || 'beer';

      return `
        <tr data-id="${z.id}">
          <td>#${z.id}</td>
          <td>${esc(z.description || '')}</td>
          <td>
            <span class="zone-color-swatch" style="display:inline-block;width:18px;height:18px;border-radius:4px;border:1px solid #ccc;background:${esc(colorSwatch)};"></span>
            <span style="margin-left:6px;">${esc(colorSwatch)}</span>
          </td>
          <td>${esc(iconName)}</td>
          <td>${adminsText}</td>
          <td class="zones-actions-cell">
            <button class="btn minimal zones-focus" data-id="${z.id}">На&nbsp;карте</button>
            <button class="btn minimal zones-edit" data-id="${z.id}">Редактировать</button>
            <button class="btn minimal danger zones-delete" data-id="${z.id}">Удалить</button>
          </td>
        </tr>
      `;
    }).join('');

    root.innerHTML = `
      <div class="zones-toolbar">
        <button id="zones-refresh" class="btn">Обновить</button>
        <button id="zones-create-hint" class="btn primary">Создать зону</button>
      </div>
      <div class="zones-table-wrap">
        <table class="zones-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Описание</th>
              <th>Цвет</th>
              <th>Значок</th>
              <th>Администраторы</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            ${rows || '<tr><td colspan="6" class="muted" style="text-align:center;">Зоны пока не созданы</td></tr>'}
          </tbody>
        </table>
      </div>
      <div id="zones-form"></div>
      <div class="zones-hint">
        <p class="muted" style="font-size:13px;line-height:1.4;">
          Геометрию зон рисуем на карте (режим рисования + модалка «Зона»).
          Здесь можно посмотреть зоны, отцентрировать на них карту,
          отредактировать описание/цвет/значок и удалить зону.
        </p>
      </div>
    `;

    const btnRefresh = document.getElementById('zones-refresh');
    if (btnRefresh && !btnRefresh.dataset.bound) {
      btnRefresh.dataset.bound = '1';
      btnRefresh.addEventListener('click', () => {
        loadZonesData();
      });
    }

    const btnCreate = document.getElementById('zones-create-hint');
    if (btnCreate && !btnCreate.dataset.bound) {
      btnCreate.dataset.bound = '1';
      btnCreate.addEventListener('click', () => {
        closeZonesModal();
        toast(
          'Чтобы создать зону: включите режим рисования зоны на карте, обведите область и сохраните через модалку «Зона». После этого зона появится в списке.',
          'info'
        );
      });
    }

    const tbody = root.querySelector('tbody');
    if (tbody && !tbody.dataset.bound) {
      tbody.dataset.bound = '1';
      tbody.addEventListener('click', async (e) => {
        const focusBtn = e.target.closest('.zones-focus');
        const editBtn = e.target.closest('.zones-edit');
        const delBtn = e.target.closest('.zones-delete');
        if (focusBtn) {
          const id = Number(focusBtn.dataset.id);
          focusZoneOnMap(id);
        } else if (editBtn) {
          const id = Number(editBtn.dataset.id);
          const zone = zones.find(z => z.id === id);
          if (zone) openEditForm(zone);
        } else if (delBtn) {
          const id = Number(delBtn.dataset.id);
          await deleteZone(id);
        }
      });
    }
  }

  function openEditForm(zone) {
    const formWrap = document.getElementById('zones-form');
    if (!formWrap) return;

    const icon = zone.icon || 'beer';
    const color = zone.color || '#ffcc00';
    const desc = zone.description || '';

    formWrap.innerHTML = `
      <div class="zones-form-card">
        <h4>Редактировать зону #${zone.id}</h4>
        <div class="form-row">
          <label>Описание</label>
          <input id="zone-form-desc" class="input" type="text" value="${esc(desc)}" placeholder="Описание зоны">
        </div>
        <div class="form-row">
          <label>Цвет</label>
          <input id="zone-form-color" class="input" type="color" value="${esc(color)}">
        </div>
        <div class="form-row">
          <label>Значок</label>
          <select id="zone-form-icon" class="input">
            <option value="beer" ${icon === 'beer' ? 'selected' : ''}>🍺 beer</option>
            <option value="car-crash" ${icon === 'car-crash' ? 'selected' : ''}>🚗💥 car-crash</option>
            <option value="user-secret" ${icon === 'user-secret' ? 'selected' : ''}>🕵️ user-secret</option>
            <option value="gavel" ${icon === 'gavel' ? 'selected' : ''}>⚖️ gavel</option>
            <option value="exclamation-triangle" ${icon === 'exclamation-triangle' ? 'selected' : ''}>⚠️ exclamation-triangle</option>
          </select>
        </div>
        <div class="form-actions">
          <button id="zone-form-save" class="btn primary">Сохранить</button>
          <button id="zone-form-cancel" class="btn">Отмена</button>
        </div>
      </div>
    `;

    const btnSave = document.getElementById('zone-form-save');
    const btnCancel = document.getElementById('zone-form-cancel');

    // Привязываем закрытие формы через bindOnce, если доступен
    if (btnCancel) {
      if (typeof window.bindOnce === 'function') {
        window.bindOnce(btnCancel, 'click', () => {
          formWrap.innerHTML = '';
        }, 'ZoneCancel');
      } else if (!btnCancel.dataset.bound) {
        btnCancel.dataset.bound = '1';
        btnCancel.addEventListener('click', () => {
          formWrap.innerHTML = '';
        });
      }
    }

    if (btnSave) {
      if (typeof window.bindOnce === 'function') {
        window.bindOnce(btnSave, 'click', async () => {
          const descInput = document.getElementById('zone-form-desc');
          const colorInput = document.getElementById('zone-form-color');
          const iconInput = document.getElementById('zone-form-icon');

          const newDesc = descInput ? descInput.value.trim() : '';
          const newColor = colorInput ? colorInput.value : color;
          const newIcon = iconInput ? iconInput.value : icon;

          const payload = {
            description: newDesc,
            color: newColor,
            icon: newIcon,
          };

          // Стараемся не трогать геометрию: если backend требует geometry,
          // берём либо из zone.geometry, либо из карты.
          let geom = zone.geometry || null;
          if (!geom) {
            try {
              const polyMap = window.zonePolygonMap || {};
              const layer = polyMap[zone.id];
              if (layer && typeof layer.getLatLngs === 'function') {
                const arr = layer.getLatLngs()[0] || [];
                const latlngs = arr.map(p => ({ lat: p.lat, lng: p.lng }));
                geom = { latlngs };
              }
            } catch (e) {
              console.warn('failed to reconstruct geometry for zone', zone.id, e);
            }
          }
          if (geom) payload.geometry = geom;

          try {
            const resp = await fetch(`${API_ZONES}/${zone.id}`, {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload),
            });
            if (!resp.ok) {
              let data = null;
              try { data = await resp.json(); } catch (_) {}
              const msg = (data && data.error) || 'Не удалось обновить зону';
              toast(msg, 'error');
              return;
            }
            // Локально обновляем зону
            zone.description = newDesc;
            zone.color = newColor;
            zone.icon = newIcon;

            // Обновляем отображение на карте, если есть полигон/маркер
            try {
              const polyMap = window.zonePolygonMap || {};
              const markMap = window.zoneMarkerMap || {};
              const layer = polyMap[zone.id];
              const marker = markMap[zone.id];

              if (layer && layer.setStyle) {
                layer.setStyle({ color: '#000000', weight: 2, fillColor: newColor, fillOpacity: 0.15 });
                if (newDesc && layer.bindPopup) {
                  layer.bindPopup(esc(newDesc));
                }
                layer.iconName = newIcon;
              }
              if (marker) {
                marker.iconName = newIcon;
                // Обновлять сам HTML иконки не будем, он обновится при перезагрузке карты / зон.
              }
            } catch (e) {
              console.warn('zones: failed to update map layer for zone', zone.id, e);
            }

            toast('Зона обновлена', 'success');
            formWrap.innerHTML = '';
            renderZones();
          } catch (err) {
            console.error('zones: update zone error', err);
            toast('Ошибка при обновлении зоны', 'error');
          }
        }, 'ZoneSave');
      } else if (!btnSave.dataset.bound) {
        btnSave.dataset.bound = '1';
        btnSave.addEventListener('click', async () => {
          const descInput = document.getElementById('zone-form-desc');
          const colorInput = document.getElementById('zone-form-color');
          const iconInput = document.getElementById('zone-form-icon');

          const newDesc = descInput ? descInput.value.trim() : '';
          const newColor = colorInput ? colorInput.value : color;
          const newIcon = iconInput ? iconInput.value : icon;

          const payload = {
            description: newDesc,
            color: newColor,
            icon: newIcon,
          };

          // Стараемся не трогать геометрию: если backend требует geometry,
          // берём либо из zone.geometry, либо из карты.
          let geom = zone.geometry || null;
          if (!geom) {
            try {
              const polyMap = window.zonePolygonMap || {};
              const layer = polyMap[zone.id];
              if (layer && typeof layer.getLatLngs === 'function') {
                const arr = layer.getLatLngs()[0] || [];
                const latlngs = arr.map(p => ({ lat: p.lat, lng: p.lng }));
                geom = { latlngs };
              }
            } catch (e) {
              console.warn('failed to reconstruct geometry for zone', zone.id, e);
            }
          }
          if (geom) payload.geometry = geom;

          try {
            const resp = await fetch(`${API_ZONES}/${zone.id}`, {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload),
            });
            if (!resp.ok) {
              let data = null;
              try { data = await resp.json(); } catch (_) {}
              const msg = (data && data.error) || 'Не удалось обновить зону';
              toast(msg, 'error');
              return;
            }
            // Локально обновляем зону
            zone.description = newDesc;
            zone.color = newColor;
            zone.icon = newIcon;

            // Обновляем отображение на карте, если есть полигон/маркер
            try {
              const polyMap = window.zonePolygonMap || {};
              const markMap = window.zoneMarkerMap || {};
              const layer = polyMap[zone.id];
              const marker = markMap[zone.id];

              if (layer && layer.setStyle) {
                layer.setStyle({ color: '#000000', weight: 2, fillColor: newColor, fillOpacity: 0.15 });
                if (newDesc && layer.bindPopup) {
                  layer.bindPopup(esc(newDesc));
                }
                layer.iconName = newIcon;
              }
              if (marker) {
                marker.iconName = newIcon;
                // Обновлять сам HTML иконки не будем, он обновится при перезагрузке карты / зон.
              }
            } catch (e) {
              console.warn('zones: failed to update map layer for zone', zone.id, e);
            }

            toast('Зона обновлена', 'success');
            formWrap.innerHTML = '';
            renderZones();
          } catch (err) {
            console.error('zones: update zone error', err);
            toast('Ошибка при обновлении зоны', 'error');
          }
        });
      }
    }
  }

  function focusZoneOnMap(zoneId) {
    try {
      const polyMap = window.zonePolygonMap || {};
      const markMap = window.zoneMarkerMap || {};
      const poly = polyMap[zoneId];
      const marker = markMap[zoneId];
      const map = window.map;

      if (!map) return;

      if (poly && typeof poly.getBounds === 'function') {
        const bounds = poly.getBounds();
        map.fitBounds(bounds, { padding: [40, 40] });
        if (poly.openPopup) poly.openPopup();
      } else if (marker && marker.getLatLng) {
        const currentZoom = map.getZoom ? map.getZoom() : 15;
        const targetZoom = Math.max(currentZoom || 15, 15);
        map.setView(marker.getLatLng(), targetZoom);
        if (marker.openPopup) marker.openPopup();
      }
    } catch (err) {
      console.error('focusZoneOnMap error', err);
    }
  }

  async function deleteZone(zoneId) {
    if (!zoneId) return;
    if (!confirm('Удалить эту зону? Действие необратимо.')) return;
    try {
      if (typeof window.deleteZoneFromServer === 'function') {
        await window.deleteZoneFromServer(zoneId);
      } else {
        await fetch(`${API_ZONES}/${zoneId}`, { method: 'DELETE' });
        toast('Зона удалена', 'success');
      }

      zones = zones.filter(z => z.id !== zoneId);

      try {
        const polyMap = window.zonePolygonMap || {};
        const markMap = window.zoneMarkerMap || {};
        const poly = polyMap[zoneId];
        const marker = markMap[zoneId];
        const zonesLayer = window.zonesLayer;

        if (zonesLayer && poly && zonesLayer.removeLayer) zonesLayer.removeLayer(poly);
        if (zonesLayer && marker && zonesLayer.removeLayer) zonesLayer.removeLayer(marker);

        delete polyMap[zoneId];
        delete markMap[zoneId];
      } catch (e) {
        console.warn('zonesLayer cleanup failed', e);
      }

      renderZones();
    } catch (err) {
      console.error('deleteZone error', err);
      toast('Ошибка удаления зоны', 'error');
    }
  }

  async function loadZonesData() {
    const root = document.getElementById('zones-root');
    if (!root) return;
    isLoading = true;
    renderZones();
    try {
      const [zonesResp, adminsResp] = await Promise.all([
        fetch(API_ZONES),
        fetch(API_ADMINS),
      ]);
      if (!zonesResp.ok) throw new Error('zones load failed');
      zones = await zonesResp.json();

      if (adminsResp.ok) {
        admins = await adminsResp.json();
      } else {
        admins = [];
      }
    } catch (err) {
      console.error('loadZonesData error', err);
      toast('Не удалось загрузить зоны или админов', 'error');
    } finally {
      isLoading = false;
      renderZones();
    }
  }

  function openZonesModal() {
    const backdrop = document.getElementById('zones-backdrop');
    if (!backdrop) return;
    backdrop.style.display = 'flex';
    backdrop.classList.add('open');
    loadZonesData();
  }

  function closeZonesModal() {
    const backdrop = document.getElementById('zones-backdrop');
    if (!backdrop) return;
    backdrop.classList.remove('open');
    backdrop.style.display = 'none';
    const root = document.getElementById('zones-root');
    if (root) root.innerHTML = '';
  }

  function bindZonesUI() {
    const btn = document.getElementById('btn-zones');
    if (btn && !btn.dataset.bound) {
      btn.dataset.bound = '1';
      btn.addEventListener('click', openZonesModal);
    }

    const backdrop = document.getElementById('zones-backdrop');
    const closeBtn = document.getElementById('zones-close');

    if (backdrop && !backdrop.dataset.bound) {
      backdrop.dataset.bound = '1';
      backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) closeZonesModal();
      });
    }

    if (closeBtn && !closeBtn.dataset.bound) {
      closeBtn.dataset.bound = '1';
      closeBtn.addEventListener('click', closeZonesModal);
    }
  }

  document.addEventListener('DOMContentLoaded', bindZonesUI);
})();
