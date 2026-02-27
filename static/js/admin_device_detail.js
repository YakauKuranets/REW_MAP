/* Device detail (drill-down)

  Страница: /admin/devices/<device_id>
  API:
    - /api/tracker/admin/device/<id>
    - /api/tracker/admin/device/<id>/health_log
    - /api/tracker/admin/device/<id>/points
    - /api/tracker/admin/device/<id>/export/health.csv
    - /api/tracker/admin/device/<id>/export/points.csv
*/

(function(){
  const root = document.querySelector('.dd-main');
  const deviceId = (window.DEVICE_ID || (root && root.dataset.deviceId) || '').toString();
  if(!deviceId){
    console.error('DEVICE_ID missing');
    return;
  }

  const $ = (sel) => document.querySelector(sel);
  const elAlert = $('#dd-alert');
  const elTitle = $('#dd-title');
  const elSub = $('#dd-sub');
  const elKv = $('#dd-kv');
  const btnRefresh = $('#btn-refresh');
  const btnRevoke = $('#btn-revoke');
  const btnRotate = $('#btn-rotate');
  const btnFit = $('#btn-fit');
  const selHours = $('#sel-hours');
  const selRouteHours = $('#sel-route-hours');

// Advanced time ranges (epoch ms)
const inpRouteFrom = $('#route-from');
const inpRouteTo = $('#route-to');
const btnRouteApply = $('#btn-route-apply');
const btnRouteClear = $('#btn-route-clear');

const inpAlertsFrom = $('#alerts-from');
const inpAlertsTo = $('#alerts-to');
const btnAlertsApply = $('#btn-alerts-apply');
const btnAlertsClear = $('#btn-alerts-clear');

let _routeRange = { from: null, to: null };
let _alertsRange = { from: null, to: null };


  const selAlerts = $('#sel-alerts');
  const btnAckAll = $('#btn-ack-all');
  const btnCloseAll = $('#btn-close-all');
  const elAlertsSummary = $('#dd-alerts-summary');
  const elAlerts = $('#dd-alerts');

  const aHealth = $('#btn-export-health');
  const aPoints = $('#btn-export-points');
  const aGpx = $('#btn-export-gpx');
  const aAlertsCsv = $('#btn-export-alerts');
  const elRecs = $('#dd-recs');
  const selAlertHours = $('#sel-alert-hours');
  const elRouteHoursLbl = $('#dd-route-hours-lbl');
  const elPointsSummary = $('#dd-points-summary');
  const elWs = $('#ws-status');

  // кнопка чата (DM) для этого устройства
  const btnChatDevice = document.getElementById('btn-chat-device');
  if (btnChatDevice) {
    btnChatDevice.onclick = async () => {
      try {
        // Используем новый событийный чат (chat2): создаём или получаем DM-канал
        const payload = { device_id: deviceId };
        const resp = await fetch('/api/chat2/ensure_dm_channel', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        if (resp.ok) {
          const data = await resp.json();
          const chId = (data && data.id) ? data.id : null;
          if (chId) {
            // Открываем чат в панели администратора в новой вкладке, передавая идентификатор канала
            const url = `/admin/panel?chat2Channel=${encodeURIComponent(chId)}`;
            window.open(url, '_blank', 'noopener');
            return;
          }
        }
        // если chat2 недоступен, пробуем fallback на старый чат с пользователем
        if (typeof window.chatOpenToUser === 'function') {
          // получаем пользователя из последних данных устройства, если есть
          let uid = null;
          try {
            if (_lastDevice && _lastDevice.user_id) uid = String(_lastDevice.user_id);
          } catch (_e) {}
          if (uid) {
            window.chatOpenToUser(uid);
          } else {
            // если данных нет, пробуем с deviceId (хотя chatOpenToUser ожидает user_id)
            window.chatOpenToUser(String(deviceId));
          }
        }
      } catch (err) {
        console.warn('Failed to open DM chat', err);
      }
    };
  }

  // allow open page with preset periods:
  //   /admin/devices/<id>?h=12&r=24&a=72
  (function prefillFromQuery(){
    try{
      const sp = new URLSearchParams(location.search || '');
      const h = sp.get('h');
      const r = sp.get('r');
      const a = sp.get('a');
      const setIfExists = (sel, val) => {
        if(!sel || val == null || val === '') return;
        const s = String(val);
        const ok = Array.from(sel.options || []).some(o => String(o.value) === s);
        if(ok) sel.value = s;
      };
      setIfExists(selHours, h);
      setIfExists(selRouteHours, r);
      setIfExists(selAlertHours, a);
    }catch(_){ }
  })();

  let _lastDevice = null;
  let _lastHealth = null;
  let _lastAlerts = [];

  const tbHealth = $('#tb-health');
  const tbPoints = $('#tb-points');

  const cBat = $('#ch-battery');
  const cQueue = $('#ch-queue');
  const cAcc = $('#ch-acc');

  function getHealthHours(){
    return parseFloat(selHours && selHours.value ? selHours.value : '12') || 12;
  }

  function getRouteHours(){
    return parseFloat(selRouteHours && selRouteHours.value ? selRouteHours.value : (selHours && selHours.value ? selHours.value : '12')) || 12;
  }

  function getAlertHours(){
    return parseFloat(selAlertHours && selAlertHours.value ? selAlertHours.value : '72') || 72;
  }


function _parseEpochMs(v){
  if(v == null) return null;
  const s = String(v).trim();
  if(!s) return null;
  const n = Number(s);
  if(Number.isFinite(n) && n > 0) return Math.trunc(n);
  return null;
}

function _toLocalInputValue(ms){
  if(!Number.isFinite(ms)) return '';
  const d = new Date(ms);
  const pad = (x) => String(x).padStart(2,'0');
  const yyyy = d.getFullYear();
  const MM = pad(d.getMonth()+1);
  const dd = pad(d.getDate());
  const hh = pad(d.getHours());
  const mm = pad(d.getMinutes());
  return `${yyyy}-${MM}-${dd}T${hh}:${mm}`;
}

function _fromLocalInputValue(v){
  if(!v) return null;
  const ms = Date.parse(v);
  return Number.isFinite(ms) ? Math.trunc(ms) : null;
}

function _fmtLocal(ms){
  if(!Number.isFinite(ms)) return '—';
  const d = new Date(ms);
  const pad = (x) => String(x).padStart(2,'0');
  return `${pad(d.getDate())}.${pad(d.getMonth()+1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function _rangeLbl(r){
  if(!r || !Number.isFinite(r.from) || !Number.isFinite(r.to)) return '';
  return `${_fmtLocal(r.from)}–${_fmtLocal(r.to)}`;
}

function _getRouteRange(){
  if(_routeRange && Number.isFinite(_routeRange.from) && Number.isFinite(_routeRange.to)) return _routeRange;
  return null;
}

function _getAlertsRange(){
  if(_alertsRange && Number.isFinite(_alertsRange.from) && Number.isFinite(_alertsRange.to)) return _alertsRange;
  return null;
}

  function hoursLbl(h){
    const n = Number(h);
    if(!Number.isFinite(n)) return '—';
    if(n >= 168) return '7д';
    if(n >= 72) return '72ч';
    return `${n}ч`;
  }

  function updateExportLinks(){
  const hHours = getHealthHours();
  const rHours = getRouteHours();
  const aHours = getAlertHours();

  const rr = _getRouteRange();
  const ar = _getAlertsRange();

  const routeQS = rr ? `from=${encodeURIComponent(rr.from)}&to=${encodeURIComponent(rr.to)}` : `hours=${encodeURIComponent(rHours)}`;
  const alertsQS = ar ? `from=${encodeURIComponent(ar.from)}&to=${encodeURIComponent(ar.to)}` : `hours=${encodeURIComponent(aHours)}`;

  if(aHealth) aHealth.href = `/api/tracker/admin/device/${encodeURIComponent(deviceId)}/export/health.csv?hours=${encodeURIComponent(hHours)}`;
  if(aPoints) aPoints.href = `/api/tracker/admin/device/${encodeURIComponent(deviceId)}/export/points.csv?${routeQS}`;
  if(aGpx) aGpx.href = `/api/tracker/admin/device/${encodeURIComponent(deviceId)}/export/points.gpx?${routeQS}`;
  if(aAlertsCsv) aAlertsCsv.href = `/api/tracker/admin/device/${encodeURIComponent(deviceId)}/export/alerts.csv?${alertsQS}&active=all`;

  if(elRouteHoursLbl){
    elRouteHoursLbl.textContent = rr ? _rangeLbl(rr) : hoursLbl(rHours);
  }

function _syncUrlParams(){
  try{
    const u = new URL(window.location.href);
    const sp = u.searchParams;

    if(selHours && selHours.value) sp.set('h', String(selHours.value));
    if(selRouteHours && selRouteHours.value) sp.set('r', String(selRouteHours.value));
    if(selAlertHours && selAlertHours.value) sp.set('a', String(selAlertHours.value));

    const rr = _getRouteRange();
    const ar = _getAlertsRange();

    if(rr){ sp.set('rfrom', String(rr.from)); sp.set('rto', String(rr.to)); } else { sp.delete('rfrom'); sp.delete('rto'); }
    if(ar){ sp.set('afrom', String(ar.from)); sp.set('ato', String(ar.to)); } else { sp.delete('afrom'); sp.delete('ato'); }

    window.history.replaceState({}, '', u.toString());
  }catch(_){}
}

if(btnRouteApply) btnRouteApply.addEventListener('click', ()=>{
  const f = _fromLocalInputValue(inpRouteFrom && inpRouteFrom.value);
  const t = _fromLocalInputValue(inpRouteTo && inpRouteTo.value);
  if(f && t){
    _routeRange = {from:f, to:t};
  }else{
    _routeRange = {from:null, to:null};
  }
  updateExportLinks();
  _syncUrlParams();
  loadPoints().catch(()=>{});
});

if(btnRouteClear) btnRouteClear.addEventListener('click', ()=>{
  _routeRange = {from:null, to:null};
  if(inpRouteFrom) inpRouteFrom.value = '';
  if(inpRouteTo) inpRouteTo.value = '';
  updateExportLinks();
  _syncUrlParams();
  loadPoints().catch(()=>{});
});

if(btnAlertsApply) btnAlertsApply.addEventListener('click', ()=>{
  const f = _fromLocalInputValue(inpAlertsFrom && inpAlertsFrom.value);
  const t = _fromLocalInputValue(inpAlertsTo && inpAlertsTo.value);
  if(f && t){
    _alertsRange = {from:f, to:t};
  }else{
    _alertsRange = {from:null, to:null};
  }
  updateExportLinks();
  _syncUrlParams();
  loadAlerts().catch(()=>{});
});

if(btnAlertsClear) btnAlertsClear.addEventListener('click', ()=>{
  _alertsRange = {from:null, to:null};
  if(inpAlertsFrom) inpAlertsFrom.value = '';
  if(inpAlertsTo) inpAlertsTo.value = '';
  updateExportLinks();
  _syncUrlParams();
  loadAlerts().catch(()=>{});
});

}


  function renderRecommendations(){
    if(!elRecs) return;
    if(!(window.Recs && window.Recs.block)) { elRecs.innerHTML = ''; return; }
    const list = [];
    try{
      if(_lastDevice && _lastDevice.is_revoked){ list.push('Доступ отозван: нажмите Restore для восстановления'); }
      if(_lastHealth){ list.push.apply(list, window.Recs.fromHealth(_lastHealth)); }
      (_lastAlerts || []).filter(a => a && (a.is_active === true)).forEach(a => { list.push.apply(list, window.Recs.fromAlert(a)); });
    }catch(e){}
    elRecs.innerHTML = window.Recs.block(list, 'Что сделать на устройстве');
  }

  updateExportLinks();


  function showAlert(msg){
    if(!elAlert) return;
    elAlert.textContent = msg;
    elAlert.style.display = msg ? 'block' : 'none';
  }


/* v17: skeleton */
function skelBlock(){
  return `<div class="skel" style="margin:8px 0">
    <div class="skel-line tall" style="width:64%"></div>
    <div class="skel-line" style="width:92%"></div>
    <div class="skel-line small" style="width:58%"></div>
  </div>`;
}
function setLoading(){
  try{
    if(elKv) elKv.innerHTML = skelBlock() + skelBlock();
    if(tbHealth) tbHealth.innerHTML = `<tr><td colspan="6">${skelBlock()}</td></tr>`;
    if(tbPoints) tbPoints.innerHTML = `<tr><td colspan="6">${skelBlock()}</td></tr>`;
  }catch(e){}
}

  async function fetchJSON(url, opts){
    const r = await fetch(url, opts || {});
    if(!r.ok){
      let t = '';
      try{ t = await r.text(); }catch(e){}
      throw new Error(`HTTP ${r.status}: ${t || r.statusText}`);
    }
    return await r.json();
  }

  function escapeHtml(s){
    return String(s ?? '')
      .replaceAll('&','&amp;')
      .replaceAll('<','&lt;')
      .replaceAll('>','&gt;')
      .replaceAll('"','&quot;')
      .replaceAll("'", '&#039;');
  }

  function fmtTime(iso){
    if(!iso) return '—';
    const d = new Date(iso);
    if(isNaN(+d)) return iso;
    return d.toLocaleString();
  }

  function hms(sec){
    if(sec == null) return '—';
    sec = Math.max(0, Number(sec) || 0);
    const m = Math.floor(sec/60);
    const s = sec % 60;
    const h = Math.floor(m/60);
    const mm = m % 60;
    if(h>0) return `${h}ч ${mm}м`;
    if(mm>0) return `${mm}м ${s}с`;
    return `${s}с`;
  }

  function kv(label, value){
    return `<div class="kv">${label}: <b>${value ?? '—'}</b></div>`;
  }

  function drawLine(canvas, xs, ys, opts){
    if(!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width = canvas.clientWidth;
    const h = canvas.height = canvas.getAttribute('height') ? parseInt(canvas.getAttribute('height'),10) : canvas.clientHeight;
    ctx.clearRect(0,0,w,h);

    // backdrop grid
    ctx.globalAlpha = 0.25;
    ctx.strokeStyle = 'rgba(255,255,255,0.22)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for(let i=1;i<4;i++){
      const y = Math.round(h*i/4)+0.5;
      ctx.moveTo(0,y); ctx.lineTo(w,y);
    }
    ctx.stroke();
    ctx.globalAlpha = 1;

    if(!ys || ys.length < 2){
      ctx.fillStyle = 'rgba(255,255,255,0.55)';
      ctx.font = '12px sans-serif';
      ctx.fillText('нет данных', 8, 20);
      return;
    }

    const ymin = (opts && opts.ymin != null) ? opts.ymin : Math.min(...ys.filter(v => v!=null && !isNaN(v)));
    const ymax = (opts && opts.ymax != null) ? opts.ymax : Math.max(...ys.filter(v => v!=null && !isNaN(v)));
    const pad = 6;
    const lo = (ymin === ymax) ? (ymin - 1) : ymin;
    const hi = (ymin === ymax) ? (ymax + 1) : ymax;

    const x0 = xs[0];
    const x1 = xs[xs.length-1];
    const dx = (x1 - x0) || 1;

    function sx(x){
      return pad + (w - pad*2) * ((x - x0) / dx);
    }
    function sy(y){
      const t = (y - lo) / (hi - lo);
      return (h - pad) - (h - pad*2) * t;
    }

    ctx.strokeStyle = 'rgba(255,255,255,0.95)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    let started = false;
    for(let i=0;i<ys.length;i++){
      const y = ys[i];
      if(y == null || isNaN(y)) continue;
      const x = xs[i];
      const px = sx(x);
      const py = sy(y);
      if(!started){ ctx.moveTo(px,py); started = true; }
      else ctx.lineTo(px,py);
    }
    ctx.stroke();

    // last dot
    const lastIdx = (()=>{
      for(let i=ys.length-1;i>=0;i--){
        const y = ys[i];
        if(y != null && !isNaN(y)) return i;
      }
      return -1;
    })();
    if(lastIdx>=0){
      const px = sx(xs[lastIdx]);
      const py = sy(ys[lastIdx]);
      ctx.fillStyle = 'rgba(255,255,255,0.95)';
      ctx.beginPath(); ctx.arc(px,py,3,0,Math.PI*2); ctx.fill();
    }

    // min/max labels
    ctx.fillStyle = 'rgba(255,255,255,0.55)';
    ctx.font = '11px sans-serif';
    ctx.fillText(String(Math.round(hi*10)/10), 6, 12);
    ctx.fillText(String(Math.round(lo*10)/10), 6, h-4);
  }

  let map, layerLine, layerMarker, layerAcc;
  function initMap(){
    if(map) return;
    map = L.map('dev-map', { zoomControl: true });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);
    layerLine = L.polyline([], { weight: 3 }).addTo(map);
    layerMarker = L.marker([0,0]);
    layerAcc = L.circle([0,0], { radius: 0, weight: 1, fillOpacity: 0.08 });
  }

  function setMap(points){
    initMap();
    if(!points || points.length === 0){
      map.setView([53.9, 27.5667], 11); // Minsk fallback
      try{ if(layerAcc && layerAcc._map) map.removeLayer(layerAcc); }catch(e){}
      try{ if(layerMarker && layerMarker._map) map.removeLayer(layerMarker); }catch(e){}
      return;
    }
    // downsample if huge
    const max = 1500;
    let pts = points;
    if(points.length > max){
      const step = Math.ceil(points.length / max);
      pts = points.filter((_,i)=>i%step===0);
    }
    const latlngs = pts.map(p => [p.lat, p.lon]).filter(x => isFinite(x[0]) && isFinite(x[1]));
    layerLine.setLatLngs(latlngs);
    const last = points[points.length-1];
    if(last && isFinite(last.lat) && isFinite(last.lon)){
      layerMarker.setLatLng([last.lat, last.lon]);
      if(!layerMarker._map) layerMarker.addTo(map);

      // accuracy circle (если есть)
      const acc = (last.accuracy_m != null) ? Number(last.accuracy_m) : null;
      if(layerAcc && acc != null && Number.isFinite(acc) && acc > 0){
        layerAcc.setLatLng([last.lat, last.lon]);
        layerAcc.setRadius(acc);
        if(!layerAcc._map) layerAcc.addTo(map);
      }else{
        try{ if(layerAcc && layerAcc._map) map.removeLayer(layerAcc); }catch(e){}
      }
    }
    if(latlngs.length){
      map.fitBounds(layerLine.getBounds().pad(0.2));
    }
  }

  function setPointsSummary(points){
    if(!elPointsSummary) return;
    const n = Array.isArray(points) ? points.length : 0;
    const last = (points && points.length) ? points[points.length-1] : null;
    const bits = [];
    bits.push(`точек: ${n}`);
    if(last && last.ts){ bits.push(`последняя: ${fmtTime(last.ts)}`); }
    if(last && last.accuracy_m != null){ bits.push(`acc: ~${Math.round(Number(last.accuracy_m))}м`); }
    elPointsSummary.textContent = bits.join(' · ');
  }

  function renderHealthTable(items){
    if(!tbHealth) return;
    const rows = (items || []).slice(0, 30);
    tbHealth.innerHTML = rows.map(it => {
      const err = (it.last_error || '').toString();
      const errShort = err.length > 60 ? err.slice(0,57)+'…' : err;
      return `<tr>
        <td>${fmtTime(it.ts)}</td>
        <td>${it.battery_pct ?? '—'}${it.is_charging ? '⚡' : ''}</td>
        <td>${it.net || '—'}</td>
        <td>${it.gps || '—'}</td>
        <td>${it.accuracy_m != null ? Math.round(it.accuracy_m) : '—'}</td>
        <td>${it.queue_size ?? '—'}</td>
        <td>${it.tracking_on == null ? '—' : (it.tracking_on ? 'on' : 'off')}</td>
        <td title="${err.replaceAll('"','&quot;')}">${errShort || '—'}</td>
      </tr>`;
    }).join('');
  }

  function renderPointsTable(points){
    if(!tbPoints) return;
    const rows = (points || []).slice(-50).reverse();
    tbPoints.innerHTML = rows.map(p => {
      return `<tr data-lat="${p.lat}" data-lon="${p.lon}">
        <td>${fmtTime(p.ts)}</td>
        <td>${(p.lat ?? '').toString().slice(0, 10)}</td>
        <td>${(p.lon ?? '').toString().slice(0, 10)}</td>
        <td>${p.accuracy_m != null ? Math.round(p.accuracy_m) : '—'}</td>
        <td>${p.kind || '—'}</td>
      </tr>`;
    }).join('');

    tbPoints.querySelectorAll('tr').forEach(tr => {
      tr.addEventListener('click', ()=>{
        const lat = parseFloat(tr.dataset.lat);
        const lon = parseFloat(tr.dataset.lon);
        if(map && isFinite(lat) && isFinite(lon)){
          map.setView([lat,lon], Math.max(map.getZoom(), 16));
        }
      });
    });
  }


function sevClass(sev){
  const s = String(sev || '').toLowerCase();
  if(s === 'crit' || s === 'critical') return 'sev-crit';
  if(s === 'warn' || s === 'warning') return 'sev-warn';
  return 'sev-info';
}

function renderAlerts(items){
  if(!elAlerts) return;
  const list = Array.isArray(items) ? items : [];
  const activeCnt = list.filter(x => !!x.is_active).length;
  const critCnt = list.filter(x => String(x.severity).toLowerCase().startsWith('crit')).length;
  const ackCnt = list.filter(x => !!x.acked_at).length;

  if(elAlertsSummary){
    elAlertsSummary.textContent = `Всего: ${list.length} · активных: ${activeCnt} · crit: ${critCnt} · ACK: ${ackCnt}`;
  }

  if(!list.length){
    elAlerts.innerHTML = '<div class="muted">Алёртов нет.</div>';
    return;
  }

  elAlerts.innerHTML = list.slice(0, 120).map(a => {
    const isActive = !!a.is_active;
    const sev = String(a.severity || 'warn').toLowerCase();
    const kind = escapeHtml(a.kind || 'alert');
    const msg = escapeHtml(a.message || '');
    const upd = fmtTime(a.updated_at || a.created_at);
    const created = fmtTime(a.created_at);
    const ack = a.acked_at ? (fmtTime(a.acked_at) + (a.acked_by ? (' · ' + escapeHtml(a.acked_by)) : '')) : '—';
    const closed = a.closed_at ? (fmtTime(a.closed_at) + (a.closed_by ? (' · ' + escapeHtml(a.closed_by)) : '')) : '—';

    const pills = [
      `<span class="dd-pill ${sevClass(sev)}">${escapeHtml(sev.toUpperCase())}</span>`,
      isActive ? `<span class="dd-pill">ACTIVE</span>` : `<span class="dd-pill">closed</span>`,
      a.acked_at ? `<span class="dd-pill">ACK</span>` : ''
    ].filter(Boolean).join(' ');

    return `
      <div class="dd-alert-item ${isActive ? 'active' : ''}" data-alert-id="${a.id}">
        <div class="dd-alert-top">
          <div>
            <div class="dd-alert-kind">${kind}</div>
            <div class="dd-alert-meta">updated: ${escapeHtml(upd)} · created: ${escapeHtml(created)}</div>
          </div>
          <div style="display:flex; gap:6px; flex-wrap:wrap; justify-content:flex-end;">
            ${pills}
          </div>
        </div>
        ${msg ? `<div class="dd-alert-msg">${msg}</div>` : ''}
        <div class="dd-alert-meta" style="margin-top:8px">ACK: ${escapeHtml(ack)} · CLOSE: ${escapeHtml(closed)}</div>
        <div class="dd-alert-actions">
          <button class="btn" data-act="ack" ${a.acked_at ? 'disabled' : ''}><i class="fa-solid fa-check"></i> ACK</button>
          <button class="btn warn" data-act="close" ${isActive ? '' : 'disabled'}><i class="fa-solid fa-xmark"></i> Close</button>
        </div>
      </div>
    `;
  }).join('');

  elAlerts.querySelectorAll('button[data-act]').forEach(btn => {
    btn.addEventListener('click', async (ev) => {
      const wrap = ev.target.closest('.dd-alert-item');
      const alertId = wrap ? wrap.getAttribute('data-alert-id') : null;
      const act = btn.getAttribute('data-act');
      if(!alertId || !act) return;
      try{
        const url = act === 'ack'
          ? `/api/tracker/admin/alerts/${encodeURIComponent(alertId)}/ack`
          : `/api/tracker/admin/alerts/${encodeURIComponent(alertId)}/close`;
        await fetchJSON(url, { method:'POST', headers:{'Content-Type':'application/json'}, body:'{}' });
        await loadAlerts().catch(()=>{});
      }catch(e){
        console.error(e);
        showAlert(String(e.message || e));
      }
    });
  });
}

async function loadAlerts(){
  const flt = selAlerts ? (selAlerts.value || 'all') : 'all';
  const active = (flt === 'active') ? '1' : (flt === 'closed' ? '0' : 'all');
  const ar = _getAlertsRange();
  const aHours = parseFloat(selAlertHours && selAlertHours.value ? selAlertHours.value : '72') || 72;
  const qs = ar ? `from=${encodeURIComponent(ar.from)}&to=${encodeURIComponent(ar.to)}` : `hours=${encodeURIComponent(aHours)}`;
  const res = await fetchJSON(`/api/tracker/admin/device/${encodeURIComponent(deviceId)}/alerts?${qs}&limit=200&active=${encodeURIComponent(active)}`);
  _lastAlerts = (res.items || []);
  renderAlerts(_lastAlerts);
  renderRecommendations();
}


async function ackOrCloseAll(kind){
  // kind: 'ack' | 'close'
  const aHours = parseFloat(selAlertHours && selAlertHours.value ? selAlertHours.value : '72') || 72;
    const ar = _getAlertsRange();
    const qs = ar ? `from=${encodeURIComponent(ar.from)}&to=${encodeURIComponent(ar.to)}` : `hours=${encodeURIComponent(aHours)}`;
    const res = await fetchJSON(`/api/tracker/admin/device/${encodeURIComponent(deviceId)}/alerts?${qs}&limit=500&active=1`);
  const list = Array.isArray(res.items) ? res.items : [];
  let targets = list;
  if(kind === 'ack') targets = targets.filter(x => !x.acked_at);
  if(kind === 'close') targets = targets.filter(x => !!x.is_active);

  if(!targets.length){
    showAlert(kind === 'ack' ? 'Нет алёртов для ACK.' : 'Нет активных алёртов для Close.');
    setTimeout(()=>showAlert(''), 1800);
    return;
  }

  showAlert(`Выполняю ${kind.toUpperCase()} (${targets.length})…`);
  for(const a of targets){
    try{
      const url = kind === 'ack'
        ? `/api/tracker/admin/alerts/${encodeURIComponent(a.id)}/ack`
        : `/api/tracker/admin/alerts/${encodeURIComponent(a.id)}/close`;
      await fetchJSON(url, { method:'POST', headers:{'Content-Type':'application/json'}, body:'{}' });
    }catch(e){
      console.error(e);
    }
  }
  await loadAlerts().catch(()=>{});
  showAlert('');
}

  async function loadDeviceDetail(){
    const detail = await fetchJSON(`/api/tracker/admin/device/${encodeURIComponent(deviceId)}`);
    const d = detail.device || {};

    const title = (d.label || d.public_id || 'Устройство');
    elTitle.textContent = title;

    const subBits = [];
    subBits.push(`user_id: ${d.user_id || '—'}`);
    subBits.push(`revoked: ${d.is_revoked ? 'YES' : 'no'}`);
    subBits.push(`last_seen: ${fmtTime(d.last_seen_at)}`);
    if(d.health && d.health.updated_at){
      subBits.push(`health_age: ${hms(d.health_age_sec)}`);
    }
    elSub.textContent = subBits.join(' · ');

    btnRevoke.classList.toggle('warn', !d.is_revoked);
    btnRevoke.classList.toggle('primary', d.is_revoked);
    btnRevoke.querySelector('.lbl').textContent = d.is_revoked ? 'Restore' : 'Revoke';
    btnRevoke.querySelector('i').className = d.is_revoked ? 'fa-solid fa-rotate-left' : 'fa-solid fa-ban';

    const prof = d.profile || {};
    const hp = d.health || {};
    _lastDevice = d;
    _lastHealth = hp;
    renderRecommendations();
    updateExportLinks();
    const lp = d.last_point || {};

    const kvs = [];
    kvs.push(kv('device_id', d.public_id));
    kvs.push(kv('label', d.label || '—'));
    kvs.push(kv('created', fmtTime(d.created_at)));
    kvs.push(kv('last_seen', fmtTime(d.last_seen_at)));
    kvs.push(kv('tracking_active', d.tracking_active ? 'YES' : 'no'));
    kvs.push(kv('active_shift_id', d.active_shift_id ?? '—'));
    kvs.push(kv('active_session_id', d.active_session_id ?? '—'));

    kvs.push(kv('battery', hp.battery_pct != null ? `${hp.battery_pct}%${hp.is_charging ? ' ⚡' : ''}` : '—'));
    kvs.push(kv('net/gps', `${hp.net || '—'} / ${hp.gps || '—'}`));
    kvs.push(kv('accuracy', hp.accuracy_m != null ? `${Math.round(hp.accuracy_m)} м` : '—'));
    kvs.push(kv('queue', hp.queue_size ?? '—'));
    kvs.push(kv('Последняя отправка', fmtTime(hp.last_send_at || hp.updated_at)));
    kvs.push(kv('app', hp.app_version || '—'));
    kvs.push(kv('device', hp.device_model || '—'));
    kvs.push(kv('os', hp.os_version || '—'));

    kvs.push(kv('ФИО', prof.full_name || '—'));
    kvs.push(kv('Наряд', prof.duty_number || '—'));
    kvs.push(kv('Подразделение', prof.unit || '—'));
    kvs.push(kv('Должность', prof.position || '—'));
    kvs.push(kv('Звание', prof.rank || '—'));
    kvs.push(kv('Телефон', prof.phone || '—'));

    if(lp && lp.ts){
      kvs.push(kv('last_point', `${fmtTime(lp.ts)} · ${String(lp.lat).slice(0,10)}, ${String(lp.lon).slice(0,10)} · ${lp.kind || ''}`));
    } else {
      kvs.push(kv('last_point', '—'));
    }
    elKv.innerHTML = kvs.join('');

    return d;
  }

  async function loadHealthLog(){
    const hours = getHealthHours();
    const hl = await fetchJSON(`/api/tracker/admin/device/${encodeURIComponent(deviceId)}/health_log?hours=${encodeURIComponent(hours)}&limit=500`);
    const hitemsDesc = hl.items || [];
    renderHealthTable(hitemsDesc);
    const hitems = [...hitemsDesc].reverse(); // asc
    const xs = hitems.map(it => new Date(it.ts).getTime()).filter(x => isFinite(x));
    // keep xs aligned: if parsing fails, use index
    const base = Date.now();
    const xs2 = xs.length === hitems.length ? xs : hitems.map((_,i)=>base + i);

    const bat = hitems.map(it => it.battery_pct == null ? null : Number(it.battery_pct));
    const queue = hitems.map(it => it.queue_size == null ? null : Number(it.queue_size));
    const acc = hitems.map(it => it.accuracy_m == null ? null : Number(it.accuracy_m));

    drawLine(cBat, xs2, bat, {ymin:0, ymax:100});
    drawLine(cQueue, xs2, queue);
    drawLine(cAcc, xs2, acc);
    return hitemsDesc;
  }

  async function loadPoints(){
    const rr = _getRouteRange();
    const qs = rr ? `from=${encodeURIComponent(rr.from)}&to=${encodeURIComponent(rr.to)}` : `hours=${encodeURIComponent(getRouteHours())}`;
    const ptsRes = await fetchJSON(`/api/tracker/admin/device/${encodeURIComponent(deviceId)}/points?${qs}&limit=2000`);
    const pDesc = ptsRes.items || [];
    const points = [...pDesc].reverse();
    renderPointsTable(points);
    setMap(points);
    setPointsSummary(points);
    return points;
  }


  async function loadAll(){
    showAlert('');
    setLoading();

    updateExportLinks();

    await loadDeviceDetail();
    await loadHealthLog();
    await loadPoints();
    await loadAlerts().catch(()=>{});
  }

  async function refreshDeviceAndHealth(){
    try{
      updateExportLinks();
      if(typeof _syncUrlParams==='function') _syncUrlParams();
      await loadDeviceDetail();
      await loadHealthLog();
    }catch(e){
      console.error(e);
    }
  }

  let _lastPointsRefreshAt = 0;
  async function refreshPointsMaybe(force){
    const now = Date.now();
    if(!force && (now - _lastPointsRefreshAt) < 60000) return;
    _lastPointsRefreshAt = now;
    try{
      updateExportLinks();
      if(typeof _syncUrlParams==='function') _syncUrlParams();
      await loadPoints();
    }catch(e){
      console.error(e);
    }
  }

  function setWsState(state){
    if(!elWs) return;
    elWs.classList.remove('is-on','is-bad');
    if(state === 'on'){
      elWs.classList.add('is-on');
      elWs.title = 'Realtime: подключено';
    }else if(state === 'bad'){
      elWs.classList.add('is-bad');
      elWs.title = 'Realtime: переподключение…';
    }else{
      elWs.title = 'Realtime: нет соединения';
    }
  }

  function setupRealtime(){
    if(!(window.Realtime && typeof window.Realtime.on === 'function')) return;
    try{ window.Realtime.connect(); }catch(e){}
    setWsState(window.Realtime.isConnected && window.Realtime.isConnected() ? 'on' : '');

    const debHealth = (window.Realtime.debounce ? window.Realtime.debounce(()=>{
      refreshDeviceAndHealth();
      refreshPointsMaybe(false);
    }, 800) : ()=>{
      refreshDeviceAndHealth();
      refreshPointsMaybe(false);
    });

    const debAlerts = (window.Realtime.debounce ? window.Realtime.debounce(()=>loadAlerts().catch(()=>{}), 700) : ()=>loadAlerts().catch(()=>{}));

    window.Realtime.on('__open__', ()=>setWsState('on'));
    window.Realtime.on('__close__', ()=>setWsState('bad'));

    window.Realtime.on('tracker_health', (data)=>{
      try{
        if(data && String(data.device_id) === String(deviceId)) debHealth();
      }catch(e){}
    });

    ['tracker_alert','tracker_alert_closed','tracker_alert_acked'].forEach((ev)=>{
      window.Realtime.on(ev, (data)=>{
        try{
          if(data && String(data.device_id) === String(deviceId)) debAlerts();
        }catch(e){}
      });
    });

    window.Realtime.on('tracker_device_updated', (data)=>{
      try{
        if(data && String(data.device_id) === String(deviceId)) refreshDeviceAndHealth();
      }catch(e){}
    });
  }

  async function doRevokeRestore(){
    try{
      const detail = await fetchJSON(`/api/tracker/admin/device/${encodeURIComponent(deviceId)}`);
      const d = detail.device || {};
      const url = d.is_revoked
        ? `/api/tracker/admin/device/${encodeURIComponent(deviceId)}/restore`
        : `/api/tracker/admin/device/${encodeURIComponent(deviceId)}/revoke`;
      await fetchJSON(url, { method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}' });
      await loadAll();
    }catch(e){
      console.error(e);
      showAlert(String(e.message || e));
    }
  }

  btnRefresh && btnRefresh.addEventListener('click', ()=>loadAll().catch(e=>showAlert(String(e.message||e))));
  selAlerts && selAlerts.addEventListener('change', ()=>loadAlerts().catch(e=>showAlert(String(e.message||e))));
  btnAckAll && btnAckAll.addEventListener('click', ()=>ackOrCloseAll('ack'));
  btnCloseAll && btnCloseAll.addEventListener('click', ()=>ackOrCloseAll('close'));

  btnRevoke && btnRevoke.addEventListener('click', ()=>doRevokeRestore());
  btnRotate && btnRotate.addEventListener('click', async ()=>{
    if(!confirm('Rotate token для устройства? Старый токен станет недействительным.')) return;
    try{
      const r = await fetchJSON(`/api/tracker/admin/device/${encodeURIComponent(deviceId)}/rotate`, { method:'POST', headers:{'Content-Type':'application/json'}, body:'{}' });
      const token = (r && r.data && (r.data.new_token || r.data.token)) || r.new_token || r.token || '';
      if(token){
        showAlert('Новый токен: ' + token);
        try{ await navigator.clipboard.writeText(token); }catch(e){}
      } else {
        showAlert('Токен обновлён.');
      }
      setTimeout(()=>showAlert(''), 6000);
    }catch(e){
      console.error(e);
      showAlert(String(e.message || e));
    }
  });

  btnFit && btnFit.addEventListener('click', ()=>{
    if(map && layerLine && layerLine.getLatLngs && layerLine.getLatLngs().length){
      map.fitBounds(layerLine.getBounds().pad(0.2));
    }
  });
  selHours && selHours.addEventListener('change', ()=>{ updateExportLinks(); refreshDeviceAndHealth(); });
  selRouteHours && selRouteHours.addEventListener('change', ()=>{ updateExportLinks(); refreshPointsMaybe(true); });
  selAlertHours && selAlertHours.addEventListener('change', ()=>{ updateExportLinks(); loadAlerts().catch(e=>showAlert(String(e.message||e))); });
  selAlerts && selAlerts.addEventListener('change', ()=>{ loadAlerts().catch(e=>showAlert(String(e.message||e))); });

  // initial
  loadAll().catch(e=>{
    console.error(e);
    showAlert(String(e.message || e));
  });

  setupRealtime();

  // мягкий фолбэк-поллинг (если WS не доступен)
  setInterval(()=>{
    if(window.Realtime && window.Realtime.isConnected && window.Realtime.isConnected()) return;
    refreshDeviceAndHealth();
    refreshPointsMaybe(false);
    loadAlerts().catch(()=>{});
  }, 20000);
})();
