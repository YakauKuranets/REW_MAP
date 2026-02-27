/* ========= Search & autocomplete module ========= */
/**
 * Модуль отвечает за:
 *  - автодополнение поля поиска по адресу (#search)
 *  - выпадение подсказок (#search-suggestions)
 *
 * Не зависит от main.js, кроме того, что использует глобальную карту `map`
 * (создана в map_core.js) и стандартный fetch API.
 */
(function() {
  function debounce(fn, ms) {
    let t;
    return function(...args) {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(this, args), ms);
    };
  }

  function autocompleteSearch() {
    const searchEl = document.getElementById('search');
    const sugg = document.getElementById('search-suggestions');
    if (!searchEl || !sugg) return;
    const q = (searchEl.value || '').trim();
    if (q.length < 3) { sugg.style.display = 'none'; return; }
    fetch(`/api/geocode?q=${encodeURIComponent(q)}&limit=5`)
      .then(res => res.ok ? res.json() : [])
      .then(arr => {
        sugg.innerHTML = '';
        arr.forEach(item => {
          const li = document.createElement('li');
          li.textContent = item.display_name || '';
          li.onclick = () => {
            searchEl.value = item.display_name;
            sugg.style.display = 'none';
            try {
              const lat = parseFloat(item.lat);
              const lon = parseFloat(item.lon);
              if (!isNaN(lat) && !isNaN(lon) && window.map) {
                window.map.setView([lat, lon], 16);
              }
            } catch (_) {}
          };
          sugg.appendChild(li);
        });
        const rect = searchEl.getBoundingClientRect();
        sugg.style.left = `${rect.left + window.pageXOffset}px`;
        sugg.style.top = `${rect.bottom + window.pageYOffset + 2}px`;
        sugg.style.width = `${rect.width}px`;
        sugg.style.display = arr.length ? 'block' : 'none';
      })
      .catch(() => { sugg.style.display = 'none'; });
  }

  function bindSearchUI() {
    const searchEl = document.getElementById('search');
    if (searchEl) {
      const debouncedAuto = debounce(() => { try { autocompleteSearch(); } catch (_) {} }, 300);
      const debouncedList = debounce(() => {
        try {
          if (typeof window.refreshList === 'function') window.refreshList();
        } catch (err) { console.warn('refreshList failed', err); }
      }, 250);
      searchEl.addEventListener('input', () => { debouncedAuto(); debouncedList(); });
}

    // Клик вне подсказок — закрываем список
    document.addEventListener('click', (ev) => {
      const sugg = document.getElementById('search-suggestions');
      const search = document.getElementById('search');
      if (!sugg || !search) return;
      if (sugg.contains(ev.target) || search.contains(ev.target)) return;
      sugg.style.display = 'none';
    });
  }

  // Экспортируем функцию на всякий случай (если захочется переиспользовать)
  window.autocompleteSearch = autocompleteSearch;

  document.addEventListener('DOMContentLoaded', () => {
    try {
      bindSearchUI();
    } catch (err) {
      console.warn('Failed to init search UI', err);
    }
  });
})();
