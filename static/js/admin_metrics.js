/* admin_metrics.js — мониторинг KPI + алёртов */

(function(){
  const $ = (sel) => document.querySelector(sel);

  const el = {
    serverTime: $('#server-time'),
    gen: $('#kpi-gen'),
    onlineWindow: $('#kpi-online-window'),

    total: $('#kpi-total'),
    online: $('#kpi-online'),
    revoked: $('#kpi-revoked'),
    activeAlerts: $('#kpi-active-alerts'),
    critAlerts: $('#kpi-crit-alerts'),
    points5m: $('#kpi-points-5m'),

    alertbar: $('#alertbar'),
    tblActive: $('#tbl-active'),
    tblRecent: $('#tbl-recent'),
    btnRefresh: $('#btn-refresh'),
  };

  function fmtTs(iso){
    if(!iso) return '—';
    try{
      const d = new Date(iso);
      if(isNaN(d.getTime())) return String(iso);
      return d.toLocaleString();
    }catch(e){
      return String(iso);
    }
  }

  function sevClass(sev){
    const s = (sev||'').toLowerCase();
    if(s === 'crit') return 'am-sev am-sev--crit';
    if(s === 'warn') return 'am-sev am-sev--warn';
    return 'am-sev am-sev--info';
  }

  function esc(s){
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  function renderAlerts(tbody, rows){
    if(!rows || !rows.length){
      tbody.innerHTML = `<tr><td colspan="5" class="muted">—</td></tr>`;
      return;
    }
    tbody.innerHTML = rows.map(a => {
      const t = fmtTs(a.updated_at || a.created_at);
      const did = a.device_id || '—';
      const dlabel = a.device_label || did;
      const sev = (a.severity || 'info').toUpperCase();
      const kind = a.kind || '';
      const msg = a.message || '';
      const devLink = did && did !== '—' ? `/admin/devices/${encodeURIComponent(did)}` : null;

      return `
        <tr class="am-row">
          <td>${esc(t)}</td>
          <td class="am-dev">${devLink ? `<a href="${devLink}" title="Открыть устройство">${esc(dlabel)}</a>` : esc(dlabel)}</td>
          <td><span class="${sevClass(a.severity)}">${esc(sev)}</span></td>
          <td><code>${esc(kind)}</code></td>
          <td class="am-msg">${esc(msg)}</td>
        </tr>
      `;
    }).join('');
  }

  function showError(msg){
    el.alertbar.style.display = 'block';
    el.alertbar.textContent = msg;
  }

  function hideError(){
    el.alertbar.style.display = 'none';
    el.alertbar.textContent = '';
  }

  async function loadOnce(){
    try{
      const r = await fetch('/api/tracker/admin/metrics', { cache: 'no-store' });
      if(!r.ok){
        showError(`HTTP ${r.status}: не удалось получить /api/tracker/admin/metrics`);
        return;
      }
      const j = await r.json();
      hideError();

      // _ok response includes server_time
      if(el.serverTime) el.serverTime.textContent = fmtTs(j.server_time);

      const gen = j.generated_at || j.server_time;
      if(el.gen) el.gen.textContent = fmtTs(gen);

      const m = j.metrics || {};
      el.total.textContent = m.total_devices ?? 0;
      el.online.textContent = m.online_devices ?? 0;
      el.revoked.textContent = m.revoked_devices ?? 0;
      el.activeAlerts.textContent = m.active_alerts ?? 0;
      el.critAlerts.textContent = m.crit_alerts ?? 0;
      el.points5m.textContent = m.points_last_5m ?? 0;
      if(el.onlineWindow) el.onlineWindow.textContent = m.online_window_sec ?? '—';

      renderAlerts(el.tblActive, j.active_alerts_sample || []);
      renderAlerts(el.tblRecent, j.recent_alerts || []);

    }catch(e){
      showError(`Ошибка загрузки метрик: ${e}`);
    }
  }

  let timer = null;
  function start(){
    loadOnce();
    timer = setInterval(loadOnce, 10000);
    if(el.btnRefresh) el.btnRefresh.addEventListener('click', loadOnce);
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', start);
  }else{
    start();
  }
})();
