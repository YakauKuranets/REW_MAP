/* ========= i18n (RU/EN) =========
 * - Default: RU
 * - Storage: localStorage.ui_lang
 * - API: window.i18n.getLang(), setLang(lang), t(key, vars), trStatusRuEn(), trCategoryRuEn()
 */
(function(){
  const LS_KEY = 'ui_lang';
  const SUPPORTED = ['ru','en'];

  const dict = {
    ru: {
      // Command Center
      cc_title: 'Командный центр — Map v12',
      cc_brand: 'Командный центр',
      cc_server_time: 'время сервера:',
      cc_search_ph: 'Поиск: наряд / TG ID / заявка #…',
      cc_btn_find: 'Найти',
      cc_btn_panel: 'Панель',
      cc_btn_code: 'Код',
      cc_btn_chat: 'Чат',
      cc_btn_service: 'Служба',
      cc_btn_map: 'Карта',
      cc_btn_devices: 'Устройства',
      cc_btn_problems: 'Проблемы',
      cc_btn_metrics: 'Метрики',
      cc_btn_duty: 'Дежурства',

      cc_kpi_shifts: 'Наряды',
      cc_kpi_live: 'В эфире',
      cc_kpi_breaks: 'Обеды',
      cc_kpi_problems: 'Проблемы',
      cc_kpi_sos: 'SOS',
      cc_kpi_stale: 'Нет связи',
      cc_kpi_acc: 'Точность',
      cc_kpi_queue: 'Очередь',

      cc_qf_all: 'Все',
      cc_qf_live: 'В эфире',
      cc_qf_problems: 'Проблемы',
      cc_qf_sos: 'SOS',
      cc_qf_stale: 'Нет связи',
      cc_qf_revoked: 'Отозвано',

      cc_status_sos: 'SOS',
      cc_status_crit: 'КРИТ',
      cc_status_stale: 'НЕТ СВЯЗИ',
      cc_status_warn: 'ПРОБЛЕМА',
      cc_status_ok: 'В ЭФИРЕ',
      cc_status_idle: 'НЕ В ЭФИРЕ',
      cc_status_ended: 'КОНЕЦ СЛУЖБЫ',
      cc_status_revoked: 'ОТОЗВАНО',

      cc_legend_title: 'Легенда',
      cc_legend_live: 'В эфире',
      cc_legend_idle: 'Не в эфире',
      cc_legend_problem_stale: 'Проблема / нет связи',
      cc_legend_sos: 'SOS',
      cc_legend_revoked: 'Отозвано',
      cc_legend_hint: 'Клик по точке открывает карточку наряда.',

      cc_critical_now: 'Критично сейчас',
      cc_btn_open: 'Открыть',
      cc_last_prefix: 'посл.:',

      cc_quality_5m_prefix: '5м',
      cc_quality_pts: 'точек',
      cc_quality_avg: 'ср.',
      cc_quality_jumps: 'скачков',

      cc_sidebar_active: 'Активные наряды',
      cc_flt_live: 'только в эфире',
      cc_flt_break: 'с обедом',
      cc_flt_sos: 'с SOS',
      cc_flt_stale: 'нет обновлений > 5 мин',
      cc_loading: 'Загрузка…',
      cc_none: '—',
      cc_sidebar_breaks: 'Обеды',
      cc_sidebar_sos: 'SOS',
      cc_sidebar_sos_hint: 'Новые SOS всплывают поверх экрана. Клик по записи — фокус на карте.',
      cc_sidebar_pending: 'Заявки (pending)',
      cc_sidebar_pending_hint: 'Совет: одобрение сразу создаёт метку на основной карте.',
      cc_sidebar_tips: 'Быстрые подсказки',

      cc_tab_overview: 'Обзор',
      cc_tab_track: 'Маршрут',
      cc_tab_journal: 'Журнал',

      cc_box_shift_start: 'Старт смены',
      cc_box_last_update: 'Последнее обновление',
      cc_box_tracking_status: 'Статус трекинга',
      cc_box_accuracy_last: 'Точность (последняя)',
      cc_box_speed_last: 'Скорость (последняя)',
      cc_box_kpi_5m: 'KPI за 5 минут',
      cc_box_coords_last: 'Координаты (последняя точка)',
      cc_box_positioning: 'Позиционирование',
      cc_pos_source: 'Источник',
      cc_pos_conf: 'Доверие',
      cc_pos_details: 'Детали',
      cc_tip_live: 'в эфире',
      cc_tip_idle: 'не в эфире',
      cc_tip_est: 'оценка',
      cc_tip_gnss: 'GNSS',
      cc_pos_method_tile: 'радио‑карта',
      cc_pos_method_anchor: 'якоря',
      cc_box_health: 'Устройство (health)',

      cc_break_title: 'Обед',
      cc_break_status_requested: 'запрошен',
      cc_break_status_approved: 'одобрен',
      cc_break_status_started: 'идёт',
      cc_break_status_due: 'время вышло',
      cc_break_status_ended: 'завершён',

      cc_sos_active: 'SOS активен',
      cc_sos_status_open: 'открыт',
      cc_sos_status_acked: 'принят',
      cc_sos_status_closed: 'закрыт',

      cc_actions_quick: 'Быстрые действия',
      cc_action_show: 'Показать',
      cc_action_track: 'Маршрут',
      cc_action_copy: 'Копировать',
      cc_action_device: 'Устройство',
      cc_action_journal: 'Журнал',
      cc_action_card: 'Карточка',
      cc_action_write: 'Написать',
      cc_action_dismiss: 'Убрать',
      cc_shift_hash: 'наряд #',
      cc_start_short: 'старт',
      cc_critical_now: 'Критично сейчас',
      cc_last_prefix: 'посл.:',

      cc_last_point: 'последняя точка',
      cc_update_age: 'обновление',
      cc_phone_line_prefix: 'телефон',

      cc_recs_lbl: 'Что исправить',

      cc_toast_open_shift_failed: 'Не удалось открыть карточку: {status}',
      cc_toast_track_load_failed: 'Не удалось загрузить трек: {status}',
      cc_toast_no_last_coord: 'Нет последней координаты',
      cc_toast_chat_not_ready: 'Чат ещё не готов',
      cc_toast_copied: 'Координаты скопированы',
      cc_toast_copy_failed: 'Не удалось скопировать',
      cc_toast_no_coords_for: 'Нет координат у: {title}',
      cc_toast_chat_not_inited: 'Чат ещё не инициализировался',
      cc_toast_pending_new: '🔔 Новая заявка #{id}',
      cc_toast_break_due: '⏱ Время обеда истекло у TG {user_id}',

      // Map page
      map_title: 'Map v12 — онлайн + офлайн',
      map_search_ph: 'Поиск…',
      map_access_btn: 'Тип доступа',
      map_btn_add: 'Добавить',
      map_btn_data: 'Данные',
      map_btn_delete_selected: 'Удалить выбранное',
      map_btn_lang: 'RU',
      map_btn_theme_dark: 'Тема: тёмная',
      map_btn_theme_light: 'Тема: светлая',

      map_cat_all: 'Все категории',
      map_cat_video: 'Видеонаблюдение',
      map_cat_dom: 'Домофон',
      map_cat_slag: 'Шлагбаум',

      map_status_all: 'Все',
      map_status_local: 'Локальный доступ',
      map_status_remote: 'Удалённый доступ',

      map_photo_title: 'Фото',



map_filter_lbl: 'Фильтр:',
map_filter_all: 'все адреса',
map_filter_cat_fmt: 'категория = {cat}',
map_filter_access_local: 'доступ = локальный',
map_filter_access_remote: 'доступ = удалённый',

map_total_lbl: 'Адресов:',
map_total_in_radius_fmt: '(в радиусе: {n})',

map_chip_all: 'Все',
map_chip_video: 'Видео',
map_chip_dom: 'Домофон',
map_chip_slag: 'Шлагбаум',
map_chip_local: 'Локальные',
map_chip_remote: 'Удалённые',

map_sum_video: 'Видео',
map_sum_dom: 'Домофон',
map_sum_slag: 'Шлагбаум',
map_sum_local: 'Локальных',
map_sum_remote: 'Удалённых',

map_empty: 'Нет записей',
map_no_address: 'Без адреса',
map_photo: 'Фото',

map_ctx_add_here: 'Добавить метку здесь',
map_ctx_add_incident_here: 'Добавить инцидент здесь',
map_ctx_radius: 'Фильтр радиуса…',
map_ctx_cancel: 'Отмена',
map_ctx_coords_prefilled: 'Координаты подставлены: {lat}, {lon}',
map_ctx_radius_prompt: 'Радиус (км):',
map_ctx_radius_invalid: 'Введите положительный радиус',

map_shortcuts_help: 'Сочетания клавиш:\n  / — поиск\n  t — тема светлая/тёмная\n  s — показать/скрыть сайдбар\n  a — добавить запись\n  Esc — закрыть окна',
map_theme_toast_fmt: 'Тема: {theme}',
      map_theme_dark_label: 'тёмная',
      map_theme_light_label: 'светлая',

map_modal_add: 'Добавить',
map_modal_edit: 'Редактирование',
map_modal_save: 'Сохранить',
map_modal_saving: 'Сохранение…',
map_modal_saved: 'Сохранено',
map_modal_save_err: 'Ошибка сохранения',

map_err_need_address: 'Укажи адрес (улица, дом, ориентир).',
map_err_coords_nums: 'Координаты должны быть числами. Можно получить их через «Геокодинг».',
map_err_desc_long: 'Описание слишком длинное (максимум 500 символов).',
map_err_link_long: 'Ссылка слишком длинная (максимум 255 символов).',

map_geocode_searching: 'Поиск…',
map_geocode_btn: 'Геокодинг',
map_err_fields_not_found: 'Поля формы не найдены',
map_err_enter_address: 'Введите адрес',
map_err_coords_not_found: 'Координаты не найдены для этого адреса',
map_err_geocode_failed_fmt: 'Ошибка геокодинга: {err}',
      // Common
      common_lang_ru: 'RU',
      common_lang_en: 'EN',
      common_theme: 'Тема',
      common_language: 'Язык',
    },
    en: {
      // Command Center
      cc_title: 'Command Center — Map v12',
      cc_brand: 'Command Center',
      cc_server_time: 'server time:',
      cc_search_ph: 'Search: unit / TG ID / request #…',
      cc_btn_find: 'Find',
      cc_btn_panel: 'Panel',
      cc_btn_code: 'Code',
      cc_btn_chat: 'Chat',
      cc_btn_service: 'Service',
      cc_btn_map: 'Map',
      cc_btn_devices: 'Devices',
      cc_btn_problems: 'Problems',
      cc_btn_metrics: 'Metrics',
      cc_btn_duty: 'Duty',

      cc_kpi_shifts: 'Units',
      cc_kpi_live: 'Live',
      cc_kpi_breaks: 'Breaks',
      cc_kpi_problems: 'Problems',
      cc_kpi_sos: 'SOS',
      cc_kpi_stale: 'Stale',
      cc_kpi_acc: 'Accuracy',
      cc_kpi_queue: 'Queue',

      cc_qf_all: 'All',
      cc_qf_live: 'Live',
      cc_qf_problems: 'Problems',
      cc_qf_sos: 'SOS',
      cc_qf_stale: 'Stale',
      cc_qf_revoked: 'Revoked',

      cc_status_sos: 'SOS',
      cc_status_crit: 'CRIT',
      cc_status_stale: 'STALE',
      cc_status_warn: 'WARN',
      cc_status_ok: 'LIVE',
      cc_status_idle: 'IDLE',
      cc_status_ended: 'ENDED',
      cc_status_revoked: 'REVOKED',

      cc_legend_title: 'Legend',
      cc_legend_live: 'LIVE',
      cc_legend_idle: 'IDLE',
      cc_legend_problem_stale: 'PROBLEM / STALE',
      cc_legend_sos: 'SOS',
      cc_legend_revoked: 'REVOKED',
      cc_legend_hint: 'Click a dot to open the unit card.',

      cc_critical_now: 'Critical now',
      cc_btn_open: 'Open',
      cc_last_prefix: 'last:',

      cc_quality_5m_prefix: '5m',
      cc_quality_pts: 'pts',
      cc_quality_avg: 'avg',
      cc_quality_jumps: 'jumps',

      cc_sidebar_active: 'Active units',
      cc_flt_live: 'live only',
      cc_flt_break: 'with break',
      cc_flt_sos: 'with SOS',
      cc_flt_stale: 'no updates > 5 min',
      cc_loading: 'Loading…',
      cc_none: '—',
      cc_sidebar_breaks: 'Breaks',
      cc_sidebar_sos: 'SOS',
      cc_sidebar_sos_hint: 'New SOS pop on top. Click an item to focus on the map.',
      cc_sidebar_pending: 'Requests (pending)',
      cc_sidebar_pending_hint: 'Tip: approve instantly creates a marker on the main map.',
      cc_sidebar_tips: 'Quick tips',

      cc_tab_overview: 'Overview',
      cc_tab_track: 'Track',
      cc_tab_journal: 'Journal',

      cc_box_shift_start: 'Shift start',
      cc_box_last_update: 'Last update',
      cc_box_tracking_status: 'Tracking status',
      cc_box_accuracy_last: 'Accuracy (last)',
      cc_box_speed_last: 'Speed (last)',
      cc_box_kpi_5m: 'KPI (5 min)',
      cc_box_coords_last: 'Coords (last point)',
      cc_box_positioning: 'Positioning',
      cc_pos_source: 'Source',
      cc_pos_conf: 'Confidence',
      cc_pos_details: 'Details',
      cc_tip_live: 'live',
      cc_tip_idle: 'idle',
      cc_tip_est: 'estimate',
      cc_tip_gnss: 'GNSS',
      cc_pos_method_tile: 'radio map',
      cc_pos_method_anchor: 'anchors',
      cc_box_health: 'Device (health)',

      cc_break_title: 'Break',
      cc_break_status_requested: 'requested',
      cc_break_status_approved: 'approved',
      cc_break_status_started: 'running',
      cc_break_status_due: 'due',
      cc_break_status_ended: 'ended',

      cc_sos_active: 'SOS active',
      cc_sos_status_open: 'open',
      cc_sos_status_acked: 'acked',
      cc_sos_status_closed: 'closed',

      cc_actions_quick: 'Quick actions',
      cc_action_show: 'Show',
      cc_action_track: 'Track',
      cc_action_copy: 'Copy',
      cc_action_device: 'Device',
      cc_action_journal: 'Journal',
      cc_action_card: 'Card',
      cc_action_write: 'Message',
      cc_action_dismiss: 'Dismiss',
      cc_shift_hash: 'shift #',
      cc_start_short: 'start',
      cc_critical_now: 'Critical now',
      cc_last_prefix: 'last:',

      cc_last_point: 'last point',
      cc_update_age: 'age',
      cc_phone_line_prefix: 'phone',

      cc_recs_lbl: 'What to fix',

      cc_toast_open_shift_failed: 'Failed to open card: {status}',
      cc_toast_track_load_failed: 'Failed to load track: {status}',
      cc_toast_no_last_coord: 'No last coordinate',
      cc_toast_chat_not_ready: 'Chat is not ready yet',
      cc_toast_copied: 'Coordinates copied',
      cc_toast_copy_failed: 'Copy failed',
      cc_toast_no_coords_for: 'No coordinates for: {title}',
      cc_toast_chat_not_inited: 'Chat is not initialized yet',
      cc_toast_pending_new: '🔔 New request #{id}',
      cc_toast_break_due: '⏱ Break time is due for TG {user_id}',

      // Map page
      map_title: 'Map v12 — online + offline',
      map_search_ph: 'Search…',
      map_access_btn: 'Access',
      map_btn_add: 'Add',
      map_btn_data: 'Data',
      map_btn_delete_selected: 'Delete selected',
      map_btn_lang: 'EN',
      map_btn_theme_dark: 'Theme: dark',
      map_btn_theme_light: 'Theme: light',

      map_cat_all: 'All categories',
      map_cat_video: 'CCTV',
      map_cat_dom: 'Intercom',
      map_cat_slag: 'Barrier',

      map_status_all: 'All',
      map_status_local: 'Local access',
      map_status_remote: 'Remote access',

      map_photo_title: 'Photo',



map_filter_lbl: 'Filter:',
map_filter_all: 'all addresses',
map_filter_cat_fmt: 'category = {cat}',
map_filter_access_local: 'access = local',
map_filter_access_remote: 'access = remote',

map_total_lbl: 'Total:',
map_total_in_radius_fmt: '(in radius: {n})',

map_chip_all: 'All',
map_chip_video: 'Video',
map_chip_dom: 'Intercom',
map_chip_slag: 'Barrier',
map_chip_local: 'Local',
map_chip_remote: 'Remote',

map_sum_video: 'Video',
map_sum_dom: 'Intercom',
map_sum_slag: 'Barrier',
map_sum_local: 'Local',
map_sum_remote: 'Remote',

map_empty: 'No records',
map_no_address: 'No address',
map_photo: 'Photo',

map_ctx_add_here: 'Add marker here',
map_ctx_radius: 'Radius filter…',
map_ctx_cancel: 'Cancel',
map_ctx_coords_prefilled: 'Coordinates set: {lat}, {lon}',
map_ctx_radius_prompt: 'Radius (km):',
map_ctx_radius_invalid: 'Enter a positive radius',

map_shortcuts_help: 'Shortcuts:\n  / — search\n  t — toggle theme\n  s — toggle sidebar\n  a — add record\n  Esc — close dialogs',
map_theme_toast_fmt: 'Theme: {theme}',
      map_theme_dark_label: 'dark',
      map_theme_light_label: 'light',

map_modal_add: 'Add',
map_modal_edit: 'Edit',
map_modal_save: 'Save',
map_modal_saving: 'Saving…',
map_modal_saved: 'Saved',
map_modal_save_err: 'Save error',

map_err_need_address: 'Enter an address (street, building, landmark).',
map_err_coords_nums: 'Coordinates must be numbers. You can get them via “Geocoding”.',
map_err_desc_long: 'Description is too long (max 500 chars).',
map_err_link_long: 'Link is too long (max 255 chars).',

map_geocode_searching: 'Searching…',
map_geocode_btn: 'Geocoding',
map_err_fields_not_found: 'Form fields not found',
map_err_enter_address: 'Enter an address',
map_err_coords_not_found: 'Coordinates not found for this address',
map_err_geocode_failed_fmt: 'Geocoding error: {err}',
      // Common
      common_lang_ru: 'RU',
      common_lang_en: 'EN',
      common_theme: 'Theme',
      common_language: 'Language',
    }
  };

  const statusMap = {
    'Локальный доступ': { en: 'Local access' },
    'Удаленный доступ': { en: 'Remote access' },
    'Удалённый доступ': { en: 'Remote access' },
  };
  const categoryMap = {
    'Видеонаблюдение': { en: 'CCTV' },
    'Домофон': { en: 'Intercom' },
    'Шлагбаум': { en: 'Barrier' },
  };

  function getLang(){
    try{
      const v = (localStorage.getItem(LS_KEY) || '').toLowerCase();
      return SUPPORTED.includes(v) ? v : 'ru';
    }catch(_){ return 'ru'; }
  }

  function setLang(lang){
    const v = SUPPORTED.includes(String(lang).toLowerCase()) ? String(lang).toLowerCase() : 'ru';
    try{ localStorage.setItem(LS_KEY, v); }catch(_){ }
    try{ window.dispatchEvent(new CustomEvent('ui:lang', { detail: { lang: v } })); }catch(_){ }
    return v;
  }

  function t(key, vars){
    const lang = getLang();
    const base = (dict[lang] && dict[lang][key]) || (dict.ru && dict.ru[key]) || key;
    if(!vars) return base;
    return String(base).replace(/\{(\w+)\}/g, (m, k) => (vars[k] != null ? String(vars[k]) : m));
  }

  function trStatusRuEn(s){
    const lang = getLang();
    const src = String(s || '');
    if(lang !== 'en') return src;
    const m = statusMap[src];
    return (m && m.en) ? m.en : src;
  }

  function trCategoryRuEn(s){
    const lang = getLang();
    const src = String(s || '');
    if(lang !== 'en') return src;
    const m = categoryMap[src];
    return (m && m.en) ? m.en : src;
  }

  function applyDomTranslations(root){
    const r = root || document;
    r.querySelectorAll('[data-i18n]').forEach(el => {
      const k = el.getAttribute('data-i18n');
      if(k) el.textContent = t(k);
    });
    r.querySelectorAll('[data-i18n-title]').forEach(el => {
      const k = el.getAttribute('data-i18n-title');
      if(k) el.setAttribute('title', t(k));
    });
    r.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const k = el.getAttribute('data-i18n-placeholder');
      if(k) el.setAttribute('placeholder', t(k));
    });
  }

  window.i18n = {
    dict,
    getLang,
    setLang,
    t,
    trStatusRuEn,
    trCategoryRuEn,
    applyDomTranslations,
  };
})();
