// Панель проблем трекера (технич...)

(function(){
  const elList = document.getElementById('list');
  const elQ = document.getElementById('q');
  const elBtnSearch = document.getElementById('btn-search');
  const elRefresh = document.getElementById('btn-refresh');
  const elFltCrit = document.getElementById('flt-crit');
  const elFltAcked = document.getElementById('flt-acked');
  const elTime = document.getElementById('server-time');
  const elAlertbar = document.getElementById('alertbar');

  const kAll = document.getElementById('kpi-all');
  const kCrit = document.getElementById('kpi-crit');
  const kDevices = document.getElementById('kpi-devices');
  const kUnacked = document.getElementById('kpi-unacked');

  const toast = document.getElementById('toast');
  function showToast(msg, kind){
    if(!toast) return;
    toast.textContent = msg;
    toast.style.display = 'block';
    toast.style.border = '1px solid var(--admin-border)';
    toast.style.background = kind === 'err'
      ? 'color-mix(in srgb, var(--admin-danger) 18%, var(--card))'
      : kind === 'warn'
        ? 'color-mix(in srgb, var(--admin-amber) 14%, var(--card))'
        : 'color-mix(in srgb, var(--success) 12%, var(--card))';
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => { toast.style.display = 'none'; }, 3000);
  }


/* v17: skeleton */
function skelGroups(){
  const items = [];
  for(let i=0;i<4;i++){
    items.push(`<div class="skel" style="margin-bottom:10px">
      <div class="skel-line tall" style="width:62%"></div>
      <div class="skel-line" style="width:88%"></div>
      <div class="skel-line small" style="width:54%"></div>
    </div>`);
  }
  return items.join('');
}

  function fmtTs(s){
    try{ return new Date(s).toLocaleString(); }catch(e){ return s || '—'; }
  }

  async function apiGet(url){
    const r = await fetch(url, { credentials: 'same-origin' });
    const t = await r.text();
    let j = null;
    try{ j = JSON.parse(t); }catch(e){ j = null; }
    if(!r.ok) throw new Error(j && j.error ? j.error : ('HTTP ' + r.status));
    return j;
  }

  async function apiPost(url){
    const r = await fetch(url, { method:'POST', credentials:'same-origin' });
    const t = await r.text();
    let j = null;
    try{ j = JSON.parse(t); }catch(e){ j = null; }
    if(!r.ok) throw new Error(j && j.error ? j.error : ('HTTP ' + r.status));
    return j;
  }

  let state = { alerts: [] };

  function applyFilters(rows){
    const q = (elQ?.value || '').trim().toLowerCase();
    const critOnly = !!elFltCrit?.checked;
    const unackedOnly = !!elFltAcked?.checked;

    return (rows || []).filter(a => {
      if(critOnly && String(a.severity || '') !== 'crit') return false;
      if(unackedOnly && a.acked_at) return false;
      if(!q) return true;
      const hay = [a.device_id, a.user_id, a.kind, a.message, a.details]
        .map(x => (x == null ? '' : String(x))).join(' ').toLowerCase();
      return hay.includes(q);
    });
  }

  function groupByDevice(rows){
    const map = new Map();
    for(const a of (rows || [])){
      const did = a.device_id ? String(a.device_id) : '—';
      if(!map.has(did)) map.set(did, { device_id: did, alerts: [] });
      map.get(did).alerts.push(a);
    }
    const groups = Array.from(map.values());
    for(const g of groups){
      g.crit = g.alerts.filter(x => String(x.severity||'') === 'crit').length;
      g.unacked = g.alerts.filter(x => !x.acked_at).length;
      g.total = g.alerts.length;
      g.score = g.crit * 1000 + g.unacked * 100 + g.total;
    }
    groups.sort((a,b) => (b.score - a.score) || String(a.device_id).localeCompare(String(b.device_id)));
    return groups;
  }

  function render(){
    const rows = applyFilters(state.alerts);
    const all = state.alerts.length;
    const crit = state.alerts.filter(a => String(a.severity||'') === 'crit').length;
    const devices = new Set(state.alerts.map(a => String(a.device_id || ''))).size;
    const unacked = state.alerts.filter(a => !a.acked_at).length;

    if(kAll) kAll.textContent = String(all);
    if(kCrit) kCrit.textContent = String(crit);
    if(kDevices) kDevices.textContent = String(devices);
    if(kUnacked) kUnacked.textContent = String(unacked);

    if(!rows.length){
      elList.innerHTML = '<div class="muted">Нет активных проблем по фильтру.</div>';
      return;
    }

    const groups = groupByDevice(rows);
    elList.innerHTML = groups.map(g => {
      const did = g.device_id;
      const didSafe = did && did !== '—' ? encodeURIComponent(did) : '';
      const devUrl = didSafe ? `/admin/devices/${didSafe}` : '';
      const headSev = g.crit > 0
        ? `<span class="pr-sev crit"><i class="fa-solid fa-triangle-exclamation"></i> crit: ${g.crit}</span>`
        : `<span class="pr-sev warn"><i class="fa-solid fa-circle-info"></i> warn</span>`;
      const headUnacked = `<span class="pr-sev pr-ack ${g.unacked ? '' : 'ok'}"><i class="fa-solid fa-check"></i> не ACK: ${g.unacked}</span>`;
      const idsUnacked = g.alerts.filter(a => !a.acked_at).map(a => a.id).join(',');
      const idsAll = g.alerts.map(a => a.id).join(',');

      const groupActions = `
        ${devUrl ? `<a class="btn" href="${devUrl}"><i class="fa-solid fa-mobile-screen"></i> Устройство</a>` : ''}
        ${idsUnacked ? `<button class="btn" data-act="ack_all" data-ids="${idsUnacked}"><i class="fa-solid fa-check-double"></i> ACK все</button>` : ''}
        <button class="btn" data-act="close_all" data-ids="${idsAll}"><i class="fa-solid fa-xmark"></i> Close все</button>
      `;

      const alertsHtml = g.alerts
        .sort((a,b) => {
          const sa = String(a.severity||'warn') === 'crit' ? 1 : 0;
          const sb = String(b.severity||'warn') === 'crit' ? 1 : 0;
          if(sb !== sa) return sb - sa;
          const ua = a.acked_at ? 0 : 1;
          const ub = b.acked_at ? 0 : 1;
          if(ub !== ua) return ub - ua;
          return String(b.updated_at || b.created_at || '').localeCompare(String(a.updated_at || a.created_at || ''));
        })
        .map(a => {
          const sev = String(a.severity || 'warn');
          const uid = a.user_id ? String(a.user_id) : '';
          const msg = (a.message || a.kind || 'alert');
          const details = a.details ? String(a.details) : (a.payload ? payloadSummary(a.payload) : '');
          const recs = (window.Recs && window.Recs.fromAlert) ? window.Recs.fromAlert(a) : [];
          const recHtml = (window.Recs && window.Recs.block) ? window.Recs.block(recs) : '';
          const updated = fmtTs(a.updated_at || a.created_at);
          const acked = a.acked_at ? fmtTs(a.acked_at) : '';
          const chipSev = sev === 'crit'
            ? '<span class="adm-chip adm-chip--crit"><i class="fa-solid fa-triangle-exclamation"></i> crit</span>'
            : '<span class="adm-chip"><i class="fa-solid fa-circle-info"></i> warn</span>';
          const chipAck = a.acked_at
            ? '<span class="adm-chip adm-chip--ok"><i class="fa-solid fa-check"></i> ACK</span>'
            : '<span class="adm-chip"><i class="fa-regular fa-circle"></i> not ACK</span>';

          const btnAck = a.acked_at
            ? ''
            : `<button class="btn" data-act="ack" data-id="${a.id}"><i class="fa-solid fa-check"></i> ACK</button>`;
          const btnClose = `<button class="btn" data-act="close" data-id="${a.id}"><i class="fa-solid fa-xmark"></i> Close</button>`;

          return `
            <div class="pr-alert">
              <div class="pr-alert__row">
                <div>
                  <div class="pr-alert__title">${escapeHtml(msg)}</div>
                  <div class="muted" style="margin-top:3px">${updated}${acked ? ' · ack: ' + acked : ''}</div>
                  <div class="pr-alert__meta">
                    ${chipSev}
                    ${chipAck}
                    ${uid ? `<span class="adm-chip" title="user_id">👤 ${escapeHtml(uid)}</span>` : ''}
                    ${a.kind ? `<span class="adm-chip" title="kind">${escapeHtml(a.kind)}</span>` : ''}
                  </div>
                  ${details ? `<div class="pr-details">${escapeHtml(details)}</div>` : ''}
                  ${recHtml}
                </div>
                <div class="pr-alert__actions">${btnAck}${btnClose}</div>
              </div>
            </div>
          `;
        }).join('');

      return `
        <div class="pr-group ${g.crit > 0 ? 'crit' : ''}">
          <div class="pr-group__head">
            <div>
              <div class="pr-group__title">
                <i class="fa-solid fa-mobile-screen"></i>
                ${devUrl ? `<a href="${devUrl}">📱 ${escapeHtml(did)}</a>` : `<span>📱 ${escapeHtml(did)}</span>`}
                ${headSev}
                <span class="adm-chip"><i class="fa-solid fa-layer-group"></i> всего: ${g.total}</span>
                ${headUnacked}
              </div>
              <div class="pr-group__meta">Приоритет: ${g.score} · сортировка: crit → not ACK → время</div>
            </div>
            <div class="pr-group__actions">${groupActions}</div>
          </div>
          <div class="pr-group__body">
            ${alertsHtml}
          </div>
        </div>
      `;
    }).join('');
  }

  function payloadSummary(p){
    try{
      if(!p || typeof p !== 'object') return '';
      const keys = Object.keys(p);
      if(!keys.length) return '';
      // показываем только несколько ключей, чтобы не превращать UI в JSON‑свалку
      const preferred = ['age_sec','last_point_ts','last_health_ts','battery_pct','is_charging','net','gps','accuracy_m','queue_size','tracking_on','shift_id'];
      const out = [];
      const take = (k) => {
        if(!(k in p)) return;
        let v = p[k];
        if(v == null) return;
        if(typeof v === 'number'){
          if(k === 'age_sec'){
            const m = Math.round(v/60);
            out.push(`${k}=${v} (${m}m)`);
          } else {
            out.push(`${k}=${v}`);
          }
        } else {
          const s = String(v);
          out.push(`${k}=${s.length>80 ? (s.slice(0,80)+'…') : s}`);
        }
      };
      preferred.forEach(take);
      // если preferred пустой — берём первые 6 любых
      if(!out.length){
        keys.slice(0,6).forEach(take);
      }
      return out.join(' · ');
    }catch(_){
      return '';
    }
  }

  function escapeHtml(s){
    return String(s == null ? '' : s)
      .replaceAll('&','&amp;')
      .replaceAll('<','&lt;')
      .replaceAll('>','&gt;')
      .replaceAll('"','&quot;')
      .replaceAll("'",'&#39;');
  }

  async function refresh(){
    try{
      elList.innerHTML = skelGroups();
      const alerts = await apiGet('/api/tracker/admin/alerts?active=1&limit=500');
      state.alerts = Array.isArray(alerts) ? alerts : [];

      // server time if provided elsewhere
      try{
        const p = await apiGet('/api/tracker/admin/problems');
        if(p && p.server_time && elTime) elTime.textContent = fmtTs(p.server_time);
      }catch(_){ /* ignore */ }

      if(elAlertbar){
        const crit = state.alerts.filter(a => String(a.severity||'') === 'crit').length;
        if(crit > 0){
          elAlertbar.style.display = 'block';
          elAlertbar.textContent = `Критических проблем: ${crit}. Проверьте GPS/сеть/заряд/очередь.`;
        } else {
          elAlertbar.style.display = 'none';
        }
      }

      render();
    } catch (e) {
      showToast('Ошибка загрузки: ' + (e.message || e), 'err');
      elList.innerHTML = '<div class="muted">Ошибка загрузки.</div>';
    }
  }

  async function ackMany(ids){
    for(const id of ids){
      await apiPost(`/api/tracker/admin/alerts/${id}/ack`);
    }
  }

  async function closeMany(ids){
    for(const id of ids){
      await apiPost(`/api/tracker/admin/alerts/${id}/close`);
    }
  }

  async function onAction(act, id){
    try{
      if(act === 'ack'){
        await apiPost(`/api/tracker/admin/alerts/${id}/ack`);
        showToast('ACK выполнен', 'ok');
      } else if(act === 'close'){
        await apiPost(`/api/tracker/admin/alerts/${id}/close`);
        showToast('Закрыто', 'ok');
      } else if(act === 'ack_all'){
        const ids = String(id||'').split(',').map(x => x.trim()).filter(Boolean);
        if(!ids.length) return;
        if(!confirm(`ACK всех алёртов: ${ids.length} ?`)) return;
        await ackMany(ids);
        showToast(`ACK все (${ids.length})`, 'ok');
      } else if(act === 'close_all'){
        const ids = String(id||'').split(',').map(x => x.trim()).filter(Boolean);
        if(!ids.length) return;
        if(!confirm(`Закрыть все алёрты в группе: ${ids.length} ?`)) return;
        await closeMany(ids);
        showToast(`Закрыто все (${ids.length})`, 'ok');
      }
      await refresh();
    } catch (e) {
      showToast('Ошибка: ' + (e.message || e), 'err');
    }
  }

  function bind(){
    elBtnSearch?.addEventListener('click', render);
    elRefresh?.addEventListener('click', refresh);
    elQ?.addEventListener('keydown', (e) => {
      if(e.key === 'Enter') render();
    });
    elFltCrit?.addEventListener('change', render);
    elFltAcked?.addEventListener('change', render);

    document.addEventListener('click', (e) => {
      const btn = e.target?.closest?.('[data-act]');
      if(!btn) return;
      const act = btn.getAttribute('data-act');
      const id = btn.getAttribute('data-id') || btn.getAttribute('data-ids');
      if(!act || !id) return;
      onAction(act, id);
    });
  }

  function setupRealtime(){
    if(!(window.Realtime && typeof window.Realtime.on === 'function')) return;
    try{
      window.Realtime.connect();
      const deb = (window.Realtime.debounce ? window.Realtime.debounce(refresh, 600) : refresh);
      ['tracker_alert','tracker_alert_closed','tracker_alert_acked'].forEach((ev) => {
        window.Realtime.on(ev, () => { deb(); });
      });
    }catch(_){ }
  }

  bind();
  refresh();
  setupRealtime();

  // мягкий фолбэк-поллинг (если WS не доступен)
  setInterval(refresh, 20000);
})();
