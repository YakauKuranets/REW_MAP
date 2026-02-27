(function(){
  const API_DASH = '/api/duty/admin/dashboard';
  const toastEl = document.getElementById('toast');

  function toast(msg){
    if(!toastEl) return;
    toastEl.textContent = msg;
    toastEl.style.display = 'block';
    clearTimeout(toastEl._t);
    toastEl._t = setTimeout(()=>{ toastEl.style.display='none'; }, 3500);
  }

  const map = L.map('map', { zoomControl: true }).setView([53.9, 27.56], 12);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(map);

  const markersByUser = new Map();

  async function fetchJson(url, opts){
    const res = await fetch(url, opts);
    const txt = await res.text();
    try { return { ok: res.ok, status: res.status, data: JSON.parse(txt) }; }
    catch(e){ return { ok: res.ok, status: res.status, data: txt }; }
  }

  function renderShifts(shifts){
    const el = document.getElementById('list-shifts');
    const cnt = document.getElementById('count-shifts');
    if(cnt) cnt.textContent = String(shifts.length);

    if(!el) return;
    if(!shifts.length){
      el.innerHTML = '<div class="muted">Нет активных смен</div>';
      return;
    }

    el.innerHTML = '';
    shifts.forEach(sh => {
      const div = document.createElement('div');
      div.className = 'card';
      const title = document.createElement('div');
      title.className = 'row';
      const left = document.createElement('div');
      left.innerHTML = `<strong>${(sh.unit_label || ('TG ' + sh.user_id))}</strong><div class="muted">shift #${sh.shift_id}</div>`;
      const right = document.createElement('div');
      const pill = document.createElement('span');
      pill.className = 'pill ' + (sh.tracking_active ? 'live' : '');
      pill.textContent = sh.tracking_active ? 'live' : 'idle';
      right.appendChild(pill);
      title.appendChild(left);
      title.appendChild(right);

      const meta = document.createElement('div');
      meta.className = 'muted';
      const last = sh.last;
      meta.innerHTML = `Старт: ${sh.started_at ? sh.started_at : '—'}<br>` +
        `Последняя точка: ${last && last.ts ? last.ts : '—'}`;

      const actions = document.createElement('div');
      actions.style.marginTop = '8px';
      if(last && last.session_id){
        const btn = document.createElement('button');
        btn.className = 'btn primary';
        btn.textContent = 'Трек / стоянки';
        btn.onclick = () => openTracking(last.session_id);
        actions.appendChild(btn);
      } else {
        const span = document.createElement('span');
        span.className='muted';
        span.textContent='Нет live-сессии';
        actions.appendChild(span);
      }

      div.appendChild(title);
      div.appendChild(meta);
      div.appendChild(actions);
      el.appendChild(div);
    });
  }

  function renderBreaks(breaks){
    const el = document.getElementById('list-breaks');
    const cnt = document.getElementById('count-breaks');
    if(cnt) cnt.textContent = String(breaks.length);
    if(!el) return;
    if(!breaks.length){
      el.innerHTML = '<div class="muted">Нет активных запросов</div>';
      return;
    }
    el.innerHTML='';
    breaks.forEach(br => {
      const div = document.createElement('div');
      div.className='card';
      const title = document.createElement('div');
      title.className='row';
      title.innerHTML = `<strong>🍽 #${br.id}</strong><span class="pill break">${br.status}</span>`;
      const meta = document.createElement('div');
      meta.className='muted';
      meta.innerHTML = `TG: ${br.user_id}<br>Длительность: ${br.duration_min} мин<br>` +
        `Запрос: ${br.requested_at || '—'}<br>` +
        `Старт: ${br.started_at || '—'}<br>` +
        `Конец: ${br.ends_at || '—'}`;
      const actions = document.createElement('div');
      actions.style.marginTop='8px';
      if(br.status === 'requested'){
        const b = document.createElement('button');
        b.className='btn primary';
        b.textContent='Подтвердить';
        b.onclick = () => approveBreak(br.id);
        actions.appendChild(b);
      }
      if(br.status === 'started'){
        const b2 = document.createElement('button');
        b2.className='btn danger';
        b2.textContent='Закончить обед';
        b2.onclick = () => endBreak(br.id);
        actions.appendChild(b2);
      }
      div.appendChild(title);
      div.appendChild(meta);
      div.appendChild(actions);
      el.appendChild(div);
    });
  }

  function upsertMarker(sh){
    const last = sh.last;
    if(!last || last.lat == null || last.lon == null) return;

    const key = sh.user_id;
    const label = sh.unit_label || ('TG ' + sh.user_id);
    const latlng = [last.lat, last.lon];

    let mk = markersByUser.get(key);
    if(!mk){
      mk = L.marker(latlng, { title: label });
      mk.addTo(map);
      mk.on('click', () => {
        if(last.session_id){
          openTracking(last.session_id);
        } else {
          toast('Нет активной live-сессии у ' + label);
        }
      });
      markersByUser.set(key, mk);
    } else {
      mk.setLatLng(latlng);
    }
    mk.bindTooltip(label, { direction: 'top', offset: [0,-12], opacity: 0.9 });
  }

  function dropMissing(shifts){
    const keep = new Set(shifts.map(s => s.user_id));
    for(const [uid, mk] of markersByUser.entries()){
      if(!keep.has(uid)){
        map.removeLayer(mk);
        markersByUser.delete(uid);
      }
    }
  }

  async function openTracking(sessionId){
    const r = await fetchJson(`/api/duty/admin/tracking/${sessionId}`);
    if(!r.ok){
      toast('Не удалось загрузить трек: ' + r.status);
      return;
    }
    const sess = r.data.session || {};
    const stops = r.data.stops || [];
    const snap = r.data.snapshot_url;

    let html = `<div style="min-width:260px"><strong>Трек #${sessionId}</strong><div class="muted">TG: ${sess.user_id || '—'}</div>`;
    if(snap){
      html += `<div style="margin-top:6px"><a href="${snap}" target="_blank">Открыть снимок маршрута (SVG)</a></div>`;
    }
    if(stops.length){
      html += `<div style="margin-top:8px"><strong>Стоянки</strong></div>`;
      stops.slice(0, 10).forEach(st => {
        const m = Math.round((st.duration_sec||0)/60);
        html += `<div class="muted">• ${m} мин (R≈${st.radius_m||10}м) ${st.center_lat?.toFixed?.(5)||''}, ${st.center_lon?.toFixed?.(5)||''}</div>`;
      });
      if(stops.length > 10) html += `<div class="muted">… ещё ${stops.length-10}</div>`;
    } else {
      html += `<div class="muted" style="margin-top:8px">Стоянок не найдено (или мало точек)</div>`;
    }
    html += `</div>`;

    // Popup in center
    const center = map.getCenter();
    L.popup().setLatLng(center).setContent(html).openOn(map);
  }

  async function approveBreak(id){
    const r = await fetchJson(`/api/duty/admin/breaks/${id}/approve`, { method:'POST' });
    if(!r.ok){ toast('Ошибка подтверждения: ' + r.status); return; }
    toast('Обед подтверждён #' + id);
    await refresh();
  }

  async function endBreak(id){
    const r = await fetchJson(`/api/duty/admin/breaks/${id}/end`, { method:'POST' });
    if(!r.ok){ toast('Ошибка завершения: ' + r.status); return; }
    toast('Обед завершён #' + id);
    await refresh();
  }

  async function refresh(){
    const r = await fetchJson(API_DASH);
    if(!r.ok){
      toast('Dashboard недоступен: ' + r.status);
      return;
    }
    const t = document.getElementById('server-time');
    if(t) t.textContent = r.data.server_time || '—';
    const shifts = r.data.active_shifts || [];
    const breaks = r.data.breaks || [];
    renderShifts(shifts);
    renderBreaks(breaks);
    shifts.forEach(upsertMarker);
    dropMissing(shifts);
  }

  function setupRealtime(){
    if(!(window.Realtime && typeof window.Realtime.on === 'function')) return;
    try{
      window.Realtime.connect();
      const deb = (window.Realtime.debounce ? window.Realtime.debounce(refresh, 900) : refresh);

      // ключевые события для duty
      ['tracking_point','tracking_started','tracking_stopped','shift_started','shift_ended','break_started','break_ended','break_due','sos_created','sos_acked','sos_closed']
        .forEach((ev) => window.Realtime.on(ev, (data) => {
          if(ev === 'break_due'){
            toast('⏱ Время обеда истекло у TG ' + (data?.user_id || ''));
          }
          deb();
        }));
    }catch(e){}
  }

  refresh();
  setupRealtime();
  // мягкий фолбэк-поллинг (если WS не доступен)
  setInterval(refresh, 15000);
})();
