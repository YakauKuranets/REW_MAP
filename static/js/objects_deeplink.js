/* objects_deeplink.js

Поддержка deep-link'ов из /admin/objects в карту:
  /admin/panel?focus_object=<id>
  /admin/panel?edit_object=<id>

Поведение:
  - focus_object: центрирует карту на объекте и (по возможности) подсвечивает.
  - edit_object: открывает модалку редактирования ObjectsUI.openEdit(id).

Должен грузиться ПОСЛЕ leaflet + objects_ui.js.
*/

(function(){
  'use strict';

  function getMap(){
    return window.map || window.dutyMap || null;
  }

  function sleep(ms){ return new Promise(r => setTimeout(r, ms)); }

  async function waitFor(cond, tries, ms){
    for(let i=0;i<tries;i++){
      try{ if(cond()) return true; }catch(_){ }
      await sleep(ms);
    }
    return false;
  }

  async function fetchObj(id){
    const r = await fetch(`/api/objects/${encodeURIComponent(id)}`, { credentials: 'include' });
    if(!r.ok) throw new Error('HTTP '+r.status);
    return await r.json();
  }

  async function focusObject(id){
    await waitFor(()=>!!getMap(), 40, 150);
    const map = getMap();
    if(!map) return;

    try{
      const obj = await fetchObj(id);
      if(obj && obj.lat != null && obj.lon != null){
        const z = Math.max(map.getZoom ? map.getZoom() : 0, 16);
        map.setView([obj.lat, obj.lon], z, { animate: true });
      }
    }catch(e){
      try{ console.warn('focus_object failed', e); }catch(_){ }
    }
  }

  async function editObject(id){
    // wait for ObjectsUI
    await waitFor(()=>window.ObjectsUI && typeof window.ObjectsUI.openEdit === 'function', 60, 150);
    try{ window.ObjectsUI.openEdit(Number(id)); }catch(e){ try{ console.warn('edit_object failed', e); }catch(_){ } }
  }

  async function main(){
    const p = new URLSearchParams(window.location.search || '');
    const focusId = p.get('focus_object');
    const editId = p.get('edit_object');

    if(editId){
      await editObject(editId);
      return;
    }
    if(focusId){
      await focusObject(focusId);
    }
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', main);
  }else{
    main();
  }
})();
