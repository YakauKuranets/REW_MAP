/* incidents_overlay.js

Leaflet‑слой «Инциденты» для карты.

Требования этапа 1.1:
  - грузим /api/incidents/geo по bbox
  - маркеры (цвет по статусу/приоритету)
  - клик по маркеру -> /admin/incidents/<id>
  - включение/выключение без дублей и утечек
  - обновление на moveend/zoomend

Интеграция:
  - UI‑тоггл: static/js/incidents_layer_toggle.js
  - кнопка: #btn-incidents-layer

Слой экспортируется как window.IncidentsOverlay (setEnabled/refresh/destroy).
*/

(function(){
  'use strict';

  const LS_KEY = 'incidents_layer_enabled';
  const API_URL = '/api/incidents/geo';
  const API_DETAIL = (id) => `/api/incidents/${encodeURIComponent(id)}`;

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
    // index.html использует глобальную map из map_core.js
    // admin_panel.html хранит карту в window.dutyMap
    return window.map || window.dutyMap || null;
  }


function ensureScriptLoaded(src){
  return new Promise((resolve) => {
    try{
      const exists = Array.from(document.querySelectorAll('script')).some(s => (s.src || '').includes(src));
      if(exists) return resolve(true);
      const s = document.createElement('script');
      s.src = src + (src.includes('?') ? '&' : '?') + 'v=' + Date.now();
      s.async = true;
      s.onload = () => resolve(true);
      s.onerror = () => resolve(false);
      document.head.appendChild(s);
    }catch(_){ resolve(false); }
  });
}

async function ensureIncidentsUI(){
  if(window.IncidentsUI && typeof window.IncidentsUI.openEdit === 'function') return true;
  // лениво грузим, если страница не подключила модуль
  const ok = await ensureScriptLoaded('/static/js/incidents_ui.js');
  return ok && !!(window.IncidentsUI && typeof window.IncidentsUI.openEdit === 'function');
}

  function statusColor(status){
    const s = String(status || '').toLowerCase();
    if(s === 'new') return '#ef4444';
    if(s === 'assigned') return '#f97316';
    if(s === 'enroute') return '#f59e0b';
    if(s === 'on_scene') return '#3b82f6';
    if(s === 'resolved') return '#22c55e';
    if(s === 'closed') return '#64748b';
    return '#94a3b8';
  }

  function priorityColor(priority){
    const p = Number(priority);
    if(p === 1) return '#dc2626';
    if(p === 2) return '#f97316';
    if(p === 3) return '#f59e0b';
    if(p === 4) return '#10b981';
    return '#64748b';
  }

  function priorityWeight(priority){
    const p = Number(priority);
    if(p === 1) return 4;
    if(p === 2) return 3;
    if(p === 3) return 2;
    return 2;
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
      if(window.IncidentsOverlay && window.IncidentsOverlay !== Overlay){
        // на всякий случай не затираем чужой объект
        return;
      }
      window.IncidentsOverlay = Overlay;

      // Fallback: если кто-то пошлёт только событие.
      window.addEventListener('incidents-layer:toggle', (ev) => {
        const en = !!(ev && ev.detail && ev.detail.enabled);
        Overlay.setEnabled(en);
      });

      // Подхватываем состояние из localStorage.
      const shouldEnable = getBool(LS_KEY, false);
      if(shouldEnable){
        Overlay.setEnabled(true);
      }
    },

    setEnabled(enabled){
      const en = !!enabled;
      if(en === this._enabled) return;
      this._enabled = en;
      if(en) this._enable();
      else this._disable();
    },

    _enable(){
      // карта может появиться позже (особенно на admin_panel)
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

      // Идемпотентность
      if(this._map && this._map !== map){
        this._disable();
      }

      this._map = map;
      if(!this._layer){
        this._layer = L.layerGroup();
      }
      if(!map.hasLayer(this._layer)){
        this._layer.addTo(map);
      }

      this._refreshDebounced = this._refreshDebounced || debounce(() => this.refresh(), 150);
      this._boundMove = this._boundMove || (() => this._refreshDebounced());

      map.on('moveend', this._boundMove);
      map.on('zoomend', this._boundMove);

      // Первичная загрузка
      this.refresh();
    },

    _disable(){
      // снимаем слушатели/таймеры/фетчи
      try{
        if(this._waitTimer){ clearInterval(this._waitTimer); this._waitTimer = null; }
      }catch(_){ }

      try{
        if(this._abort){ this._abort.abort(); this._abort = null; }
      }catch(_){ }

      try{
        if(this._map && this._boundMove){
          this._map.off('moveend', this._boundMove);
          this._map.off('zoomend', this._boundMove);
        }
      }catch(_){ }

      // чистим слой
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

      // отменяем прошлый запрос
      try{ if(this._abort) this._abort.abort(); }catch(_){ }
      const ac = new AbortController();
      this._abort = ac;

      const bbox = bboxParam(map);
      const url = `${API_URL}?bbox=${encodeURIComponent(bbox)}&limit=500`;

      let resp = null;
      let data = null;
      try{
        resp = await fetch(url, {
          method: 'GET',
          credentials: 'same-origin',
          cache: 'no-store',
          signal: ac.signal,
          headers: { 'Accept': 'application/json' }
        });
        if(!resp.ok){
          // 401/403 на не‑админе вполне ожидаемо
          return;
        }
        data = await resp.json();
      }catch(e){
        // abort — это нормально
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

        const st = String(it.status || '');
        const pr = (it.priority === undefined || it.priority === null) ? null : Number(it.priority);

        let marker = this._markers.get(id);
        if(!marker){
          marker = L.circleMarker([lat, lon], {
            radius: 7,
            color: statusColor(st),
            weight: priorityWeight(pr),
            fillColor: priorityColor(pr),
            fillOpacity: 0.85,
          });
          const urlCard = `/admin/incidents/${encodeURIComponent(id)}`;
          marker.on('click', (ev) => {
            try{
              const oe = ev && ev.originalEvent;
              const openNew = oe && (oe.ctrlKey || oe.metaKey || oe.shiftKey);
              if(openNew){ window.open(urlCard, '_blank'); return; }

              // 1) предпочитаем редактирование прямо на карте (модалка IncidentsUI)
              ensureIncidentsUI().then((ok) => {
                if(ok){
                  try{ window.IncidentsUI.openEdit(id); }catch(_){ window.location.href = urlCard; }
                  return;
                }
                // 2) если Command Center умеет карточку — используем
                if(window.CC && typeof window.CC.openIncidentCard === 'function'){
                  try{ window.CC.openIncidentCard(id, { tab:'overview', fit:false }); return; }catch(_){ }
                }
                // 3) fallback
                window.location.href = urlCard;
              });
            }catch(_){
              window.location.href = urlCard;
            }
          });

          this._markers.set(id, marker);
          if(this._layer) this._layer.addLayer(marker);
        }else{
          try{ marker.setLatLng([lat, lon]); }catch(_){ }
          try{
            marker.setStyle({
              color: statusColor(st),
              weight: priorityWeight(pr),
              fillColor: priorityColor(pr),
            });
          }catch(_){ }
        }

        // popup/tooltip (обновляем каждый раз)
        try{
          const title = `#${escapeHtml(id)} · ${escapeHtml(st || '—')}${(pr!==null && pr!==undefined) ? (' · P'+escapeHtml(pr)) : ''}`;
          const addr = escapeHtml(it.address || '');
          const ts = escapeHtml(it.created_at || '');
          const obj = it.object ? `${escapeHtml(it.object.name || '')}${it.object.tags ? (' · '+escapeHtml(it.object.tags)) : ''}` : '';
          const html = `
            <div style="min-width:180px">
              <div style="font-weight:700;margin-bottom:4px">${title}</div>
              ${addr ? `<div style="margin-bottom:4px">${addr}</div>` : ''}
              ${obj ? `<div class="muted" style="font-size:12px;margin-bottom:4px">${obj}</div>` : ''}
              ${ts ? `<div class="muted" style="font-size:12px">${ts}</div>` : ''}
              <div class="muted" style="font-size:12px;margin-top:6px">клик → карточка</div>
            </div>
          `;
          marker.bindPopup(html, { closeButton: true, autoPan: true });
        }catch(_){ }
      }

      // удаляем маркеры, которых больше нет
      for(const [id, marker] of this._markers.entries()){
        if(!seen.has(id)){
          try{ if(this._layer) this._layer.removeLayer(marker); }catch(_){ }
          this._markers.delete(id);
        }
      }
    },

    /**
     * Фокус на инциденте: пан/зум к координатам и открыть попап.
     * Используется в Command Center (таб «Инциденты»).
     */
    async focus(id, opts){
      const incidentId = String(id ?? '').trim();
      if(!incidentId) return;
      const openPopup = !(opts && opts.openPopup === false);
      const zoom = Number(opts && opts.zoom) || 17;

      // включаем слой (лучше через кнопку, но пусть работает и напрямую)
      if(!this._enabled){
        this.setEnabled(true);
        try{ localStorage.setItem(LS_KEY, '1'); }catch(_){ }
      }

      // вытащим координаты, чтобы красиво "подлететь"
      let lat = null, lon = null;
      try{
        const resp = await fetch(API_DETAIL(incidentId), { credentials: 'include' });
        if(resp.ok){
          const d = await resp.json();
          lat = Number(d && d.lat);
          lon = Number(d && d.lon);
        }
      }catch(_){ }

      const map = resolveMap();
      if(map && isFinite(lat) && isFinite(lon)){
        try{ map.setView([lat, lon], Math.max(map.getZoom(), zoom)); }catch(_){ }
      }

      try{ await this.refresh(); }catch(_){ }

      if(!openPopup) return;
      const triesMax = 12;
      let tries = 0;
      const tick = () => {
        tries += 1;
        const m = this._markers.get(String(incidentId));
        if(m){
          try{ m.openPopup(); }catch(_){ }
          return;
        }
        if(tries < triesMax) setTimeout(tick, 200);
      };
      setTimeout(tick, 50);
    },

    destroy(){
      this.setEnabled(false);
      try{ delete window.IncidentsOverlay; }catch(_){ }
    }
  };

  // автозапуск
  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', () => Overlay.init());
  }else{
    Overlay.init();
  }

})();
