/* ========= Persist filters & settings ========= */
(function() {
  function initPersistentFilters() {
      function lsGet(k){ try { return localStorage.getItem(k); } catch(_){ return null; } }
      function lsSet(k,v){ try { localStorage.setItem(k, v); } catch(_){} }

      // Категория
      const catSel = document.getElementById('filter-category');
      if (catSel) {
        const saved = lsGet('filter-category');
        if (saved !== null) { catSel.value = saved; try { catSel.dispatchEvent(new Event('change')); } catch(_){} }
        catSel.addEventListener('change', () => {
          lsSet('filter-category', catSel.value || '');
        });
      }
      // Тип доступа (лок/удал)
      const optLocal  = document.getElementById('opt-local');
      const optRemote = document.getElementById('opt-remote');
      const writeAccess = () => {
        lsSet('access-local',  optLocal  && optLocal.checked  ? '1' : '0');
        lsSet('access-remote', optRemote && optRemote.checked ? '1' : '0');
      };
      if (optLocal) {
        const s = lsGet('access-local');  if (s !== null) optLocal.checked = (s === '1');
        optLocal.addEventListener('change', () => { writeAccess(); try { optLocal.dispatchEvent(new Event('input')); } catch(_){} });
      }
      if (optRemote) {
        const s = lsGet('access-remote'); if (s !== null) optRemote.checked = (s === '1');
        optRemote.addEventListener('change', () => { writeAccess(); try { optRemote.dispatchEvent(new Event('input')); } catch(_){} });
      }
  }

  document.addEventListener('DOMContentLoaded', () => {
    try {
      initPersistentFilters();
    } catch (err) {
      console.warn('initPersistentFilters failed', err);
    }
  });
})();
