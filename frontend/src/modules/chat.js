/* ========= Chat UI (admin) ========= */
/**
 * Модуль админского чата. Зависит от:
 *  - showToast(msg, type)
 *  - pushNotify(title, body)
 *  - стандартизированного API /api/chat/*
 */
(function() {
  // В рамках модуля держим сокет чата
  let chatSocket;

  function bindChatUI() {
  const btnChat = document.getElementById('btn-chat');
  const chatBackdrop = document.getElementById('chat-backdrop');
  const chatClose   = document.getElementById('chat-close');
  const chatList    = chatBackdrop ? chatBackdrop.querySelector('.chat-list-body') : null;
  const chatMessages= chatBackdrop ? chatBackdrop.querySelector('.chat-messages') : null;
  const chatInputField = document.getElementById('chat-input-field');
  const chatSend   = document.getElementById('chat-send');
  const chatPeerName = document.getElementById('chat-peer-name');
  const chatPeerId   = document.getElementById('chat-peer-id');
  const chatClear    = document.getElementById('chat-clear');
  const chatSearch   = document.getElementById('chat-search');
  const chatOnlyUnread = document.getElementById('chat-only-unread');
  // идентификатор активного собеседника и кеш диалогов
  let activeUser = null;
  let conversationsCache = [];

  if (!btnChat || !chatBackdrop) return;

  // Открываем модалку и загружаем диалоги
  btnChat.addEventListener('click', () => {
    if (chatBackdrop) {
      // Используем класс open, как у других модалок, чтобы задействовать анимацию и видимость
      chatBackdrop.classList.add('open');
    }
    fetchConversations();
  });
  // Закрываем модалку
  if (chatClose) chatClose.addEventListener('click', () => {
    if (chatBackdrop) {
      chatBackdrop.classList.remove('open');
    }
    activeUser = null;
    if (chatMessages) chatMessages.innerHTML = '';
    if (chatPeerName) chatPeerName.textContent = 'Выберите диалог слева';
    if (chatPeerId) chatPeerId.textContent = '';
  });

  /**
   * Загрузить список диалогов из API и отобразить его в меню слева.
   */

  async function fetchConversations() {
    try {
      const resp = await fetch('/api/chat/conversations');
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const convs = await resp.json();
      conversationsCache = Array.isArray(convs) ? convs : [];
      renderConversations();
    } catch (err) {
      console.warn('Failed to fetch conversations', err);
    }
  }

  /**
   * Отрисовать список диалогов слева с учётом поиска и фильтра "Только с новыми".
   */
  function renderConversations() {
    if (!chatList) return;
    chatList.innerHTML = '';
    let convs = Array.isArray(conversationsCache) ? conversationsCache.slice() : [];

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

    if (!convs || convs.length === 0) {
      const placeholder = document.createElement('div');
      placeholder.className = 'conv-placeholder';
      placeholder.textContent = term || onlyUnread ? 'Ничего не найдено' : 'Нет диалогов';
      chatList.appendChild(placeholder);
      return;
    }

    convs.forEach((c) => {
      const item = document.createElement('div');
      item.className = 'conv-item';
      // Сохраняем user_id и display_name в data-атрибутах,
      // чтобы позже подсветить выбранный и вывести заголовок.
      item.dataset.userId = c.user_id;
      if (c.display_name) item.dataset.displayName = c.display_name;

      const last = (c.last_text || '').trim();
      const preview = last.length > 30 ? last.slice(0, 30) + '…' : last;

      // Используем display_name, если есть (например @username), иначе fallback — user_id.
      const label = c.display_name || c.user_id;

      // Если это @username, делаем его кликабельным.
      let titleHtml = '';
      if (typeof label === 'string' && label.startsWith('@')) {
        const uname = label.slice(1);
        titleHtml = `<a href="https://t.me/${uname}" target="_blank" class="chat-username">${label}</a>`;
      } else {
        titleHtml = `<span class="chat-username">${label}</span>`;
      }

      let meta = `${c.last_sender === 'admin' ? 'Админ' : 'Пользователь'}: ${preview || 'без сообщений'}`;
      if (c.has_requests) {
        meta += ' • есть заявки';
      }
      item.innerHTML =
        `<strong>${titleHtml}</strong><br>` +
        `<small>${meta}</small>`;

      // Непрочитанные для админа
      if (c.unread && c.unread > 0) {
        const badge = document.createElement('span');
        badge.className = 'badge';
        badge.textContent = c.unread;
        item.appendChild(badge);
      }

      // Подсвечиваем активный диалог если он уже выбран
      if (activeUser && String(c.user_id) === String(activeUser)) {
        item.classList.add('active');
      }

      item.addEventListener('click', () => {
        selectConversation(c.user_id);
      });
      chatList.appendChild(item);
    });
  }

  /**
  /**
   * Загрузить историю сообщений для выбранного пользователя и отобразить её.
   * @param {string} userId
   */
  async function selectConversation(userId) {
    activeUser = userId;
    // При открытии диалога считаем его прочитанным (на уровне UI)
    if (Array.isArray(conversationsCache)) {
      conversationsCache = conversationsCache.map((c) =>
        String(c.user_id) === String(userId) ? Object.assign({}, c, { unread: 0 }) : c
      );
      // Перерисуем список, чтобы обновить бейджи и фильтр "Только с новыми"
      renderConversations();
    }
    // Подсветим выбранный диалог: снимаем выделение со всех элементов и выделяем текущий
    if (chatList) {
      chatList.querySelectorAll('.conv-item').forEach((el) => {
        if (el.dataset && typeof el.dataset.userId !== 'undefined') {
          const isActive = el.dataset.userId === userId;
          el.classList.toggle('active', isActive);
          if (isActive) {
            // Снимаем бейдж непрочитанных для выбранного диалога
            const badge = el.querySelector('.badge');
            if (badge) badge.remove();
          }
          if (isActive && chatPeerName) {
            const label = el.dataset.displayName || el.dataset.userId || userId;
            chatPeerName.textContent = label;
          }
        }
      });
    }
    if (chatPeerId) {
      chatPeerId.textContent = userId;
    }
    try {
      const resp = await fetch(`/api/chat/${encodeURIComponent(userId)}`);
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const msgs = await resp.json();
      renderMessages(msgs);
    } catch (err) {
      console.warn('Failed to fetch messages', err);
    }
  }

  /**
   * Отрисовать список сообщений в окне диалога.
   * @param {Array} msgs
   */
  function renderMessages(msgs) {
    if (!chatMessages) return;
    chatMessages.innerHTML = '';
    msgs.forEach((m) => {
      const div = document.createElement('div');
      div.className = 'msg ' + (m.sender === 'admin' ? 'admin' : 'user');
      if (m.created_at) div.dataset.createdAt = m.created_at;

      const bubble = document.createElement('span');
      bubble.textContent = m.text;
      div.appendChild(bubble);

      // Небольшая подпись со временем отправки, если оно есть
      if (m.created_at) {
        try {
          const dt = new Date(m.created_at);
          if (!isNaN(dt.getTime())) {
            const hh = String(dt.getHours()).padStart(2, '0');
            const mm = String(dt.getMinutes()).padStart(2, '0');
            const time = hh + ':' + mm;
            const meta = document.createElement('div');
            meta.className = 'msg-meta';
            meta.textContent = time;
            div.appendChild(meta);
          }
        } catch (e) {
          // игнорируем ошибки парсинга
        }
      }

      chatMessages.appendChild(div);
    });
    // Прокручиваем вниз, чтобы видеть новое сообщение
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  // Отправка нового сообщения от администратора
  if (chatSend && chatInputField) {
    chatSend.addEventListener('click', async () => {
      const text = chatInputField.value.trim();
      if (!text || !activeUser) return;
      try {
        const resp = await fetch(`/api/chat/${encodeURIComponent(activeUser)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Admin': '1' },
          body: JSON.stringify({ text }),
        });

  // Очистка истории диалога (удаление сообщений для activeUser)
  if (chatClear) {
    chatClear.addEventListener('click', async () => {
      if (!activeUser) return;
      if (!confirm('Очистить всю историю этого диалога?')) return;
      try {
        const resp = await fetch(`/api/chat/${encodeURIComponent(activeUser)}`, { method: 'DELETE' });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        // Очищаем окно сообщений и сбрасываем заголовок
        if (chatMessages) chatMessages.innerHTML = '';
        if (chatPeerName) chatPeerName.textContent = 'Выберите диалог слева';
        if (chatPeerId) chatPeerId.textContent = '';
        activeUser = null;
        // Перезагружаем список диалогов
        fetchConversations();
      } catch (err) {
        console.warn('Failed to clear conversation', err);
        alert('Не удалось очистить диалог. Проверьте консоль.');
      }
    });
  }

        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const msg = await resp.json();
        // добавляем отправленное сообщение локально
        renderMessages(
          ([]).concat(
            Array.from(chatMessages.querySelectorAll('.msg')).map((node) => {
              return {
                sender: node.classList.contains('admin') ? 'admin' : 'user',
                text: node.querySelector('span').textContent,
                created_at: node.dataset && node.dataset.createdAt ? node.dataset.createdAt : null,
              };
            }),
            [msg]
          )
        );
        // Обновляем кеш диалогов: для текущего пользователя помечаем, что новых сообщений нет
        if (Array.isArray(conversationsCache) && activeUser) {
          conversationsCache = conversationsCache.map((c) =>
            String(c.user_id) === String(activeUser) ? Object.assign({}, c, { unread: 0 }) : c
          );
          renderConversations();
        }
        chatInputField.value = '';
      } catch (err) {
        console.warn('Failed to send message', err);
        showToast('Не удалось отправить сообщение', 'error');
      }
    });
  }

  // Инициализируем WebSocket для получения уведомлений о новых сообщениях
  if (!chatSocket) {
    try {
      const wsProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = location.hostname;
      const wsUrl = `${wsProtocol}//${host}:8765`;
      chatSocket = new WebSocket(wsUrl);
      chatSocket.addEventListener('message', (ev) => {
        try {
          const data = JSON.parse(ev.data);
          if (data.event === 'chat_message') {
            const msg = data.data;
            // Обновляем список диалогов
            fetchConversations();
            // Если открыта переписка с этим пользователем, добавляем сообщение
            if (activeUser && String(msg.user_id) === String(activeUser)) {
              renderMessages(
                ([]).concat(
                  Array.from(chatMessages.querySelectorAll('.msg')).map((node) => {
                    return {
                      sender: node.classList.contains('admin') ? 'admin' : 'user',
                      text: node.querySelector('span').textContent,
                      created_at: node.dataset && node.dataset.createdAt ? node.dataset.createdAt : null,
                    };
                  }),
                  [msg]
                )
              );
            } else {
              // Если диалог не открыт, показываем push‑уведомление
              pushNotify('Новое сообщение', msg.text);
            }
          }
        } catch (ex) {
          console.warn('WS chat parse error', ex);
        }
      });
    } catch (err) {
      console.warn('Failed to initialize chat socket', err);
    }
  }
}
  // Локальный поиск и фильтр "Только с новыми"
  if (chatSearch) {
    chatSearch.addEventListener('input', () => {
      renderConversations();
    });
  }
  if (chatOnlyUnread) {
    chatOnlyUnread.addEventListener('change', () => {
      renderConversations();
    });
  }

  }

  document.addEventListener('DOMContentLoaded', () => {
    try {
      bindChatUI();
    } catch (err) {
      console.warn('Failed to init chat UI', err);
    }
  });
})();
