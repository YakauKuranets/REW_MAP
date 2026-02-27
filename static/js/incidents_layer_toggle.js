/* incidents_layer_toggle.js

UI‑тоггл для слоя «Инциденты» на карте.

- хранит состояние в localStorage
- шлёт событие window 'incidents-layer:toggle'
- при наличии window.IncidentsOverlay напрямую включает/выключает

Идея простая: кнопка должна работать даже если половина интерфейса
отвалилась.
*/

(function(){
  'use strict';

  const LS_KEY = 'incidents_layer_enabled';

  function getBool(key, defVal){
    try{
      const v = localStorage.getItem(key);
      if(v === null || v === undefined) return defVal;
      return v === '1' || v === 'true' || v === 'yes';
    }catch(e){
      return defVal;
    }
  }

  function setBool(key, val){
    try{
      localStorage.setItem(key, val ? '1' : '0');
    }catch(e){
      // ignore
    }
  }

  function setBtnState(btn, enabled){
    if(!btn) return;
    btn.classList.toggle('primary', !!enabled);
    btn.classList.toggle('is-on', !!enabled);
    btn.setAttribute('aria-pressed', enabled ? 'true' : 'false');
    btn.title = enabled ? 'Инциденты: слой включён' : 'Инциденты: слой выключен';
  }

  function broadcast(enabled){
    try{
      window.dispatchEvent(new CustomEvent('incidents-layer:toggle', { detail: { enabled: !!enabled } }));
    }catch(e){
      // CustomEvent might be blocked in some weird environments
    }
    if(window.IncidentsOverlay && typeof window.IncidentsOverlay.setEnabled === 'function'){
      try{ window.IncidentsOverlay.setEnabled(!!enabled); }catch(e){}
    }
  }

  function init(){
    const btn = document.getElementById('btn-incidents-layer');
    if(!btn) return;

    let enabled = getBool(LS_KEY, false);
    setBtnState(btn, enabled);

    btn.addEventListener('click', (ev) => {
      ev.preventDefault();
      enabled = !enabled;
      setBool(LS_KEY, enabled);
      setBtnState(btn, enabled);
      broadcast(enabled);
    });

    // если оверлей подгрузился позже, он подхватит состояние.
    broadcast(enabled);
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init);
  }else{
    init();
  }
})();
