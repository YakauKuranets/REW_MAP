/* ========= Admin Users UI (superadmin only) ========= */
/**
 * Модуль управления администраторами (AdminUser).
 *
 * Зависимости:
 *  - /api/admin/users  (REST API для админов)
 *  - /zones            (список зон для привязки)
 *  - глобальная функция showToast(msg, type) — опционально
 */
(function() {
  const API_USERS = '/api/admin/users';
  const API_ZONES = '/zones';

  let admins = [];
  let zones = [];
  let isLoading = false;

  /**
   * Унифицированный способ показать уведомление. Сначала пытается
   * воспользоваться глобальным объектом notify (см. notify.js), затем
   * fallback на showToast, затем на alert/console. Это позволяет
   * централизованно управлять стилем уведомлений и избегать прямых
   * вызовов alert().
   *
   * @param {string} msg  Сообщение пользователю
   * @param {string} type Тип: 'success', 'error' или 'info'
   */
  function safeToast(msg, type) {
    if (window.notify && typeof window.notify[type] === 'function') {
      window.notify[type](msg);
      return;
    }
    if (typeof window.showToast === 'function') {
      window.showToast(msg, type);
      return;
    }
    // Последняя защита: выводим в консоль, и для ошибок применяем alert
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

  function translateRole(role) {
    switch (role) {
      case 'viewer': return 'Наблюдатель';
      case 'editor': return 'Редактор';
      case 'superadmin': return 'Супер‑админ';
      default: return role || '—';
    }
  }

  function getZoneById(id) {
    return zones.find(z => z.id === id) || null;
  }

  function renderAdminList() {
    const root = document.getElementById('admin-users-root');
    if (!root) return;

    if (isLoading) {
      root.innerHTML = '<div class="muted">Загрузка...</div>';
      return;
    }

    const zoneOptions = zones
      .map(z => `<option value="${z.id}">${esc(z.description || ('Зона #' + z.id))}</option>`)
      .join('');

    const rows = admins.map(a => {
      const zoneNames = (a.zones || [])
        .map(id => {
          const z = getZoneById(id);
          return z ? (z.description || ('Зона #' + z.id)) : ('#' + id);
        })
        .join(', ') || '—';

      const status = a.is_active ? 'Активен' : 'Отключён';
      const created = a.created_at ? esc(a.created_at.replace('T', ' ').slice(0, 19)) : '';

      return `
        <tr data-id="${a.id}">
          <td>${esc(a.username)}</td>
          <td>${esc(translateRole(a.role))}</td>
          <td>${esc(status)}</td>
          <td>${esc(zoneNames)}</td>
          <td>${created}</td>
          <td>
            <button class="btn minimal admin-edit" data-id="${a.id}">Редактировать</button>
          </td>
        </tr>
      `;
    }).join('');

    root.innerHTML = `
      <div class="admin-users-toolbar">
        <button id="admin-create-btn" class="btn primary">Создать администратора</button>
      </div>
      <div class="admin-users-table-wrap">
        <table class="admin-users-table">
          <thead>
            <tr>
              <th>Логин</th>
              <th>Роль</th>
              <th>Статус</th>
              <th>Зоны</th>
              <th>Создан</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            ${rows || '<tr><td colspan="6" class="muted" style="text-align:center;">Пока нет администраторов</td></tr>'}
          </tbody>
        </table>
      </div>
      <div id="admin-users-form"></div>
    `;

    // Навешиваем обработчики (через делегирование)
    const tbody = root.querySelector('tbody');
    if (tbody) {
      const handler = (e) => {
        const btn = e.target.closest('.admin-edit');
        if (!btn) return;
        const id = Number(btn.dataset.id);
        const admin = admins.find(a => a.id === id);
        if (admin) {
          openEditForm(admin, zoneOptions);
        }
      };
      if (typeof window.bindOnce === 'function') {
        window.bindOnce(tbody, 'click', handler);
      } else if (!tbody.dataset.bound) {
        tbody.dataset.bound = '1';
        tbody.addEventListener('click', handler);
      }
    }

    const createBtn = document.getElementById('admin-create-btn');
    if (createBtn) {
      const handler = () => openCreateForm(zoneOptions);
      if (typeof window.bindOnce === 'function') {
        window.bindOnce(createBtn, 'click', handler);
      } else if (!createBtn.dataset.bound) {
        createBtn.dataset.bound = '1';
        createBtn.addEventListener('click', handler);
      }
    }
  }

  function openCreateForm(zoneOptionsHtml) {
    const formWrap = document.getElementById('admin-users-form');
    if (!formWrap) return;

    formWrap.innerHTML = `
      <div class="admin-users-form-card">
        <h4>Создать администратора</h4>
        <div class="form-row">
          <label>Логин</label>
          <input id="admin-form-username" class="input" placeholder="username">
        </div>
        <div class="form-row">
          <label>Пароль</label>
          <input id="admin-form-password" class="input" type="password" placeholder="Пароль">
        </div>
        <div class="form-row">
          <label>Роль</label>
          <select id="admin-form-role" class="input">
            <option value="viewer">Наблюдатель</option>
            <option value="editor" selected>Редактор</option>
            <option value="superadmin">Супер-админ</option>
          </select>
        </div>
        <div class="form-row">
          <label>Зоны (опционально)</label>
          <select id="admin-form-zones" class="input" multiple size="5">
            ${zoneOptionsHtml}
          </select>
        </div>
        <div class="form-actions">
          <button id="admin-form-save" class="btn primary">Сохранить</button>
          <button id="admin-form-cancel" class="btn">Отмена</button>
        </div>
      </div>
    `;

    const saveBtn = document.getElementById('admin-form-save');
    const cancelBtn = document.getElementById('admin-form-cancel');

    if (cancelBtn) {
      const handler = () => {
        formWrap.innerHTML = '';
      };
      if (typeof window.bindOnce === 'function') {
        window.bindOnce(cancelBtn, 'click', handler);
      } else if (!cancelBtn.dataset.bound) {
        cancelBtn.dataset.bound = '1';
        cancelBtn.addEventListener('click', handler);
      }
    }

    if (saveBtn) {
      const handler = async () => {
        const usernameInput = document.getElementById('admin-form-username');
        const passwordInput = document.getElementById('admin-form-password');
        const roleInput = document.getElementById('admin-form-role');
        const zonesSelect = document.getElementById('admin-form-zones');

        const username = usernameInput ? usernameInput.value.trim() : '';
        const password = passwordInput ? passwordInput.value : '';
        const role = roleInput ? roleInput.value : 'editor';

        const zonesIds = [];
        if (zonesSelect) {
          for (const opt of zonesSelect.options) {
            if (opt.selected) zonesIds.push(Number(opt.value));
          }
        }

        if (!username || !password) {
          safeToast('Логин и пароль обязательны', 'error');
          return;
        }

        try {
          const resp = await fetch(API_USERS + '/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, role, zones: zonesIds }),
          });
          if (!resp.ok) {
            const data = await resp.json().catch(() => ({}));
            const msg = (data && data.error) || 'Не удалось создать администратора';
            safeToast(msg, 'error');
            return;
          }
          const newAdmin = await resp.json();
          admins.push(newAdmin);
          safeToast('Администратор создан', 'success');
          formWrap.innerHTML = '';
          renderAdminList();
        } catch (err) {
          console.error(err);
          safeToast('Ошибка при создании администратора', 'error');
        }
      };
      if (typeof window.bindOnce === 'function') {
        window.bindOnce(saveBtn, 'click', handler);
      } else if (!saveBtn.dataset.bound) {
        saveBtn.dataset.bound = '1';
        saveBtn.addEventListener('click', handler);
      }
    }
  }


  function openEditForm(admin, zoneOptionsHtml) {
    const formWrap = document.getElementById('admin-users-form');
    if (!formWrap) return;

    const selectedZones = new Set((admin.zones || []).map(Number));

    const zoneOptions = zones
      .map(z => `<option value="${z.id}" ${selectedZones.has(z.id) ? 'selected' : ''}>${esc(z.description || ('Зона #' + z.id))}</option>`)
      .join('');

    formWrap.innerHTML = `
      <div class="admin-users-form-card">
        <h4>Редактировать: ${esc(admin.username)}</h4>
        <div class="form-row">
          <label>Логин</label>
          <input class="input" value="${esc(admin.username)}" disabled>
        </div>
        <div class="form-row">
          <label>Роль</label>
          <select id="admin-form-role" class="input">
            <option value="viewer" ${admin.role === 'viewer' ? 'selected' : ''}>Наблюдатель</option>
            <option value="editor" ${admin.role === 'editor' ? 'selected' : ''}>Редактор</option>
            <option value="superadmin" ${admin.role === 'superadmin' ? 'selected' : ''}>Супер‑админ</option>
          </select>
        </div>
        <div class="form-row">
          <label>Статус</label>
          <label style="display:flex;align-items:center;gap:6px;">
            <input id="admin-form-active" type="checkbox" ${admin.is_active ? 'checked' : ''}>
            Активен
          </label>
        </div>
        <div class="form-row">
          <label>Новый пароль (опционально)</label>
          <input id="admin-form-password" class="input" type="password" placeholder="Оставьте пустым, чтобы не менять">
        </div>
        <div class="form-row">
          <label>Зоны</label>
          <select id="admin-form-zones" class="input" multiple size="5">
            ${zoneOptions}
          </select>
        </div>
        <div class="form-actions">
          <button id="admin-form-save" class="btn primary">Сохранить</button>
          <button id="admin-form-cancel" class="btn">Отмена</button>
          <button id="admin-form-delete" class="btn danger" style="margin-left:auto;">Удалить</button>
        </div>
      </div>
    `;

    const cancelBtn = document.getElementById('admin-form-cancel');
    const saveBtn = document.getElementById('admin-form-save');
    const deleteBtn = document.getElementById('admin-form-delete');

    // Cancel button handler
    if (cancelBtn) {
      const handler = () => {
        formWrap.innerHTML = '';
      };
      if (typeof window.bindOnce === 'function') {
        window.bindOnce(cancelBtn, 'click', handler);
      } else if (!cancelBtn.dataset.bound) {
        cancelBtn.dataset.bound = '1';
        cancelBtn.addEventListener('click', handler);
      }
    }

    // Save button handler
    if (saveBtn) {
      const handler = async () => {
        const roleInput = document.getElementById('admin-form-role');
        const activeInput = document.getElementById('admin-form-active');
        const passwordInput = document.getElementById('admin-form-password');
        const zonesSelect = document.getElementById('admin-form-zones');

        const role = roleInput ? roleInput.value : admin.role;
        const is_active = activeInput ? !!activeInput.checked : admin.is_active;
        const password = passwordInput ? passwordInput.value : '';
        const zonesIds = [];
        if (zonesSelect) {
          for (const opt of zonesSelect.options) {
            if (opt.selected) zonesIds.push(Number(opt.value));
          }
        }

        const payload = { role, is_active, zones: zonesIds };
        if (password) payload.password = password;

        try {
          const resp = await fetch(`${API_USERS}/${admin.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
          if (!resp.ok) {
            const data = await resp.json().catch(() => ({}));
            const msg = (data && data.error) || 'Не удалось обновить администратора';
            safeToast(msg, 'error');
            return;
          }
          const updated = await resp.json();
          const idx = admins.findIndex(a => a.id === admin.id);
          if (idx !== -1) admins[idx] = updated;
          safeToast('Изменения сохранены', 'success');
          formWrap.innerHTML = '';
          renderAdminList();
        } catch (err) {
          console.error(err);
          safeToast('Ошибка при сохранении администратора', 'error');
        }
      };
      if (typeof window.bindOnce === 'function') {
        window.bindOnce(saveBtn, 'click', handler);
      } else if (!saveBtn.dataset.bound) {
        saveBtn.dataset.bound = '1';
        saveBtn.addEventListener('click', handler);
      }
    }

    // Delete button handler
    if (deleteBtn) {
      const handler = async () => {
        if (!confirm('Удалить администратора? Это действие необратимо.')) return;
        try {
          const resp = await fetch(`${API_USERS}/${admin.id}`, { method: 'DELETE' });
          if (!resp.ok) {
            const data = await resp.json().catch(() => ({}));
            const msg = (data && data.error) || 'Не удалось удалить администратора';
            safeToast(msg, 'error');
            return;
          }
          admins = admins.filter(a => a.id !== admin.id);
          formWrap.innerHTML = '';
          renderAdminList();
          safeToast('Администратор удалён', 'success');
        } catch (err) {
          console.error(err);
          safeToast('Ошибка при удалении администратора', 'error');
        }
      };
      if (typeof window.bindOnce === 'function') {
        window.bindOnce(deleteBtn, 'click', handler);
      } else if (!deleteBtn.dataset.bound) {
        deleteBtn.dataset.bound = '1';
        deleteBtn.addEventListener('click', handler);
      }
    }
  }

  async function loadDataAndRender() {
    const root = document.getElementById('admin-users-root');
    if (!root) return;
    isLoading = true;
    renderAdminList();
    try {
      const [adminsResp, zonesResp] = await Promise.all([
        fetch(API_USERS + '/'),
        fetch(API_ZONES),
      ]);
      if (!adminsResp.ok) throw new Error('admins load failed');
      if (!zonesResp.ok) throw new Error('zones load failed');
      admins = await adminsResp.json();
      zones = await zonesResp.json();
    } catch (err) {
      console.error(err);
      safeToast('Не удалось загрузить администраторов или зоны', 'error');
    } finally {
      isLoading = false;
      renderAdminList();
    }
  }

  function openAdminUsersModal() {
    const backdrop = document.getElementById('admin-users-backdrop');
    if (!backdrop) {
      console.warn('admin-users-backdrop not found');
      return;
    }
    backdrop.style.display = 'flex';
    backdrop.classList.add('open');
    loadDataAndRender();
  }

  function closeAdminUsersModal() {
    const backdrop = document.getElementById('admin-users-backdrop');
    if (!backdrop) return;
    backdrop.classList.remove('open');
    backdrop.style.display = 'none';
    const root = document.getElementById('admin-users-root');
    if (root) root.innerHTML = '';
    const formWrap = document.getElementById('admin-users-form');
    if (formWrap) formWrap.innerHTML = '';
  }

  function bindAdminUsersUI() {
    const btn = document.getElementById('btn-admin-users');
    if (btn && !btn.dataset.bound) {
      btn.dataset.bound = '1';
      btn.addEventListener('click', openAdminUsersModal);
    }

    const backdrop = document.getElementById('admin-users-backdrop');
    const closeBtn = document.getElementById('admin-users-close');

    if (backdrop && !backdrop.dataset.bound) {
      backdrop.dataset.bound = '1';
      backdrop.addEventListener('click', (e) => {
        if (e.target === backdrop) closeAdminUsersModal();
      });
    }

    if (closeBtn && !closeBtn.dataset.bound) {
      closeBtn.dataset.bound = '1';
      closeBtn.addEventListener('click', closeAdminUsersModal);
    }
  }

  document.addEventListener('DOMContentLoaded', bindAdminUsersUI);
})();
