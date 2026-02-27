/* ========= Persist filters & settings ========= */
(function() {
  function initPersistentFilters() {
      // Категория
      const catSel = document.getElementById('filter-category');
      if (catSel) {
        const saved = localStorage.getItem('filter-category');
        if (saved !== null) { catSel.value = saved; try { catSel.dispatchEvent(new Event('change')); } catch(_){} }
        catSel.addEventListener('change', () => {
          localStorage.setItem('filter-category', catSel.value || '');
        });
      }
      // Тип доступа (лок/удал)
      const optLocal  = document.getElementById('opt-local');
      const optRemote = document.getElementById('opt-remote');
      const writeAccess = () => {
        localStorage.setItem('access-local',  optLocal  && optLocal.checked  ? '1' : '0');
        localStorage.setItem('access-remote', optRemote && optRemote.checked ? '1' : '0');
      };
      if (optLocal) {
        const s = localStorage.getItem('access-local');  if (s !== null) optLocal.checked = (s === '1');
        optLocal.addEventListener('change', () => { writeAccess(); try { optLocal.dispatchEvent(new Event('input')); } catch(_){} });
      }
      if (optRemote) {
        const s = localStorage.getItem('access-remote'); if (s !== null) optRemote.checked = (s === '1');
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
