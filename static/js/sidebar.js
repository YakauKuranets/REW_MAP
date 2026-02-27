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
function t(key, vars){
  try{
    if(window.i18n && typeof window.i18n.t === 'function') return window.i18n.t(key, vars);
  }catch(_){}
  // fallback: return key itself
  const base = String(key || '');
  if(!vars) return base;
  return base.replace(/\{(\w+)\}/g, (m,k) => (vars[k]!=null ? String(vars[k]) : m));
}

function trCategory(s){
  try{
    if(window.i18n && typeof window.i18n.trCategoryRuEn === 'function') return window.i18n.trCategoryRuEn(s||'');
  }catch(_){}
  return String(s||'');
}

function trAccess(s){
  const src = String(s||'');
  const low = src.toLowerCase();
  if(low.includes('локал') || low.includes('local')) return t('map_status_local');
  if(low.includes('удал') || low.includes('remote')) return t('map_status_remote');
  return src;
}

  function updateSummary() {
  const panel = document.getElementById('summary-panel');
  if (!panel) return;

  const items = (radiusFiltered || ITEMS || []);
  const countsCat = { 'Видеонаблюдение': 0, 'Домофон': 0, 'Шлагбаум': 0 };
  let localCount = 0, remoteCount = 0;

  for (const it of items) {
    if (countsCat.hasOwnProperty(it.category)) countsCat[it.category]++;
    const status = (it.status || '').toLowerCase();
    if (status.includes('локал') || status.includes('local')) localCount++;
    else if (status.includes('удален') || status.includes('удал') || status.includes('remote')) remoteCount++;
  }

  panel.innerHTML =
    `<span>${t('map_sum_video')}: ${countsCat['Видеонаблюдение']}</span>` +
    `<span>${t('map_sum_dom')}: ${countsCat['Домофон']}</span>` +
    `<span>${t('map_sum_slag')}: ${countsCat['Шлагбаум']}</span>` +
    `<span>${t('map_sum_local')}: ${localCount}</span>` +
    `<span>${t('map_sum_remote')}: ${remoteCount}</span>`;
}
  function computeCounts(items) {
  const out = { total: items.length, video:0, dom:0, slag:0, local:0, remote:0 };
  for (const it of items) {
    const cat = (it.category || '').toLowerCase();
    if (cat.includes('видео') || cat.includes('video')) out.video++;
    else if (cat.includes('домоф') || cat.includes('intercom')) out.dom++;
    else if (cat.includes('шлаг') || cat.includes('barrier')) out.slag++;

    const st = (it.status || '').toLowerCase();
    if (st.includes('локал') || st.includes('local')) out.local++;
    else if (st.includes('удал') || st.includes('remote')) out.remote++;
  }
  return out;
}

  function updateCurrentFilterLabel() {
  const valEl = document.getElementById('current-filter-val') || document.getElementById('current-filter');
  if (!valEl) return;

  const catSel = document.getElementById('filter-category');
  const optLocal = document.getElementById('opt-local');
  const optRemote = document.getElementById('opt-remote');

  const catVal = (catSel && catSel.value) ? catSel.value.trim() : '';
  const isLocal = optLocal && optLocal.checked;
  const isRemote = optRemote && optRemote.checked;

  const parts = [];
  if (catVal) parts.push(t('map_filter_cat_fmt', { cat: trCategory(catVal) }));
  if (isLocal && !isRemote) parts.push(t('map_filter_access_local'));
  else if (isRemote && !isLocal) parts.push(t('map_filter_access_remote'));

  if (!parts.length) valEl.textContent = t('map_filter_all');
  else valEl.textContent = parts.join(', ');
}
  function renderQuickCounters() {
  const wrap = document.getElementById('quick-counters');
  if (!wrap) return;

  const items = (radiusFiltered || ITEMS || []);
  const c = computeCounts(items);
  wrap.innerHTML = '';

  const chips = [
    { k:'all',   label:`${t('map_chip_all')} (${c.total})` },
    { k:'video', label:`${t('map_chip_video')} (${c.video})`, filter: { category: 'Видеонаблюдение' } },
    { k:'dom',   label:`${t('map_chip_dom')} (${c.dom})`, filter: { category: 'Домофон' } },
    { k:'slag',  label:`${t('map_chip_slag')} (${c.slag})`, filter: { category: 'Шлагбаум' } },
    { k:'local', label:`${t('map_chip_local')} (${c.local})`, filter: { status: 'Локальный доступ' } },
    { k:'remote',label:`${t('map_chip_remote')} (${c.remote})`, filter: { status: 'Удаленный доступ' } },
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
        const isLocal = String(ch.filter.status).toLowerCase().includes('локал');
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
  const root = document.getElementById('filter-summary');
  if (!root) return;

  const countEl = document.getElementById('filter-summary-count');
  const extraEl = document.getElementById('filter-summary-extra');

  const items = (radiusFiltered || ITEMS || []);
  const total = Array.isArray(ITEMS) ? ITEMS.length : 0;
  const filtered = Array.isArray(items) ? items.length : 0;

  if (countEl) countEl.textContent = String(total || 0);

  if (!total) {
    if (extraEl) extraEl.textContent = '';
    return;
  }

  if (radiusFiltered && filtered !== total) {
    if (extraEl) extraEl.textContent = ' ' + t('map_total_in_radius_fmt', { n: filtered });
    else root.textContent = `${t('map_total_lbl')} ${total} ${t('map_total_in_radius_fmt', { n: filtered })}`;
  } else {
    if (extraEl) extraEl.textContent = '';
    else root.textContent = `${t('map_total_lbl')} ${total}`;
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

      list.innerHTML = `<div class=\"empty\">${t('map_empty')}</div>`;

      const bulkBtn = $('#btn-bulk-del'); if (bulkBtn) bulkBtn.disabled = true;

      renderQuickCounters();

      updateSummary();

      updateCurrentFilterLabel();

      updateFilterSummary();

      return;

    }



    for (const it of items) {

      const div = document.createElement('div'); div.className = 'item';

      const name = it.name || it.address || t('map_no_address');

      const addrEsc = escapeHTML(name);

      const statusEsc = escapeHTML(trAccess(it.status || ''));

      const catEsc = escapeHTML((window.i18n && window.i18n.trCategoryRuEn) ? window.i18n.trCategoryRuEn(it.category || '') : (it.category || ''));

      const notes = it.notes || it.description || '';

      const descHtml = notes ? '<br>' + linkify(notes) : '';

      const linkHtml = it.link ? `<br><a href="${escapeHTML(it.link)}" target="_blank" rel="noopener noreferrer">${escapeHTML(it.link)}</a>` : '';

      // Photo indicator: if the item has a photo property, show a camera icon linking to the image

      const photoIconHtml = it.photo ? ` <a href="/uploads/${escapeAttr(it.photo)}" target="_blank" title="${t('map_photo')}">📷</a>` : '';



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
