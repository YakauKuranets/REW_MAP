/* ========= Realtime client (WebSocket) ========= */
/*
  Единый клиент для WS-событий (chat/pending/duty/tracker/sos).

  - Получает короткоживущий токен через /api/realtime/token (только admin)
  - Подключается к WS (same-port / отдельный порт) с фолбэками
  - Автопереподключение с backoff
  - Раздаёт события подписчикам: Realtime.on('event', fn)

  Формат входящего сообщения:
    {"event":"name","data":{...}}
*/
(function(){
  const listeners = new Map();   // event -> Set(fn)
  const anyListeners = new Set();// Set(fn(event, data))
  let ws = null;
  let connecting = false;
  let backoffMs = 1000;
  let closedByUser = false;
  let pingTimer = null;
  const PING_MS = 25000;

  function _emit(event, data){
    try{
      const set = listeners.get(event);
      if(set){
        for(const fn of Array.from(set)){
          try{ fn(data, event); }catch(e){}
        }
      }
      for(const fn of Array.from(anyListeners)){
        try{ fn(event, data); }catch(e){}
      }
    }catch(e){}
  }

  function on(event, fn){
    if(!event || typeof fn !== 'function'){
      return function(){};
    }
    let set = listeners.get(event);
    if(!set){
      set = new Set();
      listeners.set(event, set);
    }
    set.add(fn);
    return function(){
      try{ set.delete(fn); }catch(e){}
    };
  }

  function onAny(fn){
    if(typeof fn !== 'function') return function(){};
    anyListeners.add(fn);
    return function(){
      anyListeners.delete(fn);
    };
  }

  async function _fetchTokenUrls(){
    try{
      const r = await fetch('/api/realtime/token', { credentials: 'same-origin' });
      if(!r || !r.ok) throw new Error('HTTP ' + (r ? r.status : ''));
      const j = await r.json();
      const urls = [];
      if(j && j.ws_url_sameport) urls.push(j.ws_url_sameport);
      if(j && j.ws_url_port) urls.push(j.ws_url_port);

      // legacy fallback derived from token (if server publishes only token)
      if(j && j.token){
        const wsProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = location.hostname;
        urls.push(`${wsProtocol}//${host}:8765/ws?token=${encodeURIComponent(j.token)}`);
      }

      // uniq
      const uniq = [];
      for(const u of urls){
        if(!u) continue;
        if(uniq.indexOf(u) === -1) uniq.push(u);
      }
      return { urls: uniq, expiresIn: Number(j && j.expires_in ? j.expires_in : 0) };
    }catch(e){
      return { urls: [], expiresIn: 0, error: e };
    }
  }

  function _cleanupSocket(){
    try{
      if(ws){
        ws.onopen = ws.onmessage = ws.onerror = ws.onclose = null;
        ws.close();
      }
    }catch(e){}
    try{ if(pingTimer){ clearInterval(pingTimer); } }catch(e){}
    pingTimer = null;
    ws = null;
  }

  function _scheduleReconnect(){
    if(closedByUser) return;
    const delay = Math.min(backoffMs, 30000);
    backoffMs = Math.min(Math.floor(backoffMs * 1.6 + 250), 30000);
    setTimeout(function(){
      if(closedByUser) return;
      connect();
    }, delay);
  }

  function _tryConnectUrls(urls, idx){
    if(closedByUser) return;
    if(!urls || idx >= urls.length){
      connecting = false;
      _scheduleReconnect();
      return;
    }

    let opened = false;
    let sock = null;

    try{
      sock = new WebSocket(urls[idx]);
    }catch(e){
      return _tryConnectUrls(urls, idx + 1);
    }

    sock.addEventListener('open', function(){
      opened = true;
      ws = sock;
      connecting = false;
      backoffMs = 1000;
      _emit('__open__', { url: urls[idx] });

      // keepalive: Cloudflare/proxies may drop totally-idle WS.
      try{
        if(pingTimer) clearInterval(pingTimer);
        pingTimer = setInterval(function(){
          try{
            if(ws && ws.readyState === 1) ws.send('ping');
          }catch(e){}
        }, PING_MS);
      }catch(e){}
    });

    sock.addEventListener('message', function(ev){
      try{
        const msg = JSON.parse(ev && ev.data ? ev.data : '{}');
        if(!msg || !msg.event) return;
        _emit(String(msg.event), msg.data || {});
      }catch(e){}
    });

    sock.addEventListener('close', function(){
      if(!opened){
        try{ sock.close(); }catch(e){}
        return _tryConnectUrls(urls, idx + 1);
      }
      _emit('__close__', {});
      _cleanupSocket();
      connecting = false;
      _scheduleReconnect();
    });

    sock.addEventListener('error', function(){
      if(!opened){
        try{ sock.close(); }catch(e){}
        return _tryConnectUrls(urls, idx + 1);
      }
    });
  }

  async function connect(){
    if(closedByUser) return;
    if(ws && ws.readyState === 1) return;
    if(connecting) return;

    connecting = true;
    const tok = await _fetchTokenUrls();
    const urls = tok.urls || [];

    if(!urls.length){
      connecting = false;
      return; // not admin / realtime disabled / server not ready
    }

    _tryConnectUrls(urls, 0);
  }

  function disconnect(){
    closedByUser = true;
    connecting = false;
    _cleanupSocket();
  }

  function isConnected(){
    return !!(ws && ws.readyState === 1);
  }

  async function refreshCounters(){
    try{
      const r = await fetch('/api/notifications/counters', { credentials: 'same-origin' });
      if(!r.ok) return;
      const d = await r.json();

      const reqCount = Number((d && d.requests != null) ? d.requests : (d && d.pending) ? d.pending : 0);
      const chatUnread = Number((d && d.chat_unread) ? d.chat_unread : 0);

      // badge on map page
      const b = document.getElementById('notif-count');
      if(b){
        if(reqCount > 0){
          b.textContent = String(reqCount);
          b.classList.remove('hidden');
        }else{
          b.textContent = '0';
          b.classList.add('hidden');
        }
      }

      // chat badge on map page
      const root = document.getElementById('chat-react-root');
      if(root){
        if(chatUnread > 0){
          const label = chatUnread > 99 ? '99+' : String(chatUnread);
          root.textContent = 'новых: ' + label;
          root.classList.add('has-unread');
        }else{
          root.textContent = '';
          root.classList.remove('has-unread');
        }
      }
    }catch(e){}
  }

  function debounce(fn, ms){
    let t = null;
    return function(){
      const args = arguments;
      clearTimeout(t);
      t = setTimeout(function(){ fn.apply(null, args); }, ms || 250);
    };
  }

  window.Realtime = window.Realtime || {
    connect,
    disconnect,
    on,
    onAny,
    isConnected,
    refreshCounters,
    debounce
  };

  // auto-connect
  if(document.readyState === 'complete' || document.readyState === 'interactive'){
    setTimeout(connect, 0);
  }else{
    document.addEventListener('DOMContentLoaded', function(){ connect(); });
  }
})();
