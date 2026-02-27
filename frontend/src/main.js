/**
 * Входная точка Vite-фронтенда.
 *
 * Здесь мы подключаем:
 *  - реальные ES-модули фронта (sidebar_module и т.п.), чтобы они попали в бандл;
 *  - React-компоненты для сложных участков (аналитика, чат, колокольчик).
 *
 * Боевой интерфейс карты по-прежнему может работать и без Vite:
 * если нет static/dist/manifest.json, Flask использует старые
 * static/js/*.js. Когда manifest есть, подхватывается этот бандл.
 */

import {
  toggleSidebar,
  renderList,
  updateSummary,
  renderQuickCounters,
  updateFilterSummary,
  updateCurrentFilterLabel,
  computeCounts
} from './modules/sidebar_module.js';

import React from 'react';
import ReactDOM from 'react-dom/client';
import AnalyticsPreview from './react/AnalyticsPreview.jsx';
import ChatPreview from './react/ChatPreview.jsx';
import RequestsPreview from './react/RequestsPreview.jsx';

// Лёгкий лог, чтобы убедиться, что модуль sidebar подключён.
console.log('[Vite] sidebar_module подключён:', {
  hasToggleSidebar: typeof toggleSidebar === 'function',
  hasRenderList: typeof renderList === 'function',
  hasUpdateSummary: typeof updateSummary === 'function',
  hasComputeCounts: typeof computeCounts === 'function'
});

document.addEventListener('DOMContentLoaded', () => {
  // React-превью аналитики в сайдбаре.
  const analyticsRoot = document.getElementById('analytics-react-root');
  if (analyticsRoot) {
    try {
      const root = ReactDOM.createRoot(analyticsRoot);
      root.render(<AnalyticsPreview />);
      console.log('[Vite] React AnalyticsPreview смонтирован');
    } catch (err) {
      console.error('[Vite] Не удалось смонтировать AnalyticsPreview:', err);
    }
  }

  // Индикатор чата в шапке.
  const chatRoot = document.getElementById('chat-react-root');
  if (chatRoot) {
    try {
      const root = ReactDOM.createRoot(chatRoot);
      root.render(<ChatPreview />);
      console.log('[Vite] React ChatPreview смонтирован');
    } catch (err) {
      console.error('[Vite] Не удалось смонтировать ChatPreview:', err);
    }
  }

  // Индикатор заявок в хедере колокольчика.
  const reqRoot = document.getElementById('requests-react-root');
  if (reqRoot) {
    try {
      const root = ReactDOM.createRoot(reqRoot);
      root.render(<RequestsPreview />);
      console.log('[Vite] React RequestsPreview смонтирован');
    } catch (err) {
      console.error('[Vite] Не удалось смонтировать RequestsPreview:', err);
    }
  }
});

// В будущем сюда можно добавлять:
//  - полноценную React-панель аналитики (замену модалки);
//  - React-UI чата (список диалогов + окно переписки);
//  - продвинутый дашборд с графиками.
