/* sidebar_tabs.js

Command Center: табы левой панели (Объекты с камерами / Инциденты).

Требования:
  - без "магии": только show/hide уже существующих блоков
  - запоминать выбранный таб в localStorage
  - поддерживать badge‑счётчики (примерно)
  - показать агрегированные непрочитанные чаты (shift/incident) прямо на табах

Примечания:
  - агрегат читается из /api/chat2/channels (там уже есть unread по каналам)
  - обновляемся периодически + по realtime (chat2_message/chat2_receipt)
*/

(() => {
  const LS_KEY = 'cc_sidebar_tab';

  function q(sel){ return document.querySelector(sel); }
  function qa(sel){ return Array.from(document.querySelectorAll(sel)); }

  function setTab(tabName){
    const tabs = qa('.ap-sidebar-tabs .ap-stab');
    const panes = qa('.ap-sidebar-pane');
    tabs.forEach(btn => {
      const on = btn.getAttribute('data-stab') === tabName;
      btn.classList.toggle('active', on);
      btn.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    panes.forEach(p => {
      const on = p.getAttribute('data-spane') === tabName;
      p.classList.toggle('active', on);
      if(on) p.removeAttribute('hidden');
      else p.setAttribute('hidden', '');
    });
    try{ localStorage.setItem(LS_KEY, tabName); }catch(_){ }
  }

  function getSavedTab(){
    try{ return localStorage.getItem(LS_KEY) || ''; }catch(_){ return ''; }
  }

  function syncBadges(){
    // Объекты/Инциденты: используем счётчики из DOM
    const incidents = (q('#count-incidents')?.textContent || '0').trim();
    const objects = (q('#count-objects')?.textContent || '0').trim();
    const bi = q('#tab-incidents-badge');
    const bo = q('#tab-objects-badge');
    if(bi) bi.textContent = incidents || '0';
    if(bo) bo.textContent = objects || '0';
  }

  // ===== unread aggregate =====
  let lastUnreadFetchAt = 0;
  let unreadDebounceTimer = null;

  function setUnreadBadge(el, n){
    if(!el) return;
    const x = Number(n || 0) || 0;
    el.textContent = String(x);
    el.style.display = x > 0 ? '' : 'none';
  }

  async function fetchUnreadTotals(){
    try{
      const resp = await fetch('/api/chat2/channels', { cache: 'no-store' });
      if(!resp.ok) return null;
      const data = await resp.json();
      if(!Array.isArray(data)) return null;
      let total = 0;
      let incidents = 0;
      data.forEach((ch) => {
        const u = Number(ch?.unread || 0) || 0;
        if(u <= 0) return;
        total += u;
        if(ch?.type === 'incident') incidents += u;
      });
      return { total, incidents };
    }catch(_e){
      return null;
    }
  }

  async function refreshUnreadTabs({force=false} = {}){
    const now = Date.now();
    // защита от частых запросов при realtime-спаме
    if(!force && (now - lastUnreadFetchAt) < 1200) return;
    lastUnreadFetchAt = now;

    const totals = await fetchUnreadTotals();
    if(!totals) return;

    setUnreadBadge(q('#tab-incidents-unread'), totals.incidents);
    setUnreadBadge(q('#btn-chat-unread'), totals.total);
  }

  function refreshUnreadTabsDebounced(){
    if(unreadDebounceTimer) clearTimeout(unreadDebounceTimer);
    unreadDebounceTimer = setTimeout(() => {
      unreadDebounceTimer = null;
      refreshUnreadTabs({force:false});
    }, 250);
  }

  function bindRealtimeUnread(){
    if(!window.Realtime || typeof window.Realtime.on !== 'function') return;
    try{ window.Realtime.connect(); }catch(_){ }
    try{
      window.Realtime.on('chat2_message', () => refreshUnreadTabsDebounced());
      window.Realtime.on('chat2_receipt', () => refreshUnreadTabsDebounced());
    }catch(_){ }
  }

  function init(){
    const tabs = qa('.ap-sidebar-tabs .ap-stab');
    if(!tabs.length) return;

    tabs.forEach(btn => {
      btn.addEventListener('click', () => {
        const t = btn.getAttribute('data-stab');
        if(t) setTab(t);
      });
    });

    // Валидация сохранённого таба (в старых сборках мог быть 'units')
    const saved = getSavedTab();
    const hasSaved = !!saved && !!q(`.ap-sidebar-tabs .ap-stab[data-stab="${saved}"]`);
    if(hasSaved) setTab(saved);
    else setTab('objects');

    // экспорт для других модулей (чат, панели)
    window.CC = window.CC || {};
    window.CC.refreshUnreadTabs = (force=false) => refreshUnreadTabs({force: !!force});

    syncBadges();
    refreshUnreadTabs({force:true});
    bindRealtimeUnread();

    setInterval(syncBadges, 1000);
    // fallback polling (если WS не работает)
    setInterval(() => refreshUnreadTabs({force:false}), 12000);
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init);
  }else{
    init();
  }
})();
