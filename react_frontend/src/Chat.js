import React, { useEffect, useState } from 'react';
import axios from 'axios';

// Компонент чата показывает список диалогов слева и сообщения справа.
// При выборе диалога загружает историю сообщений и позволяет
// отправлять новые сообщения через API.

export default function Chat() {
  const [conversations, setConversations] = useState([]);
  const [activeUser, setActiveUser] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');

  // Загружаем список диалогов при загрузке компонента
  useEffect(() => {
    fetchConversations();
    // Запускаем веб‑сокет для получения новых сообщений
    const ws = new WebSocket('ws://localhost:8765');
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.event === 'chat_message') {
          const msg = data.data;
          // Если сообщение принадлежит текущему активному диалогу, добавляем его
          if (activeUser && msg.user_id === activeUser) {
            setMessages((prev) => [...prev, msg]);
          }
          // Обновляем список диалогов, чтобы отобразить последнее сообщение
          fetchConversations();
        }
      } catch (e) {
        console.error('WS parse error', e);
      }
    };
    return () => {
      ws.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeUser]);

  const fetchConversations = async () => {
    try {
      const res = await axios.get('/api/chat/conversations');
      setConversations(res.data);
    } catch (e) {
      console.error('Failed to fetch conversations', e);
    }
  };

  const loadMessages = async (userId) => {
    setActiveUser(userId);
    try {
      const res = await axios.get(`/api/chat/${userId}`);
      setMessages(res.data);
    } catch (e) {
      console.error('Failed to fetch messages', e);
    }
  };

  const sendMessage = async () => {
    if (!input || !activeUser) return;
    try {
      const res = await axios.post(`/api/chat/${activeUser}`, { text: input });
      setMessages((prev) => [...prev, res.data]);
      setInput('');
    } catch (e) {
      console.error('Failed to send message', e);
    }
  };

  return (
    <div style={{ display: 'flex', border: '1px solid #ccc', minHeight: '400px' }}>
      <div style={{ width: '30%', borderRight: '1px solid #ccc', overflowY: 'auto' }}>
        <h3 style={{ padding: '10px' }}>Диалоги</h3>
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {conversations.map((c) => (
            <li
              key={c.user_id}
              onClick={() => loadMessages(c.user_id)}
              style={{
                padding: '10px',
                cursor: 'pointer',
                background: activeUser === c.user_id ? '#f0f0f0' : 'transparent',
              }}
            >
              <strong>{c.user_id}</strong>
              <br />
              <small>
                {c.last_sender === 'admin' ? 'Админ' : 'Пользователь'}:
                {` ${c.last_text}`.slice(0, 30)}
              </small>
            </li>
          ))}
        </ul>
      </div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        {activeUser ? (
          <>
            <div style={{ flex: 1, overflowY: 'auto', padding: '10px' }}>
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  style={{
                    margin: '4px 0',
                    textAlign: msg.sender === 'admin' ? 'right' : 'left',
                  }}
                >
                  <span
                    style={{
                      display: 'inline-block',
                      padding: '6px 10px',
                      borderRadius: '8px',
                      background: msg.sender === 'admin' ? '#e1f5fe' : '#fff3e0',
                      border: '1px solid #ddd',
                    }}
                  >
                    {msg.text}
                  </span>
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', padding: '10px', borderTop: '1px solid #ccc' }}>
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                style={{ flex: 1, padding: '6px' }}
                placeholder="Введите сообщение..."
              />
              <button onClick={sendMessage} style={{ marginLeft: '8px' }}>
                Отправить
              </button>
            </div>
          </>
        ) : (
          <p style={{ margin: 'auto' }}>Выберите диалог слева, чтобы начать</p>
        )}
      </div>
    </div>
  );
}