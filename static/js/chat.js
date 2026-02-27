/* ========= Admin Chat UI ========= */
/**
 * Зависимости:
 *  - showToast(msg, type)
 *  - pushNotify(title, body)  (необязательно, но если есть — будут пуши)
 *  - API:
 *      GET  /api/chat/conversations
 *      GET  /api/chat/<user_id>
 *      POST /api/chat/<user_id>            { text }
 *      DELETE /api/chat/<user_id>
 *      POST /api/chat/<user_id>/status     { status }
 *  - WebSocket (опционально):
 *      ws://<host>:8765, событие { event: 'chat_message', data: { user_id, text, sender, created_at } }
 */

(function () {
  // DOM-ссылки
  let btnChat;
  let chatBackdrop;
  let chatClose;
  let chatList;
  let chatMessages;
  let chatInputField;
  let chatSend;
  let chatPeerName;
  let chatPeerId;
  let chatClear;
  let chatSearch;
  let chatOnlyUnread;
  let chatStatusSelect;

  // Состояние
  let activeUser = null;       // id текущего собеседника
  let conversations = [];      // кеш диалогов
  let chatSocket = null;       // WebSocket чата (если получилось подключиться)

  // Пагинация для infinite-scroll вверх
  const paging = { oldestId: null, hasOlder: true, loading: false, pageSize: 200, initialSize: 500 };
  let topLoaderEl = null;

  /* ===== Утилиты ===== */

  function safeText(v) {
    return (v == null ? '' : String(v));
  }

  function humanStatus(status) {
    if (status === 'closed') return 'закрыт';
    if (status === 'in_progress') return 'в работе';
    if (status === 'new') return 'новый';
    return status || 'неизвестно';
  }

  function collectMessagesFromDOM() {
    if (!chatMessages) return [];
    return Array.from(chatMessages.querySelectorAll('.msg')).map((node) => {
      const span = node.querySelector('span');
      return {
        sender: node.classList.contains('admin') ? 'admin' : 'user',
        text: span ? span.textContent : '',
        created_at: node.dataset && node.dataset.createdAt ? node.dataset.createdAt : null
      };
    });
  }

  function scrollMessagesToBottom() {
    if (!chatMessages) return;
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  /* ===== Загрузка и рендер списка диалогов ===== */

  async function loadConversations() {
    try {
      const resp = await fetch('/api/chat/conversations');
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      conversations = Array.isArray(data) ? data : [];
      renderConversations();
    } catch (err) {
      console.warn('Failed to load conversations', err);
      showToast && showToast('Не удалось загрузить диалоги', 'error');
    }
  }

  function renderConversations() {
    if (!chatList) return;

    chatList.innerHTML = '';

    let convs = Array.isArray(conversations) ? conversations.slice() : [];

    const term = (chatSearch && chatSearch.value || '').trim().toLowerCase();
    const onlyUnread = chatOnlyUnread && chatOnlyUnread.checked;

    if (term) {
      convs = convs.filter((c) => {
        const label = String(c.display_name || c.user_id || '').toLowerCase();
        return label.includes(term);
      });
    }

    if (onlyUnread) {
      convs = convs.filter((c) => (c.unread || 0) > 0);
    }

    if (!convs.length) {
      const placeholder = document.createElement('div');
      placeholder.className = 'conv-placeholder';
      placeholder.textContent = term || onlyUnread ? 'Ничего не найдено' : 'Нет диалогов';
      chatList.appendChild(placeholder);
      return;
    }

    convs.forEach((c) => {
      const item = document.createElement('div');
      item.className = 'conv-item';
      item.dataset.userId = safeText(c.user_id);
      if (c.display_name) item.dataset.displayName = safeText(c.display_name);

      const label = c.display_name || c.user_id;
      let titleHtml = '';

      // username вида @name делаем кликабельным
      if (typeof label === 'string' && label.startsWith('@')) {
        const uname = label.slice(1);
        titleHtml = `<a href="https://t.me/${uname}" target="_blank" class="chat-username">${label}</a>`;
      } else {
        titleHtml = `<span class="chat-username">${safeText(label)}</span>`;
      }

      const last = safeText(c.last_text).trim();
      const preview = last.length > 30 ? last.slice(0, 30) + '…' : last;

      let meta = `${c.last_sender === 'admin' ? 'Админ' : 'Пользователь'}: ${preview || 'без сообщений'}`;

      if (c.status) {
        meta += ` • статус: ${humanStatus(c.status)}`;
      }
      if (c.has_requests) {
        meta += ' • есть заявки';
      }

      item.innerHTML = `<strong>${titleHtml}</strong><br><small>${meta}</small>`;

      // Бейдж непрочитанных
      if (c.unread && c.unread > 0) {
        const badge = document.createElement('span');
        badge.className = 'badge';
        badge.textContent = c.unread;
        item.appendChild(badge);
      }

      // Подсветка активного
      if (activeUser && String(c.user_id) === String(activeUser)) {
        item.classList.add('active');
      }

      item.addEventListener('click', () => {
        selectConversation(c.user_id);
      });

      chatList.appendChild(item);
    });
  }

  /* ===== Выбор диалога и загрузка сообщений ===== */

  async function selectConversation(userId) {
    if (!userId) return;
    activeUser = userId;

    // обнуляем unread для выбранного диалога
    if (Array.isArray(conversations)) {
      conversations = conversations.map((c) =>
        String(c.user_id) === String(userId)
          ? Object.assign({}, c, { unread: 0 })
          : c
      );
    }

    // подсветка слева
    if (chatList) {
      chatList.querySelectorAll('.conv-item').forEach((el) => {
        const isActive = el.dataset && el.dataset.userId === String(userId);
        el.classList.toggle('active', isActive);
        if (isActive) {
          const badge = el.querySelector('.badge');
          if (badge) badge.remove();
          if (chatPeerName) {
            const label = el.dataset.displayName || el.dataset.userId || String(userId);
            chatPeerName.textContent = label;
          }
        }
      });
    }

    if (chatPeerId) chatPeerId.textContent = String(userId);

    // выставляем статус в select
    if (chatStatusSelect && Array.isArray(conversations)) {
      const conv = conversations.find((c) => String(c.user_id) === String(userId));
      if (conv && conv.status) {
        chatStatusSelect.value = conv.status;
      }
    }

    // грузим историю сообщений
    try {
      const resp = await fetch(`/api/chat/${encodeURIComponent(userId)}?limit=${paging.initialSize}&tail=1`);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const msgs = await resp.json();
      renderMessages(msgs, 'replace');
      paging.oldestId = (Array.isArray(msgs) && msgs.length ? (msgs[0].id ?? null) : null);
      paging.hasOlder = Array.isArray(msgs) ? (msgs.length >= paging.initialSize) : false;
      paging.loading = false;

    } catch (err) {
      console.warn('Failed to fetch messages', err);
      showToast && showToast('Не удалось загрузить сообщения', 'error');
    }
  }

  function _createMessageEl(m) {
  const div = document.createElement('div');
  div.className = 'msg ' + (m.sender === 'admin' ? 'admin' : 'user');
  if (m.created_at) div.dataset.createdAt = m.created_at;
  if (m.id != null) div.dataset.msgId = String(m.id);

  const bubble = document.createElement('span');
  bubble.textContent = safeText(m.text);
  div.appendChild(bubble);

  if (m.created_at) {
    try {
      const dt = new Date(m.created_at);
      const hh = String(dt.getHours()).padStart(2,'0');
      const mm = String(dt.getMinutes()).padStart(2,'0');
      const time = `${hh}:${mm}`;
      const meta = document.createElement('div');
      meta.className = 'msg-meta';
      meta.textContent = time;
      div.appendChild(meta);
    } catch (_) {}
  }
  return div;
}

function _ensureTopLoader() {
  if (!chatMessages) return;
  if (topLoaderEl && topLoaderEl.parentElement) return;
  topLoaderEl = document.createElement('div');
  topLoaderEl.className = 'chat-loader-top';
  topLoaderEl.textContent = 'Загрузка...';
  topLoaderEl.style.display = 'none';
  chatMessages.prepend(topLoaderEl);
}

function _setTopLoaderVisible(on) {
  if (!topLoaderEl) return;
  topLoaderEl.style.display = on ? 'block' : 'none';
}

function renderMessages(msgs, mode = 'replace') {
  if (!chatMessages) return;
  _ensureTopLoader();

  if (mode === 'replace') {
    // оставляем loader первым элементом
    chatMessages.querySelectorAll('.msg').forEach((el) => el.remove());
  }

  const frag = document.createDocumentFragment();
  (msgs || []).forEach((m) => {
    frag.appendChild(_createMessageEl(m));
  });

  if (mode === 'prepend') {
    // вставляем после loader
    const anchor = topLoaderEl && topLoaderEl.nextSibling ? topLoaderEl.nextSibling : null;
    chatMessages.insertBefore(frag, anchor);
  } else {
    chatMessages.appendChild(frag);
  }

  if (mode === 'replace') {
    scrollMessagesToBottom();
  }
}

async function loadOlderMessages() {
  if (!activeUser) return;
  if (!paging.hasOlder || paging.loading) return;
  if (!paging.oldestId) { paging.hasOlder = false; return; }

  paging.loading = true;
  _ensureTopLoader();
  _setTopLoaderVisible(true);

  const prevScrollHeight = chatMessages.scrollHeight;
  const prevScrollTop = chatMessages.scrollTop;

  try {
    const url = `/api/chat/${encodeURIComponent(activeUser)}?before_id=${encodeURIComponent(paging.oldestId)}&limit=${paging.pageSize}`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const msgs = await resp.json();

    if (!Array.isArray(msgs) || msgs.length === 0) {
      paging.hasOlder = false;
      return;
    }

    // обновим oldestId
    if (msgs[0] && msgs[0].id != null) paging.oldestId = msgs[0].id;

    // prepend
    renderMessages(msgs, 'prepend');

    // удерживаем позицию прокрутки (чтобы не прыгало)
    const newScrollHeight = chatMessages.scrollHeight;
    chatMessages.scrollTop = (newScrollHeight - prevScrollHeight) + prevScrollTop;

    if (msgs.length < paging.pageSize) paging.hasOlder = false;
  } catch (err) {
    console.warn('Failed to load older messages', err);
  } finally {
    paging.loading = false;
    _setTopLoaderVisible(false);
  }
}

  /* ===== Отправка, очистка, статус ===== */

  async function sendCurrentMessage() {
    const text = chatInputField && chatInputField.value ? chatInputField.value.trim() : '';
    if (!text || !activeUser) return;

    try {
      const resp = await fetch(`/api/chat/${encodeURIComponent(activeUser)}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Admin': '1'
        },
        body: JSON.stringify({ text })
      });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const msg = await resp.json();

      const current = collectMessagesFromDOM();
      renderMessages(current.concat([msg]));
      chatInputField.value = '';

      // обновляем кеш: для этого пользователя unread = 0, last_text обновляем
      conversations = conversations.map((c) =>
        String(c.user_id) === String(activeUser)
          ? Object.assign({}, c, { unread: 0, last_text: msg.text, last_sender: 'admin' })
          : c
      );
      renderConversations();
    } catch (err) {
      console.warn('Failed to send message', err);
      showToast && showToast('Не удалось отправить сообщение', 'error');
    }
  }

  async function clearCurrentConversation() {
    if (!activeUser) return;
    if (!confirm('Очистить всю историю этого диалога?')) return;
    try {
      const resp = await fetch(`/api/chat/${encodeURIComponent(activeUser)}`, {
        method: 'DELETE'
      });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);

      if (chatMessages) chatMessages.innerHTML = '';
      if (chatPeerName) chatPeerName.textContent = 'Выберите диалог слева';
      if (chatPeerId) chatPeerId.textContent = '';
      activeUser = null;

      await loadConversations();
    } catch (err) {
      console.warn('Failed to clear conversation', err);
      showToast && showToast('Не удалось очистить диалог', 'error');
    }
  }

  async function updateCurrentStatus() {
    if (!activeUser || !chatStatusSelect) return;
    const val = chatStatusSelect.value;
    if (!val) return;

    try {
      const resp = await fetch(`/api/chat/${encodeURIComponent(activeUser)}/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: val })
      });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);

      conversations = conversations.map((c) =>
        String(c.user_id) === String(activeUser)
          ? Object.assign({}, c, { status: val })
          : c
      );
      renderConversations();
      showToast && showToast('Статус диалога обновлён', 'success');
    } catch (err) {
      console.warn('Failed to update chat status', err);
      showToast && showToast('Не удалось обновить статус диалога', 'error');
    }
  }

  /* ===== WebSocket уведомления ===== */

  let _chatSocketConnecting = false;

  function _bindChatSocket(ws) {
    chatSocket = ws;
    chatSocket.addEventListener('message', (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (!data || !data.event) return;
        if (data.event !== 'chat_message') return;
        const msg = data.data || {};

        // Обновляем список диалогов
        loadConversations();

        // Если открыт диалог с этим пользователем — добавляем сообщение
        if (activeUser && String(msg.user_id) === String(activeUser)) {
          const current = collectMessagesFromDOM();
          renderMessages(current.concat([msg]));
        } else if (typeof pushNotify === 'function' && msg.text) {
          pushNotify('Новое сообщение', msg.text);
        }

        // Подтянуть агрегированные счётчики (если модуль requests.js экспортировал функцию)
        if (typeof window.refreshNotifCount === 'function') {
          window.refreshNotifCount();
        }
      } catch (ex) {
        console.warn('WS chat parse error', ex);
      }
    });

    chatSocket.addEventListener('error', (err) => {
      console.warn('Chat socket error', err);
    });
  }

  function _connectWithFallback(urls, idx) {
    if (!urls || idx >= urls.length) {
      _chatSocketConnecting = false;
      return;
    }
    let opened = false;
    let ws;
    try {
      ws = new WebSocket(urls[idx]);
    } catch (e) {
      return _connectWithFallback(urls, idx + 1);
    }
    ws.addEventListener('open', () => {
      opened = true;
      _chatSocketConnecting = false;
      _bindChatSocket(ws);
    });
    ws.addEventListener('close', () => {
      if (!opened) {
        try { ws.close(); } catch (e) {}
        _connectWithFallback(urls, idx + 1);
      }
    });
    ws.addEventListener('error', () => {
      if (!opened) {
        try { ws.close(); } catch (e) {}
        _connectWithFallback(urls, idx + 1);
      }
    });
  }

  async function initChatSocket() {
    // v22: предпочтительно использовать единый Realtime-клиент
    if (window.Realtime && typeof window.Realtime.on === 'function') {
      try {
        window.Realtime.connect();
        if (!window.__chat_realtime_bound) {
          window.__chat_realtime_bound = true;
          window.Realtime.on('chat_message', (msg) => {
            try {
              msg = msg || {};
              // Обновляем список диалогов
              loadConversations();

              // Если открыт диалог с этим пользователем — добавляем сообщение
              if (activeUser && String(msg.user_id) === String(activeUser)) {
                const current = collectMessagesFromDOM();
                renderMessages(current.concat([msg]));
              } else if (typeof pushNotify === 'function' && msg.text) {
                pushNotify('Новое сообщение', msg.text);
              }

              // Подтянуть агрегированные счётчики
              if (window.Realtime && typeof window.Realtime.refreshCounters === 'function') {
                window.Realtime.refreshCounters();
              }
              if (typeof window.refreshNotifCount === 'function') {
                window.refreshNotifCount();
              }
            } catch (e) {
              console.warn('Realtime chat handler error', e);
            }
          });

          // после админских действий (очистка/удаление) — просто перезагрузим список
          window.Realtime.on('chat_cleared', () => { try{ loadConversations(); }catch(_){ } });
          window.Realtime.on('chat_deleted', () => { try{ loadConversations(); }catch(_){ } });
        }
      } catch (_) {}
      return;
    }

    if (chatSocket || _chatSocketConnecting) return;
    _chatSocketConnecting = true;

    const wsProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = location.hostname;

    let urls = [];
    try {
      const r = await fetch('/api/realtime/token', { credentials: 'same-origin' });
      if (r && r.ok) {
        const j = await r.json();
        if (j && j.ws_url_sameport) urls.push(j.ws_url_sameport);
        if (j && j.ws_url_port) urls.push(j.ws_url_port);
        if (j && j.token) {
          urls.push(`${wsProtocol}//${host}:8765/ws?token=${encodeURIComponent(j.token)}`);
        }
      }
    } catch (e) {
      // ignore
    }

    // Последний фолбэк (старый dev-режим без токена — может быть выключен сервером)
    urls.push(`${wsProtocol}//${host}:8765/ws`);

    // Удаляем пустые / дубли
    urls = (urls || []).filter(Boolean).filter((u, i, a) => a.indexOf(u) === i);

    _connectWithFallback(urls, 0);
  }

  /* ===== Открытие / закрытие модалки ===== */

  function openChat() {
    if (!chatBackdrop) return;
    chatBackdrop.style.display = 'flex';
    chatBackdrop.classList.add('open');
    loadConversations();
  }

  function closeChat() {
    if (!chatBackdrop) return;
    chatBackdrop.classList.remove('open');
    chatBackdrop.style.display = 'none';
    activeUser = null;
    if (chatMessages) chatMessages.innerHTML = '';
    if (chatPeerName) chatPeerName.textContent = 'Выберите диалог слева';
    if (chatPeerId) chatPeerId.textContent = '';
  }

  /* ===== Инициализация UI ===== */

  function bindChatUI() {
    btnChat          = document.getElementById('btn-chat');
    chatBackdrop     = document.getElementById('chat-backdrop');
    chatClose        = document.getElementById('chat-close');
    chatList         = chatBackdrop ? chatBackdrop.querySelector('.chat-list-body') : null;
    chatMessages     = chatBackdrop ? chatBackdrop.querySelector('.chat-messages') : null;
    chatInputField   = document.getElementById('chat-input-field');
    chatSend         = document.getElementById('chat-send');
    chatPeerName     = document.getElementById('chat-peer-name');
    chatPeerId       = document.getElementById('chat-peer-id');
    chatClear        = document.getElementById('chat-clear');
    chatSearch       = document.getElementById('chat-search');
    chatOnlyUnread   = document.getElementById('chat-only-unread');
    chatStatusSelect = document.getElementById('chat-status');

    if (!btnChat || !chatBackdrop) {
      // чата может не быть (например, гость)
      return;
    }

    // Если реализована новая система чатов (chat2), используем её для кнопки
    if (typeof window.chat2OpenList === 'function') {
      btnChat.addEventListener('click', (e) => {
        try {
          e.preventDefault();
          e.stopPropagation();
          window.chat2OpenList();
        } catch (_e) {
          // fallback: открыть старый чат
          openChat();
        }
      });
    } else {
      btnChat.addEventListener('click', openChat);
    }

    if (chatClose) {
      chatClose.addEventListener('click', closeChat);
    }

    // клик по фону — закрыть модалку
    chatBackdrop.addEventListener('click', (e) => {
      if (e.target === chatBackdrop) closeChat();
    });

    if (chatSend && chatInputField) {
      chatSend.addEventListener('click', sendCurrentMessage);
      chatInputField.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          sendCurrentMessage();
        }
      });
    }

    if (chatClear) {
      chatClear.addEventListener('click', clearCurrentConversation);
    }

    if (chatSearch) {
      chatSearch.addEventListener('input', renderConversations);
    }

    if (chatOnlyUnread) {
      chatOnlyUnread.addEventListener('change', renderConversations);
    }

    if (chatStatusSelect) {
      chatStatusSelect.addEventListener('change', updateCurrentStatus);
    }

    initChatSocket();
  

// infinite-scroll вверх
if (chatMessages) {
  chatMessages.addEventListener('scroll', () => {
    try {
      if (!activeUser) return;
      if (!paging.hasOlder || paging.loading) return;
      if (chatMessages.scrollTop <= 10) {
        loadOlderMessages();
      }
    } catch (_) {}
  });
}
}


  // Экспорт для других модулей (например SOS-overlay):
  // открыть чат и перейти к конкретному пользователю.
  window.chatOpenToUser = async function(userId) {
    try {
      openChat();
      await loadConversations();
      await selectConversation(String(userId));
    } catch (e) {
      console.warn('chatOpenToUser failed', e);
    }
  };

  document.addEventListener('DOMContentLoaded', () => {
    try {
      bindChatUI();
      try {
        const p = new URLSearchParams(window.location.search || '');
        const uid = p.get('chatUser');
        if (uid) {
          setTimeout(() => {
            if (typeof window.chatOpenToUser === 'function') window.chatOpenToUser(uid);
          }, 350);
        }
      } catch (e) {}
    } catch (err) {
      console.warn('Failed to init chat UI', err);
    }
  });
})();
