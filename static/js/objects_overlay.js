/* objects_overlay.js

Leaflet‑слой «Объекты» (адреса + камеры) для карты.

Требования этапа 2 (метки как ядро):
  - грузим /api/objects/geo по bbox
  - маркеры объектов
  - клик -> всплывающая карточка (адрес/описание/камеры + быстрые действия)
  - включение/выключение без дублей и утечек
  - обновление на moveend/zoomend

Слой экспортируется как window.ObjectsOverlay (setEnabled/refresh/destroy).
*/

(function(){
  'use strict';

  const LS_KEY = 'objects_layer_enabled';
  const API_URL = '/api/objects/geo';
  const API_DETAIL = (id) => `/api/objects/${encodeURIComponent(id)}`;

  function getBool(key, defVal){
    try{
      const v = localStorage.getItem(key);
      if(v === null || v === undefined) return defVal;
      return v === '1' || v === 'true' || v === 'yes';
    }catch(e){
      return defVal;
    }
  }

  function escapeHtml(s){
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[c]));
  }

  function resolveMap(){
    return window.map || window.dutyMap || null;
  }

  function bboxParam(map){
    const b = map.getBounds();
    const west  = b.getWest();
    const south = b.getSouth();
    const east  = b.getEast();
    const north = b.getNorth();
    return [west,south,east,north].map(x => Number(x).toFixed(6)).join(',');
  }

  function debounce(fn, ms){
    let t = null;
    return function(){
      const args = arguments;
      if(t) clearTimeout(t);
      t = setTimeout(() => { t = null; fn.apply(null, args); }, ms);
    };
  }

  function iconStyle(){
    return {
      radius: 6,
      color: '#0ea5e9',
      weight: 2,
      fillColor: '#38bdf8',
      fillOpacity: 0.85,
    };
  }

  function renderPopup(obj){
    const name = escapeHtml(obj.name || obj.address || `Объект #${obj.id}`);
    const tags = escapeHtml(obj.tags || '');
    const desc = escapeHtml(obj.description || '');

    const cams = Array.isArray(obj.cameras) ? obj.cameras : [];
    const camsHtml = cams.length
      ? `<div class="muted small" style="margin-top:6px">Камеры</div>` +
        `<div style="display:flex; flex-direction:column; gap:4px; margin-top:4px">` +
        cams.map((c, idx) => {
          const label = escapeHtml(c.label || `Камера ${idx+1}`);
          const url = String(c.url || '').trim();
          const safeUrl = escapeHtml(url);
          const type = escapeHtml(c.type || '');
          const link = url ? `<a href="${safeUrl}" target="_blank" rel="noopener">Открыть</a>` : '<span class="muted">(нет ссылки)</span>';
          return `<div style="display:flex; gap:8px; justify-content:space-between; align-items:center;">
                    <div style="min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                      <b>${label}</b> <span class="muted small">${type}</span>
                    </div>
                    <div>${link}</div>
                  </div>`;
        }).join('') +
        `</div>`
      : `<div class="muted small" style="margin-top:6px">Камеры не привязаны</div>`;

    const btnEdit = `<button class="btn" type="button" data-act="obj-edit" data-id="${escapeHtml(obj.id)}">Редактировать</button>`;
    const btnIncident = `<button class="btn primary" type="button" data-act="obj-incident" data-id="${escapeHtml(obj.id)}">Создать инцидент</button>`;
    const btnOpen = `<a class="btn" href="/admin/objects?highlight=${encodeURIComponent(obj.id)}" target="_blank" rel="noopener">Открыть</a>`;

    return `
      <div style="min-width:240px; max-width:320px">
        <div style="display:flex; flex-direction:column; gap:2px">
          <b>${name}</b>
          ${tags ? `<div class="muted small">${tags}</div>` : ''}
          ${desc ? `<div style="margin-top:6px">${desc}</div>` : ''}
        </div>
        ${camsHtml}
        <div style="display:flex; gap:6px; margin-top:10px; flex-wrap:wrap">
          ${btnIncident}
          ${btnEdit}
          ${btnOpen}
        </div>
      </div>
    `;
  }

  async function fetchJson(url, signal){
    const resp = await fetch(url, {
      method: 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
      signal,
      headers: { 'Accept': 'application/json' }
    });
    if(!resp.ok) return null;
    return await resp.json();
  }

  const Overlay = {
    _enabled: false,
    _map: null,
    _layer: null,
    _markers: new Map(),
    _abort: null,
    _boundMove: null,
    _refreshDebounced: null,
    _waitTimer: null,

    init(){
      if(window.ObjectsOverlay && window.ObjectsOverlay !== Overlay) return;
      window.ObjectsOverlay = Overlay;

      window.addEventListener('objects-layer:toggle', (ev) => {
        const en = !!(ev && ev.detail && ev.detail.enabled);
        Overlay.setEnabled(en);
      });

      const shouldEnable = getBool(LS_KEY, false);
      if(shouldEnable) Overlay.setEnabled(true);
    },

    setEnabled(enabled){
      const en = !!enabled;
      if(en === this._enabled) return;
      this._enabled = en;
      if(en) this._enable();
      else this._disable();
    },

    _enable(){
      const map = resolveMap();
      if(!map){
        this._waitTimer = this._waitTimer || setInterval(() => {
          const m = resolveMap();
          if(m){
            clearInterval(this._waitTimer);
            this._waitTimer = null;
            if(this._enabled) this._enable();
          }
        }, 150);
        return;
      }

      if(this._map && this._map !== map){
        this._disable();
      }

      this._map = map;
      if(!this._layer) this._layer = L.layerGroup();
      if(!map.hasLayer(this._layer)) this._layer.addTo(map);

      this._refreshDebounced = this._refreshDebounced || debounce(() => this.refresh(), 150);
      this._boundMove = this._boundMove || (() => this._refreshDebounced());

      map.on('moveend', this._boundMove);
      map.on('zoomend', this._boundMove);

      this.refresh();
    },

    _disable(){
      try{ if(this._waitTimer){ clearInterval(this._waitTimer); this._waitTimer=null; } }catch(_){ }
      try{ if(this._abort){ this._abort.abort(); this._abort=null; } }catch(_){ }
      try{
        if(this._map && this._boundMove){
          this._map.off('moveend', this._boundMove);
          this._map.off('zoomend', this._boundMove);
        }
      }catch(_){ }

      try{
        if(this._layer){
          this._layer.clearLayers();
          if(this._map && this._map.hasLayer(this._layer)) this._map.removeLayer(this._layer);
        }
      }catch(_){ }

      this._markers.clear();
      this._map = null;
    },

    async refresh(){
      if(!this._enabled) return;
      const map = this._map || resolveMap();
      if(!map) return;

      try{ if(this._abort) this._abort.abort(); }catch(_){ }
      const ac = new AbortController();
      this._abort = ac;

      const bbox = bboxParam(map);
      const url = `${API_URL}?bbox=${encodeURIComponent(bbox)}&limit=1000`;

      let data = null;
      try{
        data = await fetchJson(url, ac.signal);
      }catch(e){
        return;
      }
      if(!Array.isArray(data)) return;

      const seen = new Set();

      for(const it of data){
        if(!it || it.id === undefined || it.id === null) continue;
        const id = String(it.id);
        const lat = Number(it.lat);
        const lon = Number(it.lon);
        if(!isFinite(lat) || !isFinite(lon)) continue;
        seen.add(id);

        let marker = this._markers.get(id);
        if(!marker){
          marker = L.circleMarker([lat, lon], iconStyle());
          marker.on('click', async (ev) => {
            // Ctrl/Shift открывает полный список/карточку в новой вкладке
            try{
              const oe = ev && ev.originalEvent;
              const openNew = oe && (oe.ctrlKey || oe.metaKey || oe.shiftKey);
              if(openNew){
                const url = `/admin/objects?highlight=${encodeURIComponent(id)}`;
                window.open(url, '_blank');
                return;
              }
            }catch(_){ }

            // Если Command Center умеет drawer, используем его
            if(window.CC && typeof window.CC.openObjectCard === 'function'){
              window.CC.openObjectCard(id, { tab:'overview', fit:false });
              return;
            }

            // Подробности тянем лениво
            let detail = null;
            try{
              detail = await fetchJson(API_DETAIL(id));
            }catch(_){ detail = null; }
            const payload = detail || { id, name: it.name, tags: it.tags };
            const html = renderPopup(payload);
            marker.bindPopup(html, { closeButton: true, maxWidth: 360 }).openPopup();
            // Навесим обработчики кнопок внутри попапа
            setTimeout(() => {
              try{
                const el = marker.getPopup && marker.getPopup().getElement ? marker.getPopup().getElement() : null;
                if(!el) return;
                const btnEdit = el.querySelector('[data-act="obj-edit"]');
                const btnInc = el.querySelector('[data-act="obj-incident"]');
                if(btnEdit){
                  btnEdit.addEventListener('click', (ev) => {
                    ev.preventDefault();
                    if(window.ObjectsUI && typeof window.ObjectsUI.openEdit === 'function'){
                      window.ObjectsUI.openEdit(id);
                    }
                  }, { once: true });
                }
                if(btnInc){
                  btnInc.addEventListener('click', (ev) => {
                    ev.preventDefault();
                    if(window.ObjectsUI && typeof window.ObjectsUI.createIncidentFromObject === 'function'){
                      window.ObjectsUI.createIncidentFromObject(id, { interactive: !!(ev && ev.shiftKey) });
                    }
                  }, { once: true });
                }
              }catch(_){ }
            }, 0);
          });
          this._markers.set(id, marker);
          marker.addTo(this._layer);
        }else{
          marker.setLatLng([lat, lon]);
        }
      }

      // убираем ушедшие
      for(const [id, marker] of this._markers.entries()){
        if(!seen.has(id)){
          try{ this._layer.removeLayer(marker); }catch(_){ }
          this._markers.delete(id);
        }
      }
    },

    /**
     * Фокус на объекте: пан/зум к координатам и (опционально) открыть попап.
     * Используется в Command Center (левая панель объектов).
     */
    async focus(id, opts){
      const objectId = String(id ?? '').trim();
      if(!objectId) return;

      const openPopup = opts && Object.prototype.hasOwnProperty.call(opts, 'openPopup')
        ? !!opts.openPopup
        : true;
      const zoom = (opts && opts.zoom != null) ? Number(opts.zoom) : 17;

      // гарантируем включение слоя (иначе маркера может не быть)
      if(!this._enabled) this.setEnabled(true);

      // подтянем координаты
      let detail = null;
      try{ detail = await fetchJson(API_DETAIL(objectId)); }catch(_){ detail = null; }

      const lat = detail && detail.lat != null ? Number(detail.lat) : null;
      const lon = detail && detail.lon != null ? Number(detail.lon) : null;
      const map = this._map || resolveMap();

      if(map && lat != null && lon != null && isFinite(lat) && isFinite(lon)){
        try{ map.setView([lat, lon], Math.max(map.getZoom(), isFinite(zoom) ? zoom : 17)); }catch(_){ }
      }

      // обновим слой под новый bbox
      try{ await this.refresh(); }catch(_){ }

      if(!openPopup) return;

      // попробуем найти маркер (после refresh он может появиться не сразу)
      let tries = 0;
      const maxTries = 10;
      const tick = async () => {
        tries += 1;
        const marker = this._markers.get(objectId);
        if(marker){
          try{
            // если детали уже есть, можем открыть попап без повторного GET
            if(detail){
              const html = renderPopup(detail);
              marker.bindPopup(html, { closeButton: true, maxWidth: 360 }).openPopup();
            }else{
              marker.fire('click');
            }
          }catch(_){ }
          return;
        }
        if(tries >= maxTries) return;
        setTimeout(tick, 180);
      };
      setTimeout(tick, 80);
    },

    destroy(){
      this.setEnabled(false);
      try{ delete window.ObjectsOverlay; }catch(_){ }
    }
  };

  Overlay.init();
})();
