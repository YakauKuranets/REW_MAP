/* ========= Chat2: список каналов ========= */
/**
 * Этот модуль реализует модальное окно со списком каналов для нового
 * событийного чата (chat2). Он показывает все каналы администратора,
 * отображает количество непрочитанных сообщений и позволяет открыть
 * чат по смене одним кликом. В будущем можно добавить поддержку
 * incident/dm-каналов, поиск, фильтры и тёмную тему.
 */

(function () {
  // DOM элементы
  let backdrop;
  let listContainer;
  let closeBtn;

  // Поле поиска, флаг фильтра "только непрочитанные" и кэшированный список каналов
  let searchInput;
  let filterUnread;
  let cachedChannels = [];

  /**
   * Получить список каналов для администратора.
   * Возвращает массив объектов: {id, type, shift_id, marker_id, preview, unread}
   */
  async function fetchChannels() {
    try {
      const resp = await fetch('/api/chat2/channels');
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      return Array.isArray(data) ? data : [];
    } catch (err) {
      console.warn('Failed to fetch chat channels', err);
      return [];
    }
  }

  /**
   * Отобразить список каналов.
   * @param {Array} items
   */
  function renderList(items) {
    if (!listContainer) return;
    listContainer.innerHTML = '';
    if (!Array.isArray(items) || !items.length) {
      const p = document.createElement('div');
      p.className = 'chat2-channel-empty';
      p.textContent = 'Нет чатов';
      listContainer.appendChild(p);
      return;
    }
    // Группируем каналы по типу
    const groups = {
      shift: [],
      incident: [],
      dm: [],
      other: [],
    };
    items.forEach((ch) => {
      if (ch.type === 'shift') groups.shift.push(ch);
      else if (ch.type === 'incident') groups.incident.push(ch);
      else if (ch.type === 'dm') groups.dm.push(ch);
      else groups.other.push(ch);
    });
    const order = ['shift', 'incident', 'dm', 'other'];
    const titles = {
      shift: 'Смены',
      incident: 'Инциденты',
      dm: 'Support',
      other: 'Прочие',
    };
    order.forEach((key) => {
      let arr = groups[key];
      if (!arr || arr.length === 0) return;
      // Сортируем каналы внутри группы: сначала по числу непрочитанных (desc), затем по времени последнего сообщения (desc)
      arr = arr.slice().sort((a, b) => {
        const ua = a.unread || 0;
        const ub = b.unread || 0;
        if (ua !== ub) return ub - ua;
        // Сравниваем по last_message_at (ISO)
        const ta = a.last_message_at ? Date.parse(a.last_message_at) : 0;
        const tb = b.last_message_at ? Date.parse(b.last_message_at) : 0;
        return tb - ta;
      });
      // Заголовок группы
      const h = document.createElement('div');
      h.className = 'chat2-channel-group';
      h.innerHTML = `<strong>${titles[key]}</strong>`;
      h.style.marginTop = '8px';
      listContainer.appendChild(h);
      arr.forEach((ch) => {
        const div = document.createElement('div');
        div.className = 'chat2-channel-item';
        // Название канала
        let label = '';
        if (ch.type === 'shift' && ch.shift_id != null) {
          label = `Смена #${ch.shift_id}`;
        } else if (ch.type === 'incident' && ch.marker_id != null) {
          label = `Инцидент #${ch.marker_id}`;
        } else if (ch.type === 'dm') {
          label = 'Support';
        } else {
          label = ch.id || '(канал)';
        }
        // Превью текста
        let preview = ch.preview || '';
        if (typeof preview === 'string' && preview.length > 40) {
          preview = preview.slice(0, 40) + '…';
        }
        div.innerHTML = `<strong>${label}</strong><br><small class="muted">${escapeHtml(preview || '')}</small>`;
        // Бейдж непрочитанных
        if (ch.unread && ch.unread > 0) {
          const badge = document.createElement('span');
          badge.className = 'ap-badge red';
          badge.textContent = ch.unread;
          badge.style.marginLeft = '6px';
          div.appendChild(badge);
        }
        div.addEventListener('click', () => {
          try {
            if (ch.type === 'shift' && ch.shift_id != null) {
              if (typeof window.chat2OpenForShift === 'function') {
                window.chat2OpenForShift(ch.shift_id);
              }
            } else {
              const title = (ch.type === 'incident' && ch.marker_id != null)
                ? `Инцидент #${ch.marker_id}`
                : (ch.type === 'dm' ? 'Support' : `Канал ${ch.id}`);
              if (typeof window.chat2OpenChannel === 'function') {
                window.chat2OpenChannel(ch.id, title);
              }
            }
          } catch (_e) {
            console.warn('Failed to open channel', _e);
          }
          closeList();
        });
        listContainer.appendChild(div);
      });
    });
  }

  /**
   * Открыть список чатов. Загружает данные и отображает модалку.
   */
  async function openList() {
    if (!backdrop) return;
    backdrop.style.display = 'flex';
    backdrop.classList.add('open');
    // загружаем список
    const channels = await fetchChannels();
    cachedChannels = Array.isArray(channels) ? channels : [];
    // при открытии очищаем поле поиска
    if (searchInput) searchInput.value = '';
    renderList(cachedChannels);
  }

  /** Закрыть модальное окно со списком чатов */
  function closeList() {
    if (!backdrop) return;
    backdrop.classList.remove('open');
    backdrop.style.display = 'none';
    // очищаем список
    if (listContainer) listContainer.innerHTML = '';
  }

  /** Инициализировать DOM-ссылки и обработчики */
  function initList() {
    backdrop = document.getElementById('chat2-list-backdrop');
    listContainer = document.getElementById('chat2-channel-list');
    closeBtn = document.getElementById('chat2-list-close');
    searchInput = document.getElementById('chat2-search');
    filterUnread = document.getElementById('chat2-filter-unread');
    if (!backdrop) return;
    // Закрытие по клику на фон
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) closeList();
    });
    if (closeBtn) {
      closeBtn.addEventListener('click', () => closeList());
    }
    // Обработчик поиска: фильтрует каналы по имени или превью
    if (searchInput) {
      searchInput.addEventListener('input', () => {
        const q = String(searchInput.value || '').trim().toLowerCase();
        // Фильтрация: сначала по чекбоксу "только непрочитанные"
        const base = cachedChannels.filter((ch) => {
          if (filterUnread && filterUnread.checked && (!ch.unread || ch.unread <= 0)) return false;
          return true;
        });
        if (!q) {
          renderList(base);
          return;
        }
        const filtered = base.filter((ch) => {
          // Формируем строку поиска: название и превью
          let label = '';
          if (ch.type === 'shift' && ch.shift_id != null) label = `Смена #${ch.shift_id}`;
          else if (ch.type === 'incident' && ch.marker_id != null) label = `Инцидент #${ch.marker_id}`;
          else if (ch.type === 'dm') label = 'Support';
          else label = String(ch.id || '');
          const preview = String(ch.preview || '');
          const haystack = (label + ' ' + preview).toLowerCase();
          return haystack.includes(q);
        });
        renderList(filtered);
      });
    }
    // Обработчик для фильтра "только непрочитанные": когда пользователь отмечает чекбокс, пересчитываем список
    if (filterUnread) {
      filterUnread.addEventListener('change', () => {
        const q = String(searchInput?.value || '').trim().toLowerCase();
        // Применяем фильтрацию аналогично обработчику поиска
        const base = cachedChannels.filter((ch) => {
          if (filterUnread.checked && (!ch.unread || ch.unread <= 0)) return false;
          return true;
        });
        if (!q) {
          renderList(base);
          return;
        }
        const filtered = base.filter((ch) => {
          let label = '';
          if (ch.type === 'shift' && ch.shift_id != null) label = `Смена #${ch.shift_id}`;
          else if (ch.type === 'incident' && ch.marker_id != null) label = `Инцидент #${ch.marker_id}`;
          else if (ch.type === 'dm') label = 'Support';
          else label = String(ch.id || '');
          const preview = String(ch.preview || '');
          const haystack = (label + ' ' + preview).toLowerCase();
          return haystack.includes(q);
        });
        renderList(filtered);
      });
    }
  }

  // Инициализация при загрузке DOM
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initList);
  } else {
    initList();
  }

  // Экспортируем глобальную функцию
  window.chat2OpenList = openList;
})();