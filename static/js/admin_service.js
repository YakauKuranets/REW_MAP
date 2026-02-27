(function () {
  const $ = (sel) => document.querySelector(sel);

  const elRefresh = $("#svc-refresh");
  const elLanBest = $("#lan-best");
  const elLanIps = $("#lan-ips");

  const elAccessEmpty = $("#svc-access-empty");
  const elAccessTable = $("#svc-access-table");
  const elAccessBody = elAccessTable ? elAccessTable.querySelector("tbody") : null;

  const elConnectEmpty = $("#svc-connect-empty");
  const elConnectTable = $("#svc-connect-table");
  const elConnectBody = elConnectTable ? elConnectTable.querySelector("tbody") : null;

  let lan = { ips: [], recommended_base_urls: [], port: null };

  const fmt = (iso) => {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return iso;
      return d.toLocaleString();
    } catch (e) { return iso; }
  };

  const pill = (text, cls) => {
    const span = document.createElement("span");
    span.className = `svc-pill ${cls || ""}`.trim();
    span.textContent = text;
    return span;
  };

  const statusPill = (status) => {
    const s = String(status || "").toLowerCase();
    if (s === "pending") return pill("pending", "svc-pill--pending");
    if (s === "approved") return pill("approved", "svc-pill--approved");
    if (s === "denied") return pill("denied", "svc-pill--denied");
    if (s === "officer") return pill("officer", "svc-pill--officer");
    if (s === "admin") return pill("admin", "svc-pill--admin");
    if (s === "guest") return pill("guest", "svc-pill--guest");
    return pill(s || "—", "");
  };

  const tokenStatePill = (st) => {
    const s = String(st || "");
    if (!s) return pill("—", "");
    if (s === "active") return pill("active", "svc-pill--active");
    if (s === "used") return pill("used", "svc-pill--used");
    if (s === "expired") return pill("expired", "svc-pill--expired");
    if (s === "missing") return pill("missing", "svc-pill--denied");
    return pill(s, "");
  };

  async function apiGet(url) {
    const r = await fetch(url, { credentials: "same-origin" });
    const text = await r.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (e) { data = { _raw: text }; }
    if (!r.ok) throw { status: r.status, data };
    return data;
  }

  async function apiPost(url, payload) {
    const r = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {})
    });
    const text = await r.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (e) { data = { _raw: text }; }
    if (!r.ok) throw { status: r.status, data };
    return data;
  }

  async function loadLan() {
    try {
      const data = await apiGet("/api/system/lan-info");
      lan = data || lan;

      const best = (lan.recommended_base_urls && lan.recommended_base_urls[0]) || "—";
      elLanBest.textContent = best;
      elLanIps.textContent = (lan.ips && lan.ips.length) ? lan.ips.join(", ") : "—";
    } catch (e) {
      elLanBest.textContent = "Ошибка";
      elLanIps.textContent = "—";
    }
  }

  function buildBaseUrlSelect(current) {
    const sel = document.createElement("select");
    sel.className = "input svc-select";

    const opts = [];
    opts.push({ v: "auto", t: "auto" });

    const rec = (lan.recommended_base_urls || []);
    rec.forEach((u) => opts.push({ v: u, t: u }));

    if (current && !opts.some(o => o.v === current)) {
      opts.push({ v: current, t: current });
    }

    // По умолчанию пытаемся выбрать «лучший» (обычно public HTTPS), а не auto
    let defaultVal = (current || "").trim();
    if (!defaultVal || defaultVal.toLowerCase() === "auto") {
      defaultVal = (rec && rec.length ? String(rec[0]) : "auto");
    }

    opts.forEach((o) => {
      const opt = document.createElement("option");
      opt.value = o.v;
      opt.textContent = o.t;
      if (String(defaultVal) === o.v) opt.selected = true;
      sel.appendChild(opt);
    });

    return sel;
  }

  async function loadServiceAccessPending() {
    if (!elAccessBody) return;
    elAccessTable.style.display = "none";
    elAccessEmpty.style.display = "block";
    elAccessEmpty.textContent = "Загрузка…";

    try {
      const data = await apiGet("/api/service/access/admin/pending");
      const items = (data && data.items) ? data.items : [];
      elAccessBody.innerHTML = "";

      if (!items.length) {
        elAccessEmpty.textContent = "Нет заявок.";
        return;
      }

      elAccessEmpty.style.display = "none";
      elAccessTable.style.display = "table";

      items.forEach((it) => {
        const tr = document.createElement("tr");

        const tdId = document.createElement("td");
        tdId.className = "svc-mono";
        tdId.textContent = it.tg_user_id || "—";

        const tdStatus = document.createElement("td");
        tdStatus.appendChild(statusPill(it.status || "pending"));

        const tdNote = document.createElement("td");
        tdNote.textContent = it.note || "—";

        const tdAt = document.createElement("td");
        tdAt.textContent = fmt(it.requested_at || it.created_at);

        const tdAct = document.createElement("td");
        tdAct.className = "svc-actions";

        const btnApprove = document.createElement("button");
        btnApprove.className = "btn";
        btnApprove.textContent = "Approve";
        btnApprove.onclick = async () => {
          btnApprove.disabled = true;
          try {
            await apiPost("/api/service/access/admin/approve", { tg_user_id: it.tg_user_id });
            await refreshAll();
          } catch (e) {
            alert("Ошибка approve: " + (e.data && JSON.stringify(e.data)));
          } finally {
            btnApprove.disabled = false;
          }
        };

        const btnDeny = document.createElement("button");
        btnDeny.className = "btn btn--danger";
        btnDeny.textContent = "Deny";
        btnDeny.onclick = async () => {
          btnDeny.disabled = true;
          try {
            await apiPost("/api/service/access/admin/deny", { tg_user_id: it.tg_user_id });
            await refreshAll();
          } catch (e) {
            alert("Ошибка deny: " + (e.data && JSON.stringify(e.data)));
          } finally {
            btnDeny.disabled = false;
          }
        };

        tdAct.appendChild(btnApprove);
        tdAct.appendChild(btnDeny);

        tr.appendChild(tdId);
        tr.appendChild(tdStatus);
        tr.appendChild(tdNote);
        tr.appendChild(tdAt);
        tr.appendChild(tdAct);

        elAccessBody.appendChild(tr);
      });

    } catch (e) {
      elAccessEmpty.textContent = "Ошибка загрузки.";
    }
  }

  async function loadConnectPending() {
    if (!elConnectBody) return;
    elConnectTable.style.display = "none";
    elConnectEmpty.style.display = "block";
    elConnectEmpty.textContent = "Загрузка…";

    try {
      const items = await apiGet("/api/mobile/connect/admin/pending");
      elConnectBody.innerHTML = "";

      if (!items || !items.length) {
        elConnectEmpty.textContent = "Нет заявок.";
        return;
      }

      elConnectEmpty.style.display = "none";
      elConnectTable.style.display = "table";

      items.forEach((it) => {
        const tr = document.createElement("tr");

        const tdId = document.createElement("td");
        tdId.className = "svc-mono";
        tdId.textContent = it.tg_user_id || "—";

        const tdStatus = document.createElement("td");
        tdStatus.appendChild(statusPill(it.status || "pending"));

        const tdBase = document.createElement("td");
        const sel = buildBaseUrlSelect(it.base_url || "auto");
        tdBase.appendChild(sel);

        const tdToken = document.createElement("td");
        const state = tokenStatePill(it.last_token_state);
        tdToken.appendChild(state);
        const small = document.createElement("div");
        small.className = "muted";
        small.style.fontSize = "12px";
        small.textContent = it.last_pair_code ? ("pair: " + it.last_pair_code) : "—";
        tdToken.appendChild(small);

        const tdSend = document.createElement("td");
        const sendLine = document.createElement("div");
        sendLine.textContent = it.last_sent_at ? ("sent: " + fmt(it.last_sent_at)) : "—";
        const err = document.createElement("div");
        err.className = "muted";
        err.style.fontSize = "12px";
        err.textContent = it.last_send_error ? ("err: " + it.last_send_error) : "";
        tdSend.appendChild(sendLine);
        tdSend.appendChild(err);

        const tdAct = document.createElement("td");
        tdAct.className = "svc-actions";

        const btnApprove = document.createElement("button");
        btnApprove.className = "btn";
        btnApprove.textContent = "Approve";
        btnApprove.onclick = async () => {
          btnApprove.disabled = true;
          try {
            const payload = { tg_user_id: it.tg_user_id };
            const v = (sel && sel.value) ? String(sel.value).trim() : "";
            // Не отправляем "auto" как строку - сервер сам выберет BOOTSTRAP_PREFERRED_BASE_URL / current_origin
            if (v && v.toLowerCase() !== "auto") payload.base_url = v;

            const r = await apiPost("/api/mobile/connect/admin/approve", payload);
            if (r && r.send_ok === false) {
              const req = r.request || {};
              const msg = [
                "Не удалось отправить в Telegram.",
                (r.send_error ? ("Причина: " + r.send_error) : ""),
                (req.base_url ? ("BASE_URL: " + req.base_url) : ""),
                (req.last_pair_code ? ("PAIR: " + req.last_pair_code) : ""),
              ].filter(Boolean).join("\n");
              alert(msg);
            }
            await refreshAll();
          } catch (e) {
            alert("Ошибка approve: " + (e.data && JSON.stringify(e.data)));
          } finally { btnApprove.disabled = false; }
        };

        const btnDeny = document.createElement("button");
        btnDeny.className = "btn btn--danger";
        btnDeny.textContent = "Deny";
        btnDeny.onclick = async () => {
          btnDeny.disabled = true;
          try {
            await apiPost("/api/mobile/connect/admin/deny", { tg_user_id: it.tg_user_id });
            await refreshAll();
          } catch (e) {
            alert("Ошибка deny: " + (e.data && JSON.stringify(e.data)));
          } finally { btnDeny.disabled = false; }
        };

        const btnReset = document.createElement("button");
        btnReset.className = "btn";
        btnReset.textContent = "Reset";
        btnReset.onclick = async () => {
          btnReset.disabled = true;
          try {
            await apiPost("/api/mobile/connect/admin/reset", { tg_user_id: it.tg_user_id });
            await refreshAll();
          } catch (e) {
            alert("Ошибка reset: " + (e.data && JSON.stringify(e.data)));
          } finally { btnReset.disabled = false; }
        };

        tdAct.appendChild(btnApprove);
        tdAct.appendChild(btnDeny);
        tdAct.appendChild(btnReset);

        tr.appendChild(tdId);
        tr.appendChild(tdStatus);
        tr.appendChild(tdBase);
        tr.appendChild(tdToken);
        tr.appendChild(tdSend);
        tr.appendChild(tdAct);

        elConnectBody.appendChild(tr);
      });

    } catch (e) {
      elConnectEmpty.textContent = "Ошибка загрузки.";
    }
  }

  async function refreshAll() {
    await loadLan();
    await loadServiceAccessPending();
    await loadConnectPending();
  }

  if (elRefresh) elRefresh.onclick = () => refreshAll();

  // auto refresh
  refreshAll();
  setInterval(() => refreshAll(), 7000);
})();
