/* ========= Заявки / уведомления (колокольчик) ========= */
/**
 * Модуль работы с входящими заявками:
 *  - /api/requests/pending
 *  - /api/requests/{id}
 *  - badge колокольчика и выпадающий список
 *
 * Зависимости:
 *  - showToast
 *  - openAdd
 *  - escapeHTML
 *  - CURRENT_REQUEST_ID, _notifOpen (глобалы из main.js)
 */
(function() {
  async function fetchPendingRequests() {
    try {
      const r = await fetch('/api/requests/pending');
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return await r.json();
    } catch (e) {
      console.error('fetchPendingRequests failed', e);
      return [];
    }
  }
  async function refreshNotifCount() {
    try {
      let count = 0;
      const r = await fetch('/api/requests/count');
      if (r.ok) {
        const d = await r.json();
        count = Number(d.count || 0);
      } else {
        const list = await fetchPendingRequests();
        count = Array.isArray(list) ? list.length : 0;
      }
      updateNotifBadge(count);
    } catch (_) {}
  }
  function updateNotifBadge(count) {
    const b = document.getElementById('notif-count');
    if (!b) return;
    if (count > 0) { b.textContent = count; b.classList.remove('hidden'); }
    else { b.textContent = '0'; b.classList.add('hidden'); }
  }

  /* ========= ВАЖНО: Аккуратная отрисовка заявок ========= */
  function renderNotifList(list) {
    const ul = document.getElementById('notif-list');
    const empty = document.querySelector('.notif-empty');
    if (!ul) return;
    ul.innerHTML = '';

    if (!list || !list.length) {
      if (empty) empty.classList.remove('hidden');
      return;
    }
    if (empty) empty.classList.add('hidden');

    list.forEach(req => {
      const li = document.createElement('li');
      li.className = 'notif-item';
      if (req.id != null) li.dataset.id = req.id;

      const title   = escapeHTML(req.title || req.name || req.address || 'Без названия');
      const desc    = escapeHTML(req.description || req.notes || '');
      const surname = (req && req.reporter && req.reporter.surname) ? escapeHTML(req.reporter.surname) : '';
      const category = req.category ? escapeHTML(req.category) : '';
      const status   = req.status ? escapeHTML(req.status) : '';
      let coords  = '';
      if (req.lat != null && req.lon != null) {
        const lat = Number(req.lat), lon = Number(req.lon);
        if (!isNaN(lat) && !isNaN(lon)) coords = `${lat.toFixed(6)}, ${lon.toFixed(6)}`;
      }
      const safeLink = (typeof req.link === 'string') ? req.link : '';

      li.innerHTML = `
        <div class="notif-info">
          <b>${title}</b>
          ${desc      ? `<p style="margin:6px 0 0 0;"><b>Описание:</b> ${desc}</p>` : ''}
          ${surname   ? `<p style="margin:6px 0 0 0;"><b>Инициатор:</b> ${surname}</p>` : ''}
          ${category  ? `<p style="margin:6px 0 0 0;"><b>Категория:</b> ${category}</p>` : ''}
          ${status    ? `<p style="margin:6px 0 0 0;"><b>Доступ:</b> ${status}</p>` : ''}
          ${coords    ? `<p style="margin:6px 0 0 0;"><b>Координаты:</b> ${coords}</p>` : ''}
          ${safeLink  ? `<p style="margin:6px 0 0 0;"><b>Ссылка:</b> <a href="${escapeAttr(safeLink)}" target="_blank" rel="noopener">открыть</a></p>` : ''}
        </div>
        <div class="notif-actions">
          <button class="btn primary" data-act="approve">Подтвердить</button>
          <button class="btn warn" data-act="reject">Отменить</button>
        </div>
      `;

      li.querySelector('[data-act="approve"]').onclick = () => approveRequest(req.id);
      li.querySelector('[data-act="reject"]').onclick = () => rejectRequest(req.id);
      ul.appendChild(li);
    });
  }

  /* ========= Меню уведомлений ========= */
  async function openNotifMenu() {
    const menu = document.getElementById('notif-menu');
    const btn  = document.getElementById('btn-bell');
    if (!menu || !btn) return;

    if (menu.style.display === 'block') {
      menu.style.display = 'none';
      if (menu._restore) {
        const { parent, next } = menu._restore;
        next ? parent.insertBefore(menu, next) : parent.appendChild(menu);
        menu._restore = null;
      }
      _notifOpen = false;
      return;
    }

    try {
      const list = await fetchPendingRequests();
      renderNotifList(list);
      updateNotifBadge(list.length);
    } catch (e) { console.error('openNotifMenu fetch/render failed', e); }

    if (menu.parentElement !== document.body) {
      menu._restore = { parent: menu.parentElement, next: menu.nextSibling };
      document.body.appendChild(menu);
    }
    const r = btn.getBoundingClientRect();
    menu.style.position = 'fixed';
    menu.style.left = Math.round(r.left) + 'px';
    menu.style.top  = Math.round(r.bottom + 6) + 'px';
    menu.style.zIndex = '9999';
    menu.style.display = 'block';
    _notifOpen = true;
  }
  function closeNotifMenuIfOutside(target) {
    const btn = document.getElementById('btn-bell');
    const menu = document.getElementById('notif-menu');
    if (!menu || !btn) return;
    if (_notifOpen && !menu.contains(target) && !btn.contains(target)) {
      menu.style.display = 'none';
      _notifOpen = false;
    }
  }

  /** Отмена заявки */
  async function rejectRequest(id) {
    try {
      const r = await fetch(`/api/requests/${encodeURIComponent(id)}`, { method: 'DELETE' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const li = document.querySelector(`.notif-item[data-id="${id}"]`);
      if (li && li.parentElement) li.parentElement.removeChild(li);
      const left = document.querySelectorAll('.notif-item').length;
      updateNotifBadge(left);
      const empty = document.querySelector('.notif-empty');
      if (left === 0 && empty) empty.classList.remove('hidden');
      showToast('Запрос отклонён', 'success');
    } catch (e) { console.error('rejectRequest failed', e); showToast('Ошибка отклонения запроса', 'error'); }
  }

  /** Подтверждение заявки */
  async function approveRequest(id) {
    try {
      const r = await fetch(`/api/requests/${encodeURIComponent(id)}`);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const req = await r.json();
      const it = {
        id: null,
        name: req.name || req.title || req.address || '',
        address: req.address || req.name || req.title || '',
        lat: (req.lat != null) ? parseFloat(req.lat) : (req.latitude != null ? parseFloat(req.latitude) : ''),
        lon: (req.lon != null) ? parseFloat(req.lon) : (req.longitude != null ? parseFloat(req.longitude) : ''),
        notes: req.notes || req.description || '',
        description: req.description || req.notes || '',
        status: req.status || '',
        link: req.link || '',
        category: req.category || 'Видеонаблюдение'
      };
      openAdd(it);
      CURRENT_REQUEST_ID = id;
    } catch (e) { console.error('approveRequest failed', e); showToast('Не удалось открыть запрос', 'error'); }
  }

  document.addEventListener('DOMContentLoaded', () => {
      // --- Уведомления (заявки) ---
      const btnBell = $('#btn-bell');
      if (btnBell) {
        btnBell.onclick = (e) => {
          e.stopPropagation();
          openNotifMenu();
        };
      }
      if (!window.__notifOutsideBound) {
        document.addEventListener('click', (e) => {
          const btn  = document.getElementById('btn-bell');
          const menu = document.getElementById('notif-menu');
          if (!btn || !menu) return;
          if (btn.contains(e.target) || menu.contains(e.target)) return;
          menu.style.display = 'none';
          _notifOpen = false;
  });
})();
