/* ========= Shift Chat (chat2) UI ========= */
/*
  Этот модуль реализует простое окно для обмена сообщениями по смене (shift‑chat).
  Он полагается на API /api/chat2/* и на глобальный realtime‑клиент (window.Realtime)
  для получения сообщений в реальном времени. Подробности API описаны в
  документации сервера. Основной функцией модуля является
  window.chat2OpenForShift(shiftId), которую вызывают другие части UI
  (например, карточка смены) для открытия диалога.

  Зависимости:
    - window.Realtime (из static/js/realtime.js) — для WS событий
    - showToast(msg, type) (опционально) — для уведомлений об ошибках
*/
(function(){
  // DOM элементы
  let backdrop;
  let messagesEl;
  let inputField;
  let sendBtn;
  let titleEl;
  let closeBtn;
  let templatesEl;

  // Текущее состояние
  let currentShiftId = null;
  let currentChannelId = null;
  let msgs = [];
  let templates = [];
  let unsubRealtime = null;

  /* ===== Утилиты ===== */

  function escapeHtml(str) {
    return String(str || '').replace(/[&<>"]|'/g, function (s) {
      switch (s) {
        case '&': return '&amp;';
        case '<': return '&lt;';
        case '>': return '&gt;';
        case '"': return '&quot;';
        case "'": return '&#39;';
        default: return s;
      }
    });
  }

  function fmtDate(d) {
    try {
      // при невалидной строке просто вернём её
      const dt = new Date(d);
      if (isNaN(dt.getTime())) return String(d || '');
      // выводим локальное время без секунд
      const hh = String(dt.getHours()).padStart(2, '0');
      const mi = String(dt.getMinutes()).padStart(2, '0');
      return `${hh}:${mi}`;
    } catch (_) {
      return String(d || '');
    }
  }

  function uuidv4() {
    // простая генерация UUIDv4, fallback для браузеров без crypto.randomUUID
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    let d = new Date().getTime();
    if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
      d += performance.now();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      const r = (d + Math.random()*16)%16 | 0;
      d = Math.floor(d/16);
      return (c==='x' ? r : (r&0x3|0x8)).toString(16);
    });
  }

  /* ===== Сетевые функции ===== */

  async function ensureChannelForShift(shiftId) {
    try {
      const resp = await fetch('/api/chat2/ensure_shift_channel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ shift_id: shiftId })
      });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      return data && (data.channel_id || data.id || data.channelId || data.channel);
    } catch (err) {
      console.warn('Failed to ensure shift channel', err);
      if (typeof showToast === 'function') {
        showToast('Не удалось создать чат смены', 'error');
      }
      return null;
    }
  }

  async function ensureChannelForIncident(incidentId) {
    try {
      const resp = await fetch('/api/chat2/ensure_incident_channel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ marker_id: incidentId })
      });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      return data && (data.channel_id || data.id || data.channelId || data.channel);
    } catch (err) {
      console.warn('Failed to ensure incident channel', err);
      if (typeof showToast === 'function') {
        showToast('Не удалось создать чат инцидента', 'error');
      }
      return null;
    }
  }


  async function loadHistory(channelId, limit=200) {
    try {
      const resp = await fetch(`/api/chat2/history?channel_id=${encodeURIComponent(channelId)}&limit=${limit}`);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      return Array.isArray(data) ? data : [];
    } catch (err) {
      console.warn('Failed to load chat history', err);
      return [];
    }
  }

  async function sendText(channelId, text) {
    const clientMsgId = uuidv4();
    try {
      const resp = await fetch('/api/chat2/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ channel_id: channelId, client_msg_id: clientMsgId, text: text })
      });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const msg = await resp.json();
      return msg;
    } catch (err) {
      console.warn('Failed to send message', err);
      if (typeof showToast === 'function') {
        showToast('Ошибка отправки сообщения', 'error');
      }
      return null;
    }
  }

  async function sendTemplateMsg(channelId, templateId) {
    try {
      const resp = await fetch('/api/chat2/send_template', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ channel_id: channelId, template_id: templateId })
      });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const msg = await resp.json();
      return msg;
    } catch (err) {
      console.warn('Failed to send template', err);
      if (typeof showToast === 'function') {
        showToast('Ошибка отправки шаблона', 'error');
      }
      return null;
    }
  }

  async function fetchTemplates() {
    try {
      const resp = await fetch('/api/chat2/templates');
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      return Array.isArray(data) ? data : [];
    } catch (err) {
      console.warn('Failed to fetch templates', err);
      return [];
    }
  }

  /* ===== Отрисовка ===== */

  function renderMessages() {
    if (!messagesEl) return;
    messagesEl.innerHTML = '';
    msgs.forEach((m) => {
      const div = document.createElement('div');
      const isAdmin = (m.sender_type === 'admin' || m.sender === 'admin');
      div.className = 'chat2-msg' + (isAdmin ? ' admin' : '');
      let contentHtml = '';
      // Определяем, как отображать содержимое
      if (m.media_key) {
        // медиавложение: показываем изображение или ссылку
        const url = `/uploads/chat2/${encodeURIComponent(m.media_key)}`;
        if (m.mime && m.mime.startsWith('image/')) {
          const alt = escapeHtml(m.text || '');
          contentHtml = `<a href="${url}" target="_blank"><img src="${url}" alt="${alt}" class="chat2-img"></a>`;
          if (m.text) {
            contentHtml += `<div class="chat2-caption">${escapeHtml(m.text)}</div>`;
          }
        } else {
          // ссылка на файл
          const label = m.text ? escapeHtml(m.text) : '[файл]';
          contentHtml = `<a href="${url}" target="_blank">${label}</a>`;
        }
      } else if (m.kind && m.kind !== 'text') {
        // нестандартный тип (например, шаблон)
        contentHtml = `<span class="chat2-nontext">${escapeHtml(m.text || '')}</span>`;
      } else {
        contentHtml = escapeHtml(m.text || '');
      }
      // Время и статус доставки/прочтения
      const time = fmtDate(m.created_at);
      const delCnt = m.delivered_count || 0;
      const readCnt = m.read_count || 0;
      // Статус: показываем два числа, разделённых косой, можно заменить иконками
      const statusHtml = `<span class="chat2-status">${delCnt}/${readCnt}</span>`;
      div.innerHTML = `<span class="chat2-content">${contentHtml}</span><br><small class="muted chat2-time">${escapeHtml(time)} ${statusHtml}</small>`;
      messagesEl.appendChild(div);
      // Отправляем квитанцию о доставке, если не отправляли ранее
      try {
        markDelivered(m);
      } catch (_e) {}
    });
    // автопрокрутка вниз
    messagesEl.scrollTop = messagesEl.scrollHeight;
    // Отмечаем канал прочитанным до последнего сообщения
    const lastMsg = msgs.length ? msgs[msgs.length - 1] : null;
    if (lastMsg) {
      try {
        markRead(lastMsg);
      } catch (_) {}
    }
  }

  function renderTemplates() {
    if (!templatesEl) return;
    templatesEl.innerHTML = '';
    templates.forEach((t) => {
      const btn = document.createElement('button');
      btn.className = 'btn template-btn';
      btn.type = 'button';
      btn.textContent = t.text || t.label || t.id;
      btn.dataset.templateId = t.id || t.template_id;
      btn.title = t.text || '';
      btn.addEventListener('click', () => {
        if (!currentChannelId) return;
        const tplId = btn.dataset.templateId;
        sendTemplateMsg(currentChannelId, tplId).then((msg) => {
          if (msg) {
            msgs.push(msg);
            renderMessages();
          }
        });
      });
      templatesEl.appendChild(btn);
    });
  }

  /* ===== Квитанции ===== */

  // Уведомляем оболочку (Command Center) что непрочитанные могли измениться
  let _unreadNotifyTimer = null;
  function notifyUnreadChanged(){
    try{
      if(_unreadNotifyTimer) clearTimeout(_unreadNotifyTimer);
      _unreadNotifyTimer = setTimeout(() => {
        _unreadNotifyTimer = null;
        try{
          if(window.CC && typeof window.CC.refreshUnreadTabs === 'function') window.CC.refreshUnreadTabs(false);
        }catch(_e){}
      }, 250);
    }catch(_e){}
  }

  // Множества, чтобы избежать повторной отправки квитанций
  const deliveredSet = new Set();
  const readSet = new Set();

  /**
   * Отправить квитанцию о доставке для сообщения. Отправляется один раз на сессию
   * при первом отображении сообщения.
   * @param {object} m
   */
  function markDelivered(m) {
    if (!m || !m.id || deliveredSet.has(m.id)) return;
    deliveredSet.add(m.id);
    try {
      const payload = {
        channel_id: currentChannelId,
        message_id: m.id,
        type: 'delivered',
      };
      fetch('/api/chat2/receipt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }).catch(() => {});
    } catch (_e) {}
  }

  /**
   * Отправить квитанцию о прочтении сообщения и обновить last_read_message_id.
   * @param {object} m
   */
  function markRead(m) {
    if (!m || !m.id || readSet.has(m.id)) return;
    readSet.add(m.id);
    try {
      const payload1 = {
        channel_id: currentChannelId,
        message_id: m.id,
        type: 'read',
      };
      // Отправляем квитанцию "read"
      fetch('/api/chat2/receipt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload1),
      }).catch(() => {});
      // Обновляем отметку прочитанности канала
      const payload2 = {
        channel_id: currentChannelId,
        last_read_message_id: m.id,
      };
      fetch('/api/chat2/read', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload2),
      }).catch(() => {});
      // обновим агрегаты непрочитанных в оболочке
      try{ notifyUnreadChanged(); }catch(_e){}
    } catch (_e) {}
  }

  /* ===== Realtime ===== */

  function subscribeRealtime() {
    if (!window.Realtime || typeof window.Realtime.on !== 'function') return;
    // Убедимся, что Realtime подключён
    try { window.Realtime.connect(); } catch (_) {}
    // Отписаться от старой подписки
    if (typeof unsubRealtime === 'function') {
      try { unsubRealtime(); } catch (_) {}
      unsubRealtime = null;
    }
    // Подписываемся только на нужный канал
    const offMsg = window.Realtime.on('chat2_message', (msg) => {
      try {
        if (!msg || !msg.channel_id) return;
        if (String(msg.channel_id) !== String(currentChannelId)) return;
        msgs.push(msg);
        renderMessages();
      } catch (e) {
        console.warn('chat2 realtime handler error', e);
      }
    });
    // Подписка на квитанции: обновляем счётчики и перерисовываем сообщения
    const offRcpt = window.Realtime.on('chat2_receipt', (ev) => {
      try {
        if (!ev || !ev.channel_id || !ev.message_id) return;
        if (String(ev.channel_id) !== String(currentChannelId)) return;
        // Обновляем локальные данные
        for (let i = 0; i < msgs.length; i++) {
          const m = msgs[i];
          if (m.id && String(m.id) === String(ev.message_id)) {
            if (typeof ev.delivered_count === 'number') m.delivered_count = ev.delivered_count;
            if (typeof ev.read_count === 'number') m.read_count = ev.read_count;
            break;
          }
        }
        renderMessages();
      } catch (e) {
        console.warn('chat2 receipt handler error', e);
      }
    });
    unsubRealtime = () => {
      try { offMsg(); } catch (_e) {}
      try { offRcpt(); } catch (_e) {}
    };
  }

  /* ===== Открытие и закрытие ===== */
  /**
   * Открыть чат по произвольному каналу. Используется для incident/dm‑каналов
   * и вызывается после того, как канал уже существует. Устанавливает заголовок,
   * очищает историю, загружает сообщения и подписывается на realtime.
   * @param {string} channelId
   * @param {string} title
   */
  async function openChat2Channel(channelId, title) {
    if (!backdrop) return;
    currentShiftId = null;
    currentChannelId = channelId;
    if (titleEl && title) {
      titleEl.textContent = String(title);
    }
    backdrop.style.display = 'flex';
    backdrop.classList.add('open');
    msgs = [];
    renderMessages();
    // Загружаем историю
    msgs = await loadHistory(channelId, 200);
    renderMessages();
    subscribeRealtime();
  }

  async function openChat2(shiftId) {
    if (!backdrop) return;
    currentShiftId = shiftId;
    // Заголовок модалки
    const title = `Смена #${shiftId}`;
    if (titleEl) {
      titleEl.textContent = title;
    }
    // Показываем модалку
    backdrop.style.display = 'flex';
    backdrop.classList.add('open');
    // Очистить историю
    msgs = [];
    renderMessages();
    // Получаем канал
    const chId = await ensureChannelForShift(shiftId);
    if (!chId) {
      return;
    }
    // Вызываем общий обработчик
    await openChat2Channel(chId, title);
  }

  async function openChat2ForIncident(incidentId) {
    if (!backdrop) return;
    const iid = String(incidentId || '').trim();
    if (!iid) return;
    const title = `Инцидент #${iid}`;
    if (titleEl) titleEl.textContent = title;
    backdrop.style.display = 'flex';
    backdrop.classList.add('open');
    msgs = [];
    renderMessages();
    const chId = await ensureChannelForIncident(iid);
    if (!chId) return;
    await openChat2Channel(chId, title);
  }


  function closeChat2() {
    if (!backdrop) return;
    backdrop.classList.remove('open');
    backdrop.style.display = 'none';
    currentShiftId = null;
    currentChannelId = null;
    msgs = [];
    if (typeof unsubRealtime === 'function') {
      try { unsubRealtime(); } catch (_) {}
      unsubRealtime = null;
    }
  }

  function initChat2() {
    backdrop = document.getElementById('chat2-backdrop');
    messagesEl = document.getElementById('chat2-messages');
    inputField = document.getElementById('chat2-input-field');
    sendBtn = document.getElementById('chat2-send');
    titleEl = document.getElementById('chat2-title');
    closeBtn = document.getElementById('chat2-close');
    templatesEl = document.getElementById('chat2-templates');
    // Загрузить шаблоны
    fetchTemplates().then((t) => {
      templates = t;
      renderTemplates();
    });
    // События ввода
    if (sendBtn) {
      sendBtn.addEventListener('click', () => {
        const txt = (inputField && inputField.value ? inputField.value.trim() : '');
        if (!txt || !currentChannelId) return;
        sendText(currentChannelId, txt).then((msg) => {
          if (msg) {
            msgs.push(msg);
            renderMessages();
          }
          if (inputField) inputField.value = '';
        });
      });
    }
    if (inputField) {
      inputField.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          if (sendBtn) sendBtn.click();
        }
      });
    }
    if (closeBtn) {
      closeBtn.addEventListener('click', () => closeChat2());
    }
  }

  // Инициализация при загрузке DOM
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initChat2);
  } else {
    initChat2();
  }

  // Экспортируем глобальную функцию
  window.chat2OpenForShift = openChat2;
  window.chat2OpenChannel = openChat2Channel;
  window.chat2OpenForIncident = openChat2ForIncident;
})();