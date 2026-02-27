/* objects_layer_toggle.js

UI‑тоггл для слоя «Объекты» на карте.

- хранит состояние в localStorage
- шлёт событие window 'objects-layer:toggle'
- при наличии window.ObjectsOverlay напрямую включает/выключает
*/

(function(){
  'use strict';

  const LS_KEY = 'objects_layer_enabled';

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
    try{ localStorage.setItem(key, val ? '1' : '0'); }catch(e){}
  }

  function setBtnState(btn, enabled){
    if(!btn) return;
    btn.classList.toggle('primary', !!enabled);
    btn.classList.toggle('is-on', !!enabled);
    btn.setAttribute('aria-pressed', enabled ? 'true' : 'false');
    btn.title = enabled ? 'Объекты: слой включён' : 'Объекты: слой выключен';
  }

  function broadcast(enabled){
    try{
      window.dispatchEvent(new CustomEvent('objects-layer:toggle', { detail: { enabled: !!enabled } }));
    }catch(e){}
    if(window.ObjectsOverlay && typeof window.ObjectsOverlay.setEnabled === 'function'){
      try{ window.ObjectsOverlay.setEnabled(!!enabled); }catch(e){}
    }
  }

  function init(){
    const btn = document.getElementById('btn-objects-layer');
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

    broadcast(enabled);
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init);
  }else{
    init();
  }
})();
