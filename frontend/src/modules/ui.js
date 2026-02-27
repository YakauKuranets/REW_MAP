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

  function bindCtxDocCaptureOnce(){
    if(__ctxDocCaptureBound) return;
    __ctxDocCaptureBound = true;

    // В разных местах приложения могли появиться доп. обработчики,
    // которые копируют координаты при клике. Чтобы пункт "Добавить инцидент"
    // ВСЕГДА открывал модалку, перехватываем клик в capture-фазе на document.
    document.addEventListener('click', (ev) => {
      const mi = ev.target && ev.target.closest ? ev.target.closest('#map-context-menu .mi') : null;
      if(!mi) return;
      const menuEl = document.getElementById('map-context-menu');
      if(!menuEl || !menuEl.classList.contains('open')) return;
      __ctxMenu = menuEl;

      try{ ev.preventDefault(); ev.stopPropagation(); ev.stopImmediatePropagation && ev.stopImmediatePropagation(); }catch(_){ }

      const cmd = mi.getAttribute('data-cmd');
      if(cmd === 'cancel'){ closeMapMenu(); return; }
      const ll = __ctxLL || window.__cc_ctxLL;
      if(!ll){ closeMapMenu(); return; }
      const lat = Number(ll.lat.toFixed(6));
      const lon = Number(ll.lng.toFixed(6));
      closeMapMenu();

      if(cmd === 'add'){
        // "Добавить метку" = форма объекта/метки в точке клика.
        if (window.ObjectsUI && typeof window.ObjectsUI.openCreateAt === 'function') {
          window.ObjectsUI.openCreateAt(lat, lon);
          return;
        }
        if (typeof window.openAdd === 'function') {
          window.openAdd({ id: null, name: '', address: '', lat, lon, notes: '', description: '',
            status: 'Локальный доступ', link: '', category: 'Видеонаблюдение' });
          return;
        }
        showToast('Не найден обработчик добавления объекта/метки');
        return;
      }

      if(cmd === 'incident'){
        ensureIncidentsLoaded().then((ok) => {
          if(ok){
            try{ window.IncidentsUI.openModalAt(lat, lon); }catch(_){ }
          }else{
            showToast('Модуль инцидентов не загружен');
          }
        });
        return;
      }

      if(cmd === 'radius'){
        let km = prompt('Радиус (км):', '1.0');
        if (km == null) return;
        km = parseFloat(km);
        if (!km || km <= 0) { showToast('Введите положительный радиус', 'error'); return; }
        startRadiusSearch(km, __ctxLL);
        return;
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
        <div class="mi" data-cmd="add"><span>📍</span><span>Добавить метку здесь</span></div>
        <div class="mi" data-cmd="radius"><span>🧭</span><span>Фильтр радиуса…</span></div>
        <div class="sep"></div>
        <div class="mi" data-cmd="cancel"><span>✖️</span><span>Отмена</span></div>
        <div class="mi" data-cmd="incident"><span>⚠️</span><span>Добавить инцидент здесь</span></div>
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
      __ctxMenu.addEventListener('click', async (ev) => {
        try{ ev.preventDefault(); ev.stopPropagation(); ev.stopImmediatePropagation && ev.stopImmediatePropagation(); }catch(_){}
        const btn = ev.target.closest('.mi');
        if (!btn) return;
        const cmd = btn.getAttribute('data-cmd');
        if (cmd === 'cancel') { closeMapMenu(); return; }
        if (!__ctxLL) return;
        const lat = Number(__ctxLL.lat.toFixed(6));
        const lon = Number(__ctxLL.lng.toFixed(6));
        if (cmd === 'add') {
          closeMapMenu();
          openAdd({ id: null, name: '', address: '', lat, lon, notes: '', description: '',
            status: 'Локальный доступ', link: '', category: 'Видеонаблюдение' });
          showToast(`Координаты подставлены: ${lat}, ${lon}`);
          return;
        }
        if (cmd === 'incident') {
          closeMapMenu();
          const lat2 = Number(__ctxLL.lat.toFixed(6));
          const lon2 = Number(__ctxLL.lng.toFixed(6));
          if (window.IncidentsUI && typeof window.IncidentsUI.openModalAt === 'function') {
            window.IncidentsUI.openModalAt(lat2, lon2);
            showToast(`Координаты подставлены: ${lat2}, ${lon2}`);
          } else {
            showToast('Модуль инцидентов не загружен');
          }
          return;
        }
        if (cmd === 'radius') {
          closeMapMenu();
          let km = prompt('Радиус (км):', '1.0');
          if (km == null) return;
          km = parseFloat(km);
          if (!km || km <= 0) { showToast('Введите положительный радиус', 'error'); return; }
          startRadiusSearch(km, __ctxLL);
          return;
        }
      }, true);
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

  // --- Lazy-load incidents module for pages where it isn't bundled ---
  function ensureScriptLoaded(src){
    return new Promise((resolve) => {
      try{
        const existing = Array.from(document.scripts || []).find(s => (s.src || '').includes(src));
        if(existing) return resolve(true);
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
    await ensureScriptLoaded('/static/js/incidents_ui.js');
    return !!(window.IncidentsUI && typeof window.IncidentsUI.openModalAt === 'function');
  }

  function applyTheme(t) {
    if (t !== 'dark' && t !== 'light') t = 'light';
    document.body.classList.remove('light', 'dark');
    document.body.classList.add(t);
    localStorage.setItem('theme', t);
    const b = $('#btn-theme');
    if (b) b.textContent = (t === 'dark') ? '☀️' : '🌙';
  }
  function applyAccent(t) {
    const accentClasses = ['theme-blue'];
    document.body.classList.remove(...accentClasses);
    if (t) document.body.classList.add('theme-' + t);
    try { localStorage.setItem('accent', t || ''); } catch (_) {}
  }
  function toggleTheme() {
    const t = (localStorage.getItem('theme') === 'dark') ? 'light' : 'dark';
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
          showToast(`Тема: ${next === 'dark' ? 'тёмная' : 'светлая'}`);
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
        showToast(
          'Сочетания клавиш:\\n' +
          '  / — поиск\\n' +
          '  t — тема светлая/тёмная\\n' +
          '  s — показать/скрыть сайдбар\\n' +
          '  a — добавить запись\\n' +
          '  Esc — закрыть окна'
        );
        return;
      }
    });
  }

  /* ========= Geolocate control (Leaflet) ========= */
  function initGeolocateControl() {
    if (!(window.L && window.map)) return;
    const GeoBtn = L.Control.extend({
      onAdd: function() {
        const btn = L.DomUtil.create('a', 'leaflet-bar geolocate-btn');
        btn.href = '#';
        btn.title = 'Моё местоположение';
        btn.innerHTML = '◎';
        L.DomEvent.on(btn, 'click', (e) => {
          L.DomEvent.stop(e);
          if (!navigator.geolocation) { showToast('Геолокация недоступна', 'error'); return; }
          navigator.geolocation.getCurrentPosition(
            (pos) => {
              const { latitude, longitude } = pos.coords;
              const latlng = L.latLng(latitude, longitude);
              map.setView(latlng, Math.max(map.getZoom(), 14));
              L.circleMarker(latlng, { radius: 6, color: '#2563eb', weight: 2, fillOpacity: 0.6 }).addTo(map)
                .bindPopup('Вы здесь').openPopup();
            },
            (err) => { console.warn(err); showToast('Не удалось получить местоположение', 'error'); },
            { enableHighAccuracy: true, timeout: 8000, maximumAge: 30000 }
          );
        });
        return btn;
      }
    });
    map.addControl(new GeoBtn({ position: 'topleft' }));
  }

  // Экспорт в глобальную область
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
})();
