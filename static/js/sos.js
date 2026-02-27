/* SOS overlay (admin) — full screen alert + actions.
   Работает в / (главная карта) и /admin/duty (панель нарядов).
   Требует админскую сессию (иначе просто тихо не показывается).
*/
(function () {
  const API_ACTIVE = "/api/duty/admin/sos/active";

  function wsUrl() {
    const proto = (location.protocol === "https:") ? "wss" : "ws";
    return `${proto}://${location.hostname}:8765`;
  }

  const state = {
    overlay: null,
    active: new Map(), // id -> sos
    currentId: null,
    ws: null,
    connectedOnce: false,
  };

  function fmtTime(iso) {
    try {
      if (!iso) return "";
      const d = new Date(iso);
      return d.toLocaleString();
    } catch (e) { return ""; }
  }

  function ensureOverlay() {
    if (state.overlay) return state.overlay;

    const wrap = document.createElement("div");
    wrap.id = "sos-overlay";
    wrap.style.cssText = [
      "position:fixed",
      "left:0","top:0","right:0","bottom:0",
      "display:none",
      "z-index:100000",
      "background:rgba(0,0,0,0.75)",
      "backdrop-filter: blur(2px)",
      "padding:24px",
    ].join(";");

    const card = document.createElement("div");
    card.style.cssText = [
      "max-width:860px",
      "margin:0 auto",
      "background:#fff",
      "border-radius:16px",
      "box-shadow:0 20px 80px rgba(0,0,0,0.35)",
      "padding:18px 18px 14px 18px",
      "font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif",
    ].join(";");

    card.innerHTML = `
      <div style="display:flex;align-items:center;gap:12px;">
        <div style="font-size:28px;line-height:1;">🆘</div>
        <div style="flex:1;">
          <div style="font-size:18px;font-weight:700;">SOS: экстренный сигнал</div>
          <div id="sos-sub" style="margin-top:2px;color:#333;"></div>
        </div>
        <button id="sos-hide" style="border:0;background:#eee;border-radius:10px;padding:8px 10px;cursor:pointer;">Свернуть</button>
      </div>
      <div id="sos-body" style="margin-top:14px;line-height:1.35;color:#222;"></div>
      <div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:14px;">
        <button id="sos-pan" style="border:0;background:#222;color:#fff;border-radius:10px;padding:10px 12px;cursor:pointer;">Показать на карте</button>
        <button id="sos-chat" style="border:0;background:#2c7be5;color:#fff;border-radius:10px;padding:10px 12px;cursor:pointer;">Написать</button>
        <button id="sos-ack" style="border:0;background:#10b981;color:#fff;border-radius:10px;padding:10px 12px;cursor:pointer;">Подтвердить</button>
        <button id="sos-close" style="border:0;background:#ef4444;color:#fff;border-radius:10px;padding:10px 12px;cursor:pointer;">Закрыть SOS</button>
      </div>
      <div id="sos-hint" style="margin-top:10px;color:#666;font-size:12px;"></div>
    `;

    wrap.appendChild(card);
    document.body.appendChild(wrap);

    wrap.querySelector("#sos-hide").addEventListener("click", () => {
      wrap.style.display = "none";
    });

    wrap.querySelector("#sos-pan").addEventListener("click", () => {
      const sos = getCurrent();
      if (!sos) return;
      panTo(sos.lat, sos.lon);
    });

    wrap.querySelector("#sos-chat").addEventListener("click", () => {
      const sos = getCurrent();
      if (!sos) return;
      if (typeof window.chatOpenToUser === "function") {
        window.chatOpenToUser(String(sos.user_id));
      } else {
        // На странице /admin/duty чат может не быть загружен — откроем главную карту с параметром.
        window.location.href = "/?chatUser=" + encodeURIComponent(String(sos.user_id));
      }
    });

    wrap.querySelector("#sos-ack").addEventListener("click", async () => {
      const sos = getCurrent();
      if (!sos) return;
      await postJson(`/api/duty/admin/sos/${encodeURIComponent(sos.id)}/ack`);
    });

    wrap.querySelector("#sos-close").addEventListener("click", async () => {
      const sos = getCurrent();
      if (!sos) return;
      if (!confirm("Закрыть SOS?")) return;
      await postJson(`/api/duty/admin/sos/${encodeURIComponent(sos.id)}/close`);
    });

    state.overlay = wrap;
    return wrap;
  }

  function getCurrent() {
    if (state.currentId == null) return null;
    return state.active.get(state.currentId) || null;
  }

  function chooseCurrent() {
    // показываем самый свежий open, иначе acked
    const arr = Array.from(state.active.values());
    if (!arr.length) {
      state.currentId = null;
      if (state.overlay) state.overlay.style.display = "none";
      return;
    }
    const score = (s) => {
      const t = Date.parse(s.created_at || "") || 0;
      const pr = (s.status === "open") ? 2 : (s.status === "acked" ? 1 : 0);
      return pr * 1e15 + t;
    };
    arr.sort((a,b) => score(b)-score(a));
    state.currentId = arr[0].id;
    render(arr[0]);
  }

  function render(sos) {
    if (!sos) return;
    const wrap = ensureOverlay();
    const sub = wrap.querySelector("#sos-sub");
    const body = wrap.querySelector("#sos-body");
    const hint = wrap.querySelector("#sos-hint");

    const unit = sos.unit_label ? `Наряд: <b>${escapeHtml(sos.unit_label)}</b>` : `Пользователь: <b>${escapeHtml(String(sos.user_id))}</b>`;
    const st = sos.status || "open";
    const statusText = st === "acked" ? "✅ Принят" : (st === "closed" ? "🟢 Закрыт" : "🆘 Новый");
    sub.innerHTML = `${unit} · ${statusText} · ${escapeHtml(fmtTime(sos.created_at))}`;

    body.innerHTML = `
      <div><b>Координаты:</b> ${escapeHtml(String(sos.lat))}, ${escapeHtml(String(sos.lon))}</div>
      ${sos.accuracy_m ? `<div><b>Точность:</b> ~${escapeHtml(String(Math.round(sos.accuracy_m)))} м</div>` : ``}
      ${sos.note ? `<div><b>Примечание:</b> ${escapeHtml(String(sos.note))}</div>` : ``}
    `;

    hint.textContent = "Подсказка: если у наряда включён live‑трекинг, его маршрут и стоянки доступны в панели нарядов.";

    // show/hide buttons depending status
    wrap.querySelector("#sos-ack").style.display = (st === "open") ? "" : "none";
    wrap.querySelector("#sos-close").style.display = (st === "closed") ? "none" : "";

    wrap.style.display = "block";
  }

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll("\"", "&quot;")
      .replaceAll("'", "&#039;");
  }

  async function postJson(url, payload) {
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: payload ? JSON.stringify(payload) : "{}",
      });
      const data = await r.json().catch(() => ({}));
      if (data && data.sos) {
        upsert(data.sos);
      }
      return data;
    } catch (e) {
      console.warn("SOS post failed", e);
      return null;
    }
  }

  function panTo(lat, lon) {
    try {
      const m = window.dutyMap || window.map;
      if (!m || typeof m.setView !== "function") return;
      const z = (typeof m.getZoom === "function") ? m.getZoom() : 15;
      m.setView([lat, lon], Math.max(z, 16), { animate: true });

      if (window.L && typeof window.L.marker === "function") {
        const marker = L.marker([lat, lon]).addTo(m);
        setTimeout(() => {
          try { m.removeLayer(marker); } catch (e) {}
        }, 15000);
      }
    } catch (e) {}
  }

  function upsert(sos) {
    if (!sos || !sos.id) return;
    state.active.set(sos.id, sos);
    chooseCurrent();
  }

  function remove(id) {
    if (!id) return;
    state.active.delete(id);
    chooseCurrent();
  }

  async function fetchActive() {
    try {
      const r = await fetch(API_ACTIVE, { headers: { "Accept": "application/json" } });
      if (!r.ok) return;
      const arr = await r.json();
      if (!Array.isArray(arr)) return;
      state.active.clear();
      for (const s of arr) upsert(s);
      chooseCurrent();
    } catch (e) {}
  }

  function setupRealtime() {
    if (!(window.Realtime && typeof window.Realtime.on === 'function')) return;
    try {
      window.Realtime.connect();
      state.connectedOnce = true;

      window.Realtime.on('sos_created', (payload) => { try{ upsert(payload); }catch(e){} });
      window.Realtime.on('sos_acked', (payload) => { try{ upsert(payload); }catch(e){} });
      window.Realtime.on('sos_closed', (payload) => {
        try{
          const id = payload && payload.id ? payload.id : null;
          if(id) remove(id);
          else fetchActive();
        }catch(e){}
      });
    } catch (e) {}
  }

  // init
  fetchActive();
  setupRealtime();
  // фолбэк: периодически подтягиваем активные SOS
  setInterval(fetchActive, 30000);
})();
