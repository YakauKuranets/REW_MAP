/* ========= UI / UX helpers ========= */
/**
 * Модуль:
 *  - ensureInjectedStyles (микро-анимации, ripple)
 *  - контекстное меню карты (ensureContextMenu / openMapMenu / closeMapMenu)
 *  - showToast
 *  - темы / акценты (applyTheme / applyAccent / toggleTheme)
 *  - initShortcuts (горячие клавиши)
 *  - initGeolocateControl (кнопка "мое местоположение")
 *
 * Экспортируем в window.*, чтобы main.js и другие модули могли использовать эти функции.
 */
(function() {
  function ensureInjectedStyles() {
    injectStyleOnce('ux-spin-bump-ripple', `
      @keyframes spin360 { to { transform: rotate(360deg); } }
      #btn-settings:hover { animation: spin360 1.2s linear infinite; }
      @media (prefers-reduced-motion: reduce) {
        #btn-settings:hover { animation: none !important; }
      }
      @keyframes bump { 0% { transform: translateY(0) scale(1); } 40% { transform: translateY(-2px) scale(1.12); } 100% { transform: translateY(0) scale(1); } }
      .marker--bump { animation: bump .35s ease; }
      .btn, .icon { position: relative; overflow: hidden; }
      .btn .ripple, .icon .ripple {
        position: absolute; left: 0; top: 0; width: 8px; height: 8px; border-radius: 50%;
        transform: translate(-50%, -50%) scale(0); opacity: .45; background: currentColor; pointer-events: none;
        animation: ripple .6s ease-out forwards; mix-blend-mode: screen;
      }
      @keyframes ripple { to { transform: translate(-50%, -50%) scale(18); opacity: 0; } }
      #map-context-menu {
        position: fixed; min-width: 200px; background: var(--card); color: inherit;
        border: 1px solid rgba(0,0,0,.1); border-radius: 8px; box-shadow: var(--shadow);
        z-index: 7002; display: none; overflow: hidden;
      }
      #map-context-menu.open { display: block; }
      #map-context-menu .mi { padding: 8px 12px; font-size: 14px; display: flex; align-items: center; gap: 8px; cursor: pointer; }
      #map-context-menu .mi:hover { background: rgba(0,0,0,.06); }
      #map-context-menu .sep { height: 1px; background: rgba(0,0,0,.06); margin: 4px 0; }
      body.dark #map-context-menu { border-color: rgba(255,255,255,.08); }
      body.dark #map-context-menu .mi:hover { background: rgba(255,255,255,.06); }
    `);
  }

  
function t(key, vars){
  try{
    if(window.i18n && typeof window.i18n.t === 'function') return window.i18n.t(key, vars);
  }catch(_){}
  const base = String(key || '');
  if(!vars) return base;
  return base.replace(/\{(\w+)\}/g, (m,k) => (vars[k]!=null ? String(vars[k]) : m));
}

/* ========= Глобальные слои и состояние ========= */
  let map, markersLayer, markersCluster, tileLayer;
  let zonesLayer, drawControl;
  let radiusSearchActive = false;
  let radiusCircle = null;
  let _pendingZoneLayer = null;

  let mapDownloadStart = null;
  let geocodeDownloadStart = null;

  const markerMap = {};
  const listMap = {};
  let currentSelectedId = null;

  /* ========= Контекст-меню карты (правый клик) ========= */
  let __ctxLL = null;
  let __ctxMenu = null;
  let __ctxDocCaptureBound = false;

  /* ========= Lazy loader: incidents_ui.js может не быть подключён на некоторых страницах ========= */
  function ensureScriptLoaded(src){
    return new Promise((resolve) => {
      try{
        const existed = Array.from(document.getElementsByTagName('script'))
          .some(s => (s.getAttribute('src') || '').includes(src));
        if(existed) return resolve(true);
        const s = document.createElement('script');
        s.src = src + (src.includes('?') ? '&' : '?') + 'v=' + Date.now();
        s.async = true;
        s.onload = () => resolve(true);
        s.onerror = () => resolve(false);
        document.head.appendChild(s);
      }catch(_){ resolve(false); }
    });
  }

  async function ensureIncidentsLoaded(){
    if(window.IncidentsUI && typeof window.IncidentsUI.openModalAt === 'function') return true;
    // пытаемся подгрузить модуль, если его забыли подключить на странице
    await ensureScriptLoaded('/static/js/incidents_ui.js');
    return !!(window.IncidentsUI && typeof window.IncidentsUI.openModalAt === 'function');
  }

  function bindCtxDocCaptureOnce(){
    if(__ctxDocCaptureBound) return;
    __ctxDocCaptureBound = true;

    // В разных сборках/модулях могли появиться дополнительные обработчики кликов,
    // которые, например, копируют координаты. Чтобы пункт "Добавить инцидент"
    // ВСЕГДА открывал модалку инцидента, перехватываем клики по меню на уровне document
    // в capture-фазе (самый ранний этап обработки события).
    document.addEventListener('click', (ev) => {
      const mi = ev.target && ev.target.closest ? ev.target.closest('#map-context-menu .mi') : null;
      if(!mi) return;
      const menuEl = document.getElementById('map-context-menu');
      if(!menuEl || !menuEl.classList.contains('open')) return;
      __ctxMenu = menuEl;

      try{ ev.preventDefault(); ev.stopPropagation(); ev.stopImmediatePropagation && ev.stopImmediatePropagation(); }catch(_){ }

      const cmd = mi.getAttribute('data-cmd');
      if(cmd === 'cancel') { closeMapMenu(); return; }
      const ll = __ctxLL || window.__cc_ctxLL;
      if(!ll) { closeMapMenu(); return; }
      const lat = Number(ll.lat.toFixed(6));
      const lon = Number(ll.lng.toFixed(6));
      closeMapMenu();

      if(cmd === 'add'){
        // "Добавить метку" = форма объекта/метки в точке клика.
        if (window.ObjectsUI && typeof window.ObjectsUI.openCreateAt === 'function') {
          window.ObjectsUI.openCreateAt(lat, lon);
          return;
        }
        if (typeof openAdd === 'function') {
          openAdd({ id: null, name: '', address: '', lat, lon, notes: '', description: '',
            status: 'Локальный доступ', link: '', category: 'Видеонаблюдение' });
          return;
        }
        showToast('Не найден обработчик добавления объекта/метки');
        return;
      }

      if(cmd === 'incident'){
        // Новый пункт: "Добавить инцидент" — открываем модалку инцидента.
        // (1) если модуль не загружен — подгружаем лениво
        ensureIncidentsLoaded().then((ok) => {
          if(ok){
            try{ window.IncidentsUI.openModalAt(lat, lon); }catch(_){ }
          }else{
            showToast('Модуль инцидентов не загружен на этой странице');
          }
        });
        return;
      }

      if(cmd === 'radius'){
        let km = prompt(t('map_ctx_radius_prompt'), '1.0');
        if (km == null) return;
        km = parseFloat(km);
        if (!km || km <= 0) { showToast(t('map_ctx_radius_invalid'), 'error'); return; }
        startRadiusSearch(km, __ctxLL);
      }
    }, true);
  }

  function ensureContextMenu() {
    if (!__ctxMenu) {
      __ctxMenu = document.getElementById('map-context-menu');
      // Если меню уже существовало, могли быть навешаны чужие обработчики (например, копирование координат).
      // Заменяем узел на свежий клон, чтобы гарантированно сбросить все старые listeners.
      if (__ctxMenu) {
        const fresh = __ctxMenu.cloneNode(false);
        fresh.id = 'map-context-menu';
        try { __ctxMenu.parentNode && __ctxMenu.parentNode.replaceChild(fresh, __ctxMenu); } catch (_) {}
        __ctxMenu = fresh;
      }
      // Порядок пунктов: метка → радиус → отмена → инцидент
      const html = `
        <div class="mi" data-cmd="add"><span>📍</span><span>${t('map_ctx_add_here')}</span></div>
        <div class="mi" data-cmd="radius"><span>🧭</span><span>${t('map_ctx_radius')}</span></div>
        <div class="sep"></div>
        <div class="mi" data-cmd="cancel"><span>✖️</span><span>${t('map_ctx_cancel')}</span></div>
        <div class="mi" data-cmd="incident"><span>⚠️</span><span>${t('map_ctx_add_incident_here')}</span></div>
      `;
      if (!__ctxMenu) {
        // создаём минимальное меню, если его нет в HTML
        __ctxMenu = document.createElement('div');
        __ctxMenu.id = 'map-context-menu';
        document.body.appendChild(__ctxMenu);
      }
      // Всегда приводим разметку к нашей версии, чтобы cmd не "поплыл".
      __ctxMenu.innerHTML = html;
      __ctxMenu.dataset.coreui = '1';
      // Перехват кликов по меню в capture-фазе (см. bindCtxDocCaptureOnce)
      bindCtxDocCaptureOnce();
      document.addEventListener('click', (ev) => {
        if (!__ctxMenu || !__ctxMenu.classList.contains('open')) return;
        if (!__ctxMenu.contains(ev.target)) closeMapMenu();
      });
      document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape') closeMapMenu(); });
    }
  }
  function openMapMenu(pixel, latlng) {
    ensureContextMenu();
    __ctxLL = latlng;
    try{ window.__cc_ctxLL = latlng; }catch(_){ }
    if (!__ctxMenu) return;
    // Позиционируем меню в координатах viewport (position:fixed).
    // И дополнительно "зажимаем" в окно, чтобы меню не уезжало за край.
    let x = Number(pixel && pixel.x);
    let y = Number(pixel && pixel.y);
    if(!isFinite(x) || !isFinite(y)) { x = 20; y = 20; }

    __ctxMenu.style.left = Math.round(x) + 'px';
    __ctxMenu.style.top  = Math.round(y) + 'px';
    __ctxMenu.classList.add('open');
    __ctxMenu.setAttribute('aria-hidden', 'false');

    try{
      const pad = 8;
      const r = __ctxMenu.getBoundingClientRect();
      if(x + r.width > window.innerWidth - pad) x = window.innerWidth - pad - r.width;
      if(y + r.height > window.innerHeight - pad) y = window.innerHeight - pad - r.height;
      if(x < pad) x = pad;
      if(y < pad) y = pad;
      __ctxMenu.style.left = Math.round(x) + 'px';
      __ctxMenu.style.top  = Math.round(y) + 'px';
    }catch(_){ }
  }
  function closeMapMenu() {
    if (!__ctxMenu) return;
    __ctxMenu.classList.remove('open');
    __ctxMenu.setAttribute('aria-hidden', 'true');
  }

  function showToast(message, type = 'default', duration = 3000) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = 'toast';
    if (type === 'success') toast.classList.add('success');
    else if (type === 'error') toast.classList.add('error');
    toast.textContent = message;
    container.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => {
      toast.classList.remove('show');
      toast.classList.add('hide');
      setTimeout(() => toast.parentElement && toast.parentElement.removeChild(toast), 300);
    }, duration);
  }

  function applyTheme(t) {
    if (t !== 'dark' && t !== 'light') t = 'light';
    document.body.classList.remove('light', 'dark');
    document.body.classList.add(t);
    try { localStorage.setItem('theme', t); } catch (_) {}
const b = $('#btn-theme');
    if (b) b.textContent = (t === 'dark') ? '☀️' : '🌙';
  

    // синхронизация чекбокса темы (в настройках)
    const cb = document.getElementById('theme-toggle-checkbox');
    if (cb) cb.checked = (t === 'dark');

  }
  function applyAccent(t) {
    const accentClasses = ['theme-blue'];
    document.body.classList.remove(...accentClasses);
    if (t) document.body.classList.add('theme-' + t);
    try { localStorage.setItem('accent', t || ''); } catch (_) {}
  }
  function toggleTheme() {
    let _cur = 'light';
    try { _cur = (localStorage.getItem('theme') || 'light'); } catch (_) { _cur = 'light'; }
    const t = (_cur === 'dark') ? 'light' : 'dark';
    applyTheme(t);
  }

  function initShortcuts() {
    const isEditable = (el) => el && (['INPUT','TEXTAREA'].includes(el.tagName) || el.isContentEditable);


    document.addEventListener('keydown', (e) => {
      // Некоторые события могут не содержать поле key. Если его нет, просто игнорируем.
      if (!e || typeof e.key === 'undefined') {
        return;
      }
      const active = document.activeElement;

      // ESC — закрыть модалки/меню
          if (e.key === 'Escape') {
        try {
          document.getElementById('notif-menu')?.classList?.remove?.('open');
          document.getElementById('access-menu')?.classList?.remove?.('open');
          document.getElementById('file-menu')?.classList?.remove?.('open');
          document.getElementById('modal-backdrop')?.classList?.remove?.('open');
          document.getElementById('settings-backdrop')?.classList?.remove?.('open');
          document.getElementById('zone-backdrop')?.classList?.remove?.('open');
          closePhotoModal(); // закрываем модалку с фото
        } catch(_) {}
        return;
      }


      // Не перехватывать печать в полях
      if (isEditable(active)) return;

      // / — фокус на поиск
      if (e.key === '/') {
        e.preventDefault();
        document.getElementById('search')?.focus();
        return;
      }

      // t — тема
      if (e.key.toLowerCase() === 't') {
        e.preventDefault();
        try {
          const cur = (localStorage.getItem('theme') || 'light');
          const next = (cur === 'light') ? 'dark' : 'light';
          applyTheme(next);
          localStorage.setItem('theme', next);
          showToast(t('map_theme_toast_fmt', { theme: (next === 'dark') ? t('map_theme_dark_label') : t('map_theme_light_label') }));
        } catch(_) {}
        return;
      }

      // s — сайдбар
      if (e.key.toLowerCase() === 's') {
        e.preventDefault();
        toggleSidebar();
        return;
      }

      // a — добавить
      if (e.key.toLowerCase() === 'a') {
        e.preventDefault();
        if (typeof openAdd === 'function') openAdd();
        return;
      }

      // ? — подсказка
      if (e.key === '?') {
        e.preventDefault();
        showToast(t('map_shortcuts_help'));
        return;
      }
    });
  }

  /* ========= Geolocate control (Leaflet) ========= */
  function initGeolocateControl() {
  const btn = document.getElementById('btn-geolocate');
  // Кнопки нет — тихо выходим
  if (!btn) {
    console.warn('initGeolocateControl: #btn-geolocate not found');
    return;
  }

  // Карта ещё не инициализирована — тоже выходим
  if (typeof map === 'undefined' || !map || typeof map.setView !== 'function') {
    console.warn('initGeolocateControl: map is not ready');
    return;
  }

  // Если браузер не поддерживает геолокацию — скрываем кнопку
  if (!('geolocation' in navigator)) {
    btn.style.display = 'none';
    return;
  }

  // Навешиваем обработчик только один раз через helper bindOnce.
  if (typeof window.bindOnce === 'function') {
    window.bindOnce(btn, 'click', () => {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const lat = pos.coords.latitude;
          const lon = pos.coords.longitude;
          try {
            const currentZoom = typeof map.getZoom === 'function' ? map.getZoom() : 13;
            const targetZoom = Math.max(currentZoom, 14);
            map.setView([lat, lon], targetZoom);
          } catch (err) {
            console.warn('Geolocate move failed', err);
          }
        },
        (err) => {
          console.warn('Geolocate error', err);
          try {
            showToast('Не удалось получить геопозицию', 'error');
          } catch (_) {}
        },
        { enableHighAccuracy: true, timeout: 10000 }
      );
    }, 'Geolocate');
  } else {
    // Fallback: без helper — простой разовый биндинг
    if (!btn.dataset.boundGeolocate) {
      btn.dataset.boundGeolocate = '1';
      btn.addEventListener('click', () => {
        navigator.geolocation.getCurrentPosition(
          (pos) => {
            const lat = pos.coords.latitude;
            const lon = pos.coords.longitude;
            try {
              const currentZoom = typeof map.getZoom === 'function' ? map.getZoom() : 13;
              const targetZoom = Math.max(currentZoom, 14);
              map.setView([lat, lon], targetZoom);
            } catch (err) {
              console.warn('Geolocate move failed', err);
            }
          },
          (err) => {
            console.warn('Geolocate error', err);
            try {
              showToast('Не удалось получить геопозицию', 'error');
            } catch (_) {}
          },
          { enableHighAccuracy: true, timeout: 10000 }
        );
      });
    }
  }
}


  // Экспорт в глобальную область


  function initThemeToggleCheckbox() {
    const cb = document.getElementById('theme-toggle-checkbox');
    if (!cb) return;
    if (cb.dataset.boundTheme) return;
    cb.dataset.boundTheme = '1';

    let cur = 'light';
    try { cur = (localStorage.getItem('theme') || 'light'); } catch (_) { cur = 'light'; }
    cb.checked = (cur === 'dark');

    cb.addEventListener('change', () => {
      applyTheme(cb.checked ? 'dark' : 'light');
    });
  }


  /* ========= Язык (RU/EN) ========= */
  function applyLangUI(){
    try{
      if(window.i18n && typeof window.i18n.applyDomTranslations === 'function'){
        window.i18n.applyDomTranslations(document);
      }
    }catch(_){}
    try{
      const btn = document.getElementById('btn-lang');
      if(btn) btn.textContent = (window.i18n && window.i18n.getLang && window.i18n.getLang()==='en') ? 'EN' : 'RU';
    }catch(_){}
    try{
      // Ререндер списка/меток (чтобы статусы/категории показывались на выбранном языке)
      window.refreshList && window.refreshList();
    }catch(_){}
  }

  function initLangToggle(){
    const btn = document.getElementById('btn-lang');
    if(!btn) return;
    if(btn.dataset && btn.dataset.boundLang) return;
    if(btn.dataset) btn.dataset.boundLang = '1';

    // restore default (ru)
    try{
      if(window.i18n && typeof window.i18n.setLang === 'function'){
        window.i18n.setLang(window.i18n.getLang());
      }
    }catch(_){}
    applyLangUI();

    btn.addEventListener('click', () => {
      try{
        if(window.i18n && typeof window.i18n.setLang === 'function'){
          const cur = window.i18n.getLang();
          window.i18n.setLang(cur === 'en' ? 'ru' : 'en');
        }
      }catch(_){}
      applyLangUI();
    });

    window.addEventListener('ui:lang', () => applyLangUI());
  }

  /* ========= Кнопки создания инцидента (верхняя панель) ========= */
  function initIncidentButtons(){
    // Кнопка может быть либо btn-object-add (переиспользована под инцидент), либо legacy btn-incident-add
    const btn = document.getElementById('btn-object-add') || document.getElementById('btn-incident-add');
    if(!btn) return;
    if(btn.dataset && btn.dataset.boundIncidentBtn) return;
    if(btn.dataset) btn.dataset.boundIncidentBtn = '1';

    // Если это переиспользованный "Добавить объект", то он должен работать как инцидент.
    // Вешаем обработчик в capture-фазе, чтобы перехватить клик раньше модулей объектов,
    // и гасим propagation, чтобы ничего не дублировалось.
    btn.addEventListener('click', (ev) => {
      try{ ev.preventDefault(); ev.stopPropagation(); ev.stopImmediatePropagation && ev.stopImmediatePropagation(); }catch(_){ }
      ensureIncidentsLoaded().then((ok) => {
        if(!ok){ showToast('Модуль инцидентов не загружен на этой странице'); return; }
        const ui = window.IncidentsUI;
        if(ui && typeof ui.startCreate === 'function'){
          ui.startCreate();
          return;
        }
        // fallback: открыть модалку в центре карты
        const m = window.dutyMap || window.__map || null;
        if(ui && typeof ui.openModalAt === 'function' && m && typeof m.getCenter === 'function'){
          const c = m.getCenter();
          ui.openModalAt(c.lat, c.lng);
          return;
        }
        showToast('Не найден обработчик создания инцидента');
      });
    }, true);
  }

  // Инициализация чекбокса темы (если он есть в шаблоне)
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initThemeToggleCheckbox);
    document.addEventListener('DOMContentLoaded', initLangToggle);
    document.addEventListener('DOMContentLoaded', initIncidentButtons);
  } else {
    initThemeToggleCheckbox();
    initLangToggle();
    initIncidentButtons();
  }

  window.ensureInjectedStyles = ensureInjectedStyles;
  window.ensureContextMenu = ensureContextMenu;
  window.openMapMenu = openMapMenu;
  window.closeMapMenu = closeMapMenu;
  window.showToast = showToast;
  window.applyTheme = applyTheme;
  window.applyAccent = applyAccent;
  window.toggleTheme = toggleTheme;
  window.initShortcuts = initShortcuts;
  window.initGeolocateControl = initGeolocateControl;

  /* ========= Хелпер для привязки событий только один раз ========= */
  /**
   * Привязывает обработчик к элементу лишь однажды. Если обработчик уже был
   * привязан (с использованием этого метода), повторное привязывание не выполняется.
   *
   * @param {HTMLElement} el       Элемент, к которому нужно привязать обработчик
   * @param {string} evt           Название события (например, 'click')
   * @param {Function} handler     Функция‑обработчик события
   * @param {string} [key]         Необязательный уникальный ключ. Если указан, то в data‑атрибутах элемента
   *                               будет использован именно этот ключ. Иначе ключ строится по имени события.
   */
  function bindOnce(el, evt, handler, key) {
    if (!el || typeof el.addEventListener !== 'function') return;
    const attr = key ? `bound${key}` : `bound${evt}`;
    if (el.dataset && el.dataset[attr]) return;
    if (el.dataset) el.dataset[attr] = '1';
    el.addEventListener(evt, handler);
  }
  // Экспортируем helper в глобальную область
  window.bindOnce = bindOnce;
})();
