import React, { useEffect, useState } from 'react';

/**
 * Индикатор заявок в хедере выпадающего списка колокольчика.
 *
 * Берёт данные из /api/requests/pending и показывает:
 *  - количество входящих запросов;
 *  - слегка обновляет данные в фоне.
 *
 * Основная отрисовка списка остаётся за requests.js,
 * здесь только маленький React-надзор.
 */
export default function RequestsPreview() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [count, setCount] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const resp = await fetch('/api/requests/pending');
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        if (cancelled) return;
        const list = Array.isArray(data) ? data : (Array.isArray(data.items) ? data.items : []);
        setCount(list.length);
      } catch (err) {
        if (!cancelled) setError(err.message || String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    const timer = setInterval(load, 45000);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  if (loading) {
    return <span className="muted" style={{ fontSize: '11px', marginLeft: 4 }}>…</span>;
  }
  if (error) {
    return <span className="muted" style={{ fontSize: '11px', marginLeft: 4 }}>err</span>;
  }
  if (!count) {
    return <span className="muted" style={{ fontSize: '11px', marginLeft: 4 }}>нет новых</span>;
  }
  return (
    <span style={{ fontSize: '11px', marginLeft: 4 }}>
      новых: <b>{count}</b>
    </span>
  );
}
