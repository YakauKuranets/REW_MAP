// Дополнительные клиентские функции для Map v12
// Этот файл реализует автодополнение поиска и модальное окно аналитики.

// Дожидаемся полной загрузки документа, чтобы привязать UI
document.addEventListener('DOMContentLoaded', () => {
  try {
    bindAnalyticsUI();
    bindSearchAutocomplete();
    // Перехватываем applyRole для отображения кнопки аналитики только администратору
    if (typeof window.applyRole === 'function') {
      const originalApplyRole = window.applyRole;
      window.applyRole = function(role) {
        originalApplyRole(role);
        const btnAnalytics = document.getElementById('btn-analytics');
        if (btnAnalytics) {
          btnAnalytics.style.display = (role === 'admin') ? '' : 'none';
        }
      };
    }
  } catch (err) {
    console.warn('Failed to init extra UI', err);
  }
});

/**
 * Инициализация UI аналитики.
 * Создаёт обработчики для кнопки аналитики и загружает данные по запросу.
 */
function bindAnalyticsUI() {
  const btnAnalytics = document.getElementById('btn-analytics');
  const analyticsBackdrop = document.getElementById('analytics-backdrop');
  const analyticsClose = document.getElementById('analytics-close');
  const analyticsSummary = document.getElementById('analytics-summary');
  const chartCanvas = document.getElementById('analytics-chart');
  let chart = null;

  async function loadAnalytics() {
    if (!analyticsSummary || !chartCanvas) return;
    analyticsSummary.innerHTML = 'Загрузка…';
    try {
      const resp = await fetch('/api/analytics/summary');
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const data = await resp.json();
      // Заполняем сводные числа
      analyticsSummary.innerHTML = `\n        <p><strong>Всего объектов:</strong> ${data.total}</p>\n        <p><strong>Активных заявок:</strong> ${data.pending}</p>\n        <p><strong>Одобренных:</strong> ${data.approved}</p>\n        <p><strong>Отклонённых:</strong> ${data.rejected}</p>\n        <p><strong>Добавлено за 7 дней:</strong> ${data.added_last_7d}</p>\n      `;
      // Данные для графика: категории и статусы
      const categoryLabels = Object.keys(data.by_category || {});
      const categoryValues = categoryLabels.map(k => data.by_category[k]);
      const statusLabels = Object.keys(data.by_status || {});
      const statusValues = statusLabels.map(k => data.by_status[k]);
      const datasets = [];
      if (categoryLabels.length) {
        datasets.push({ label: 'Категории', data: categoryValues, backgroundColor: '#4a90e2' });
      }
      if (statusLabels.length) {
        datasets.push({ label: 'Статусы', data: statusValues, backgroundColor: '#50e3c2' });
      }
      if (chart) chart.destroy();
      const ctx = chartCanvas.getContext('2d');
      chart = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: categoryLabels.length ? categoryLabels : statusLabels,
          datasets: datasets,
        },
        options: {
          responsive: true,
          scales: { y: { beginAtZero: true } },
        },
      });
    } catch (err) {
      analyticsSummary.innerHTML = '<p>Не удалось загрузить данные</p>';
    }
  }

  if (btnAnalytics) {
    btnAnalytics.addEventListener('click', () => {
      if (analyticsBackdrop) {
        analyticsBackdrop.classList.add('open');
        loadAnalytics();
      }
    });
  }
  if (analyticsClose) {
    analyticsClose.addEventListener('click', () => {
      if (analyticsBackdrop) analyticsBackdrop.classList.remove('open');
    });
  }
}

/**
 * Подключить автодополнение для поля поиска.
 * Делает запросы к /api/geocode и отображает результаты под полем.
 */
function bindSearchAutocomplete() {
  const input = document.getElementById('search');
  const sugg = document.getElementById('search-suggestions');
  if (!input || !sugg) return;
  let timer = null;
  input.addEventListener('input', () => {
    const q = input.value.trim();
    if (timer) clearTimeout(timer);
    if (!q) {
      sugg.innerHTML = '';
      sugg.style.display = 'none';
      return;
    }
    timer = setTimeout(() => {
      fetch('/api/geocode?q=' + encodeURIComponent(q) + '&limit=5')
        .then(r => (r.ok ? r.json() : []))
        .then(list => {
          sugg.innerHTML = '';
          if (!list || !Array.isArray(list) || list.length === 0) {
            sugg.style.display = 'none';
            return;
          }
          list.forEach(item => {
            const li = document.createElement('li');
            li.textContent = item.display_name || '';
            li.addEventListener('click', () => {
              input.value = item.display_name || '';
              sugg.innerHTML = '';
              sugg.style.display = 'none';
            });
            sugg.appendChild(li);
          });
          sugg.style.display = '';
        })
        .catch(() => {
          sugg.innerHTML = '';
          sugg.style.display = 'none';
        });
    }, 300);
  });
  document.addEventListener('click', ev => {
    if (!sugg.contains(ev.target) && ev.target !== input) {
      sugg.innerHTML = '';
      sugg.style.display = 'none';
    }
  });
}