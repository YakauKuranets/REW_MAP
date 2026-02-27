/* ========= Унифицированные уведомления ========= */
/**
 * Этот модуль определяет объект notify с методами success/error/info,
 * обёртывающими вызов showToast из ui.js. Такой подход позволяет
 * стандартизировать вывод уведомлений и в дальнейшем легко заменить
 * механизм (например, на библиотеку toastify) без правки каждой функции.
 */
(function() {
  function callToast(message, type) {
    if (window.showToast) {
      window.showToast(message, type);
    } else {
      // Фолбэк на alert, если showToast не загружен
      alert(message);
    }
  }
  const notify = {
    success(msg) { callToast(msg, 'success'); },
    error(msg)   { callToast(msg, 'error'); },
    info(msg)    { callToast(msg, 'default'); }
  };
  window.notify = notify;
})();