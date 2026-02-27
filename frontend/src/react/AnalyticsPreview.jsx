import React, { useEffect, useState } from 'react';

/**
 * Небольшой React-компонент для превью аналитики внутри сайдбара.
 *
 * Использует API /api/analytics/summary и показывает краткую сводку:
 *  - всего адресов
 *  - активные/одобренные/отклонённые заявки
 *  - добавлено за 7 дней
 *
 * Это первый шаг по 5.3: сложный участок (аналитика) переведён
 * на React-компонент, при этом остальной фронт остаётся на ванильном JS.
 */
export default function AnalyticsPreview() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        setError(null);
        const resp = await fetch('/api/analytics/summary');
        if (!resp.ok) {
          throw new Error('HTTP ' + resp.status);
        }
        const json = await resp.json();
        if (!cancelled) {
          setData(json);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message || String(err));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    load();
    // Можно обновлять по hover/фокусу позже,
    // сейчас достаточно одного запроса при монтировании.
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <div className="muted" style={{ fontSize: '11px' }}>
        Загрузка аналитики…
      </div>
    );
  }
  if (error) {
    return (
      <div className="muted" style={{ fontSize: '11px' }}>
        Ошибка аналитики: {error}
      </div>
    );
  }
  if (!data) {
    return null;
  }

  const total = data.total || 0;
  const pending = data.pending || 0;
  const approved = data.approved || 0;
  const rejected = data.rejected || 0;
  const added7d = data.added_last_7d || 0;

  return (
    <div style={{ fontSize: '11px' }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>Мини‑сводка</div>
      <div className="muted" style={{ marginBottom: 4 }}>
        Быстрый взгляд на систему прямо в сайдбаре. Полная аналитика доступна по кнопке
        <span style={{ marginLeft: 4 }}>📊</span> в шапке.
      </div>
      <div className="section" style={{ marginBottom: 4 }}>
        <div>Всего адресов: <b>{total}</b></div>
        <div>Активных заявок: <b>{pending}</b></div>
        <div>Одобрено: <b>{approved}</b></div>
        <div>Отклонено: <b>{rejected}</b></div>
        <div>За 7 дней добавлено: <b>{added7d}</b></div>
      </div>
    </div>
  );
}
