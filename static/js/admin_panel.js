/* Command Center admin panel (Map v12)
   v2: правый drawer «карточка наряда» + фильтры + отрисовка маршрута

   Требования:
   - /api/duty/admin/dashboard
   - /api/pending
   - /api/duty/admin/shift/<id>/detail
   - /api/duty/admin/tracking/<session_id>
*/

(function(){
  const API_DASH = '/api/duty/admin/dashboard';
  const API_PENDING = '/api/pending';
  const API_TRACKER_DEVICES = '/api/tracker/admin/devices';
  const API_TRACKER_PROBLEMS = '/api/tracker/admin/problems';
  const API_SERVICE_PENDING_COUNT = '/api/service/access/admin/pending_count';
  const API_CONNECT_PENDING_COUNT = '/api/mobile/connect/admin/pending_count';
  const API_SHIFT_DETAIL = (id) => `/api/duty/admin/shift/${encodeURIComponent(id)}/detail`;

  // Colors
  const C_INFO = '#0ea5e9'; // estimate / info

  const elToast = document.getElementById('toast');
  // i18n (RU/EN)
  function T(key, vars){
    try{
      if(window.i18n && typeof window.i18n.t === 'function') return window.i18n.t(key, vars);
    }catch(_){}
    // fallback: key
    return (vars ? String(key).replace(/\{(\w+)\}/g, (m,k)=> (vars[k]!=null?String(vars[k]):m)) : String(key));
  }
  function getLang(){
    try{ return (window.i18n && window.i18n.getLang) ? window.i18n.getLang() : 'ru'; }catch(_){ return 'ru'; }
  }

  // Layout vars: высота верхней панели KPI/фильтров (чтобы drawer/toast не перекрывали её)
  const elMain = document.querySelector('.ap-main');
  const elTopTools = document.getElementById('ap-overlay');
  function updateTopToolsHeight(){
    try{
      if(!elMain || !elTopTools) return;
      const h = elTopTools.offsetHeight || 0;
      elMain.style.setProperty('--ap-tools-h', `${h}px`);
    }catch(e){}
  }
  window.addEventListener('resize', () => { requestAnimationFrame(updateTopToolsHeight); });
  setTimeout(updateTopToolsHeight, 0);

  function showToast(msg, type){
    if(!elToast) return;
    elToast.textContent = msg;
    elToast.className = 'ap-toast ' + (type || '');
    elToast.style.display = 'block';
    clearTimeout(elToast._t);
    elToast._t = setTimeout(()=>{ elToast.style.display='none'; }, 3500);
  }

  function showToastT(key, vars, type){
    try{ return showToast(T(key, vars), type); }catch(_){ return showToast(String(key), type); }
  }

  // Сделаем доступным для chat.js
  window.showToast = window.showToast || showToast;

  async function fetchJson(url, opts){
    const res = await fetch(url, opts);
    const txt = await res.text();
    let data = txt;
    try { data = JSON.parse(txt); } catch(e) {}
    return { ok: res.ok, status: res.status, data };
  }

  async function loadDevicePointsPeriod(deviceId, {hours=12, fromIso=null, toIso=null, fit=false}={}){
    if(!deviceId) return { ok:false, items:[], err:'no_device' };
    const qs = [];
    if(fromIso) qs.push(`from=${encodeURIComponent(fromIso)}`);
    if(toIso) qs.push(`to=${encodeURIComponent(toIso)}`);
    if(!fromIso && !toIso && hours) qs.push(`hours=${encodeURIComponent(String(hours))}`);
    qs.push('limit=2000');
    const url = `/api/tracker/admin/device/${encodeURIComponent(deviceId)}/points?` + qs.join('&');
    const r = await fetchJson(url);
    if(!r.ok) return { ok:false, items:[], status:r.status };
    const items = Array.isArray(r.data?.items) ? r.data.items.slice() : [];
    // API returns DESC; polyline wants ASC
    items.reverse();
    const pts = items.map(p => ({
      ts: p.ts,
      lat: p.lat,
      lon: p.lon,
      accuracy_m: p.accuracy_m,
      kind: p.kind,
    }));
    // store as tracking (period)
    state.selected.tracking = { session: { id: 'period', started_at: pts[0]?.ts, ended_at: pts[pts.length-1]?.ts }, points: pts, stops: [] };
    state.selected.tracking_loaded_for = 'period';
    drawTrack(pts, [], fit);
    prepareReplayControls();
    renderTrackExtras();
    return { ok:true, items:pts };
  }

  async function loadDeviceAlerts(deviceId, {hours=72, active='all', fromIso=null, toIso=null}={}){
    if(!deviceId) return { ok:false, items:[], err:'no_device' };
    const qs = [];
    if(fromIso) qs.push(`from=${encodeURIComponent(fromIso)}`);
    if(toIso) qs.push(`to=${encodeURIComponent(toIso)}`);
    if(!fromIso && !toIso && hours) qs.push(`hours=${encodeURIComponent(String(hours))}`);
    qs.push('limit=200');
    qs.push(`active=${encodeURIComponent(String(active))}`);
    const url = `/api/tracker/admin/device/${encodeURIComponent(deviceId)}/alerts?` + qs.join('&');
    const r = await fetchJson(url);
    if(!r.ok) return { ok:false, items:[], status:r.status };
    const items = Array.isArray(r.data?.items) ? r.data.items : [];
    return { ok:true, items };
  }

  function escapeHtml(s){
    return String(s ?? '')
      .replaceAll('&','&amp;')
      .replaceAll('<','&lt;')
      .replaceAll('>','&gt;')
      .replaceAll('"','&quot;')
      .replaceAll("'", '&#039;');
  }

  function fmtIso(iso){
    try{
      if(!iso) return '—';
      const d = new Date(iso);
      return d.toLocaleString();
    } catch(e){ return iso || '—'; }
  }

  function fmtAge(sec){
    if(sec == null) return '—';
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    if(m <= 0) return `${s}с`;
    if(m < 60) return `${m}м ${s}с`;
    const h = Math.floor(m / 60);
    const mm = m % 60;
    return `${h}ч ${mm}м`;
  }


/* v17: skeleton helpers */
function skelLines(widths){
  const ws = Array.isArray(widths) && widths.length ? widths : [78, 62, 84];
  return ws.map(w => `<div class="skel-line" style="width:${w}%"></div>`).join('');
}
function skelCard(n){
  const cards = [];
  for(let i=0;i<(n||6);i++){
    cards.push(`<div class="skel" style="margin-bottom:10px">${skelLines([72, 55, 86])}</div>`);
  }
  return cards.join('');
}
function skelBlock(lines){
  return `<div class="skel">${skelLines([78, 62, 84])}${skelLines([66, 44, 72]).replaceAll('skel-line','skel-line small')}</div>`;
}

function setListsLoading(){
  const elS = document.getElementById('list-shifts');
  const elB = document.getElementById('list-breaks');
  const elSo = document.getElementById('list-sos');
  const elP = document.getElementById('list-pending');
  if(elS) elS.innerHTML = skelCard(7);
  if(elB) elB.innerHTML = skelCard(3);
  if(elSo) elSo.innerHTML = skelCard(3);
  if(elP) elP.innerHTML = skelCard(4);
}

function setDrawerLoading(){
  if(!elDrawer) return;
  drawerOpen();
  if(elDrawerTitle) elDrawerTitle.textContent = 'Загрузка…';
  if(elDrawerSub) elDrawerSub.textContent = '';
  // disable quick actions while loading
  [elDrawerPan, elDrawerChat, elDrawerCopy, elDrawerDevice].forEach(b => { if(b) b.disabled = true; });

  const pO = pane('overview');
  const pT = pane('track');
  const pJ = pane('journal');
  if(pO) pO.innerHTML = skelBlock(6);
  if(pT) pT.innerHTML = skelBlock(6);
  if(pJ) pJ.innerHTML = skelBlock(6);
}


  async function copyToClipboard(text){
    const s = String(text ?? '');
    try{
      if(navigator.clipboard && navigator.clipboard.writeText){
        await navigator.clipboard.writeText(s);
        return true;
      }
    }catch(e){}

    // fallback
    try{
      const ta = document.createElement('textarea');
      ta.value = s;
      ta.setAttribute('readonly','');
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      ta.style.top = '-9999px';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      const ok = document.execCommand('copy');
      document.body.removeChild(ta);
      return !!ok;
    }catch(e){
      return false;
    }
  }

  /* ===== Leaflet ===== */
  const map = L.map('map', { zoomControl: true }).setView([53.9, 27.56], 12);
  window.dutyMap = map; // для sos.js

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);

  const layers = {
    shifts: L.layerGroup().addTo(map),
    sos: L.layerGroup().addTo(map),
    pending: L.layerGroup().addTo(map),
    selected: L.layerGroup().addTo(map),
    focus: L.layerGroup().addTo(map), // v32: всегда видимый фокус-маркер для кнопки «Показать»
  };

function _cssVar(name, fallback){
  try{
    const v = getComputedStyle(document.body).getPropertyValue(name).trim();
    return v || fallback;
  }catch(e){ return fallback; }
}

const C_SUCCESS = _cssVar('--success', '#10b981');
const C_WARN = _cssVar('--warn', '#ef4444');
const C_AMBER = _cssVar('--admin-amber', '#ffb020');
const C_MUTED = _cssVar('--admin-muted', '#64748b');
const C_PURPLE = '#6d28d9';

function addMapLegend(){
  const legend = L.control({ position: 'bottomright' });
  legend.onAdd = function(){
    const div = L.DomUtil.create('div', 'map-legend');
    div.innerHTML = `
      <div class="ml-title">${escapeHtml(T('cc_legend_title'))}</div>
      <div class="ml-row"><span class="ml-dot" style="--c:${C_SUCCESS}"></span><span>${escapeHtml(T('cc_legend_live'))}</span></div>
      <div class="ml-row"><span class="ml-dot" style="--c:${C_MUTED}"></span><span>${escapeHtml(T('cc_legend_idle'))}</span></div>
      <div class="ml-row"><span class="ml-dot" style="--c:${C_AMBER}"></span><span>${escapeHtml(T('cc_legend_problem_stale'))}</span></div>
      <div class="ml-row"><span class="ml-dot" style="--c:${C_WARN}"></span><span>${escapeHtml(T('cc_legend_sos'))}</span></div>
      <div class="ml-row"><span class="ml-dot" style="--c:${C_PURPLE}"></span><span>${escapeHtml(T('cc_legend_revoked'))}</span></div>
      <div class="ml-hint">${escapeHtml(T('cc_legend_hint'))}</div>
    `;
    L.DomEvent.disableClickPropagation(div);
    return div;
  };
  legend.addTo(map);
}


addMapLegend();


  const state = {
    shifts: [],
    breaks: [],
    sos: [],
    pending: [],

    mkShift: new Map(),
    mkShiftAcc: new Map(),
    mkSos: new Map(),
    mkPending: new Map(),

    // v32: отдельный слой фокуса для кнопок «Показать» (не зависит от слоёв смен/фильтров)
    focus: { mk: null, acc: null, key: null },

    selected: {
      shift_id: null,
      // v41: drawer может показывать не только смену
      incident_id: null,
      object_id: null,
      user_id: null,
      detail: null,
      tracking: null,
      tracking_loaded_for: null,
      replay: { idx: 0, playing: false, timer: null, marker: null },
    }
    ,
    // stale alerts
    staleUsers: new Set(),
    lastBeepAtMs: 0,

    // tracker meta (for revoked/problems KPIs)
    trackerDevices: [],
    trackerProblems: [],
    deviceById: new Map(),
    deviceByUser: new Map(),
    problemsByDevice: new Map(),

    // quick filter bar
    quickFilter: (localStorage.getItem('ap_qf') || 'all'),

    // v31: UI-only скрытые карточки (кнопка ✕). Храним в localStorage.
    dismissedShiftIds: new Set(),

    // v41: режим drawer (shift/incident/object)
    drawer: { mode: 'shift' },
  };

  function labelForShift(sh){
    return (sh.unit_label || ('TG ' + sh.user_id));
  }

  // v32: нормализация последней точки + фокус-маркер (чтобы кнопка «Показать» всегда давала видимый маркер)
  function _toNum(v){
    const n = Number(v);
    return (Number.isFinite(n) ? n : null);
  }

  function _pick(obj, keys){
    if(!obj) return null;
    for(const k of keys){
      if(obj[k] != null) return obj[k];
    }
    return null;
  }

  function _normalizePoint(p){
    if(!p || typeof p !== 'object') return null;
    const lat = _toNum(_pick(p, ['lat','latitude','Lat','Latitude']));
    const lon = _toNum(_pick(p, ['lon','lng','longitude','Lon','Lng','Longitude']));
    if(lat == null || lon == null) return null;
    const ts = _pick(p, ['ts','timestamp','created_at','at','time']);
    const session_id = _pick(p, ['session_id','sessionId','session','sid','last_session_id']);
    const accuracy_m = _toNum(_pick(p, ['accuracy_m','accuracy','acc_m','acc','hacc']));
    return { ...p, lat, lon, ts: ts || null, session_id: session_id || null, accuracy_m: accuracy_m };
  }

  function getShiftLastPoint(sh){
    if(!sh) return null;
    const p = sh.last || sh.last_point || sh.lastPoint || sh.last_location || sh.lastLocation || null;
    const np = _normalizePoint(p);
    if(np && !sh.last) sh.last = np;
    return np;
  }

  function getDetailLastPoint(detail){
    if(!detail) return null;
    const p = detail.last || detail.last_point || detail.lastPoint || null;
    const np = _normalizePoint(p);
    if(np && !detail.last) detail.last = np;
    return np;
  }

  function isEstimatePoint(p){
    if(!p) return false;
    try{
      const kind = String(p.kind || '').toLowerCase();
      if(kind === 'est') return true;
      const flags = p.flags || (p.meta && p.meta.flags) || [];
      if(Array.isArray(flags) && flags.includes('est')) return true;
      const src = String(p.source || p.src || '').toLowerCase();
      if(src.includes('wifi') || src.includes('est')) return true;
      const method = String(p.method || '').toLowerCase();
      if(method.includes('radio') || method.includes('tile') || method.includes('finger')) return true;
    }catch(_){ }
    return false;
  }

  function fmtPercent01(v){
    const x = Number(v);
    if(!Number.isFinite(x)) return null;
    return Math.round(x * 100);
  }

  function getPositioningSourceLabel(p){
    if(!p) return T('cc_none');
    if(isEstimatePoint(p)){
      const m = String(p.method || '').toLowerCase();
      const isTile = (m === 'radio_tile' || m === 'tile' || m.includes('tile') || m.includes('radio'));
      const meth = isTile ? T('cc_pos_method_tile') : T('cc_pos_method_anchor');
      return T('cc_tip_est') + ' · ' + meth;
    }
    return T('cc_tip_gnss');
  }

  function getPositioningDetailsText(p){
    if(!p) return T('cc_none');
    if(!isEstimatePoint(p)) return T('cc_none');
    const parts = [];
    const mw = p.matches_wifi != null ? Number(p.matches_wifi) : null;
    const mc = p.matches_cell != null ? Number(p.matches_cell) : null;
    if(Number.isFinite(mw)) parts.push('Wi‑Fi: ' + mw);
    if(Number.isFinite(mc)) parts.push('Cell: ' + mc);
    if(p.tile_id) parts.push('tile: ' + String(p.tile_id).slice(0,12));
    const rssi = p.rssi_diff_avg_db != null ? Number(p.rssi_diff_avg_db) : null;
    if(Number.isFinite(rssi)) parts.push('ΔWi‑Fi: ' + Math.round(rssi) + 'dB');
    const cd = p.cell_diff_avg_db != null ? Number(p.cell_diff_avg_db) : null;
    if(Number.isFinite(cd)) parts.push('ΔCell: ' + Math.round(cd) + 'dB');
    return parts.length ? parts.join(', ') : T('cc_none');
  }

  // MAX-3: стабилизация realtime-позиции (гистерезис GNSS ↔ estimate)
  function _tsMs(v){
    try{
      const t = Date.parse(v || '');
      return Number.isFinite(t) ? t : null;
    }catch(_){ return null; }
  }

  function _ageSecIso(iso){
    const ms = _tsMs(iso);
    if(ms == null) return null;
    return (Date.now() - ms) / 1000.0;
  }

  function _haversine_m(lat1, lon1, lat2, lon2){
    const R = 6371000.0;
    const toRad = (x) => (Number(x) * Math.PI / 180.0);
    const dLat = toRad(Number(lat2) - Number(lat1));
    const dLon = toRad(Number(lon2) - Number(lon1));
    const a = Math.sin(dLat/2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * (Math.sin(dLon/2) ** 2);
    const c = 2 * Math.asin(Math.min(1, Math.sqrt(a)));
    return R * c;
  }

  function _ensureRt(sh){
    if(!sh) return { good_gnss_streak: 0, last_good_gnss: null, prev_good_gnss: null };
    if(!sh._rt) sh._rt = { good_gnss_streak: 0, last_good_gnss: null, prev_good_gnss: null };
    return sh._rt;
  }

  function _isGoodGnssPoint(p){
    if(!p || isEstimatePoint(p)) return false;
    const acc = Number(p.accuracy_m);
    const age = _ageSecIso(p.ts);
    if(age != null && age > 90) return false;
    return Number.isFinite(acc) && acc > 0 && acc <= 60;
  }

  function _isPoorGnssPoint(p){
    if(!p || isEstimatePoint(p)) return false;
    const acc = Number(p.accuracy_m);
    const age = _ageSecIso(p.ts);
    if(age != null && age > 120) return true;
    return (!Number.isFinite(acc) || acc <= 0 || acc > 120);
  }

  function _shouldAcceptRealtimePoint(sh, prev, next){
    if(!next || next.lat == null || next.lon == null) return false;
    if(!prev) return true;

    const rt = _ensureRt(sh);
    const prevIsEst = isEstimatePoint(prev);
    const nextIsEst = isEstimatePoint(next);

    const nextGoodGnss = _isGoodGnssPoint(next);

    // update GNSS streak state
    if(!nextIsEst){
      if(nextGoodGnss){
        rt.prev_good_gnss = rt.last_good_gnss;
        rt.last_good_gnss = next;
        rt.good_gnss_streak = Math.min(5, (rt.good_gnss_streak || 0) + 1);
      } else {
        rt.good_gnss_streak = 0;
      }
    }

    // estimate -> estimate
    if(prevIsEst && nextIsEst) return true;

    // GNSS -> GNSS
    if(!prevIsEst && !nextIsEst) return true;

    // estimate -> GNSS: переключаемся только на "стабильный" хороший GNSS
    if(prevIsEst && !nextIsEst){
      const prevAge = _ageSecIso(prev.ts);
      if(prevAge != null && prevAge > 180) return true; // оценка устарела — лучше взять любой GNSS
      if(!nextGoodGnss) return false;

      const a = rt.last_good_gnss;
      const b = rt.prev_good_gnss;
      if(!a || !b) return false;
      const ageA = _ageSecIso(a.ts);
      const ageB = _ageSecIso(b.ts);
      if(ageA == null || ageB == null) return false;
      if(ageA > 25 || ageB > 25) return false;

      try{
        const d = _haversine_m(a.lat, a.lon, b.lat, b.lon);
        if(!(Number.isFinite(d) && d <= 50)) return false;
      }catch(_){
        return false;
      }
      return true;
    }

    // GNSS -> estimate: включаем оценку, если GNSS плохой/устарел И confidence норм
    if(!prevIsEst && nextIsEst){
      const prevPoor = _isPoorGnssPoint(prev);
      const prevGood = _isGoodGnssPoint(prev);

      const nextConf = Number(next.confidence);
      const confOk = Number.isFinite(nextConf) ? (nextConf >= 0.45) : true;

      if(prevGood) return false; // хороший GNSS — не "мигаем" оценкой
      if(prevPoor && confOk) return true;
      return confOk;
    }

    return true;
  }




  function _focusMarker(lat, lon, { title=null, accuracy_m=null, shift_id=null } = {}){
    const ll = [lat, lon];

    // основной фокус-маркер (в отдельном слое layers.focus)
    if(!state.focus.mk){
      state.focus.mk = L.circleMarker(ll, { radius: 10, weight: 3, fillOpacity: 0.25, opacity: 0.98 });
      state.focus.mk.addTo(layers.focus);
      state.focus.mk.on('click', () => {
        try{
          if(state.focus.key){
            openShiftCard(String(state.focus.key), { tab:'overview', fit:false });
          }
        }catch(_){ }
      });
    } else {
      state.focus.mk.setLatLng(ll);
    }

    // стиль фокуса: голубой (чётко видно и на светлой, и на тёмной теме)
    try{ state.focus.mk.setStyle({ color: '#0ea5e9', fillColor: '#0ea5e9', weight: 3, opacity: 0.98, fillOpacity: 0.22 }); }catch(_){ }

    // круг точности
    const acc = (accuracy_m != null && Number.isFinite(Number(accuracy_m))) ? Number(accuracy_m) : null;
    if(acc && acc > 0){
      const r = Math.min(300, Math.max(5, acc));
      if(!state.focus.acc){
        state.focus.acc = L.circle(ll, { radius: r, weight: 2, fillOpacity: 0.04, opacity: 0.5 });
        state.focus.acc.addTo(layers.focus);
      } else {
        state.focus.acc.setLatLng(ll);
        try{ state.focus.acc.setRadius(r); }catch(_){ }
      }
      try{ state.focus.acc.setStyle({ color: '#0ea5e9', fillColor: '#0ea5e9', weight: 2, opacity: 0.45, fillOpacity: 0.03 }); }catch(_){ }
    } else if(state.focus.acc){
      try{ layers.focus.removeLayer(state.focus.acc); }catch(_){ }
      state.focus.acc = null;
    }

    // tooltip
    try{
      const accTxt = (acc && Number.isFinite(acc)) ? ` ±${Math.round(acc)}м` : '';
      const tip = title ? (escapeHtml(title) + accTxt) : (`${lat.toFixed(5)}, ${lon.toFixed(5)}` + accTxt);
      state.focus.mk.bindTooltip(tip, { direction:'top', opacity:0.95 });
      // не делаем openTooltip всегда, чтобы не мешать — но при вызове «Показать» оно полезно
      state.focus.mk.openTooltip();
    }catch(_){ }

    // запомним к чему привязан фокус
    state.focus.key = (shift_id != null) ? String(shift_id) : null;

    // пан/зум
    try{ map.setView(ll, Math.max(map.getZoom(), 16), { animate:true }); }catch(_){ }
  }

  function focusShiftOnMap(sh){
    const last = getShiftLastPoint(sh);
    if(!last){
      showToastT('cc_toast_no_coords_for', { title: labelForShift(sh) }, 'warn');
      return false;
    }
    // гарантируем наличие маркера смены (если слой shifts по каким-то причинам не обновился)
    try{ upsertShiftMarker(sh); }catch(e){ console.warn('upsertShiftMarker failed', e); }

    _focusMarker(last.lat, last.lon, { title: labelForShift(sh), accuracy_m: last.accuracy_m, shift_id: sh.shift_id });
    return true;
  }

  function focusDetailOnMap(detail){
    const sh = detail && detail.shift ? detail.shift : {};
    const last = getDetailLastPoint(detail);
    if(!last){
      showToastT('cc_toast_no_last_coord', null, 'warn');
      return false;
    }
    _focusMarker(last.lat, last.lon, { title: labelForShift(sh), accuracy_m: last.accuracy_m, shift_id: sh.id });
    return true;
  }

  // v31: persisted dismiss (UI-only)
  function _loadDismissedShiftIds(){
    try{
      const raw = localStorage.getItem('cc_dismissed_shifts');
      if(!raw) return;
      const arr = JSON.parse(raw);
      if(Array.isArray(arr)) arr.forEach(x => state.dismissedShiftIds.add(String(x)));
    }catch(e){}
  }
  function _saveDismissedShiftIds(){
    try{
      const arr = Array.from(state.dismissedShiftIds || []).slice(0, 500);
      localStorage.setItem('cc_dismissed_shifts', JSON.stringify(arr));
    }catch(e){}
  }
  function _dismissShiftId(shiftId){
    try{
      state.dismissedShiftIds.add(String(shiftId));
      _saveDismissedShiftIds();
      rerenderVisible();
    }catch(e){}
  }
  _loadDismissedShiftIds();

  // v31 hotfix: _hasAlert() был потерян при мердже, из-за чего падала отрисовка списка нарядов.
  function _getAllAlertsForShift(sh){
    const all = [];
    try{
      if(sh && Array.isArray(sh.alerts)) all.push(...sh.alerts);
    }catch(e){}
    try{
      const dev = state.deviceByUser ? state.deviceByUser.get(String(sh.user_id)) : null;
      if(dev && Array.isArray(dev.alerts)) all.push(...dev.alerts);
    }catch(e){}
    return all;
  }
  function _hasAlert(sh, severity){
    const sev = String(severity || '');
    const alerts = _getAllAlertsForShift(sh);
    return alerts.some(a => a && String(a.severity || '') === sev);
  }

  function _shiftIsRevoked(sh){
  const uid = String(sh.user_id);
  const h = sh.health || null;
  if(h && h.device_id){
    const d = state.deviceById.get(String(h.device_id));
    if(d) return !!d.is_revoked;
  }
  const d2 = state.deviceByUser.get(uid);
  if(d2) return !!d2.is_revoked;
  return false;
}

function _shiftAlerts(sh){
  const h = sh.health || null;
  const did = h && h.device_id ? String(h.device_id) : null;
  if(did && state.problemsByDevice.has(did)) return (state.problemsByDevice.get(did) || []);
  return [];
}

function _shiftHasProblems(sh){
  // 1) активные алёрты
  const alerts = _shiftAlerts(sh);
  if(alerts && alerts.length) return true;

  // 2) stale (точки/health)
  if(_isShiftStale(sh)) return true;

  // 3) health эвристики (даже если алёрты ещё не созданы)
  const h = sh.health || null;
  if(h){
    if(h.last_error) return true;
    if(h.net === 'none') return true;
    if(h.gps && (h.gps === 'off' || h.gps === 'denied')) return true;
    if(typeof h.battery_pct === 'number' && h.battery_pct <= 15 && !h.is_charging) return true;
    if(typeof h.queue_size === 'number' && h.queue_size >= 300) return true;
    if(typeof sh.health_age_sec === 'number' && sh.health_age_sec >= 180) return true;
  }
  return false;
}

function _applyQuickFilter(list){
  const qf = (state.quickFilter || 'all');
  const sosUsers = new Set((state.sos || []).map(x => String(x.user_id)));
  if(qf === 'all') return list;

  return (list || []).filter(sh => {
    if(qf === 'live') return !!sh.tracking_active;
    if(qf === 'sos') return sosUsers.has(String(sh.user_id));
    if(qf === 'stale') return _isShiftStale(sh);
    if(qf === 'revoked') return _shiftIsRevoked(sh);
    if(qf === 'problems') return _shiftHasProblems(sh);
    return true;
  });
}

function updateQuickFiltersUI(){
  const shiftsAll = Array.isArray(state.shifts) ? state.shifts : [];
  const sosUsers = new Set((state.sos || []).map(x => String(x.user_id)));

  const cntAll = shiftsAll.length;
  const cntLive = shiftsAll.filter(s => !!s.tracking_active).length;
  const cntSos = shiftsAll.filter(s => sosUsers.has(String(s.user_id))).length;
  const cntStale = shiftsAll.filter(_isShiftStale).length;
  const cntRev = shiftsAll.filter(_shiftIsRevoked).length;
  const cntProb = shiftsAll.filter(_shiftHasProblems).length;

  const set = (id, v) => { const el = document.getElementById(id); if(el) el.textContent = String(v); };
  set('qf-all', cntAll);
  set('qf-live', cntLive);
  set('qf-problems', cntProb);
  set('qf-sos', cntSos);
  set('qf-stale', cntStale);
  set('qf-revoked', cntRev);

  // active class
  const root = document.getElementById('ap-quickfilters');
  if(root){
    Array.from(root.querySelectorAll('[data-qf]')).forEach(btn => {
      btn.classList.toggle('active', String(btn.dataset.qf) === String(state.quickFilter || 'all'));
    });
  }
}

function updateKpi(){
  const elSh = document.getElementById('kpi-shifts');
  const elLive = document.getElementById('kpi-live');
  const elBr = document.getElementById('kpi-breaks');
  const elSos = document.getElementById('kpi-sos');
  const elProb = document.getElementById('kpi-problems');
  const elStale = document.getElementById('kpi-stale');
  const elAcc = document.getElementById('kpi-acc');
  const elQueue = document.getElementById('kpi-queue');

  const shifts = Array.isArray(state.shifts) ? state.shifts : [];
  const breaks = Array.isArray(state.breaks) ? state.breaks : [];
  const sos = Array.isArray(state.sos) ? state.sos : [];

  const cntLive = shifts.filter(s => !!s.tracking_active).length;
  const cntProb = shifts.filter(_shiftHasProblems).length;
  const cntStale = shifts.filter(_isShiftStale).length;

  // accuracy avg
  const accVals = shifts.map(s => s.health && typeof s.health.accuracy_m === 'number' ? s.health.accuracy_m : null).filter(v => v != null);
  const accAvg = accVals.length ? Math.round(accVals.reduce((a,b)=>a+b,0) / accVals.length) : null;

  // queue total
  const qVals = shifts.map(s => s.health && typeof s.health.queue_size === 'number' ? s.health.queue_size : 0);
  const qTotal = qVals.reduce((a,b)=>a+b,0);

  if(elSh) elSh.textContent = String(shifts.length);
  if(elLive) elLive.textContent = String(cntLive);
  if(elBr) elBr.textContent = String(breaks.length);
  if(elSos) elSos.textContent = String(sos.length);

  if(elProb) elProb.textContent = String(cntProb);
  if(elStale) elStale.textContent = String(cntStale);
  if(elAcc) elAcc.textContent = (accAvg != null ? (String(accAvg) + 'м') : '—');
  if(elQueue) elQueue.textContent = String(qTotal);

  updateQuickFiltersUI();
  updateTopToolsHeight();
}


  function updateEmptyState(){
    const el = document.getElementById('ap-empty');
    if(!el) return;
    const isEmpty = (
      (state.shifts || []).length === 0 &&
      (state.breaks || []).length === 0 &&
      (state.sos || []).length === 0 &&
      (state.pending || []).length === 0
    );
    el.style.display = isEmpty ? '' : 'none';
  }

  /* ===== STALE alert bar ===== */

  function _isShiftStale(sh){
    // Единая логика: если сервер уже посчитал статус устройства — используем его.
    // Фолбэк: прежние эвристики (точки/health), чтобы не ломать старые бэкенды.
    try{
      const ds = sh && sh.device_status;
      if(ds && (ds.code === 'no_signal' || ds.code === 'offline')) return true;
    }catch(e){}

    // legacy: stale по точкам (5 мин) или по health (Android) (3 мин)
    const now = Date.now();
    try{
      const ts = sh.last?.ts ? Date.parse(sh.last.ts) : null;
      if(ts && (now - ts) > 5*60*1000) return true;
    }catch(e){}
    const ha = (typeof sh.health_age_sec === 'number') ? sh.health_age_sec : null;
    if(ha != null && ha > 180) return true;
    return false;
  }

  function _deviceStatusPillHtml(ds){
    try{
      if(!ds || !ds.label) return '';
      let cls = 'idle';
      if(ds.code === 'on_air') cls = 'live';
      else if(ds.code === 'no_signal') cls = 'warn';
      else if(ds.code === 'offline') cls = 'crit';

      const tUpd = (ds.last_update_age_sec != null) ? fmtAge(ds.last_update_age_sec) : '—';
      const tPt  = (ds.last_point_age_sec != null) ? fmtAge(ds.last_point_age_sec) : '—';
      const tHb  = (ds.heartbeat_age_sec != null) ? fmtAge(ds.heartbeat_age_sec) : '—';
      const basis = ds.basis ? String(ds.basis) : '';
      const title = `Обновлено: ${tUpd}; точка: ${tPt}; heartbeat: ${tHb}` + (basis ? `; basis: ${basis}` : '');
      return `<span class="ap-pill ${cls}" title="${escapeHtml(title)}">${escapeHtml(String(ds.label))}</span>`;
    }catch(e){
      return '';
    }
  }

  function _beep(){
    try{
      // WebAudio короткий сигнал (если браузер позволит)
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = 'square';
      o.frequency.value = 880;
      g.gain.value = 0.03;
      o.connect(g); g.connect(ctx.destination);
      o.start();
      setTimeout(() => { try{o.stop(); ctx.close();}catch(e){} }, 180);
    }catch(e){}
  }

  function updateStaleAlertBar(){
    const bar = document.getElementById('ap-alertbar');
    if(!bar) return;
    const shifts = Array.isArray(state.shifts) ? state.shifts : [];
    const staleNow = new Set(shifts.filter(_isShiftStale).map(s => String(s.user_id)));

    // текст
    const n = staleNow.size;
    if(n > 0){
      bar.style.display = '';
      bar.textContent = `⚠ Нет обновлений: ${n}. Открой карточку наряда и проверь телефон (батарея/сеть/GPS).`;
    } else {
      bar.style.display = 'none';
    }

    // звук: только на новые stale и не чаще 1 раза в 10с
    const newlyStale = [];
    for(const uid of staleNow){
      if(!state.staleUsers.has(uid)) newlyStale.push(uid);
    }
    state.staleUsers = staleNow;
    const nowMs = Date.now();
    if(newlyStale.length && (nowMs - state.lastBeepAtMs) > 10000){
      state.lastBeepAtMs = nowMs;
      _beep();
    }
  }


/* ===== Drawer ===== */
  const elDrawer = document.getElementById('ap-drawer');
  const elDrawerTitle = document.getElementById('drawer-title');
  const elDrawerSub = document.getElementById('drawer-sub');
  const elDrawerPan = document.getElementById('drawer-pan');
  const elDrawerChat = document.getElementById('drawer-chat');

  const elDrawerChatBadge = document.getElementById('drawer-chat-badge');

  function setDrawerChatBadge(n){
    if(!elDrawerChatBadge) return;
    const v = Number(n || 0);
    if(v > 0){
      elDrawerChatBadge.style.display = 'inline-flex';
      elDrawerChatBadge.textContent = (v > 99) ? '99+' : String(v);
    }else{
      elDrawerChatBadge.style.display = 'none';
      elDrawerChatBadge.textContent = '';
    }
  }

  async function refreshDrawerChatBadge(){
    try{
      if(state.drawer.mode === 'incident' && state.selected.incident_id){
        const iid = state.selected.incident_id;
        const r = await fetchJson(`/api/chat2/unread_for_incidents?ids=${encodeURIComponent(iid)}`);
        if(r && r.ok){
          const n = Number((r.data && (r.data[String(iid)] ?? r.data[iid])) || 0);
          setDrawerChatBadge(n);
          return;
        }
      }
      if(state.drawer.mode === 'shift' && state.selected.shift_id){
        const sid = state.selected.shift_id;
        const r = await fetchJson(`/api/chat2/unread_for_shifts?ids=${encodeURIComponent(sid)}`);
        if(r && r.ok){
          const n = Number((r.data && (r.data[String(sid)] ?? r.data[sid])) || 0);
          setDrawerChatBadge(n);
          return;
        }
      }
      setDrawerChatBadge(0);
    }catch(_){
      setDrawerChatBadge(0);
    }
  }
  const elDrawerCopy = document.getElementById('drawer-copy');
  const elDrawerDevice = document.getElementById('drawer-device');
  const elDrawerClose = document.getElementById('drawer-close');
  const elPanes = elDrawer ? Array.from(elDrawer.querySelectorAll('.ap-pane')) : [];
  const elTabs = elDrawer ? Array.from(elDrawer.querySelectorAll('.ap-tab')) : [];

  function drawerOpen(){
    if(!elDrawer) return;
    elDrawer.classList.add('open');
    elDrawer.setAttribute('aria-hidden','false');
  }
  function drawerClose(){
    if(!elDrawer) return;
    elDrawer.classList.remove('open');
    elDrawer.setAttribute('aria-hidden','true');
    // не убираем трек принудительно — иногда оператору удобно оставить линию. Но уберём replay-marker.
    stopReplay();
    // сброс выделения (маркер/список)
    state.selected.user_id = null;
    state.selected.detail = null;
    state.selected.shift_id = null;
    state.selected.incident_id = null;
    state.selected.object_id = null;
    state.drawer.mode = 'shift';
    setDrawerChatBadge(0);
    rerenderVisible();
  }

  function drawerSetTab(name){
    if(!elDrawer) return;
    // режимы incident/object не поддерживают трек
    if(state.drawer.mode === 'object' && name === 'track') name = 'overview';
    elTabs.forEach(t => t.classList.toggle('active', t.dataset.tab === name));
    elPanes.forEach(p => p.style.display = (p.dataset.pane === name) ? '' : 'none');
    if(name === 'track' && state.drawer.mode === 'shift') {
      // если есть выбранная сессия — рисуем
      const sid = state.selected.detail?.last_session_id;
      if(sid) loadTracking(sid, { fit: false, quiet: true });
    }
    // запомним текущий таб, чтобы refreshAll мог корректно пересобрать карточку
    try{ state.drawer.last_tab = name; }catch(_){ }
  }

  function _tabEl(tab){
    return elTabs.find(t => t && t.dataset && t.dataset.tab === tab) || null;
  }

  function _tabLabelEl(tab){
    const t = _tabEl(tab);
    if(!t) return null;
    return t.querySelector("span") || t;
  }

  function setTabLabel(tab, text){
    const el = _tabLabelEl(tab);
    if(el) el.textContent = text;
  }

  function setDrawerMode(mode){
    const m = (mode === 'incident' || mode === 'object') ? mode : 'shift';
    state.drawer.mode = m;

    // вкладки
    const tTrack = _tabEl('track');
    if(tTrack) tTrack.style.display = (m === 'shift' || m === 'incident') ? '' : 'none';
    if(m === 'object') {
      // если вдруг был активен трек (для объекта трека нет)
      if(tTrack && tTrack.classList.contains('active')) drawerSetTab('overview');
    }

    // подписи вкладок
    try{
      setTabLabel("overview", "Обзор");
      if(m === "shift"){
        setTabLabel("track", "Маршрут");
        setTabLabel("journal", "Журнал");
      } else if(m === "incident"){
        setTabLabel("track", "Назначения");
        setTabLabel("journal", "События");
      } else {
        setTabLabel("track", "Маршрут");
        setTabLabel("journal", "Журнал");
      }
    }catch(_){ }

    // кнопки (по умолчанию включаем, а дальше render* решит, что отключать)
    try{
      [elDrawerPan, elDrawerChat, elDrawerCopy, elDrawerDevice].forEach(b => {
        if(!b) return;
        b.style.display = '';
        b.disabled = false;
      });
      if(m !== 'shift'){
        if(elDrawerDevice){ elDrawerDevice.disabled = true; elDrawerDevice.style.display = 'none'; }
        if(m === 'incident'){
          // Stage41.10: чат по инциденту
          if(elDrawerChat){ elDrawerChat.disabled = false; }
        } else {
          if(elDrawerChat){ elDrawerChat.disabled = true; }
        }
      }
    }catch(_){ }
  }

  function toLocalInputValue(d){
    try{
      const pad = (n)=> String(n).padStart(2,'0');
      const yyyy = d.getFullYear();
      const mm = pad(d.getMonth()+1);
      const dd = pad(d.getDate());
      const hh = pad(d.getHours());
      const mi = pad(d.getMinutes());
      return `${yyyy}-${mm}-${dd}T${hh}:${mi}`;
    }catch(_){ return ''; }
  }

  function parseLocalInputToIso(v){
    try{
      if(!v) return null;
      const d = new Date(v);
      if(isNaN(d.getTime())) return null;
      return d.toISOString();
    }catch(_){ return null; }
  }

  function pane(name){
    return elDrawer ? elDrawer.querySelector(`.ap-pane[data-pane="${name}"]`) : null;
  }

  function clearSelectedLayers(){
    try{ layers.selected.clearLayers(); }catch(e){}
  }

  function stopReplay(){
    const rp = state.selected.replay;
    rp.playing = false;
    if(rp.timer){ clearInterval(rp.timer); rp.timer = null; }
    if(rp.marker){ try{ layers.selected.removeLayer(rp.marker); }catch(e){} rp.marker = null; }
  }

  function startReplay(){
    const rp = state.selected.replay;
    const pts = state.selected.tracking?.points || [];
    if(pts.length < 2) return;
    if(rp.timer) clearInterval(rp.timer);
    rp.playing = true;
    rp.timer = setInterval(() => {
      if(!rp.playing) return;
      rp.idx = Math.min(pts.length - 1, rp.idx + 1);
      updateReplayUI();
      if(rp.idx >= pts.length - 1) {
        rp.playing = false;
        clearInterval(rp.timer);
        rp.timer = null;
      }
    }, 900);
  }

  function updateReplayUI(){
    const pts = state.selected.tracking?.points || [];
    if(!pts.length) return;
    const rp = state.selected.replay;
    const idx = Math.max(0, Math.min(pts.length - 1, rp.idx));
    const p = pts[idx];
    // marker
    if(p.lat == null || p.lon == null) return;
    if(!rp.marker){
      rp.marker = L.circleMarker([p.lat, p.lon], { radius: 7, weight: 2, fillOpacity: 0.55 }).addTo(layers.selected);
    } else {
      rp.marker.setLatLng([p.lat, p.lon]);
    }
    // UI
    const elRange = document.getElementById('rp-range');
    const elLbl = document.getElementById('rp-lbl');
    if(elRange) elRange.value = String(idx);
    if(elLbl) elLbl.textContent = `${idx+1}/${pts.length} · ${fmtIso(p.ts)} · ${p.lat.toFixed?.(5) ?? p.lat}, ${p.lon.toFixed?.(5) ?? p.lon}`;
  }

  function drawTrack(points, stops, fit){
    clearSelectedLayers();
    stopReplay();

    const latlngs = (points || []).filter(p => p.lat != null && p.lon != null).map(p => [p.lat, p.lon]);
    if(latlngs.length){
      const line = L.polyline(latlngs, { weight: 4, opacity: 0.85 }).addTo(layers.selected);
      // старт/финиш
      const p0 = latlngs[0];
      const p1 = latlngs[latlngs.length - 1];
      L.circleMarker(p0, { radius: 6, weight: 2, fillOpacity: 0.45 }).addTo(layers.selected).bindTooltip('Старт', {opacity:0.95});
      L.circleMarker(p1, { radius: 7, weight: 2, fillOpacity: 0.6 }).addTo(layers.selected).bindTooltip('Последняя', {opacity:0.95});

      if(fit){
        try{ map.fitBounds(line.getBounds().pad(0.2), { animate:true }); }catch(e){}
      }
    }

    // стоянки
    (stops || []).forEach((st, i) => {
      if(st.center_lat == null || st.center_lon == null) return;
      const m = Math.round((st.duration_sec || 0) / 60);
      const mk = L.circle([st.center_lat, st.center_lon], { radius: Math.max(3, st.radius_m || 10), weight: 2, opacity: 0.85, fillOpacity: 0.12 });
      mk.addTo(layers.selected);
      mk.bindTooltip(`Стоянка: ${m} мин · R≈${st.radius_m || 10}м`, {opacity:0.95});
      mk.on('click', () => {
        map.setView([st.center_lat, st.center_lon], Math.max(map.getZoom(), 17), { animate:true });
      });
    });
  }

  function renderDrawer(detail){
    if(!detail || !elDrawer) return;
    const sh = detail.shift || {};

    // связь смены с устройством трекера (для быстрых переходов)
    const shRow = (state.shifts || []).find(x => String(x.shift_id) === String(sh.id));
    const devIdFromShift = (shRow && shRow.health && shRow.health.device_id) ? String(shRow.health.device_id) : null;
    const devByUser = state.deviceByUser ? state.deviceByUser.get(String(sh.user_id)) : null;
    const devIdFromUser = devByUser ? String(devByUser.public_id || devByUser.device_id || devByUser.id || '') : null;
    const deviceId = devIdFromShift || devIdFromUser || null;

    if(elDrawerTitle) elDrawerTitle.textContent = labelForShift({ user_id: sh.user_id, unit_label: sh.unit_label });
    if(elDrawerSub) elDrawerSub.textContent = `shift #${sh.id} · TG ${sh.user_id}`;

    // кнопки
    if(elDrawerPan){
      elDrawerPan.onclick = () => {
        focusDetailOnMap(detail);
      };
    }
    if(elDrawerChat){
      elDrawerChat.onclick = () => {
        try{
          // Сначала пытаемся открыть чат по смене (chat2)
          if (typeof window.chat2OpenForShift === 'function') {
            // sh.id — идентификатор смены в объекте detail.shift
            window.chat2OpenForShift(sh.id || sh.shift_id);
            return;
          }
        }catch(_){/* ignore */}
        // Если модуль chat2 не подключён — используем старый чат с пользователем
        if (typeof window.chatOpenToUser === 'function') {
          window.chatOpenToUser(String(sh.user_id));
        } else {
          showToastT('cc_toast_chat_not_ready', null, 'warn');
        }
      };
    }

    if(elDrawerCopy){
      const last = detail.last || {};
      const okCoords = (last.lat != null && last.lon != null);
      elDrawerCopy.disabled = !okCoords;
      elDrawerCopy.onclick = async () => {
        if(!okCoords) return;
        const s = `${last.lat}, ${last.lon}`;
        const ok = await copyToClipboard(s);
        showToastT(ok ? 'cc_toast_copied' : 'cc_toast_copy_failed', null, ok ? '' : 'warn');
      };
    }

    if(elDrawerDevice){
      elDrawerDevice.disabled = !deviceId;
      elDrawerDevice.onclick = () => {
        if(!deviceId) return;
        const url = `/admin/devices/${encodeURIComponent(deviceId)}`;
        window.open(url, '_blank', 'noopener');
      };
    }

    // обзор
    const pOv = pane('overview');
    if(pOv){
      const last = detail.last || {};
      const br = detail.break;
      const sos = detail.sos_active;

      // i18n helpers
      const tOrRaw = (k, raw) => { const v = T(k); return (v === k) ? (raw || '') : v; };
      const trBreakStatus = (s) => tOrRaw('cc_break_status_' + String(s||''), String(s||''));
      const trSosStatus = (s) => tOrRaw('cc_sos_status_' + String(s||''), String(s||''));

      // KPI 5m label
      const k5 = detail.kpi_5m;
      const kpi5mLine = k5 ? (T('cc_quality_5m_prefix') + ': ' + (k5.points_5m || 0) + ' ' + T('cc_quality_pts') + ' · ' + T('cc_quality_avg') + ' ' + (k5.acc_avg_5m != null ? (k5.acc_avg_5m + 'м') : '—') + ' · ' + T('cc_quality_jumps') + ' ' + (k5.jumps_5m || 0)) : '—';

      // Stage18.1: рекомендации по исправлению
      let recsHtml = '';
      try{
        if(window.Recs && typeof window.Recs.fromShiftDetail === 'function'){
          const recs = window.Recs.fromShiftDetail(detail);
          recsHtml = window.Recs.block(recs, T('cc_recs_lbl'));
        }
      }catch(_){ recsHtml = ''; }

      // health summary: поддерживаем оба варианта полей (gps_on/queue_len и gps/queue_size)
      let healthSummary = '—';
      try{
        const h = detail.health || null;
        if(h){
          const gps = (h.gps_on != null) ? h.gps_on : (h.gps != null ? h.gps : '—');
          const q = (h.queue_len != null) ? h.queue_len : (h.queue_size != null ? h.queue_size : '—');
          healthSummary = `${h.net || '—'} · GPS ${gps} · Q ${q} · last ${fmtAge(detail.health_age_sec)}`;
        }
      }catch(_){ healthSummary = '—'; }

      // MAX: диагностика позиционирования (GNSS ↔ indoor estimate)
      let posSummary = '—';
      let posMeta = '';
      try{
        const lp = _normalizePoint(last);
        if(lp){
          const srcLbl = getPositioningSourceLabel(lp);
          const confPct = fmtPercent01(lp && lp.confidence);
          posSummary = srcLbl + (confPct != null ? (' · ' + confPct + '%') : '');
          const det = getPositioningDetailsText(lp);
          if(det && det !== T('cc_none')){
            posMeta = `${T('cc_pos_details')}: ${det}`;
          }
        }
      }catch(_){ posSummary = '—'; posMeta = ''; }

      // A3: единый статус устройства (по точкам + heartbeat) + причина
      let devStatusSummary = '—';
      let devStatusMeta = '';
      try{
        const ds = detail.device_status || null;
        if(ds && ds.label){
          devStatusSummary = String(ds.label);
          const updAt = ds.last_update_at ? fmtIso(ds.last_update_at) : '—';
          const updAge = (ds.last_update_age_sec != null) ? fmtAge(ds.last_update_age_sec) : '—';
          const ptAge  = (ds.last_point_age_sec != null) ? fmtAge(ds.last_point_age_sec) : '—';
          const hbAge  = (ds.heartbeat_age_sec != null) ? fmtAge(ds.heartbeat_age_sec) : '—';
          devStatusMeta = `обновлено ${updAge} (${updAt}); точка ${ptAge}; heartbeat ${hbAge}`;
        }
      }catch(_){ devStatusSummary='—'; devStatusMeta=''; }


      pOv.innerHTML = `
        <div class="ap-kv">
          <div class="ap-box">
            <div class="ap-box__lbl">${escapeHtml(T('cc_box_shift_start'))}</div>
            <div class="ap-box__val">${escapeHtml(fmtIso(sh.started_at))}</div>
          </div>
          <div class="ap-box">
            <div class="ap-box__lbl">${escapeHtml(T('cc_box_last_update'))}</div>
            <div class="ap-box__val">${escapeHtml(fmtAge(detail.last_age_sec))}</div>
          </div>
          <div class="ap-box">
            <div class="ap-box__lbl">${escapeHtml(tOrRaw('cc_box_device_status','Связь'))}</div>
            <div class="ap-box__val">${escapeHtml(devStatusSummary)}</div>
          </div>
          <div class="ap-box">
            <div class="ap-box__lbl">${escapeHtml(T('cc_box_tracking_status'))}</div>
            <div class="ap-box__val">${detail.tracking_active ? escapeHtml(T('cc_status_ok')) : ((detail.health && (detail.health.tracking_on===false || detail.health.trackingOn===false)) ? escapeHtml(T('cc_status_ended')) : escapeHtml(T('cc_status_idle')))}</div>
          </div>
          <div class="ap-box">
            <div class="ap-box__lbl">${escapeHtml(T('cc_box_accuracy_last'))}</div>
            <div class="ap-box__val">${(last.accuracy_m != null && isFinite(Number(last.accuracy_m))) ? ('±' + Math.round(Number(last.accuracy_m)) + 'м') : '—'}</div>
          </div>
          <div class="ap-box">
            <div class="ap-box__lbl">${escapeHtml(T('cc_box_positioning'))}</div>
            <div class="ap-box__val">${escapeHtml(posSummary)}</div>
          </div>
          <div class="ap-box">
            <div class="ap-box__lbl">${escapeHtml(T('cc_box_speed_last'))}</div>
            <div class="ap-box__val">${(last.speed_mps != null && isFinite(Number(last.speed_mps)) && Number(last.speed_mps) >= 0.3) ? (Math.round(Number(last.speed_mps)*3.6) + 'км/ч') : '—'}</div>
          </div>
          <div class="ap-box">
            <div class="ap-box__lbl">${escapeHtml(T('cc_box_kpi_5m'))}</div>
            <div class="ap-box__val">${escapeHtml(kpi5mLine)}</div>
          </div>
          <div class="ap-box">
            <div class="ap-box__lbl">${escapeHtml(T('cc_box_coords_last'))}</div>
            <div class="ap-box__val">${last.lat != null ? escapeHtml(last.lat.toFixed?.(5) ?? last.lat) : '—'}, ${last.lon != null ? escapeHtml(last.lon.toFixed?.(5) ?? last.lon) : '—'}</div>
          </div>
          <div class="ap-box">
            <div class="ap-box__lbl">${escapeHtml(T('cc_box_health'))}</div>
            <div class="ap-box__val">${escapeHtml(healthSummary)}</div>
          </div>
        </div>
        ${devStatusMeta ? `<div class="muted" style="margin-top:6px">${escapeHtml(devStatusMeta)}</div>` : ''}
        ${posMeta ? `<div class="muted" style="margin-top:6px">${escapeHtml(posMeta)}</div>` : ''}
        ${recsHtml}

        <div class="ap-list">
          ${br ? `
            <div class="ap-row">
              <div class="ap-row__top">
                <div class="ap-row__title">🍽 ${escapeHtml(T('cc_break_title'))}</div>
                <span class="ap-pill warn">${escapeHtml(trBreakStatus(br.status || ''))}</span>
              </div>
              <div class="ap-row__meta">запрос: ${escapeHtml(fmtIso(br.requested_at))} · конец: ${escapeHtml(fmtIso(br.ends_at))}</div>
            </div>
          ` : ''}
          ${sos ? `
            <div class="ap-row">
              <div class="ap-row__top">
                <div class="ap-row__title">🆘 ${escapeHtml(T('cc_sos_active'))}</div>
                <span class="ap-pill warn">${escapeHtml(trSosStatus(sos.status || 'open'))}</span>
              </div>
              <div class="ap-row__meta">${escapeHtml(fmtIso(sos.created_at))} · ${escapeHtml(String(sos.lat))}, ${escapeHtml(String(sos.lon))}</div>
            </div>
          ` : ''}
          <div class="ap-row">
            <div class="ap-row__top">
              <div class="ap-row__title">${escapeHtml(T('cc_actions_quick'))}</div>
            </div>
            <div class="ap-item__actions">
              <button class="btn" id="ov-pan">${escapeHtml(T('cc_action_show'))}</button>
              <button class="btn" id="ov-track" ${detail.last_session_id ? '' : 'disabled'}>${escapeHtml(T('cc_action_track'))}</button>
              <button class="btn" id="ov-copy" ${(detail.last && detail.last.lat != null && detail.last.lon != null) ? '' : 'disabled'}>${escapeHtml(T('cc_action_copy'))}</button>
              <button class="btn" id="ov-device" ${deviceId ? '' : 'disabled'}>${escapeHtml(T('cc_action_device'))}</button>
              <button class="btn" id="ov-journal">${escapeHtml(T('cc_action_journal'))}</button>
            </div>
          </div>
        </div>
      `;

      const bPan = document.getElementById('ov-pan');
      if(bPan) bPan.onclick = () => elDrawerPan?.click();
      const bTrack = document.getElementById('ov-track');
      if(bTrack) bTrack.onclick = () => {
        drawerSetTab('track');
        const sid = detail.last_session_id;
        if(sid) loadTracking(sid, { fit: true });
      };
      const bCopy = document.getElementById('ov-copy');
      if(bCopy) bCopy.onclick = () => elDrawerCopy?.click();
      const bDev = document.getElementById('ov-device');
      if(bDev) bDev.onclick = () => elDrawerDevice?.click();

      const bJournal = document.getElementById('ov-journal');
      if(bJournal) bJournal.onclick = () => drawerSetTab('journal');
    }

    // маршрут
    const pTr = pane('track');
    if(pTr){
      const sessions = Array.isArray(detail.sessions) ? detail.sessions : [];
      const options = sessions.map(s => {
        const lbl = `${fmtIso(s.started_at)} → ${s.ended_at ? fmtIso(s.ended_at) : '…'}${s.is_active ? ' (' + T('cc_status_ok') + ')' : ''}`;
        return `<option value="${escapeHtml(String(s.id))}">${escapeHtml(lbl)}</option>`;
      }).join('');

      pTr.innerHTML = `
        <div class="muted" style="margin-bottom:6px">Сессии трекинга: </div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <select id="trk-session" class="input" style="flex:1;min-width:210px">
            ${options || '<option value="">—</option>'}
          </select>
          <button class="btn" id="trk-load">Загрузить</button>
          <button class="btn" id="trk-fit">Фокус</button>
        </div>
        ${deviceId ? `
          <div style="height:1px;background:rgba(255,255,255,0.08);margin:12px 0"></div>
          <div class="muted" style="margin-bottom:6px">Маршрут по периоду (точки устройства):</div>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <select id="per-hours" class="input" style="height:34px">
              <option value="1">1ч</option>
              <option value="3">3ч</option>
              <option value="6">6ч</option>
              <option value="12" selected>12ч</option>
              <option value="24">24ч</option>
              <option value="72">72ч</option>
              <option value="168">7д</option>
            </select>
            <input id="per-from" class="input" type="datetime-local" style="height:34px;min-width:190px" />
            <span class="muted">—</span>
            <input id="per-to" class="input" type="datetime-local" style="height:34px;min-width:190px" />
            <button class="btn" id="per-load">Загрузить</button>
            <button class="btn" id="per-fit">Фокус</button>
            <a class="btn" id="per-csv" href="#" target="_blank" rel="noopener">CSV</a>
            <a class="btn" id="per-gpx" href="#" target="_blank" rel="noopener">GPX</a>
          </div>
          <div id="per-summary" class="muted" style="margin-top:10px">—</div>
        ` : ''}
        <div id="trk-summary" class="muted" style="margin-top:10px">—</div>
        <div id="trk-stops" class="ap-list"></div>
        <div class="ap-replay">
          <button class="btn" id="rp-play">▶</button>
          <button class="btn" id="rp-stop">■</button>
          <input id="rp-range" type="range" min="0" max="0" value="0" step="1">
        </div>
        <div id="rp-lbl" class="muted" style="margin-top:6px">—</div>
      `;

      const elSel = document.getElementById('trk-session');
      const elLoad = document.getElementById('trk-load');
      const elFit = document.getElementById('trk-fit');

      // выбираем активную/последнюю
      const defId = detail.last_session_id || (sessions[0] ? sessions[0].id : null);
      if(elSel && defId != null){ elSel.value = String(defId); }

      if(elLoad){
        elLoad.onclick = () => {
          const sid = elSel ? Number(elSel.value) : null;
          if(!sid) return;
          loadTracking(sid, { fit: true });
        };
      }
      if(elFit){
        elFit.onclick = () => {
          // просто перерисуем с fit
          const sid = elSel ? Number(elSel.value) : null;
          if(!sid) return;
          if(state.selected.tracking_loaded_for === sid && state.selected.tracking){
            drawTrack(state.selected.tracking.points, state.selected.tracking.stops, true);
          } else {
            loadTracking(sid, { fit: true });
          }
        };
      }

      // v36: периодный маршрут (по точкам устройства)
      if(deviceId){
        const elPHours = document.getElementById('per-hours');
        const elPFrom = document.getElementById('per-from');
        const elPTo = document.getElementById('per-to');
        const elPLoad = document.getElementById('per-load');
        const elPFit = document.getElementById('per-fit');
        const elPCsv = document.getElementById('per-csv');
        const elPGpx = document.getElementById('per-gpx');
        const elPSum = document.getElementById('per-summary');

        const now = new Date();
        const initHours = Number(elPHours?.value || 12);
        if(elPFrom) elPFrom.value = toLocalInputValue(new Date(now.getTime() - initHours*3600*1000));
        if(elPTo) elPTo.value = toLocalInputValue(now);

        const buildPerQS = () => {
          const fromIso = parseLocalInputToIso(elPFrom?.value || '');
          const toIso = parseLocalInputToIso(elPTo?.value || '');
          const h = Number(elPHours?.value || 12);
          const qs = [];
          if(fromIso) qs.push(`from=${encodeURIComponent(fromIso)}`);
          if(toIso) qs.push(`to=${encodeURIComponent(toIso)}`);
          if(!fromIso && !toIso) qs.push(`hours=${encodeURIComponent(String(h))}`);
          return { qs: qs.join('&'), fromIso, toIso, h };
        };

        const refreshPerExports = () => {
          const { qs } = buildPerQS();
          if(elPCsv) elPCsv.href = `/api/tracker/admin/device/${encodeURIComponent(deviceId)}/export/points.csv?${qs}`;
          if(elPGpx) elPGpx.href = `/api/tracker/admin/device/${encodeURIComponent(deviceId)}/export/points.gpx?${qs}`;
        };
        refreshPerExports();

        if(elPHours){
          elPHours.onchange = () => { refreshPerExports(); };
        }
        if(elPFrom){ elPFrom.onchange = () => { refreshPerExports(); }; }
        if(elPTo){ elPTo.onchange = () => { refreshPerExports(); }; }

        if(elPLoad){
          elPLoad.onclick = async () => {
            const { fromIso, toIso, h } = buildPerQS();
            if(elPSum) elPSum.textContent = 'Загрузка…';
            const r = await loadDevicePointsPeriod(deviceId, { hours: h, fromIso, toIso, fit: true });
            if(!r.ok){
              if(elPSum) elPSum.textContent = `Не удалось загрузить точки (status ${r.status || '—'})`;
              return;
            }
            const pts = r.items || [];
            const accs = pts.map(x => Number(x.accuracy_m)).filter(x => isFinite(x));
            const accAvg = accs.length ? Math.round(accs.reduce((a,b)=>a+b,0)/accs.length) : null;
            if(elPSum) elPSum.textContent = `Точек: ${pts.length}${accAvg!=null ? ` · средняя точность ≈ ${accAvg}м` : ''}`;
          };
        }
        if(elPFit){
          elPFit.onclick = () => {
            if(state.selected.tracking && state.selected.tracking_loaded_for === 'period'){
              drawTrack(state.selected.tracking.points, [], true);
              prepareReplayControls();
            }
          };
        }
      }
      const elPlay = document.getElementById('rp-play');
      const elStop = document.getElementById('rp-stop');
      const elRange = document.getElementById('rp-range');

      if(elPlay) elPlay.onclick = () => startReplay();
      if(elStop) elStop.onclick = () => stopReplay();
      if(elRange) elRange.oninput = () => {
        state.selected.replay.idx = Number(elRange.value);
        updateReplayUI();
      };
    }

    // журнал (события смены + история проблем трекера)
    const pJ = pane('journal');
    if(pJ){
      const ev = Array.isArray(detail.events) ? detail.events : [];
      const eventRows = ev.length
        ? ev.slice(-200).reverse().map(e => {
            const actor = e.actor || 'system';
            const payload = e.payload ? JSON.stringify(e.payload) : '';
            return `
              <div class="ap-row">
                <div class="ap-row__top">
                  <div class="ap-row__title">${escapeHtml(e.event_type || '')}</div>
                  <span class="ap-pill">${escapeHtml(actor)}</span>
                </div>
                <div class="ap-row__meta">${escapeHtml(fmtIso(e.ts))}</div>
                ${payload && payload !== '{}' ? `<div class="ap-row__meta" style="white-space:pre-wrap">${escapeHtml(payload)}</div>` : ''}
              </div>
            `;
          }).join('')
        : '<div class="muted">Нет событий смены</div>';

      const trackerBlock = deviceId ? `
        <div class="ap-row">
          <div class="ap-row__top">
            <div class="ap-row__title">📡 История проблем трекера</div>
          </div>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:8px">
            <select id="jr-hours" class="input" style="height:34px">
              <option value="24">24ч</option>
              <option value="72" selected>72ч</option>
              <option value="168">7д</option>
            </select>
            <select id="jr-active" class="input" style="height:34px">
              <option value="all" selected>Все</option>
              <option value="active">Только активные</option>
              <option value="closed">Только закрытые</option>
            </select>
            <input id="jr-from" class="input" type="datetime-local" style="height:34px;min-width:190px" />
            <span class="muted">—</span>
            <input id="jr-to" class="input" type="datetime-local" style="height:34px;min-width:190px" />
            <button id="jr-apply" class="btn" type="button"><i class="fa-solid fa-filter"></i> Применить</button>
            <button id="jr-clear" class="btn" type="button"><i class="fa-solid fa-rotate-left"></i> Сброс</button>
            <a id="jr-export" class="btn" href="#" target="_blank" rel="noopener"><i class="fa-solid fa-file-csv"></i> CSV</a>
            <a id="jr-open-device" class="btn" href="/admin/devices/${escapeHtml(String(deviceId))}" target="_blank" rel="noopener"><i class="fa-solid fa-mobile-screen"></i> Устройство</a>
          </div>
          <div id="jr-alerts-summary" class="muted" style="margin-top:10px">—</div>
          <div id="jr-alerts" class="ap-list"></div>
        </div>
        <div style="height:1px;background:rgba(255,255,255,0.08);margin:12px 0"></div>
      ` : '';

      pJ.innerHTML = trackerBlock + eventRows;

      if(deviceId){
        const elHours = document.getElementById('jr-hours');
        const elActive = document.getElementById('jr-active');
        const elFrom = document.getElementById('jr-from');
        const elTo = document.getElementById('jr-to');
        const elApply = document.getElementById('jr-apply');
        const elClear = document.getElementById('jr-clear');
        const elExport = document.getElementById('jr-export');
        const elSum = document.getElementById('jr-alerts-summary');
        const elList = document.getElementById('jr-alerts');

        const initRange = () => {
          try{
            const h = Number(elHours?.value || 72);
            const now = new Date();
            if(elFrom) elFrom.value = toLocalInputValue(new Date(now.getTime() - h*3600*1000));
            if(elTo) elTo.value = toLocalInputValue(now);
          }catch(_){ }
        };
        initRange();

        const buildQS = () => {
          const fromIso = parseLocalInputToIso(elFrom?.value || '');
          const toIso = parseLocalInputToIso(elTo?.value || '');
          const hours = Number(elHours?.value || 72);
          const active = String(elActive?.value || 'all');
          const qs = [];
          if(fromIso) qs.push(`from=${encodeURIComponent(fromIso)}`);
          if(toIso) qs.push(`to=${encodeURIComponent(toIso)}`);
          if(!fromIso && !toIso) qs.push(`hours=${encodeURIComponent(String(hours))}`);
          const exportQs = qs.join('&') + `&active=all`;
          return { qs: qs.join('&') + `&active=${encodeURIComponent(active)}`, exportQs };
        };

        const refreshExport = () => {
          if(!elExport) return;
          const { exportQs } = buildQS();
          elExport.href = `/api/tracker/admin/device/${encodeURIComponent(deviceId)}/export/alerts.csv?${exportQs}`;
        };
        refreshExport();

        const renderAlerts = (items) => {
          const arr = Array.isArray(items) ? items : [];
          const act = arr.filter(x => x && x.is_active).length;
          const crit = arr.filter(x => x && String(x.severity||'') === 'crit').length;
          const warn = arr.filter(x => x && String(x.severity||'') === 'warn').length;
          if(elSum) elSum.textContent = `Алёртов: ${arr.length} · активных: ${act} · warn: ${warn} · crit: ${crit}`;
          if(!elList) return;
          if(!arr.length){
            elList.innerHTML = '<div class="muted">Нет алёртов</div>';
            return;
          }
          elList.innerHTML = arr.slice(0, 80).map(a => {
            const pill = a.is_active ? '<span class="ap-pill warn">активен</span>' : '<span class="ap-pill">закрыт</span>';
            const sev = a.severity ? String(a.severity) : '';
            const msg = a.message ? String(a.message) : '';
            const title = `${a.kind || ''}${sev ? ' · ' + sev : ''}`;
            return `
              <div class="ap-row">
                <div class="ap-row__top">
                  <div class="ap-row__title">${escapeHtml(title)}</div>
                  ${pill}
                </div>
                <div class="ap-row__meta">${escapeHtml(fmtIso(a.updated_at || a.created_at))}${msg ? ' · ' + escapeHtml(msg) : ''}</div>
              </div>
            `;
          }).join('');
        };

        const load = async () => {
          if(elSum) elSum.textContent = 'Загрузка…';
          if(elList) elList.innerHTML = '';
          refreshExport();
          const { qs } = buildQS();
          const r = await loadDeviceAlerts(deviceId, { hours: Number(elHours?.value || 72), active: String(elActive?.value || 'all'), fromIso: parseLocalInputToIso(elFrom?.value || ''), toIso: parseLocalInputToIso(elTo?.value || '') });
          if(!r.ok){
            if(elSum) elSum.textContent = `Не удалось загрузить алёрты (status ${r.status || '—'})`;
            return;
          }
          renderAlerts(r.items);
        };

        if(elApply) elApply.onclick = () => load();
        if(elClear) elClear.onclick = () => { initRange(); load(); };
        if(elHours) elHours.onchange = () => { initRange(); refreshExport(); };
        if(elActive) elActive.onchange = () => { refreshExport(); };
        if(elFrom) elFrom.onchange = () => { refreshExport(); };
        if(elTo) elTo.onchange = () => { refreshExport(); };

        // initial
        load();
      }
    }

    // выделение в списке
    markSelectedShift(sh.id);
  }

  function markSelectedShift(shiftId){
    state.selected.shift_id = shiftId;
    // подсветка карточек (при следующей перерисовке)
    const el = document.getElementById('list-shifts');
    if(el){
      Array.from(el.querySelectorAll('.ap-item')).forEach(x => {
        x.classList.toggle('selected', x.dataset.shiftId === String(shiftId));
      });
    }
  }

  async function selectShiftById(shiftId){
    try{
      markSelectedShift(String(shiftId));
      await openShiftCard(String(shiftId), { fit:true });
    }catch(e){
      console.warn('selectShiftById failed', e);
    }
  }


  
async function openShiftCard(shiftId, opts){
  // v41: drawer может показывать разные сущности, тут явно включаем режим смены
  setDrawerMode('shift');
  state.selected.incident_id = null;
  state.selected.object_id = null;
  // v17: open drawer immediately and show skeleton while fetching
  if(!(opts && opts.quietUpdate)) setDrawerLoading();

  const r = await fetchJson(API_SHIFT_DETAIL(shiftId));
  if(!r.ok){
    showToastT('cc_toast_open_shift_failed', {status: r.status}, 'warn');
    const pO = pane('overview');
    if(pO) pO.innerHTML = '<div class="muted">Не удалось загрузить данные по смене.</div>';
    return;
  }

  state.selected.detail = r.data;
  state.selected.user_id = r.data?.shift?.user_id || null;
  state.selected.shift_id = shiftId;
  // enable quick actions after successful load
  [elDrawerPan, elDrawerChat, elDrawerCopy, elDrawerDevice].forEach(b => { if(b) b.disabled = false; });

  renderDrawer(r.data);
  drawerSetTab((opts && opts.tab) || 'overview');

  // highlight selected marker
  rerenderVisible();

  if(opts && opts.fit){
    // v32: фокусируем карту и показываем явный маркер (даже если слой смен ещё не прорисовался)
    try{ focusDetailOnMap(r.data); }catch(_){ }
  }
}

  // ===== Drawer: Incident/Object cards (v41) =====
  function _fmtTs(ts){
    const s = String(ts || '');
    return s ? s.replace('T',' ').slice(0,19) : '';
  }

  function _num(v){
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  function _focusLatLon(lat, lon, zoom){
    if(lat == null || lon == null) return;
    try{ map.setView([lat, lon], Math.max(map.getZoom(), zoom || 17), { animate:true }); }catch(_){ }
  }

  function _renderIncidentOverview(inc){
    const addr = (inc.address || '').trim();
    const descr = (inc.description || '').trim();
    const st = String(inc.status || 'new');
    const pr = (inc.priority != null && inc.priority !== '') ? String(inc.priority) : '';
    const created = _fmtTs(inc.created_at);
    const updated = _fmtTs(inc.updated_at);

    const cams = (inc.object && Array.isArray(inc.object.cameras)) ? inc.object.cameras : [];
    const camsHtml = cams.length ? (
      `<div style="margin-top:8px">
        <div class="muted" style="margin-bottom:6px">Камеры объекта</div>
        <div style="display:flex; flex-direction:column; gap:6px">`
        + cams.map((c) => {
          const label = escapeHtml(c.label || c.type || 'камера');
          const url = escapeHtml(c.url || '');
          const typ = escapeHtml(c.type || '');
          const href = c.url ? `href="${escapeHtml(c.url)}" target="_blank" rel="noopener"` : '';
          return `<a class="btn" style="justify-content:flex-start" ${href}>${label}${typ ? ` <span class="muted">(${typ})</span>` : ''}</a>`;
        }).join('')
        + `</div>
      </div>`
    ) : '';

    const objLine = inc.object ? (
      `<div class="muted" style="margin-top:6px">Объект: ${escapeHtml(inc.object.name || ('#'+inc.object.id))}${inc.object.tags ? ` · ${escapeHtml(inc.object.tags)}` : ''}</div>`
    ) : '';

    return `
      <div class="kv">
        <div><b>ID:</b> #${escapeHtml(inc.id)}</div>
        <div><b>Статус:</b> <span class="tag tag-status-${escapeHtml(st)}">${escapeHtml(st)}</span>${pr ? ` &nbsp; <b>Приоритет:</b> <span class="tag tag-priority-${escapeHtml(pr)}">P${escapeHtml(pr)}</span>` : ''}</div>
        ${created ? `<div><b>Создан:</b> ${escapeHtml(created)}</div>` : ''}
        ${updated ? `<div><b>Обновлён:</b> ${escapeHtml(updated)}</div>` : ''}
      </div>
      <div style="margin-top:10px">
        <div style="font-weight:700">${addr ? escapeHtml(addr) : (inc.lat!=null && inc.lon!=null ? escapeHtml(`[${Number(inc.lat).toFixed(5)}, ${Number(inc.lon).toFixed(5)}]`) : '—')}</div>
        ${objLine}
        ${descr ? `<div class="muted" style="margin-top:8px; white-space:pre-wrap">${escapeHtml(descr)}</div>` : ''}
      </div>
      <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:12px">
        <button class="btn primary" type="button" id="drawer-inc-open-chat" data-incident-id="${escapeHtml(String(inc.id))}"><i class="fa-solid fa-comment-dots"></i> Чат</button>
        ${inc.object ? `<button class="btn" type="button" id="drawer-inc-open-object" data-object-id="${escapeHtml(String(inc.object.id))}"><i class="fa-solid fa-building"></i> Объект</button>
        <a class="btn" href="/admin/objects?highlight=${encodeURIComponent(String(inc.object.id))}" target="_blank" rel="noopener"><i class="fa-solid fa-list"></i> Объекты</a>` : ''}
        <a class="btn" href="/admin/incidents/${encodeURIComponent(String(inc.id))}" target="_blank" rel="noopener"><i class="fa-solid fa-arrow-up-right-from-square"></i> Полная карточка</a>
      </div>
      ${camsHtml}
    `;
  }

  function _renderIncidentEvents(events){
    const items = Array.isArray(events) ? events : [];
    if(!items.length) return '<div class="muted">Событий пока нет.</div>';
    return '<div style="display:flex; flex-direction:column; gap:8px">' + items.map(ev => {
      const ts = _fmtTs(ev.ts || ev.created_at);
      const type = escapeHtml(ev.event_type || ev.type || 'event');
      let payload = '';
      try{
        if(ev.payload != null){
          const s = (typeof ev.payload === 'string') ? ev.payload : JSON.stringify(ev.payload);
          payload = escapeHtml(s);
        }
      }catch(_){ payload = ''; }
      return `
        <div class="ap-card" style="padding:10px">
          <div style="display:flex; justify-content:space-between; gap:8px">
            <div style="font-weight:700">${type}</div>
            <div class="muted" style="font-size:12px">${escapeHtml(ts)}</div>
          </div>
          ${payload ? `<div class="muted" style="margin-top:6px; font-size:12px; white-space:pre-wrap">${payload}</div>` : ''}
        </div>
      `;
    }).join('') + '</div>';
  }

  function _shiftLabelFromState(shiftId){
    try{
      const sid = String(shiftId ?? '').trim();
      const sh = Array.isArray(state.shifts) ? state.shifts.find(x => String(x.shift_id) === sid) : null;
      if(!sh) return sid ? `#${sid}` : '#?';
      const lb = String(sh.unit_label || '').trim();
      return lb ? `${lb} (#${sid})` : `#${sid}`;
    }catch(_){ return `#${shiftId}`; }
  }


  function _renderIncidentAssignments(assignments, incidentId){
    const items = Array.isArray(assignments) ? assignments : [];
    const shifts = Array.isArray(state.shifts) ? state.shifts : [];

    const opt = shifts.map(sh => {
      const id = sh.shift_id;
      const lb = String(sh.unit_label || '').trim() || `Shift #${id}`;
      const sid = escapeHtml(String(id));
      return `<option value="${sid}">${escapeHtml(lb)} (#${sid})</option>`;
    }).join('');

    const picker = shifts.length
      ? `<select id="inc-assign-shift" class="input">${opt}</select>`
      : `<input id="inc-assign-shift" class="input" placeholder="shift_id (число)" inputmode="numeric" />`;

    const assignBox = `
      <div class="ap-card" style="padding:10px">
        <div style="font-weight:700; margin-bottom:6px">Назначить наряд</div>
        <div class="muted" style="font-size:12px; margin-bottom:8px">
          ${shifts.length ? 'Выберите активную смену и нажмите «Назначить».' : 'Список активных смен не загружен. Введите shift_id вручную.'}
        </div>
        <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap">
          ${picker}
          <button id="inc-assign-btn" class="btn primary" type="button" data-incident-id="${escapeHtml(String(incidentId))}">Назначить</button>
        </div>
      </div>
    `;

    if(!items.length){
      return `<div style="display:flex; flex-direction:column; gap:8px">${assignBox}<div class="muted">Назначений пока нет.</div></div>`;
    }

    const list = items.map(a => {
      const sid = a.shift_id;
      const label = escapeHtml(_shiftLabelFromState(sid));

      const tags = [];
      if(a.sla_accept_breach) tags.push('<span class="tag bad">SLA: принять</span>');
      if(a.sla_enroute_breach) tags.push('<span class="tag bad">SLA: выезд</span>');
      if(a.sla_onscene_breach) tags.push('<span class="tag bad">SLA: прибытие</span>');
      if(!tags.length) tags.push('<span class="tag ok">SLA ok</span>');

      let cur = 'назначен';
      if(a.closed_at) cur = 'закрыт';
      else if(a.resolved_at) cur = 'завершён';
      else if(a.on_scene_at) cur = 'на месте';
      else if(a.enroute_at) cur = 'в пути';
      else if(a.accepted_at) cur = 'принят';
      tags.unshift(`<span class="tag">${escapeHtml(cur)}</span>`);

      const actions = [];
      if(!a.accepted_at) actions.push(['accepted','Принял']);
      else if(!a.enroute_at) actions.push(['enroute','В пути']);
      else if(!a.on_scene_at) actions.push(['on_scene','На месте']);
      else if(!a.resolved_at) actions.push(['resolved','Завершил']);
      else if(!a.closed_at) actions.push(['closed','Закрыть']);

      const btns = actions.length ? actions.map(([st, txt]) =>
        `<button class="btn primary" type="button" data-ia="inc-status" data-incident-id="${escapeHtml(String(incidentId))}" data-shift-id="${escapeHtml(String(sid))}" data-status="${escapeHtml(String(st))}">${escapeHtml(txt)}</button>`
      ).join('') : `<span class="muted" style="font-size:12px">Статусы завершены</span>`;

      const rows = [
        ['Назначен', _fmtTs(a.assigned_at)],
        ['Принял', _fmtTs(a.accepted_at)],
        ['В пути', _fmtTs(a.enroute_at)],
        ['На месте', _fmtTs(a.on_scene_at)],
        ['Завершил', _fmtTs(a.resolved_at)],
        ['Закрыт', _fmtTs(a.closed_at)],
      ].filter(([_,v]) => v && v !== '—');

      const timesHtml = rows.length
        ? `<div class="muted" style="font-size:12px; margin-top:6px">${rows.map(([k,v]) => `${escapeHtml(k)}: ${escapeHtml(v)}`).join(' • ')}</div>`
        : '';

      return `
        <div class="ap-card" style="padding:10px">
          <div style="display:flex; justify-content:space-between; gap:8px; align-items:center">
            <div style="font-weight:700">${label}</div>
            <div style="display:flex; gap:6px; flex-wrap:wrap; justify-content:flex-end">${tags.join('')}</div>
          </div>
          ${timesHtml}
          <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:10px">
            ${btns}
          </div>
        </div>
      `;
    }).join('');

    return `<div style="display:flex; flex-direction:column; gap:8px">${assignBox}${list}</div>`;
  }

  function _wireIncidentAssignments(incidentId){
    const btnAssign = document.getElementById('inc-assign-btn');
    if(btnAssign){
      btnAssign.onclick = async () => {
        const el = document.getElementById('inc-assign-shift');
        const raw = el ? (el.value || el.getAttribute('value') || '').trim() : '';
        const shiftId = parseInt(raw, 10);
        if(!shiftId || isNaN(shiftId)) {
          showToast('Укажите корректный shift_id');
          return;
        }
        try{
          btnAssign.disabled = true;
          const r = await fetchJson(`/api/incidents/${incidentId}/assign`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ shift_id: shiftId })
          });
          if(!r.ok){
            showToast(r.error || 'Не удалось назначить');
            btnAssign.disabled = false;
            return;
          }
          showToast('Наряд назначен');
          await openIncidentCard(incidentId, { tab: 'track', fit: false, quietUpdate: true });
        }catch(e){
          showToast('Ошибка назначения');
        }finally{
          try{ btnAssign.disabled = false; }catch(_){ }
        }
      };
    }

    document.querySelectorAll('[data-ia="inc-status"]').forEach(b => {
      b.onclick = async () => {
        const shiftId = parseInt(b.dataset.shiftId || '0', 10);
        const status = String(b.dataset.status || '').trim();
        if(!shiftId || !status) return;
        try{
          b.disabled = true;
          const r = await fetchJson(`/api/incidents/${incidentId}/status`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ shift_id: shiftId, status })
          });
          if(!r.ok){
            showToast(r.error || 'Не удалось обновить статус');
            b.disabled = false;
            return;
          }
          showToast('Статус обновлён');
          await openIncidentCard(incidentId, { tab: 'track', fit: false, quietUpdate: true });
        }catch(_){
          showToast('Ошибка обновления статуса');
        }finally{
          try{ b.disabled = false; }catch(_){ }
        }
      };
    });
  }


  async function openIncidentCard(incidentId, opts){
    const id = String(incidentId ?? '').trim();
    if(!id) return;

    setDrawerMode('incident');
    state.selected.shift_id = null;
    state.selected.detail = null;
    state.selected.user_id = null;
    state.selected.object_id = null;
    state.selected.incident_id = id;

    if(!(opts && opts.quietUpdate)) setDrawerLoading();

    const r = await fetchJson(`/api/incidents/${encodeURIComponent(id)}`, { credentials: 'same-origin' });
    if(!r.ok){
      showToast('Не удалось загрузить инцидент (HTTP ' + r.status + ')', 'warn');
      const pO = pane('overview');
      if(pO) pO.innerHTML = '<div class="muted">Не удалось загрузить инцидент.</div>';
      drawerSetTab('overview');
      return;
    }
    const inc = r.data || {};
    const lat = _num(inc.lat);
    const lon = _num(inc.lon);

    // если инцидент привязан к объекту — подтянем объект и камеры, чтобы UI был в 1–2 клика
    const objId = (inc.object && inc.object.id != null) ? String(inc.object.id).trim() : ((inc.object_id != null && String(inc.object_id).trim()) ? String(inc.object_id).trim() : ((inc.objectId != null && String(inc.objectId).trim()) ? String(inc.objectId).trim() : ''));
    state.selected.object_id = objId || null;
    if(objId && !inc.object){
      try{
        const o = await fetchJson(`/api/objects/${encodeURIComponent(objId)}`, { credentials: 'same-origin' });
        if(o.ok) inc.object = o.data || null;
      }catch(_){ /* ignore */ }
    }

    // заголовок + действия
    drawerOpen();
    refreshDrawerChatBadge();
    if(elDrawerTitle) elDrawerTitle.textContent = `Инцидент #${inc.id ?? id}`;
    if(elDrawerSub) elDrawerSub.textContent = (inc.address ? String(inc.address) : (lat!=null && lon!=null ? `[${lat.toFixed(5)}, ${lon.toFixed(5)}]` : ''));

    if(elDrawerPan){
      elDrawerPan.disabled = !(lat!=null && lon!=null);
      elDrawerPan.onclick = () => {
        // если есть overlay, лучше через него (он и слой включит)
        try{
          if(window.IncidentsOverlay && typeof window.IncidentsOverlay.focus === 'function'){
            window.IncidentsOverlay.focus(id, { openPopup: false, zoom: 17 });
            return;
          }
        }catch(_){ }
        _focusLatLon(lat, lon, 17);
      };
    }

    if(elDrawerCopy){
      const okCoords = (lat!=null && lon!=null);
      elDrawerCopy.disabled = !okCoords;
      elDrawerCopy.onclick = async () => {
        if(!okCoords) return;
        const s = `${lat}, ${lon}`;
        const ok = await copyToClipboard(s);
        showToastT(ok ? 'cc_toast_copied' : 'cc_toast_copy_failed', null, ok ? '' : 'warn');
      };
    }


    // чат по инциденту (Stage41.10)
    if(elDrawerChat){
      elDrawerChat.disabled = false;
      elDrawerChat.onclick = () => {
        try{
          const iid = String(inc.id ?? id).trim();
          if(typeof window.chat2OpenForIncident === 'function'){
            window.chat2OpenForIncident(iid);
            return;
          }
          if(typeof window.chat2OpenChannel === 'function'){
            // fallback: вручную ensure и открыть
            fetch('/api/chat2/ensure_incident_channel', {
              method: 'POST',
              headers: { 'Content-Type':'application/json' },
              body: JSON.stringify({ marker_id: iid })
            }).then(r => r.json().then(j => ({ok:r.ok, j}))).then(({ok,j}) => {
              if(!ok) throw new Error(j && j.error ? j.error : 'ensure failed');
              const chId = (j && (j.channel_id || j.id)) ? (j.channel_id || j.id) : null;
              if(chId) window.chat2OpenChannel(chId, 'Инцидент #' + iid);
            }).catch(_ => showToast('Не удалось открыть чат инцидента', 'warn'));
            return;
          }
        }catch(_){ }
        showToast('Чат не готов', 'warn');
      };
    }
    // обзор
    const pO = pane('overview');
    if(pO) pO.innerHTML = _renderIncidentOverview(inc);

    // wire: открыть объект в том же drawer
    setTimeout(() => {
      try{
        const bChat = document.getElementById('drawer-inc-open-chat');
        if(bChat){
          bChat.onclick = () => {
            try{
              if(elDrawerChat){ elDrawerChat.click(); return; }
            }catch(_e){}
            try{
              const iid = String(inc.id ?? id).trim();
              if(typeof window.chat2OpenForIncident === 'function') return window.chat2OpenForIncident(iid);
            }catch(_e){}
          };
        }
        const bObj = document.getElementById('drawer-inc-open-object');
        if(bObj){
          bObj.onclick = () => {
            const oid = String(bObj.dataset.objectId || objId || '').trim();
            if(!oid) return;
            if(typeof openObjectCard === 'function') openObjectCard(oid, { fit:true });
            else if(window.CC && typeof window.CC.openObjectCard === 'function') window.CC.openObjectCard(oid, { fit:true });
            else window.location.href = `/admin/panel?focus_object=${encodeURIComponent(oid)}`;
          };
        }
      }catch(_){ }
    }, 0);

    // журнал (подгружаем отдельно, но не ломаем если нет)
    const pJ = pane('journal');
    if(pJ) pJ.innerHTML = '<div class="muted">Загрузка событий…</div>';
    try{
      const e = await fetchJson(`/api/incidents/${encodeURIComponent(id)}/events`, { credentials: 'same-origin' });
      if(pJ) pJ.innerHTML = e.ok ? _renderIncidentEvents(e.data) : '<div class="muted">События недоступны.</div>';
    }catch(_){
      if(pJ) pJ.innerHTML = '<div class="muted">События недоступны.</div>';
    }

    // назначения (вкладка "track" для инцидента)
    const pT = pane('track');
    if(pT) pT.innerHTML = '<div class="muted">Загрузка назначений…</div>';
    try{
      const a = await fetchJson(`/api/incidents/${encodeURIComponent(id)}/assignments`, { credentials: 'same-origin' });
      if(a.ok){
        if(pT) pT.innerHTML = _renderIncidentAssignments(a.data, id);
        _wireIncidentAssignments(id);
      } else {
        if(pT) pT.innerHTML = '<div class="muted">Назначения недоступны.</div>';
      }
    }catch(_){
      if(pT) pT.innerHTML = '<div class="muted">Назначения недоступны.</div>';
    }

    drawerSetTab((opts && opts.tab) || (state.drawer.last_tab || 'overview') || 'overview');

    // легкий фокус карты, если попросили
    if(opts && opts.fit){
      try{
        if(window.IncidentsOverlay && typeof window.IncidentsOverlay.focus === 'function'){
          window.IncidentsOverlay.focus(id, { openPopup: false, zoom: 17 });
        } else {
          _focusLatLon(lat, lon, 17);
        }
      }catch(_){ }
    }
  }

  function _renderObjectOverview(obj){
    const name = (obj.name || '').trim() || (`Объект #${obj.id}`);
    const addr = (obj.address || '').trim();
    const descr = (obj.description || '').trim();
    const tags = (obj.tags || '').trim();
    const created = _fmtTs(obj.created_at);
    const updated = _fmtTs(obj.updated_at);
    const lat = _num(obj.lat);
    const lon = _num(obj.lon);

    const cams = Array.isArray(obj.cameras) ? obj.cameras : [];
    const camsHtml = cams.length ? (
      `<div style="margin-top:10px">
        <div class="muted" style="margin-bottom:6px">Камеры</div>
        <div style="display:flex; flex-direction:column; gap:6px">`
        + cams.map((c) => {
          const label = escapeHtml(c.label || c.type || 'камера');
          const url = escapeHtml(c.url || '');
          const typ = escapeHtml(c.type || '');
          const href = c.url ? `href="${escapeHtml(c.url)}" target="_blank" rel="noopener"` : '';
          return `<a class="btn" style="justify-content:flex-start" ${href}>${label}${typ ? ` <span class="muted">(${typ})</span>` : ''}</a>`;
        }).join('')
        + `</div>
      </div>`
    ) : '<div class="muted" style="margin-top:10px">Камер нет.</div>';

    return `
      <div style="font-weight:800; font-size:16px">${escapeHtml(name)}</div>
      ${addr ? `<div class="muted" style="margin-top:6px">${escapeHtml(addr)}</div>` : ''}
      <div class="kv" style="margin-top:10px">
        ${tags ? `<div><b>Теги:</b> ${escapeHtml(tags)}</div>` : ''}
        ${(lat!=null && lon!=null) ? `<div><b>Координаты:</b> ${lat.toFixed(5)}, ${lon.toFixed(5)}</div>` : ''}
        ${created ? `<div><b>Создан:</b> ${escapeHtml(created)}</div>` : ''}
        ${updated ? `<div><b>Обновлён:</b> ${escapeHtml(updated)}</div>` : ''}
      </div>
      ${descr ? `<div class="muted" style="margin-top:10px; white-space:pre-wrap">${escapeHtml(descr)}</div>` : ''}
      <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:12px">
        <button class="btn" type="button" id="drawer-obj-edit"><i class="fa-solid fa-pen"></i> Редактировать</button>
        <button class="btn primary" type="button" id="drawer-obj-incident"><i class="fa-solid fa-bolt"></i> Инцидент</button>
        <a class="btn" href="/admin/objects?highlight=${encodeURIComponent(String(obj.id))}" target="_blank" rel="noopener"><i class="fa-solid fa-arrow-up-right-from-square"></i> Открыть в списке</a>
      </div>
      ${camsHtml}
    `;
  }

  async function openObjectCard(objectId, opts){
    const id = String(objectId ?? '').trim();
    if(!id) return;

    setDrawerMode('object');
    state.selected.shift_id = null;
    state.selected.detail = null;
    state.selected.user_id = null;
    state.selected.incident_id = null;
    state.selected.object_id = id;

    if(!(opts && opts.quietUpdate)) setDrawerLoading();

    const r = await fetchJson(`/api/objects/${encodeURIComponent(id)}`, { credentials: 'same-origin' });
    if(!r.ok){
      showToast('Не удалось загрузить объект (HTTP ' + r.status + ')', 'warn');
      const pO = pane('overview');
      if(pO) pO.innerHTML = '<div class="muted">Не удалось загрузить объект.</div>';
      drawerSetTab('overview');
      return;
    }
    const obj = r.data || {};
    const lat = _num(obj.lat);
    const lon = _num(obj.lon);

    drawerOpen();
    if(elDrawerTitle) elDrawerTitle.textContent = `Объект #${obj.id ?? id}`;
    if(elDrawerSub) elDrawerSub.textContent = (obj.address ? String(obj.address) : (lat!=null && lon!=null ? `[${lat.toFixed(5)}, ${lon.toFixed(5)}]` : ''));

    if(elDrawerPan){
      elDrawerPan.disabled = !(lat!=null && lon!=null);
      elDrawerPan.onclick = () => {
        try{
          if(window.ObjectsOverlay && typeof window.ObjectsOverlay.focus === 'function'){
            window.ObjectsOverlay.focus(id, { openPopup: false, zoom: 17 });
            return;
          }
        }catch(_){ }
        _focusLatLon(lat, lon, 17);
      };
    }

    if(elDrawerCopy){
      const okCoords = (lat!=null && lon!=null);
      elDrawerCopy.disabled = !okCoords;
      elDrawerCopy.onclick = async () => {
        if(!okCoords) return;
        const s = `${lat}, ${lon}`;
        const ok = await copyToClipboard(s);
        showToastT(ok ? 'cc_toast_copied' : 'cc_toast_copy_failed', null, ok ? '' : 'warn');
      };
    }

    const pO = pane('overview');
    if(pO) pO.innerHTML = _renderObjectOverview(obj);

    // привяжем кнопки из overview
    setTimeout(() => {
      const bEdit = document.getElementById('drawer-obj-edit');
      const bInc = document.getElementById('drawer-obj-incident');
      if(bEdit){
        bEdit.onclick = () => {
          if(window.ObjectsUI && typeof window.ObjectsUI.openEdit === 'function') window.ObjectsUI.openEdit(String(obj.id ?? id));
          else showToast('Редактор объектов не готов', 'warn');
        };
      }
      if(bInc){
        bInc.onclick = () => {
          if(window.ObjectsUI && typeof window.ObjectsUI.createIncidentFromObject === 'function') window.ObjectsUI.createIncidentFromObject(String(obj.id ?? id), { interactive: !!(ev && ev.shiftKey) });
          else showToast('Создание инцидента из объекта не готово', 'warn');
        };
      }
    }, 0);

    const pJ = pane('journal');
    if(pJ) pJ.innerHTML = '<div class="muted">Для объекта журнал появится позже (инциденты/аудит).</div>';
    const pT = pane('track');
    if(pT) pT.innerHTML = '<div class="muted">Трек доступен только для смен.</div>';

    drawerSetTab((opts && opts.tab) || (state.drawer.last_tab || 'overview') || 'overview');

    if(opts && opts.fit){
      try{
        if(window.ObjectsOverlay && typeof window.ObjectsOverlay.focus === 'function'){
          window.ObjectsOverlay.focus(id, { openPopup: false, zoom: 17 });
        } else {
          _focusLatLon(lat, lon, 17);
        }
      }catch(_){ }
    }
  }

  // Экспортируем в window.CC, чтобы overlay/панели могли открывать drawer вместо перехода по страницам.
  window.CC = window.CC || {};
  window.CC.openIncidentCard = openIncidentCard;
  window.CC.openObjectCard = openObjectCard;


async function loadTracking(sessionId, {fit=false, quiet=false}={}){
    if(!sessionId) return;
    if(state.selected.tracking_loaded_for === sessionId && state.selected.tracking){
      drawTrack(state.selected.tracking.points, state.selected.tracking.stops, fit);
      // обновим replay
      prepareReplayControls();
      return;
    }
    const r = await fetchJson(`/api/duty/admin/tracking/${encodeURIComponent(sessionId)}`);
    if(!r.ok){
      if(!quiet) showToastT('cc_toast_track_load_failed', {status: r.status}, 'warn');
      return;
    }
    const points = Array.isArray(r.data.points) ? r.data.points : [];
    const stops = Array.isArray(r.data.stops) ? r.data.stops : [];
    state.selected.tracking = { session: r.data.session || {}, points, stops, snapshot_url: r.data.snapshot_url };
    state.selected.tracking_loaded_for = sessionId;

    drawTrack(points, stops, fit);
    prepareReplayControls();
    renderTrackExtras();
  }

  function prepareReplayControls(){
    const pts = state.selected.tracking?.points || [];
    const elRange = document.getElementById('rp-range');
    if(elRange){
      elRange.min = '0';
      elRange.max = String(Math.max(0, pts.length - 1));
      state.selected.replay.idx = Math.min(state.selected.replay.idx, Math.max(0, pts.length - 1));
      elRange.value = String(state.selected.replay.idx);
    }
    updateReplayUI();
  }

  function renderTrackExtras(){
    const elSummary = document.getElementById('trk-summary');
    const elStops = document.getElementById('trk-stops');
    const tr = state.selected.tracking;
    if(!tr) return;
    const pts = tr.points || [];
    const st = tr.stops || [];
    const snap = tr.snapshot_url;

    if(elSummary){
      const started = tr.session?.started_at;
      const ended = tr.session?.ended_at;
      elSummary.innerHTML = `
        <div>Точек: <b>${pts.length}</b> · стоянок: <b>${st.length}</b></div>
        <div>Начало: ${escapeHtml(fmtIso(started))} · Конец: ${escapeHtml(ended ? fmtIso(ended) : '…')}</div>
        ${snap ? `<div style="margin-top:6px"><a href="${escapeHtml(snap)}" target="_blank">Открыть снимок маршрута (SVG)</a></div>` : ''}
      `;
    }

    if(elStops){
      if(!st.length){
        elStops.innerHTML = '<div class="muted">Стоянок нет (или мало точек)</div>';
      } else {
        elStops.innerHTML = st.slice(0, 30).map((x, i) => {
          const m = Math.round((x.duration_sec || 0) / 60);
          const tt = `${m} мин · R≈${x.radius_m || 10}м`;
          const cc = `${(x.center_lat ?? 0).toFixed?.(5) ?? x.center_lat}, ${(x.center_lon ?? 0).toFixed?.(5) ?? x.center_lon}`;
          return `
            <div class="ap-row">
              <div class="ap-row__top">
                <div class="ap-row__title">Стоянка #${i+1}</div>
                <span class="ap-pill">${escapeHtml(tt)}</span>
              </div>
              <div class="ap-row__meta">${escapeHtml(cc)}</div>
              <div class="ap-item__actions">
                <button class="btn" data-stop="${i}">${escapeHtml(T('cc_action_show'))}</button>
              </div>
            </div>
          `;
        }).join('');

        Array.from(elStops.querySelectorAll('button[data-stop]')).forEach(btn => {
          btn.onclick = () => {
            const i = Number(btn.dataset.stop);
            const x = st[i];
            if(!x) return;
            if(x.center_lat != null && x.center_lon != null){
              map.setView([x.center_lat, x.center_lon], Math.max(map.getZoom(), 17), { animate:true });
            }
          };
        });
      }
    }
  }

  /* ===== Markers ===== */

function _sosUsersSet(){
  return new Set((state.sos || []).map(x => String(x.user_id)));
}

function applyShiftMarkerStyle(mk, sh){
  if(!mk || !sh) return;
  const uid = String(sh.user_id);
  const focusUid = (state.selected && state.selected.user_id != null) ? String(state.selected.user_id) : null;
  const isSelected = focusUid ? (focusUid === uid) : false;
  const isDim = (focusUid && focusUid !== uid);
  const isSos = _sosUsersSet().has(uid);
  const isRevoked = _shiftIsRevoked(sh);
  const isStale = _isShiftStale(sh);
  const hasProb = _shiftHasProblems(sh);
  const isLive = !!sh.tracking_active;
  const last = getShiftLastPoint(sh);
  const isEst = isEstimatePoint(last);

  let color = C_MUTED;
  let fill = C_MUTED;

  if(isSos){
    color = C_WARN; fill = C_WARN;
  } else if(isRevoked){
    color = C_PURPLE; fill = C_PURPLE;
  } else if(hasProb || isStale){
    color = C_AMBER; fill = C_AMBER;
  } else if(isEst){
    color = C_INFO; fill = C_INFO;
  } else if(isLive){
    color = C_SUCCESS; fill = C_SUCCESS;
  }

  const weight = isSelected ? 4 : 2;
  const fillOpacity = isDim ? 0.18 : (isSelected ? 0.75 : 0.55);
  const opacity = isDim ? 0.35 : 0.95;
  const dashArray = isEst ? '6 6' : null;
  mk.setStyle({ color, fillColor: fill, weight, fillOpacity, opacity, dashArray });

  try{ mk.setRadius(isSelected ? 9 : 7); }catch(e){}
}


function applyShiftAccuracyStyle(c, sh){
  if(!c || !sh) return;
  const uid = String(sh.user_id);
  const focusUid = (state.selected && state.selected.user_id != null) ? String(state.selected.user_id) : null;
  const isSelected = focusUid ? (focusUid === uid) : false;
  const isDim = (focusUid && focusUid !== uid);
  const isSos = _sosUsersSet().has(uid);
  const isRevoked = _shiftIsRevoked(sh);
  const isStale = _isShiftStale(sh);
  const hasProb = _shiftHasProblems(sh);
  const isLive = !!sh.tracking_active;
  const last = getShiftLastPoint(sh);
  const isEst = isEstimatePoint(last);

  let color = C_MUTED;
  let fill = C_MUTED;

  if(isSos){
    color = C_WARN; fill = C_WARN;
  } else if(isRevoked){
    color = C_PURPLE; fill = C_PURPLE;
  } else if(hasProb || isStale){
    color = C_AMBER; fill = C_AMBER;
  } else if(isEst){
    color = C_INFO; fill = C_INFO;
  } else if(isLive){
    color = C_SUCCESS; fill = C_SUCCESS;
  }

  const weight = isSelected ? 2 : 1;
  const fillOpacity = isDim ? 0.02 : (isSelected ? 0.12 : 0.06);
  const opacity = isDim ? 0.18 : 0.55;
  const dashArray = isEst ? '6 8' : null;
  c.setStyle({ color, fillColor: fill, weight, fillOpacity, opacity, dashArray });
}


  function upsertShiftMarker(sh){
    const last = getShiftLastPoint(sh);
    if(!last || last.lat == null || last.lon == null) return;

    const uid = String(sh.user_id);
    const ll = [last.lat, last.lon];
    const title = labelForShift(sh);

    let mk = state.mkShift.get(uid);
    if(!mk){
      mk = L.circleMarker(ll, {
        radius: 7,
        weight: 2,
        fillOpacity: 0.55,
      }).addTo(layers.shifts);

      mk.on('click', () => {
        // единая логика выбора (подсветка списка + маркера)
        selectShiftById(sh.shift_id);
      });
      state.mkShift.set(uid, mk);
    } else {
      mk.setLatLng(ll);
    }

    applyShiftMarkerStyle(mk, sh);

    // Accuracy circle (if backend provides accuracy_m)
    const acc = (last.accuracy_m != null) ? Number(last.accuracy_m) : null;
    let ac = state.mkShiftAcc.get(uid);
    if(acc && isFinite(acc) && acc > 0){
      const r = Math.min(300, Math.max(5, acc));
      if(!ac){
        ac = L.circle(ll, { radius: r, weight: 1, fillOpacity: 0.06, opacity: 0.55 }).addTo(layers.shifts);
        state.mkShiftAcc.set(uid, ac);
      } else {
        ac.setLatLng(ll);
        try{ ac.setRadius(r); }catch(e){}
      }
      applyShiftAccuracyStyle(ac, sh);
    } else if(ac){
      try{ layers.shifts.removeLayer(ac); }catch(e){}
      state.mkShiftAcc.delete(uid);
    }

    const accTxt = (acc && isFinite(acc)) ? ` <span style="opacity:.85">±${Math.round(acc)}м</span>` : '';
    const isEst = isEstimatePoint(last);
    const confPct = isEst ? fmtPercent01(last && last.confidence) : null;
    let stTxt = sh.tracking_active ? T('cc_tip_live') : T('cc_tip_idle');
    if(isEst){
      stTxt = T('cc_tip_est') + (confPct != null ? (' ' + confPct + '%') : '');
    } else {
      stTxt = T('cc_tip_gnss') + ' · ' + stTxt;
    }
    mk.bindTooltip(`${escapeHtml(title)}${accTxt}<br><span style="opacity:.75">${escapeHtml(stTxt)}</span>`, { direction:'top', opacity:0.95 });
  }

  function dropMissingShiftMarkers(shifts){
    const keep = new Set(shifts.map(s => String(s.user_id)));
    for(const [uid, mk] of state.mkShift.entries()){
      if(!keep.has(uid)){
        try{ layers.shifts.removeLayer(mk); }catch(e){}
        state.mkShift.delete(uid);
      }
    }
    for(const [uid, c] of state.mkShiftAcc.entries()){
      if(!keep.has(uid)){
        try{ layers.shifts.removeLayer(c); }catch(e){}
        state.mkShiftAcc.delete(uid);
      }
    }
  }

  function upsertSosMarker(sos){
    if(!sos || sos.lat == null || sos.lon == null) return;
    const id = String(sos.id);
    const ll = [sos.lat, sos.lon];
    const title = sos.unit_label || ('TG ' + sos.user_id);

    let mk = state.mkSos.get(id);
    if(!mk){
      mk = L.marker(ll).addTo(layers.sos);
      mk.on('click', () => {
        map.setView(ll, Math.max(map.getZoom(), 16), { animate:true });
        // можно открыть карточку смены (если известна)
        if(sos.shift_id) openShiftCard(sos.shift_id, { tab:'overview', fit:false });
      });
      state.mkSos.set(id, mk);
    } else {
      mk.setLatLng(ll);
    }
    mk.bindTooltip(`🆘 ${escapeHtml(title)}`, { direction:'top', opacity:0.95 });
  }

  function dropMissingSosMarkers(sosList){
    const keep = new Set(sosList.map(s => String(s.id)));
    for(const [id, mk] of state.mkSos.entries()){
      if(!keep.has(id)){
        try{ layers.sos.removeLayer(mk); }catch(e){}
        state.mkSos.delete(id);
      }
    }
  }

  function upsertPendingMarker(pm){
    if(!pm || pm.lat == null || pm.lon == null) return;
    const id = String(pm.id);
    const ll = [pm.lat, pm.lon];
    const title = pm.name || ('Заявка #' + pm.id);

    let mk = state.mkPending.get(id);
    if(!mk){
      mk = L.circleMarker(ll, { radius: 6, weight: 2, fillOpacity: 0.45 }).addTo(layers.pending);
      mk.on('click', () => openPendingPopup(pm));
      state.mkPending.set(id, mk);
    } else {
      mk.setLatLng(ll);
    }
    mk.bindTooltip(`🔔 ${escapeHtml(title)}`, { direction:'top', opacity:0.95 });
  }

  function dropMissingPendingMarkers(list){
    const keep = new Set(list.map(x => String(x.id)));
    for(const [id, mk] of state.mkPending.entries()){
      if(!keep.has(id)){
        try{ layers.pending.removeLayer(mk); }catch(e){}
        state.mkPending.delete(id);
      }
    }
  }

  /* ===== UI render ===== */

  function getShiftFilters(){
    const fltLive = document.getElementById('flt-live');
    const fltBreak = document.getElementById('flt-break');
    const fltSos = document.getElementById('flt-sos');
    const fltStale = document.getElementById('flt-stale');
    return {
      live: !!(fltLive && fltLive.checked),
      break: !!(fltBreak && fltBreak.checked),
      sos: !!(fltSos && fltSos.checked),
      stale: !!(fltStale && fltStale.checked),
    };
  }


function rerenderVisible(){
  renderShifts(state.shifts);

  // карта
  const fMap = getShiftFilters();
  const sosUsersMap = new Set(state.sos.map(x => String(x.user_id)));
  let vis = (state.shifts || []).filter(sh => {
    if(fMap.live && !sh.tracking_active) return false;
    if(fMap.break && !sh.break) return false;
    if(fMap.sos && !sosUsersMap.has(String(sh.user_id))) return false;
    if(fMap.stale && !_isShiftStale(sh)) return false;
    return true;
  });
  vis = _applyQuickFilter(vis);
  vis.forEach(sh => { try{ upsertShiftMarker(sh); }catch(e){ console.warn('upsertShiftMarker failed', e); } });
  dropMissingShiftMarkers(vis);

  updateKpi();
}


  
function _alertSummaryForShift(sh){
  const dev = state.deviceByUser ? state.deviceByUser.get(String(sh.user_id)) : null;
  const alerts = (dev && Array.isArray(dev.alerts)) ? dev.alerts : [];
  let has = alerts.length > 0;
  let crit = false, warn = false;
  let kinds = new Set();
  alerts.forEach(a => {
    if(!a) return;
    if(a.kind) kinds.add(String(a.kind));
    if(a.severity === 'crit') crit = true;
    if(a.severity === 'warn') warn = true;
  });
  return { alerts, has, crit, warn, kinds };
}

function _shiftStatus(sh){
    // revoked имеет приоритет (чтобы не путать со stale)
    if(_shiftIsRevoked(sh)) return { key:'revoked', label: T('cc_status_revoked'), color: C_PURPLE, crit:false, stale:false, revoked:true };

    const h = sh.health || null;

    // если служба остановлена корректно — показываем «конец службы», а не «потерян сигнал»
    const ended = (!sh.tracking_active) && !!h && (h.tracking_on === false || h.trackingOn === false);

    // SOS
    const hasSos = (Array.isArray(sh.sos) && sh.sos.length) || (Array.isArray(state.sos) && state.sos.some(s => String(s.user_id) === String(sh.user_id)));
    if(hasSos) return { key:'sos', label: T('cc_status_sos'), color: C_WARN, crit:true, stale:false };

    // stale (но не для ended)
    const isStale = (!ended) && _isShiftStale(sh);

    // alerts
    const hasCritAlert = _hasAlert(sh, 'crit');
    const hasWarnAlert = _hasAlert(sh, 'warn') || _hasAlert(sh, 'info') || (Array.isArray(sh.alerts) && sh.alerts.some(a => String(a.kind||'').includes('low_accuracy')));

    if(hasCritAlert) return { key:'crit', label: T('cc_status_crit'), color: C_DANGER, crit:true, stale:isStale };
    if(isStale) return { key:'stale', label: T('cc_status_stale'), color: C_AMBER, crit:true, stale:true };

    if(ended) return { key:'ended', label: T('cc_status_ended'), color: C_MUTED, crit:false, stale:false };
    if(hasWarnAlert) return { key:'warn', label: T('cc_status_warn'), color: C_AMBER2, crit:false, stale:false };

    // live / idle
    return sh.tracking_active
      ? { key:'ok', label: T('cc_status_ok'), color: C_SUCCESS, crit:false, stale:false }
      : { key:'idle', label: T('cc_status_idle'), color: C_MUTED, crit:false, stale:false };
  }

function _sortShiftsForUI(arr){
  const sosUsers = new Set(state.sos.map(x => String(x.user_id)));
  return (arr || []).slice().sort((a,b) => {
    const aSos = sosUsers.has(String(a.user_id)) ? 1 : 0;
    const bSos = sosUsers.has(String(b.user_id)) ? 1 : 0;
    if(bSos !== aSos) return bSos - aSos;

    const aSum = _alertSummaryForShift(a);
    const bSum = _alertSummaryForShift(b);
    const aCrit = aSum.crit ? 1 : 0;
    const bCrit = bSum.crit ? 1 : 0;
    if(bCrit !== aCrit) return bCrit - aCrit;

    const aSt = _isShiftStale(a) ? 1 : 0;
    const bSt = _isShiftStale(b) ? 1 : 0;
    if(bSt !== aSt) return bSt - aSt;

    const aProb = aSum.has ? 1 : 0;
    const bProb = bSum.has ? 1 : 0;
    if(bProb !== aProb) return bProb - aProb;

    const aLive = a.tracking_active ? 1 : 0;
    const bLive = b.tracking_active ? 1 : 0;
    if(bLive !== aLive) return bLive - aLive;

    // newest last point first
    const aTs = a.last && a.last.ts ? Date.parse(a.last.ts) : 0;
    const bTs = b.last && b.last.ts ? Date.parse(b.last.ts) : 0;
    return bTs - aTs;
  });
}

function renderCriticalNow(rawShifts){
  const el = document.getElementById('critical-now');
  if(!el) return;

  const sosUsers = new Set(state.sos.map(x => String(x.user_id)));
  const list = (rawShifts || []).filter(sh => {
    const a = _alertSummaryForShift(sh);
    const isSos = sosUsers.has(String(sh.user_id));
    const isStale = _isShiftStale(sh) || a.kinds.has('stale_points') || a.kinds.has('stale_health');
    return isSos || a.crit || isStale;
  });
  const sorted = _sortShiftsForUI(list).slice(0, 6);

  if(!sorted.length){
    el.style.display = 'none';
    el.innerHTML = '';
    return;
  }

  const counts = {
    sos: (rawShifts||[]).filter(x => sosUsers.has(String(x.user_id))).length,
    crit: (rawShifts||[]).filter(x => _alertSummaryForShift(x).crit).length,
    stale: (rawShifts||[]).filter(x => _isShiftStale(x) || _alertSummaryForShift(x).kinds.has('stale_points') || _alertSummaryForShift(x).kinds.has('stale_health')).length
  };

  el.style.display = '';
  el.innerHTML = `
    <div class="ap-critical__head">
      <div class="ap-critical__title">${escapeHtml(T('cc_critical_now'))}</div>
      <div class="ap-critical__meta">${escapeHtml(T('cc_status_sos'))} ${counts.sos} · ${escapeHtml(T('cc_status_crit'))} ${counts.crit} · ${escapeHtml(T('cc_status_stale'))} ${counts.stale}</div>
    </div>
    <div class="ap-critical__list">
      ${sorted.map(sh => {
        const st = _shiftStatus(sh);
        const last = getShiftLastPoint(sh);
        const lastLine = last && last.ts ? (T('cc_last_prefix') + ' ' + fmtAge(Math.max(0, (Date.now() - Date.parse(last.ts)))/1000)) : (T('cc_last_prefix') + ' —');
        return `
          <div class="ap-critical__item">
            <div class="ap-critical__left">
              <div class="ap-critical__name">${escapeHtml(labelForShift(sh))}</div>
              <div class="ap-critical__sub">${escapeHtml(lastLine)}</div>
            </div>
            <div class="ap-critical__right">
              ${st.key !== 'idle' ? `<span class="ap-badge ${st.color}">${st.label}</span>` : ''}
              <button class="btn btn-sm" data-shift-id="${escapeHtml(String(sh.shift_id))}">${escapeHtml(T('cc_btn_open'))}</button>
            </div>
          </div>
        `;
      }).join('')}
    </div>
  `;

  el.querySelectorAll('button[data-shift-id]').forEach(btn => {
    btn.addEventListener('click', () => {
      const sid = btn.getAttribute('data-shift-id');
      if(sid) selectShiftById(String(sid));
    });
  });
}

function renderShifts(rawShifts){
    const el = document.getElementById('list-shifts');
    const cnt = document.getElementById('count-shifts');
    if(!el) return;

    const f = getShiftFilters();
    const sosUsers = new Set(state.sos.map(x => String(x.user_id)));
    const now = Date.now();

    
let shifts = (rawShifts || []).filter(sh => {
  if(f.live && !sh.tracking_active) return false;
  if(f.break && !sh.break) return false;
  if(f.sos && !sosUsers.has(String(sh.user_id))) return false;
  if(f.stale && !_isShiftStale(sh)) return false;
  return true;
});

// quick filter bar (all/live/problems/sos/stale/revoked)
shifts = _applyQuickFilter(shifts);

// v31: убрать скрытые карточки (по кнопке ✕). Активные автоматически возвращаем.
let _dismissChanged = false;
shifts = (shifts || []).filter(sh => {
  const sid = String(sh.shift_id);
  if(!state.dismissedShiftIds || !state.dismissedShiftIds.has(sid)) return true;
  // если вдруг наряд снова активен (и не отозван) — вернём
  if(sh.tracking_active && !_shiftIsRevoked(sh)){
    try{ state.dismissedShiftIds.delete(sid); _dismissChanged = true; }catch(e){}
    return true;
  }
  return false;
});
if(_dismissChanged) _saveDismissedShiftIds();


    if(cnt) cnt.textContent = String(shifts.length);


    // v14: критичный блок + приоритетная сортировка
    renderCriticalNow(rawShifts || []);
    shifts = _sortShiftsForUI(shifts);

    if(!shifts.length){
      el.innerHTML = '<div class="muted">Нет нарядов по выбранным фильтрам</div>';
      return;
    }

    el.innerHTML = '';
    const focusUid = (state.selected && state.selected.user_id != null) ? String(state.selected.user_id) : null;
    shifts.forEach(sh => {
      const title = labelForShift(sh);
      const last = getShiftLastPoint(sh);

      // health (Android) — battery/net/gps/queue
      const health = sh.health || null;
      const healthAgeSec = (typeof sh.health_age_sec === 'number') ? sh.health_age_sec : null;
      const isHealthStale = (healthAgeSec != null) ? (healthAgeSec > 90) : false;
      const healthLine = health ? (
        `${T('cc_phone_line_prefix')}: ` +
        `${health.battery_pct != null ? ('🔋' + health.battery_pct + '%') : '🔋—'} ` +
        `${health.net ? ('📶' + health.net) : '📶—'} ` +
        `${health.gps ? ('🛰 ' + health.gps) : '🛰 —'} ` +
        `${health.queue_size != null ? ('📦' + health.queue_size) : '📦—'} ` +
        `${isHealthStale ? ('· ⚠ ' + fmtAge(healthAgeSec)) : (healthAgeSec != null ? ('· ' + fmtAge(healthAgeSec)) : '')}`
      ) : '';

// age of last point (для UI) + флаги состояния
let ageSec = null;
try{
  if(last && last.ts){
    const ts = Date.parse(last.ts);
    if(ts){
      ageSec = Math.max(0, Math.floor((now - ts)/1000));
    }
  }
}catch(e){}

const isStale = _isShiftStale(sh);
const isRevoked = _shiftIsRevoked(sh);
const hasProblems = _shiftHasProblems(sh);

const _alerts = hasProblems ? _shiftAlerts(sh) : [];
const _problemsCount = _alerts.length;
const _critCount = _alerts.filter(a => String(a.severity||'') === 'crit').length;
const _problemsTitle = _alerts.slice(0,4).map(a => a.message || a.kind || 'alert').join(' | ') + (_problemsCount > 4 ? ` +${_problemsCount-4}` : '');

// Stage18.1: рекомендации (RU/EN) по health/stale/accuracy
let recsList = [];
let recsPillHtml = '';
try{
  if(window.Recs && typeof window.Recs.fromShiftSummary === 'function'){
    recsList = window.Recs.fromShiftSummary(sh);
    if(Array.isArray(recsList) && recsList.length){
      const tip = recsList.slice(0,4).join('\n');
      recsPillHtml = `<span class="ap-pill hint" title="${escapeHtml(tip)}">💡${recsList.length}</span>`;
    }
  }
}catch(_){ recsList = []; recsPillHtml=''; }

const card = document.createElement('div');
const st = _shiftStatus(sh);
card.className =
  'ap-item' +
  (isStale ? ' stale' : '') +
  (hasProblems ? ' ap-item--problem' : '') +
  (isRevoked ? ' ap-item--revoked' : '') +
  (st.key === 'sos' ? ' ap-item--sos' : (st.key === 'crit' ? ' ap-item--crit' : (st.key === 'stale' ? ' ap-item--stale' : (st.key === 'warn' ? ' ap-item--warn' : (st.key === 'ok' ? ' ap-item--ok' : ''))))) +
  (String(state.selected.shift_id) === String(sh.shift_id) ? ' selected' : '') +
  ((focusUid && focusUid !== String(sh.user_id)) ? ' dim' : '');


      card.dataset.shiftId = String(sh.shift_id);

      card.innerHTML = `
        <div class="ap-item__row">
          <div>
            <div class="ap-item__title">${escapeHtml(title)}</div>
            <div class="muted ap-item__meta">${escapeHtml(T('cc_shift_hash'))}${escapeHtml(String(sh.shift_id))} · ${escapeHtml(T('cc_start_short'))}: ${escapeHtml(fmtIso(sh.started_at))}</div>
          </div>
          <div class="ap-pills">
  <span class="ap-pill ${sh.tracking_active ? 'live' : 'idle'}">${sh.tracking_active ? escapeHtml(T('cc_status_ok')) : (st.key==='ended' ? escapeHtml(T('cc_status_ended')) : escapeHtml(T('cc_status_idle')))}</span>
  ${_deviceStatusPillHtml(sh.device_status)}
  ${st.key !== 'idle' ? `<span class="ap-badge ${st.color}">${st.label}</span>` : ''}
  ${hasProblems ? `<span class="ap-pill ${_critCount>0 ? 'crit' : 'warn'}" title="${escapeHtml(_problemsTitle)}">${_critCount>0 ? '!!' : '!'}${_problemsCount>1 ? _problemsCount : ''}</span>` : ''}
  ${recsPillHtml}
  ${isRevoked ? `<span class="ap-pill warn">${escapeHtml(T('cc_status_revoked'))}</span>` : ''}
  ${(!sh.tracking_active || st.key==='ended' || isRevoked) ? `<button class="ap-item__dismiss" data-act="dismiss" title="${escapeHtml(T('cc_action_dismiss'))}">✕</button>` : ''}
</div>
        </div>
        <div class="muted ap-item__meta">${escapeHtml(T('cc_last_point'))}: ${escapeHtml(fmtIso(last && last.ts ? last.ts : ''))}${ageSec != null ? ' · ' + escapeHtml(T('cc_update_age')) + ': ' + escapeHtml(fmtAge(ageSec)) : ''}</div>
        ${healthLine ? `<div class="muted ap-item__meta">${escapeHtml(healthLine)}</div>` : ''}
        <div class="ap-item__actions">
          <button class="btn" data-act="open">${escapeHtml(T('cc_action_card'))}</button>
          <button class="btn" data-act="pan">${escapeHtml(T('cc_action_show'))}</button>
          <button class="btn" data-act="track" ${last && last.session_id ? '' : 'disabled'}>${escapeHtml(T('cc_action_track'))}</button>
          <button class="btn" data-act="chat">${escapeHtml(T('cc_action_write'))}</button>
        </div>
      `;

      card.querySelector('[data-act="open"]').onclick = () => openShiftCard(sh.shift_id, { tab:'overview', fit:false });

      card.querySelector('[data-act="pan"]').onclick = () => {
        focusShiftOnMap(sh);
      };

      const btnTrack = card.querySelector('[data-act="track"]');
      if(btnTrack){
        btnTrack.onclick = async () => {
          await openShiftCard(sh.shift_id, { tab:'track', fit:false });
          if(last && last.session_id) loadTracking(last.session_id, { fit:true });
        };
      }

      card.querySelector('[data-act="chat"]').onclick = () => {
        // Приоритет: чат по смене (chat2) если модуль загружен, иначе fallback к старому чату
        try{
          if (typeof window.chat2OpenForShift === 'function') {
            window.chat2OpenForShift(sh.shift_id || sh.id);
            return;
          }
        }catch(_){}
        if (typeof window.chatOpenToUser === 'function') {
          window.chatOpenToUser(String(sh.user_id));
        } else {
          showToastT('cc_toast_chat_not_inited', null, 'warn');
        }
      };

      const btnDismiss = card.querySelector('[data-act="dismiss"]');
      if(btnDismiss){
        btnDismiss.onclick = (e) => {
          try{ e.preventDefault(); e.stopPropagation(); }catch(_){}
          _dismissShiftId(sh.shift_id);
        };
      }

      // Клик по карточке (не по кнопкам) — открыть
      card.addEventListener('click', (e) => {
        const isBtn = e.target && (e.target.closest && e.target.closest('button'));
        if(isBtn) return;
        openShiftCard(sh.shift_id, { tab:'overview', fit:false });
      });

      el.appendChild(card);
    });
  }

  function renderBreaks(breaks){
    const el = document.getElementById('list-breaks');
    const cnt = document.getElementById('count-breaks');
    if(cnt) cnt.textContent = String((breaks || []).length);
    if(!el) return;

    if(!(breaks || []).length){
      el.innerHTML = '<div class="muted">Нет активных запросов</div>';
      return;
    }

    el.innerHTML = '';
    (breaks || []).forEach(br => {
      const card = document.createElement('div');
      card.className = 'ap-item';
      card.innerHTML = `
        <div class="ap-item__row">
          <div>
            <div class="ap-item__title">🍽 Обед #${escapeHtml(String(br.id))}</div>
            <div class="muted ap-item__meta">TG: ${escapeHtml(String(br.user_id || '—'))} · ${escapeHtml(String(br.duration_min || 30))} мин</div>
          </div>
          <span class="ap-pill warn">${escapeHtml(String(br.status || ''))}</span>
        </div>
        <div class="muted ap-item__meta">запрос: ${escapeHtml(fmtIso(br.requested_at))} · конец: ${escapeHtml(fmtIso(br.ends_at))}</div>
        <div class="ap-item__actions">
          ${br.status === 'requested' ? '<button class="btn primary" data-act="approve">Подтвердить</button>' : ''}
          ${br.status === 'started' ? '<button class="btn warn" data-act="end">Закончить</button>' : ''}
          <button class="btn" data-act="chat">${escapeHtml(T('cc_action_write'))}</button>
          ${br.shift_id ? `<button class="btn" data-act="open">${escapeHtml(T('cc_action_card'))}</button>` : ''}
        </div>
      `;

      const bApprove = card.querySelector('[data-act="approve"]');
      if(bApprove) bApprove.onclick = () => approveBreak(br.id);

      const bEnd = card.querySelector('[data-act="end"]');
      if(bEnd) bEnd.onclick = () => endBreak(br.id);

      const bChat = card.querySelector('[data-act="chat"]');
      if(bChat) bChat.onclick = () => {
        try {
          // Используем новый чат2, если доступен: чат по смене для указанного break
          if (typeof window.chat2OpenForShift === 'function' && br.shift_id) {
            window.chat2OpenForShift(br.shift_id);
            return;
          }
        } catch(_e) {}
        // fallback: старый чат с пользователем по user_id
        if (typeof window.chatOpenToUser === 'function') {
          window.chatOpenToUser(String(br.user_id));
        }
      };

      const bOpen = card.querySelector('[data-act="open"]');
      if(bOpen) bOpen.onclick = () => openShiftCard(br.shift_id, { tab:'overview', fit:false });

      el.appendChild(card);
    });
  }

  function renderSos(list){
    const el = document.getElementById('list-sos');
    const cnt = document.getElementById('count-sos');
    if(cnt) cnt.textContent = String((list || []).length);
    if(!el) return;

    if(!(list || []).length){
      el.innerHTML = '<div class="muted">Нет активных SOS</div>';
      return;
    }

    el.innerHTML = '';
    (list || []).slice(0, 20).forEach(sos => {
      const title = sos.unit_label || ('TG ' + sos.user_id);
      const card = document.createElement('div');
      card.className = 'ap-item ap-item--sos';
      card.innerHTML = `
        <div class="ap-item__row">
          <div>
            <div class="ap-item__title">🆘 ${escapeHtml(title)}</div>
            <div class="muted ap-item__meta">${escapeHtml(fmtIso(sos.created_at))} · статус: ${escapeHtml(String(sos.status || 'open'))}</div>
          </div>
          <span class="ap-pill warn">SOS</span>
        </div>
        <div class="muted ap-item__meta">${escapeHtml(String(sos.lat))}, ${escapeHtml(String(sos.lon))}</div>
        <div class="ap-item__actions">
          <button class="btn" data-act="pan">${escapeHtml(T('cc_action_show'))}</button>
          <button class="btn" data-act="chat">${escapeHtml(T('cc_action_write'))}</button>
          ${sos.shift_id ? `<button class="btn" data-act="open">${escapeHtml(T('cc_action_card'))}</button>` : ''}
          ${sos.status === 'open' ? '<button class="btn primary" data-act="ack">Принять</button>' : ''}
          <button class="btn warn" data-act="close">Закрыть</button>
        </div>
      `;

      card.querySelector('[data-act="pan"]').onclick = () => {
        if(sos.lat != null && sos.lon != null){
          map.setView([sos.lat, sos.lon], Math.max(map.getZoom(), 16), { animate:true });
        }
      };
      card.querySelector('[data-act="chat"]').onclick = () => {
        try {
          // Если доступен chat2 и есть shift_id, открываем чат по смене
          if (typeof window.chat2OpenForShift === 'function' && sos.shift_id) {
            window.chat2OpenForShift(sos.shift_id);
            return;
          }
        } catch(_e) {}
        // fallback: старый чат по user_id
        if(typeof window.chatOpenToUser === 'function') window.chatOpenToUser(String(sos.user_id));
      };

      const bOpen = card.querySelector('[data-act="open"]');
      if(bOpen) bOpen.onclick = () => openShiftCard(sos.shift_id, { tab:'overview', fit:false });

      const bAck = card.querySelector('[data-act="ack"]');
      if(bAck) bAck.onclick = () => sosAck(sos.id);

      const bClose = card.querySelector('[data-act="close"]');
      if(bClose) bClose.onclick = () => sosClose(sos.id);

      el.appendChild(card);
    });

    if((list || []).length > 20){
      const more = document.createElement('div');
      more.className = 'muted';
      more.style.padding = '8px 2px 2px 2px';
      more.textContent = `… ещё ${(list || []).length - 20}`;
      el.appendChild(more);
    }
  }

  function renderPending(list){
    const el = document.getElementById('list-pending');
    const cnt = document.getElementById('count-pending');
    if(cnt) cnt.textContent = String((list || []).length);
    if(!el) return;

    if(!(list || []).length){
      el.innerHTML = '<div class="muted">Нет pending-заявок</div>';
      return;
    }

    el.innerHTML = '';
    (list || []).slice(0, 20).forEach(pm => {
      const card = document.createElement('div');
      card.className = 'ap-item';
      const title = pm.name || ('Заявка #' + pm.id);
      card.innerHTML = `
        <div class="ap-item__row">
          <div>
            <div class="ap-item__title">🔔 ${escapeHtml(title)}</div>
            <div class="muted ap-item__meta">#${escapeHtml(String(pm.id))} · ${escapeHtml(pm.created_at || '')}</div>
          </div>
          <span class="ap-pill">pending</span>
        </div>
        <div class="muted ap-item__meta">${pm.lat != null ? escapeHtml(String(pm.lat)) : '—'}, ${pm.lon != null ? escapeHtml(String(pm.lon)) : '—'}</div>
        <div class="ap-item__actions">
          <button class="btn" data-act="pan" ${pm.lat != null ? '' : 'disabled'}>${escapeHtml(T('cc_action_show'))}</button>
          <button class="btn primary" data-act="approve">Одобрить</button>
          <button class="btn warn" data-act="reject">Отклонить</button>
        </div>
      `;

      const bPan = card.querySelector('[data-act="pan"]');
      if(bPan) bPan.onclick = () => {
        if(pm.lat != null && pm.lon != null){
          map.setView([pm.lat, pm.lon], Math.max(map.getZoom(), 16), { animate:true });
          openPendingPopup(pm);
        }
      };

      card.querySelector('[data-act="approve"]').onclick = () => approvePending(pm.id);
      card.querySelector('[data-act="reject"]').onclick = () => rejectPending(pm.id);
      el.appendChild(card);
    });

    if((list || []).length > 20){
      const more = document.createElement('div');
      more.className = 'muted';
      more.style.padding = '8px 2px 2px 2px';
      more.textContent = `… ещё ${(list || []).length - 20}`;
      el.appendChild(more);
    }
  }

  /* ===== Pending popup ===== */
  function openPendingPopup(pm){
    if(pm.lat == null || pm.lon == null) return;
    const html = `
      <div style="min-width:260px">
        <strong>Заявка #${escapeHtml(String(pm.id))}</strong>
        <div class="muted" style="margin-top:4px">${escapeHtml(pm.name || '')}</div>
        ${pm.category ? `<div class="muted">Категория: ${escapeHtml(pm.category)}</div>` : ''}
        ${pm.notes ? `<div class="muted" style="margin-top:6px">${escapeHtml(pm.notes)}</div>` : ''}
        <div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">
          <button class="btn primary" id="pm-approve">Одобрить</button>
          <button class="btn warn" id="pm-reject">Отклонить</button>
        </div>
      </div>
    `;

    L.popup({ maxWidth: 420 }).setLatLng([pm.lat, pm.lon]).setContent(html).openOn(map);
    setTimeout(() => {
      const a = document.getElementById('pm-approve');
      const r = document.getElementById('pm-reject');
      if(a) a.onclick = () => approvePending(pm.id);
      if(r) r.onclick = () => rejectPending(pm.id);
    }, 30);
  }

  /* ===== Actions ===== */
  async function approveBreak(id){
    const r = await fetchJson(`/api/duty/admin/breaks/${encodeURIComponent(id)}/approve`, { method: 'POST' });
    if(!r.ok){ showToast('Ошибка подтверждения: ' + r.status, 'warn'); return; }
    showToast('Обед подтверждён #' + id, 'ok');
    await refreshAll();
  }
  async function endBreak(id){
    const r = await fetchJson(`/api/duty/admin/breaks/${encodeURIComponent(id)}/end`, { method: 'POST' });
    if(!r.ok){ showToast('Ошибка завершения: ' + r.status, 'warn'); return; }
    showToast('Обед завершён #' + id, 'ok');
    await refreshAll();
  }
  async function sosAck(id){
    const r = await fetchJson(`/api/duty/admin/sos/${encodeURIComponent(id)}/ack`, { method: 'POST', headers: { 'Content-Type':'application/json' }, body: '{}' });
    if(!r.ok){ showToast('Ошибка SOS ACK: ' + r.status, 'warn'); return; }
    showToast('SOS принят #' + id, 'ok');
    await refreshAll();
  }
  async function sosClose(id){
    if(!confirm('Закрыть SOS #' + id + '?')) return;
    const r = await fetchJson(`/api/duty/admin/sos/${encodeURIComponent(id)}/close`, { method: 'POST', headers: { 'Content-Type':'application/json' }, body: '{}' });
    if(!r.ok){ showToast('Ошибка SOS close: ' + r.status, 'warn'); return; }
    showToast('SOS закрыт #' + id, 'ok');
    await refreshAll();
  }
  async function approvePending(id){
    const r = await fetchJson(`/api/pending/${encodeURIComponent(id)}/approve`, { method: 'POST', headers: { 'Content-Type':'application/json' }, body: '{}' });
    if(!r.ok){ showToast('Ошибка approve: ' + r.status, 'warn'); return; }
    showToast('Заявка одобрена #' + id, 'ok');
    await refreshPending();
  }
  async function rejectPending(id){
    if(!confirm('Отклонить заявку #' + id + '?')) return;
    const r = await fetchJson(`/api/pending/${encodeURIComponent(id)}/reject`, { method: 'POST', headers: { 'Content-Type':'application/json' }, body: '{}' });
    if(!r.ok){ showToast('Ошибка reject: ' + r.status, 'warn'); return; }
    showToast('Заявка отклонена #' + id, 'ok');
    await refreshPending();
  }

  /* ===== Polling ===== */
  async function refreshDashboard(){
    const r = await fetchJson(API_DASH);
    if(!r.ok){ showToast('Dashboard недоступен: ' + r.status, 'warn'); return; }

    const t = document.getElementById('server-time');
    if(t) t.textContent = r.data.server_time || '—';

    const shifts = r.data.active_shifts || [];
    const breaks = r.data.breaks || [];
    const sos = r.data.sos_active || [];

    state.shifts = shifts;
    state.breaks = breaks;
    state.sos = sos;

    renderShifts(shifts);
    renderBreaks(breaks);
    renderSos(sos);

// На карте показываем только то, что видно в списке (быстрые фильтры + чекбоксы)
const fMap = getShiftFilters();
const sosUsersMap = new Set(state.sos.map(x => String(x.user_id)));
let vis = (shifts || []).filter(sh => {
  if(fMap.live && !sh.tracking_active) return false;
  if(fMap.break && !sh.break) return false;
  if(fMap.sos && !sosUsersMap.has(String(sh.user_id))) return false;
  if(fMap.stale && !_isShiftStale(sh)) return false;
  return true;
});
vis = _applyQuickFilter(vis);

vis.forEach(sh => { try{ upsertShiftMarker(sh); }catch(e){ console.warn('upsertShiftMarker failed', e); } });
dropMissingShiftMarkers(vis);
    sos.forEach(upsertSosMarker);
    dropMissingSosMarkers(sos);

    updateKpi();
    updateEmptyState();
    updateStaleAlertBar();

    // если пришёл фокус из /admin/devices — откроем наряд и центрируем
    try{
      const focusUid = localStorage.getItem('ap_focus_user_id');
      if(focusUid){
        const sh = state.shifts.find(x => String(x.user_id) === String(focusUid));
        if(sh){
          // v32: используем единый фокус-маркер, чтобы было визуально понятно где наряд
          try{ focusShiftOnMap(sh); }catch(_){ }
          openShiftCard(sh.shift_id, { tab:'overview', fit:false });

        } else {
          showToast('Наряд не найден для user_id=' + focusUid, 'warn');
        }
        localStorage.removeItem('ap_focus_user_id');
      }
    }catch(e){}
  }

  async function refreshPending(){
    const r = await fetchJson(API_PENDING);
    if(!r.ok) return;
    const list = Array.isArray(r.data) ? r.data : [];
    state.pending = list;
    renderPending(list);
    list.forEach(upsertPendingMarker);
    dropMissingPendingMarkers(list);

    updateEmptyState();
  }




  async function refreshServicePendingCount(){
    const b1 = document.getElementById('svc-pending-badge');
    const b2 = document.getElementById('svc-pending-badge-mobile');
    if(!b1 && !b2) return;
    const [rSvc, rConn] = await Promise.all([
      fetchJson(API_SERVICE_PENDING_COUNT),
      fetchJson(API_CONNECT_PENDING_COUNT)
    ]);
    if((!rSvc || !rSvc.ok) && (!rConn || !rConn.ok)){
      // silently hide
      if(b1) b1.style.display='none';
      if(b2) b2.style.display='none';
      return;
    }
    const n1 = Number((rSvc && rSvc.data && rSvc.data.count) ?? 0) || 0;
    const n2 = Number((rConn && rConn.data && rConn.data.count) ?? 0) || 0;
    const n = n1 + n2;
    [b1,b2].forEach(b => {
      if(!b) return;
      b.textContent = String(n);
      b.style.display = n>0 ? 'inline-flex' : 'none';
    });
  }


async function refreshTrackerMeta(){
  const [rDev, rProb] = await Promise.all([fetchJson(API_TRACKER_DEVICES), fetchJson(API_TRACKER_PROBLEMS)]);

  if(rDev && rDev.ok){
    const devs = (rDev.data && rDev.data.devices) ? rDev.data.devices : [];
    state.trackerDevices = devs;

    state.deviceById = new Map();
    state.deviceByUser = new Map();
    devs.forEach(d => {
      if(d && d.public_id) state.deviceById.set(String(d.public_id), d);
      if(d && d.user_id) state.deviceByUser.set(String(d.user_id), d);
    });
  }

  if(rProb && rProb.ok){
    const devs = (rProb.data && rProb.data.devices) ? rProb.data.devices : [];
    state.trackerProblems = devs;

    state.problemsByDevice = new Map();
    devs.forEach(x => {
      const did = x && x.device_id ? String(x.device_id) : null;
      if(did) state.problemsByDevice.set(did, (x.alerts || []));
    });
  }

  // перерисуем KPI/счётчики/карточки с учётом revoked/problems
  if(Array.isArray(state.shifts) && state.shifts.length){
    renderShifts(state.shifts);

    // обновим маркеры так же, как в refreshDashboard
    const fMap = getShiftFilters();
    const sosUsersMap = new Set(state.sos.map(x => String(x.user_id)));
    let vis = (state.shifts || []).filter(sh => {
      if(fMap.live && !sh.tracking_active) return false;
      if(fMap.break && !sh.break) return false;
      if(fMap.sos && !sosUsersMap.has(String(sh.user_id))) return false;
      if(fMap.stale && !_isShiftStale(sh)) return false;
      return true;
    });
    vis = _applyQuickFilter(vis);
    vis.forEach(sh => { try{ upsertShiftMarker(sh); }catch(e){ console.warn('upsertShiftMarker failed', e); } });
    dropMissingShiftMarkers(vis);
  }

  updateKpi();
}

  async function refreshAll(){
    setListsLoading();
    await Promise.all([refreshDashboard(), refreshPending(), refreshTrackerMeta(), refreshServicePendingCount()]);
    // если открыт drawer — обновим детали (чтобы журнал/статусы были актуальны)
    const tab = (elTabs.find(t=>t.classList.contains('active'))?.dataset.tab || 'overview');
    if(state.drawer && state.drawer.mode === 'shift' && state.selected.shift_id){
      openShiftCard(state.selected.shift_id, { tab, fit:false, quietUpdate:true });
    } else if(state.drawer && state.drawer.mode === 'incident' && state.selected.incident_id){
      openIncidentCard(state.selected.incident_id, { tab, fit:false, quietUpdate:true });
    } else if(state.drawer && state.drawer.mode === 'object' && state.selected.object_id){
      openObjectCard(state.selected.object_id, { tab, fit:false, quietUpdate:true });
    }
  }

  /* ===== Search ===== */
  function findByQuery(q){
    const s = q.trim().toLowerCase();
    if(!s) return null;

    const m1 = s.match(/^#?(\d+)$/);
    if(m1){
      const id = Number(m1[1]);
      const pm = state.pending.find(x => Number(x.id) === id);
      if(pm) return { type:'pending', item: pm };
    }

    const sh = state.shifts.find(x => String(x.user_id) === s || (x.unit_label || '').toLowerCase().includes(s));
    if(sh) return { type:'shift', item: sh };

    const sos = state.sos.find(x => String(x.user_id) === s || (x.unit_label || '').toLowerCase().includes(s));
    if(sos) return { type:'sos', item: sos };

    return null;
  }

  function runSearch(){
    const inp = document.getElementById('ap-search');
    const q = inp ? inp.value : '';
    const found = findByQuery(q);
    if(!found){ showToast('Не найдено: ' + q, 'warn'); return; }

    if(found.type === 'pending'){
      const pm = found.item;
      if(pm.lat != null && pm.lon != null){
        map.setView([pm.lat, pm.lon], 16, { animate:true });
        openPendingPopup(pm);
      }
      return;
    }

    if(found.type === 'sos'){
      const s = found.item;
      if(s.lat != null && s.lon != null){
        map.setView([s.lat, s.lon], 16, { animate:true });
      }
      if(s.shift_id) openShiftCard(s.shift_id, { tab:'overview', fit:false });
      return;
    }

    if(found.type === 'shift'){
      const sh = found.item;
      // v32: в поиске тоже показываем явный маркер
      try{ focusShiftOnMap(sh); }catch(_){ }
      openShiftCard(sh.shift_id, { tab:'overview', fit:false });
      return;
    }
  }

  function bindUI(){
    const btnRefresh = document.getElementById('ap-refresh');
    if(btnRefresh) btnRefresh.onclick = refreshAll;

    // sidebar toggle (чтобы карта занимала весь экран при необходимости)
    const btnToggle = document.getElementById('ap-toggle-sidebar');

    // tracker pairing code
    const btnPair = document.getElementById('btn-pair-code');
    if(btnPair){
      btnPair.onclick = async () => {
        try{
          const label = prompt('Подпись к коду (например: Наряд 12 / Телефон #3). Можно пусто:', '') || '';
          const r = await fetch('/api/tracker/admin/pair-code', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ label })
          });
          const j = await r.json();
          if(!r.ok || !j.ok) throw new Error(j.error || 'pair-code error');
          showToast(`Код привязки: ${j.code} (действует ${j.expires_in_min} мин)`, 'ok');
          try{ navigator.clipboard && navigator.clipboard.writeText(String(j.code)); }catch(e){}
        }catch(e){
          showToast('Не удалось сгенерировать код: ' + (e.message || e), 'err');
        }
      };
    }

    // chat list (Stage41.10)
    const btnChat = document.getElementById('btn-chat');
    if(btnChat){
      btnChat.onclick = () => {
        try{
          if(typeof window.chat2OpenList === 'function'){
            window.chat2OpenList();
            return;
          }
          // fallback: открыть чат выбранной смены
          if(typeof window.chat2OpenForShift === 'function' && state && state.selected && state.selected.shift_id){
            window.chat2OpenForShift(state.selected.shift_id);
            return;
          }
          if(typeof window.chatOpenList === 'function'){
            window.chatOpenList();
            return;
          }
        }catch(_){ }
        showToast('Чат не готов', 'warn');
      };
    }

    // tools panel toggle (KPI + quickfilters) — чтобы освобождать карту
    const btnTools = document.getElementById('ap-toggle-tools');
    function setToolsHidden(on){
      try{
        if(!elMain) return;
        elMain.classList.toggle('tools-hidden', !!on);
        try{ localStorage.setItem('ap_tools_hidden', on ? '1' : '0'); }catch(e){}
        requestAnimationFrame(updateTopToolsHeight);
        setTimeout(() => { try{ map.invalidateSize(true); }catch(e){} }, 140);
      }catch(e){}
    }
    // restore state
    try{
      const storedTools = localStorage.getItem('ap_tools_hidden') === '1';
      if(storedTools) setToolsHidden(true);
    }catch(e){}
    if(btnTools){
      btnTools.onclick = () => setToolsHidden(!(elMain && elMain.classList.contains('tools-hidden')));
    }

    // compact menu (mobile/medium)
    const btnMore = document.getElementById('ap-more');
    const menuMore = document.getElementById('ap-more-menu');
    if(btnMore && menuMore){
      const openMenu = () => { menuMore.style.display = 'flex'; };
      const closeMenu = () => { menuMore.style.display = 'none'; };
      btnMore.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        if(menuMore.style.display === 'flex') closeMenu(); else openMenu();
      });
      menuMore.addEventListener('click', (e) => {
        e.stopPropagation();
        const t = e.target.closest('[data-act]');
        if(t){
          const act = String(t.dataset.act || '');
          if(act === 'toggleTools'){
            if(btnTools) btnTools.click(); else setToolsHidden(!(elMain && elMain.classList.contains('tools-hidden')));
          } else if(act === 'pair'){
            const btnPair2 = document.getElementById('btn-pair-code');
            btnPair2 && btnPair2.click();
          } else if(act === 'chat'){
            const btnChat2 = document.getElementById('btn-chat');
            btnChat2 && btnChat2.click();
          } else if(act === 'incidentAdd'){
            const btnIncAdd = document.getElementById('btn-incident-add');
            if(btnIncAdd){ btnIncAdd.click(); }
            else if(window.IncidentsUI && typeof window.IncidentsUI.startCreate === 'function'){
              window.IncidentsUI.startCreate();
            }
          } else if(act === 'objectAdd'){
            const btnObjAdd = document.getElementById('btn-object-add');
            btnObjAdd && btnObjAdd.click();
          }
          closeMenu();
        }
      });
      document.addEventListener('click', () => closeMenu());
      document.addEventListener('keydown', (e) => { if(e.key === 'Escape') closeMenu(); });
      window.addEventListener('resize', () => closeMenu());
    }

    const layout = document.querySelector('.ap-layout');

    function setCollapsed(on){
      if(!layout) return;
      layout.classList.toggle('ap-collapsed', !!on);
      // v31: чтобы не оставалось белого поля слева (style.css использует body.sidebar-hidden для #map left:0)
      try{ document.body.classList.toggle('sidebar-hidden', !!on); }catch(e){}
      try{ localStorage.setItem('ap_sidebar_collapsed', on ? '1' : '0'); }catch(e){}
      setTimeout(() => { try{ map.invalidateSize(true); }catch(e){} }, 160);
      setTimeout(() => { try{ map.invalidateSize(true); }catch(e){} }, 420);
    }

    // restore state
    if(layout){
      let stored = false;
      try{ stored = localStorage.getItem('ap_sidebar_collapsed') === '1'; }catch(e){}
      if(stored) setCollapsed(true);
    }

    if(btnToggle){
      btnToggle.onclick = () => {
        const nowCollapsed = !!(layout && layout.classList.contains('ap-collapsed'));
        setCollapsed(!nowCollapsed);
      };
    }

    const btnSearch = document.getElementById('ap-search-btn');
    if(btnSearch) btnSearch.onclick = runSearch;

    const inp = document.getElementById('ap-search');
    if(inp) inp.addEventListener('keydown', (e) => { if(e.key === 'Enter') runSearch(); });

    // drawer
    if(elDrawerClose) elDrawerClose.onclick = drawerClose;
    elTabs.forEach(t => t.addEventListener('click', () => drawerSetTab(t.dataset.tab)));

    // фильтры
    ['flt-live','flt-break','flt-sos','flt-stale'].forEach(id => {
      const el = document.getElementById(id);
      if(el) el.addEventListener('change', () => rerenderVisible());
    });


// быстрые фильтры (chips)
const qroot = document.getElementById('ap-quickfilters');
if(qroot){
  Array.from(qroot.querySelectorAll('[data-qf]')).forEach(btn => {
    btn.addEventListener('click', () => {
      state.quickFilter = String(btn.dataset.qf || 'all');
      try{ localStorage.setItem('ap_qf', state.quickFilter); }catch(e){}
      rerenderVisible();
    });
  });
}
  }


  /* ===== Live realtime (optional) ===== */
  function setupRealtime(){
    if(!(window.Realtime && typeof window.Realtime.on === 'function')) return;
    try{
      window.Realtime.connect();
      const debDash = (window.Realtime.debounce ? window.Realtime.debounce(refreshDashboard, 700) : refreshDashboard);
      const debPend = (window.Realtime.debounce ? window.Realtime.debounce(refreshPending, 700) : refreshPending);

      window.Realtime.on('tracking_point', (payload) => {
        try{
          payload = payload || {};
          const uid = String(payload.user_id || '');
          if(!uid) return;

          const sh = state.shifts.find(s => String(s.user_id) === uid);
          let accepted = false;
          if(sh){
            const next = _normalizePoint(payload);
            const prev = getShiftLastPoint(sh);
            if(next){
              accepted = _shouldAcceptRealtimePoint(sh, prev, next);
              if(accepted){
                sh.last = next;
              } else {
                sh._rt_last_rejected = next;
              }
            }
            sh.tracking_active = true;
            // маркер/список обновляем всегда (позицию — только если приняли точку)
            upsertShiftMarker(sh);
            renderShifts(state.shifts);
            updateStaleAlertBar();
          }
          if(accepted && state.selected && state.selected.user_id && String(state.selected.user_id) === uid){
            const el = document.getElementById('card-last');
            if(el){ el.textContent = payload.ts ? new Date(payload.ts).toLocaleString() : '—'; }
          }
        }catch(e){}
      });

      window.Realtime.on('tracking_started', (payload) => {
        try{
          const uid = String(payload?.user_id || '');
          const sh = state.shifts.find(s => String(s.user_id) === uid);
          if(sh){
            sh.tracking_active = true;
            renderShifts(state.shifts);
            updateStaleAlertBar();
          }
        }catch(e){}
      });

      window.Realtime.on('tracking_stopped', (payload) => {
        try{
          const uid = String(payload?.user_id || '');
          const sh = state.shifts.find(s => String(s.user_id) === uid);
          if(sh){
            sh.tracking_active = false;
            renderShifts(state.shifts);
            updateStaleAlertBar();
          }
        }catch(e){}
      });

      window.Realtime.on('tracker_paired', (payload) => {
        try{ showToast(`Трекер привязан: ${payload?.label || payload?.device_id || payload?.user_id}`, 'ok'); }catch(e){}
        debDash();
      });

      window.Realtime.on('tracker_profile', (payload) => {
        try{ showToast(`Профиль трекера обновлён: ${payload?.label || payload?.device_id}`, 'ok'); }catch(e){}
        debDash();
      });

      window.Realtime.on('tracker_health', (payload) => {
        try{
          const uid = String(payload?.user_id || '');
          if(uid){
            const sh = state.shifts.find(s => String(s.user_id) === uid);
            if(sh){
              sh.health = Object.assign({}, sh.health || {}, payload || {});
              sh.health_age_sec = 0;
              renderShifts(state.shifts);
              updateStaleAlertBar();
            }
          }
        }catch(e){}
      });

      window.Realtime.on('tracker_alert', (payload) => {
        try{
          const msgText = payload && (payload.message || payload.kind) ? (payload.message || payload.kind) : 'alert';
          showToast('⚠️ ' + msgText, (payload && payload.severity === 'crit') ? 'err' : 'warn');
        }catch(e){}
        debDash();
      });
      ['tracker_alert_closed','tracker_alert_acked'].forEach(ev => window.Realtime.on(ev, () => { debDash(); }));

      window.Realtime.on('sos_created', (payload) => {
        try{ showToast('🆘 SOS: ' + (payload?.unit_label || payload?.user_id || ''), 'warn'); }catch(e){}
        debDash();
      });
      ['sos_acked','sos_closed'].forEach(ev => window.Realtime.on(ev, () => { debDash(); }));

      // pending
      window.Realtime.on('pending_created', (payload) => {
        try{ showToastT('cc_toast_pending_new', {id: (payload?.id || '')}, 'warn'); }catch(e){}
        debPend();
        debDash();
      });
      ['pending_approved','pending_rejected','pending_cleared'].forEach(ev => window.Realtime.on(ev, () => { debPend(); debDash(); }));

      // service access / DutyTracker connect badge
      ['service_access_created','service_access_updated','mobile_connect_created','mobile_connect_updated'].forEach(ev => {
        try{ window.Realtime.on(ev, () => { try{ refreshServicePendingCount(); }catch(e){} }); }catch(e){}
      });

      // duty
      window.Realtime.on('break_due', (payload) => {
        try{ showToastT('cc_toast_break_due', {user_id: (payload?.user_id || '')}, 'warn'); }catch(e){}
      });

      // counters (map topbar / общие)
      window.Realtime.on('chat_message', () => {
        try{ window.Realtime.refreshCounters?.(); }catch(e){}
      });
    }catch(e){}
  }


  function applyLang(){
    try{
      if(window.i18n && typeof window.i18n.applyDomTranslations === 'function'){
        window.i18n.applyDomTranslations(document);
      }
    }catch(_){}
    try{ document.title = T('cc_title'); }catch(_){}
    try{
      const lbl = document.getElementById('ap-lang-label');
      if(lbl) lbl.textContent = (getLang() === 'en') ? 'EN' : 'RU';
    }catch(_){}
    try{
      // legend depends on language
      if(map){
        // remove existing legend(s)
        document.querySelectorAll('.map-legend').forEach(el => el.remove());
        addMapLegend();
      }
    }catch(_){}
    try{
      renderShifts(state.shifts);
      updateStaleAlertBar();
    }catch(_){}
  }

  function applyThemeCC(theme){
    const t = (theme === 'dark') ? 'dark' : 'light';
    try{ document.body.classList.remove('dark','light'); document.body.classList.add(t); }catch(_){}
    try{ localStorage.setItem('cc_theme', t); }catch(_){}
    try{ setTimeout(() => { try{ map && map.invalidateSize(true); }catch(e){} }, 120); }catch(_){}
  }

  function initLangTheme(){
    // theme restore (default = light)
    let th = 'light';
    try{ th = (localStorage.getItem('cc_theme') || 'light'); }catch(_){}
    applyThemeCC(th);

    // language restore (default = ru)
    try{
      if(window.i18n && typeof window.i18n.setLang === 'function'){
        // setLang will normalize and emit event
        window.i18n.setLang(window.i18n.getLang());
      }
    }catch(_){}
    applyLang();

    const btnLang = document.getElementById('ap-lang');
    if(btnLang){
      btnLang.addEventListener('click', () => {
        const next = (getLang() === 'en') ? 'ru' : 'en';
        try{ window.i18n && window.i18n.setLang && window.i18n.setLang(next); }catch(_){}
        applyLang();
      });
    }
    const btnTheme = document.getElementById('ap-theme');
    if(btnTheme){
      btnTheme.addEventListener('click', () => {
        const cur = document.body.classList.contains('dark') ? 'dark' : 'light';
        applyThemeCC(cur === 'dark' ? 'light' : 'dark');
      });
    }

    // mobile dropdown actions
    const menuMore = document.getElementById('ap-more-menu');
    if(menuMore){
      menuMore.addEventListener('click', (e) => {
        const t = e.target.closest('[data-act]');
        if(!t) return;
        const act = String(t.dataset.act || '');
        if(act === 'lang'){
          const next = (getLang() === 'en') ? 'ru' : 'en';
          try{ window.i18n && window.i18n.setLang && window.i18n.setLang(next); }catch(_){}
          applyLang();
        } else if(act === 'theme'){
          const cur = document.body.classList.contains('dark') ? 'dark' : 'light';
          applyThemeCC(cur === 'dark' ? 'light' : 'dark');
        }
      });
    }

    // external language change
    window.addEventListener('ui:lang', () => { applyLang(); });
  }


  initLangTheme();
  bindUI();
  setupRealtime();
  refreshAll();
  // мягкий фолбэк-поллинг (если WS не доступен)
  setInterval(refreshDashboard, 12000);
  setInterval(refreshPending, 20000);
  setInterval(refreshServicePendingCount, 20000);
})();
