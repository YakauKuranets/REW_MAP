import React, { useEffect, useState } from 'react';

/**
 * Небольшой индикатор состояния чата для топбара.
 *
 * Использует /api/chat/conversations и показывает краткую сводку:
 *  - сколько всего диалогов;
 *  - сколько среди них с непрочитанными сообщениями.
 *
 * Это не заменяет окно чата (которым управляет chat.js),
 * а даёт "подсветку" для администратора в шапке.
 */
export default function ChatPreview() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [total, setTotal] = useState(0);
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const resp = await fetch('/api/chat/conversations');
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        if (cancelled) return;

        const convs = Array.isArray(data) ? data : [];
        const totalConvs = convs.length;
        const unreadConvs = convs.filter(c => (c.unread || 0) > 0).length;
        setTotal(totalConvs);
        setUnread(unreadConvs);
      } catch (err) {
        if (!cancelled) setError(err.message || String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    // Чуть обновляем раз в 30 секунд, чтобы данные в шапке были живее.
    const timer = setInterval(load, 30000);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  if (loading) {
    return <span className="muted" style={{ fontSize: '11px' }}>…</span>;
  }
  if (error) {
    return <span className="muted" style={{ fontSize: '11px' }}>ч: err</span>;
  }
  if (!total) {
    return <span className="muted" style={{ fontSize: '11px' }}>диалогов нет</span>;
  }
  if (!unread) {
    return <span className="muted" style={{ fontSize: '11px' }}>без новых</span>;
  }
  return (
    <span style={{ fontSize: '11px' }}>
      чатов: {total}, новых: <b>{unread}</b>
    </span>
  );
}
