(function(){
  'use strict';

  const state = {
    devices: [],
    serverTime: null,
  };

  const elList = document.getElementById('list');
  const elToast = document.getElementById('toast');
  const elServerTime = document.getElementById('server-time');
  const elQ = document.getElementById('q');
  const elFltOnline = document.getElementById('flt-online');
  const elFltStale = document.getElementById('flt-stale');
  const elFltRevoked = document.getElementById('flt-revoked');
  const elAlertbar = document.getElementById('alertbar');

  function escapeHtml(s){
    return String(s ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[ch]));
  }

  function showToast(text){
    if(!elToast) return;
    elToast.textContent = text;
    elToast.style.display = 'block';
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => { elToast.style.display = 'none'; }, 2600);
  }


/* v17: skeleton */
function skelCards(n){
  const items = [];
  for(let i=0;i<(n||6);i++){
    items.push(`<div class="skel" style="margin-bottom:10px">
      <div class="skel-line tall" style="width:70%"></div>
      <div class="skel-line" style="width:92%"></div>
      <div class="skel-line small" style="width:58%"></div>
    </div>`);
  }
  return items.join('');
}

  function fmtAgeSec(sec){
    if(sec == null) return '—';
    if(sec < 60) return sec + 'с';
    const m = Math.floor(sec/60);
    const s = sec % 60;
    if(m < 60) return m + 'м ' + s + 'с';
    const h = Math.floor(m/60);
    const mm = m % 60;
    return h + 'ч ' + mm + 'м';
  }

  function ageFromIso(iso){
    try{
      const t = Date.parse(iso);
      if(!t) return null;
      return Math.max(0, Math.floor((Date.now() - t)/1000));
    }catch(e){
      return null;
    }
  }

  function isOnline(d){
    // online: свежий health <= 90с или last_seen <= 90с
    const ha = (typeof d.health_age_sec === 'number') ? d.health_age_sec : null;
    if(ha != null) return ha <= 90;
    const la = ageFromIso(d.last_seen_at);
    if(la != null) return la <= 90;
    return false;
  }

  function isStale(d){
    // stale: health > 180с или last_seen > 180с
    const ha = (typeof d.health_age_sec === 'number') ? d.health_age_sec : null;
    if(ha != null) return ha > 180;
    const la = ageFromIso(d.last_seen_at);
    if(la != null) return la > 180;
    return true; // нет данных - считаем stale
  }

  function tagFor(d){
    if(d.is_revoked) return {cls:'bad', text:'revoked'};
    if(isStale(d)) return {cls:'warn', text:'stale'};
    if(isOnline(d)) return {cls:'ok', text:'online'};
    return {cls:'warn', text:'idle'};
  }

  function applyFilters(list){
    const q = (elQ?.value || '').trim().toLowerCase();
    const fOnline = !!(elFltOnline && elFltOnline.checked);
    const fStale = !!(elFltStale && elFltStale.checked);
    const fRevoked = !!(elFltRevoked && elFltRevoked.checked);

    return (list || []).filter(d => {
      if(fOnline && !isOnline(d)) return false;
      if(fStale && !isStale(d)) return false;
      if(fRevoked && !d.is_revoked) return false;
      if(q){
        const blob = [d.public_id, d.user_id, d.label, d.unit_label,
          d.profile?.full_name, d.profile?.duty_number, d.profile?.phone,
          d.device_model, d.os_version, d.app_version
        ].filter(Boolean).join(' ').toLowerCase();
        if(!blob.includes(q)) return false;
      }
      return true;
    });
  }

  function render(){
    if(!elList) return;
    const all = state.devices || [];
    const list = applyFilters(all);

    // KPI
    const setKpi = (id, v) => { const el = document.getElementById(id); if(el) el.textContent = String(v); };
    setKpi('kpi-all', all.length);
    setKpi('kpi-online', all.filter(isOnline).length);
    setKpi('kpi-stale', all.filter(isStale).length);
    setKpi('kpi-revoked', all.filter(d => d.is_revoked).length);

    // Alertbar
    const staleN = all.filter(isStale).length;
    if(elAlertbar){
      if(staleN > 0){
        elAlertbar.style.display = '';
        elAlertbar.textContent = `⚠ Есть ${staleN} устройство(а/й) без свежего heartbeat. Открой карточку и проверь батарею/сеть/GPS.`;
      } else {
        elAlertbar.style.display = 'none';
      }
    }

    if(!list.length){
      elList.innerHTML = '<div class="muted">Ничего не найдено</div>';
      return;
    }

    elList.innerHTML = '';
    for(const d of list){
      const tag = tagFor(d);
      const la = ageFromIso(d.last_seen_at);
      const ha = (typeof d.health_age_sec === 'number') ? d.health_age_sec : null;
      const hp = d.health || null;

      const profile = d.profile || {};
      const title = d.label || profile.duty_number || profile.full_name || d.public_id;
      const cls = `dev-card${isStale(d) ? ' stale' : ''}${d.is_revoked ? ' revoked' : ''}`;

      const healthLine = hp ? (
        `${hp.battery_pct != null ? ('🔋' + hp.battery_pct + '%') : '🔋—'} ` +
        `${hp.net ? ('📶' + hp.net) : '📶—'} ` +
        `${hp.gps ? ('🛰 ' + hp.gps) : '🛰 —'} ` +
        `${hp.queue_size != null ? ('📦' + hp.queue_size) : '📦—'} ` +
        `${ha != null ? ('· ' + fmtAgeSec(ha)) : ''}`
      ) : '';

      const lastPoint = d.last_point ? `последняя точка: ${escapeHtml(d.last_point.ts || '—')}` : 'последняя точка: —';

      const recs = (window.Recs && window.Recs.fromDevice) ? window.Recs.fromDevice(d) : [];
      const recsHtml = (window.Recs && window.Recs.chips) ? window.Recs.chips(recs) : '';

      const el = document.createElement('div');
      el.className = cls;
      el.innerHTML = `
        <div class="dev-left">
          <div class="dev-title">
            <a class="dev-link" href="/admin/devices/${encodeURIComponent(d.public_id)}" title="Открыть детали устройства">${escapeHtml(title)}</a>
            <span class="tag ${escapeHtml(tag.cls)}">${escapeHtml(tag.text)}</span>
          </div>
          <div class="dev-meta">
            <div><b>device_id:</b> ${escapeHtml(d.public_id)} · <b>user_id:</b> ${escapeHtml(d.user_id || '—')} ${d.unit_label ? ('· <b>unit:</b> ' + escapeHtml(d.unit_label)) : ''}</div>
            <div><b>seen:</b> ${d.last_seen_at ? escapeHtml(d.last_seen_at) : '—'} ${la != null ? ('· ' + escapeHtml(fmtAgeSec(la))) : ''}</div>
            ${healthLine ? `<div><b>health:</b> ${escapeHtml(healthLine)}</div>` : ''}
            ${recsHtml ? `<div class="dev-recs">${recsHtml}</div>` : ''}
            <div><b>${escapeHtml(lastPoint)}</b></div>
            <div>${profile.full_name ? ('<b>ФИО:</b> ' + escapeHtml(profile.full_name) + ' · ') : ''}${profile.duty_number ? ('<b>№:</b> ' + escapeHtml(profile.duty_number) + ' · ') : ''}${profile.phone ? ('<b>тел:</b> ' + escapeHtml(profile.phone)) : ''}</div>
            <div>${d.device_model ? ('<b>device:</b> ' + escapeHtml(d.device_model) + ' · ') : ''}${d.os_version ? ('<b>os:</b> ' + escapeHtml(d.os_version) + ' · ') : ''}${d.app_version ? ('<b>app:</b> ' + escapeHtml(d.app_version)) : ''}</div>
          </div>
        </div>
        <div class="dev-actions">
          <button class="btn" data-act="center"><i class="fa-solid fa-location-dot"></i> Центр</button>
          <a class="btn" href="/admin/devices/${encodeURIComponent(d.public_id)}"><i class="fa-solid fa-circle-info"></i> Детали</a>
          ${d.is_revoked ? `<button class="btn" data-act="restore"><i class="fa-solid fa-unlock"></i> Restore</button>` : `<button class="btn" data-act="revoke"><i class="fa-solid fa-ban"></i> Revoke</button>`}
        </div>
      `;

      el.querySelector('[data-act="center"]').onclick = () => {
        try{ localStorage.setItem('ap_focus_user_id', String(d.user_id || '')); }catch(e){}
        location.href = '/admin/panel';
      };

      const btnRevoke = el.querySelector('[data-act="revoke"]');
      if(btnRevoke){
        btnRevoke.onclick = () => doAction(`/api/tracker/admin/device/${encodeURIComponent(d.public_id)}/revoke`, 'Revoke выполнен');
      }
      const btnRestore = el.querySelector('[data-act="restore"]');
      if(btnRestore){
        btnRestore.onclick = () => doAction(`/api/tracker/admin/device/${encodeURIComponent(d.public_id)}/restore`, 'Restore выполнен');
      }

      elList.appendChild(el);
    }
  }

  async function doAction(url, okText){
    try{
      const res = await fetch(url, { method:'POST', headers:{'Content-Type':'application/json'}, body:'{}' });
      const j = await res.json().catch(() => ({}));
      if(!res.ok){ throw new Error(j.error || ('HTTP ' + res.status)); }
      showToast(okText);
      refresh();
    }catch(e){
      showToast('Ошибка: ' + (e?.message || e));
    }
  }

  async function refresh(){
    try{
      if(elList) elList.innerHTML = skelCards(7);
      const res = await fetch('/api/tracker/admin/devices?limit=500&offset=0');
      const j = await res.json().catch(() => ({}));
      state.devices = j.devices || [];
      state.serverTime = j.server_time || null;
      if(elServerTime) elServerTime.textContent = state.serverTime ? new Date(state.serverTime).toLocaleString() : '—';
      render();
    }catch(e){
      if(elList) elList.textContent = 'Ошибка загрузки устройств';
    }
  }

  function bind(){
    document.getElementById('btn-refresh')?.addEventListener('click', refresh);
    document.getElementById('btn-search')?.addEventListener('click', render);
    [elQ, elFltOnline, elFltStale, elFltRevoked].forEach(el => {
      if(!el) return;
      el.addEventListener('input', render);
      el.addEventListener('change', render);
    });
  }

  function setupRealtime(){
    if(!(window.Realtime && typeof window.Realtime.on === 'function')) return;
    try{
      window.Realtime.connect();
      const deb = (window.Realtime.debounce ? window.Realtime.debounce(refresh, 800) : refresh);
      ['tracker_health','tracker_device_updated','tracker_paired','tracker_profile','tracker_alert','tracker_alert_closed','tracker_alert_acked']
        .forEach((ev) => window.Realtime.on(ev, () => { deb(); }));
    }catch(e){}
  }

  bind();
  setupRealtime();
  refresh();
  // мягкий фолбэк-поллинг (если WS не доступен)
  setInterval(refresh, 20000);
})();
