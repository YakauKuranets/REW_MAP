/* ========= Sidebar & layout module ========= */
/**
 * Модуль отвечает только за переключение сайдбара.
 * Вся логика списка/фильтров пока остаётся в main.js, но сам переключатель
 * вынесен сюда как отдельный модуль.
 */
(function() {
  function toggleSidebar() {
    document.body.classList.toggle('sidebar-hidden');
    // Небольшая задержка, чтобы анимация завершилась перед invalidateSize
    setTimeout(() => {
      try {
        if (window.map && typeof window.map.invalidateSize === 'function') {
          window.map.invalidateSize();
        }
      } catch (_) {}
    }, 350);
  }

  window.toggleSidebar = toggleSidebar;
})();

/* ========= Address list & summary module ========= */
/**
 * Вынесенная из main.js логика:
 *  - renderList()
 *  - updateSummary()
 *  - быстрые чипы‑счётчики и подпись текущего фильтра.
 *
 * Функции работают с глобальными структурами (ITEMS, radiusFiltered,
 * markersCluster, markerMap, listMap и т.п.), которые инициализируются
 * в других модулях.
 */
(function() {
  function updateSummary() {

    const panel = document.getElementById('summary-panel');

    if (!panel) return;

    const items = radiusFiltered || ITEMS;

    const countsCat = { 'Видеонаблюдение': 0, 'Домофон': 0, 'Шлагбаум': 0 };

    let localCount = 0, remoteCount = 0;

    for (const it of items) {

      if (countsCat.hasOwnProperty(it.category)) countsCat[it.category]++;

      const status = (it.status || '').toLowerCase();

      if (status.includes('локал')) localCount++;

      else if (status.includes('удален')) remoteCount++;

    }

    panel.innerHTML =

      `<span>Видео: ${countsCat['Видеонаблюдение']}</span>` +

      `<span>Домофон: ${countsCat['Домофон']}</span>` +

      `<span>Шлагбаум: ${countsCat['Шлагбаум']}</span>` +

      `<span>Локальных: ${localCount}</span>` +

      `<span>Удаленных: ${remoteCount}</span>`;

  }



  function computeCounts(items) {

    const out = { total: items.length, video:0, dom:0, slag:0, local:0, remote:0 };

    for (const it of items) {

      const cat = (it.category || '').toLowerCase();

      if (cat.includes('видео')) out.video++;

      else if (cat.includes('домоф')) out.dom++;

      else if (cat.includes('шлаг')) out.slag++;

      const st = (it.status || '').toLowerCase();

      if (st.includes('локал')) out.local++;

      else if (st.includes('удал')) out.remote++;

    }

    return out;

  }



  function updateCurrentFilterLabel() {

    const el = document.getElementById('current-filter');

    if (!el) return;

    const catSel = document.getElementById('filter-category');

    const optLocal = document.getElementById('opt-local');

    const optRemote = document.getElementById('opt-remote');



    const catVal = (catSel && catSel.value) ? catSel.value.trim() : '';

    const isLocal = optLocal && optLocal.checked;

    const isRemote = optRemote && optRemote.checked;



    const parts = [];

    if (catVal) {

      parts.push(`категория = ${catVal}`);

    }

    if (isLocal && !isRemote) {

      parts.push('доступ = локальный');

    } else if (isRemote && !isLocal) {

      parts.push('доступ = удалённый');

    }



    if (!parts.length) {

      el.textContent = 'Фильтр: все адреса';

    } else {

      el.textContent = 'Фильтр: ' + parts.join(', ');

    }

  }



  function renderQuickCounters() {

    const wrap = document.getElementById('quick-counters');

    if (!wrap) return;

    const items = radiusFiltered || ITEMS;

    const c = computeCounts(items);

    wrap.innerHTML = '';



    const chips = [

      { k:'all',  label:`Все (${c.total})` },

      { k:'video', label:`Видео (${c.video})`, filter: { category: 'Видеонаблюдение' } },

      { k:'dom',   label:`Домофон (${c.dom})`, filter: { category: 'Домофон' } },

      { k:'slag',  label:`Шлагбаум (${c.slag})`, filter: { category: 'Шлагбаум' } },

      { k:'local', label:`Локальные (${c.local})`, filter: { status: 'Локальный доступ' } },

      { k:'remote',label:`Удалённые (${c.remote})`, filter: { status: 'Удаленный доступ' } },

    ];

    chips.forEach(ch => {

      const b = document.createElement('button');

      b.type = 'button';

      b.className = 'chip btn';

      b.textContent = ch.label;

      b.onclick = async () => {

        if (ch.k === 'all') {

          const sel = document.getElementById('filter-category');

          if (sel) sel.value = '';

          const l = document.getElementById('opt-local');  if (l) l.checked = false;

          const r = document.getElementById('opt-remote'); if (r) r.checked = false;

        } else if (ch.filter && ch.filter.category) {

          const sel = document.getElementById('filter-category');

          if (sel) sel.value = ch.filter.category;

        } else if (ch.filter && ch.filter.status) {

          const isLocal = ch.filter.status.toLowerCase().includes('локал');

          const l = document.getElementById('opt-local');  if (l) l.checked = isLocal;

          const r = document.getElementById('opt-remote'); if (r) r.checked = !isLocal;

        }

        await refresh();

        renderQuickCounters();

      };

      wrap.appendChild(b);

    });

  }



  function updateFilterSummary() {

    const el = document.getElementById('filter-summary');

    if (!el) return;

    const items = radiusFiltered || ITEMS;

    const total = Array.isArray(ITEMS) ? ITEMS.length : 0;

    const filtered = Array.isArray(items) ? items.length : 0;



    if (!total) {

      el.textContent = 'Адресов: 0';

      return;

    }

    if (radiusFiltered && filtered !== total) {

      el.textContent = `Адресов: ${total} (в радиусе: ${filtered})`;

    } else {

      el.textContent = `Адресов: ${total}`;

    }

  }



  function renderList() {

    const list = $('#list');

    if (!list) { console.warn('renderList: #list not found'); return; }

    list.innerHTML = '';

    const items = radiusFiltered || ITEMS;

    const cntEl = $('#count'); if (cntEl) cntEl.textContent = items.length;



    try { markersCluster.clearLayers(); } catch (_) { }

    for (const id in markerMap) delete markerMap[id];

    for (const id in listMap) delete listMap[id];



    if (!items.length) {

      list.innerHTML = '<div class="empty">Нет записей</div>';

      const bulkBtn = $('#btn-bulk-del'); if (bulkBtn) bulkBtn.disabled = true;

      renderQuickCounters();

      updateSummary();

      updateCurrentFilterLabel();

      updateFilterSummary();

      return;

    }



    for (const it of items) {

      const div = document.createElement('div'); div.className = 'item';

      const name = it.name || it.address || 'Без адреса';

      const addrEsc = escapeHTML(name);

      const statusEsc = escapeHTML(it.status || '');

      const catEsc = escapeHTML(it.category || '');

      const notes = it.notes || it.description || '';

      const descHtml = notes ? '<br>' + linkify(notes) : '';

      const linkHtml = it.link ? `<br><a href="${escapeHTML(it.link)}" target="_blank" rel="noopener noreferrer">${escapeHTML(it.link)}</a>` : '';

      // Photo indicator: if the item has a photo property, show a camera icon linking to the image

      const photoIconHtml = it.photo ? ` <a href="/uploads/${escapeAttr(it.photo)}" target="_blank" title="Фото">📷</a>` : '';



          // Используем иконки FontAwesome для категорий. Это обеспечивает

          // единообразный внешний вид и выравнивание. Если категорию

          // распознать не удалось — показываем обычную метку.

          const categoryIconMap = {

            'Видеонаблюдение': '<i class="fa-solid fa-video"></i>',

            'Домофон': '<i class="fa-solid fa-door-open"></i>',

            'Шлагбаум': '<i class="fa-solid fa-road-barrier"></i>',

          };

          const itemIcon = categoryIconMap[it.category] || '<i class="fa-solid fa-location-dot"></i>';

      // Формируем содержимое строки списка. Левая колонка (.info) содержит чекбокс, иконку категории,

      // адрес и бейджи (статус/категория). Правая колонка (.actions) содержит вертикальный столбик

      // иконок: фото (если есть), увеличительное стекло, карандаш и корзину.

      div.innerHTML = `<div class="row">

        <div class="info">

          <div class="main-line">

            <input type="checkbox" data-id="${it.id}">

            <span class="item-icon">${itemIcon}</span>

            <b>${addrEsc}</b>

          </div>

          <div class="badges">

            <span class="badge">${statusEsc}</span>

            <span class="badge">${catEsc}</span>

          </div>

        </div>

        <div class="actions">

          ${photoIconHtml}

          <button class="btn minimal" data-act="zoom">🔎</button>

          <button class="btn minimal" data-act="edit">✏️</button>

          <button class="btn minimal warn" data-act="del">🗑️</button>

        </div>

      </div>`;



      const btnZoom = div.querySelector('[data-act="zoom"]');

      const btnEdit = div.querySelector('[data-act="edit"]');

      const btnDel = div.querySelector('[data-act="del"]');



      if (btnZoom) btnZoom.onclick = () => { if (it.lat != null && it.lon != null) try { map.setView([it.lat, it.lon], 16); } catch (_) { } };

      if (btnEdit) btnEdit.onclick = () => openAdd(it);

      if (btnDel) btnDel.onclick = async () => { await fetch('/api/addresses/' + it.id, { method: 'DELETE' }); await refresh(); };



      list.appendChild(div);

      listMap[it.id] = div;

      div.addEventListener('click', (ev) => {

        const tag = ev.target.tagName.toLowerCase();

        if (tag === 'button' || tag === 'input' || tag === 'a') return;

        selectItem(it.id);

      });



      if (it.lat != null && it.lon != null) {

        try {

          const categoryMap = {

            'Видеонаблюдение': { cls: 'video', icon: '📹' },

            'Домофон': { cls: 'домофон', icon: '🚪' },

            'Шлагбаум': { cls: 'slagbaum', icon: '🚧' },

          };

          const cat = categoryMap[it.category] || {

            cls: (String(it.status || '').toLowerCase().includes('локал') ? 'local' : 'remote'),

            icon: '📍'

          };

          const htmlIcon = `<div class="marker marker--${cat.cls}">${cat.icon}</div>`;

          const markerIcon = L.divIcon({ html: htmlIcon, className: '', iconSize: [28, 28], iconAnchor: [14, 28] });

          const photoPopup = it.photo ? `<br><img src="/uploads/${escapeHTML(it.photo)}" style="max-width:200px;max-height:200px;border-radius:4px;">` : '';

          const popupHtml = `<div><b>${addrEsc}</b>${descHtml}${linkHtml}${photoPopup}</div>`;

          const popupOptions = { autoClose: false, closeOnClick: false };

          const mkr = L.marker([it.lat, it.lon], { icon: markerIcon }).bindPopup(popupHtml, popupOptions);

          mkr.itemId = it.id;

          mkr.on('click', () => { selectItem(it.id); });

          markersCluster.addLayer(mkr);

          markerMap[it.id] = mkr;

        } catch (e) { console.warn('marker add failed', e); }

      }

    }



    const bulkBtn = $('#btn-bulk-del'); if (bulkBtn) bulkBtn.disabled = true;

    const cbs = document.querySelectorAll('#list input[type=checkbox][data-id]');

    cbs.forEach(cb => {

      cb.addEventListener('change', () => {

        const any = document.querySelectorAll('#list input[type=checkbox][data-id]:checked').length > 0;

        if (bulkBtn) bulkBtn.disabled = !any;

      });

    });



    updateSummary();

    renderQuickCounters();

    updateCurrentFilterLabel();

    updateFilterSummary();

    try { if (typeof applyRole === 'function' && CURRENT_ROLE) applyRole(CURRENT_ROLE); } catch (_) {}

  }

  // Экспортируем функции в глобальную область, чтобы main.js и другие
  // модули могли их вызывать как раньше.
  window.updateSummary = updateSummary;
  window.computeCounts = computeCounts;
  window.updateCurrentFilterLabel = updateCurrentFilterLabel;
  window.renderQuickCounters = renderQuickCounters;
  window.updateFilterSummary = updateFilterSummary;
  window.renderList = renderList;
})();
