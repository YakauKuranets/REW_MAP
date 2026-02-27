/* recs.js — рекомендации по алёртам/health (Stage18.1)
   Подключается как обычный <script>. Экспортирует window.Recs.

   Особенности:
   - Поддержка RU/EN (берёт язык из window.i18n.getLang() / localStorage.ui_lang)
   - Может строить рекомендации из:
     - alerts (kind + payload)
     - health (battery/net/gps/queue/accuracy)
     - shift summary/detail (synthetic stale/accuracy)
*/
(function(){
  'use strict';

  function getLang(){
    try{ return (window.i18n && typeof window.i18n.getLang === 'function') ? window.i18n.getLang() : 'ru'; }
    catch(_){ return 'ru'; }
  }
  function L(ru, en){
    return (getLang() === 'en') ? (en || ru) : ru;
  }

  function escapeHtml(s){
    return String(s == null ? '' : s).replace(/[&<>"']/g, function(m){
      return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'})[m];
    });
  }

  function uniq(list){
    const out = [];
    const seen = new Set();
    (list || []).forEach((x) => {
      const s = String(x == null ? '' : x).trim();
      if(!s) return;
      const key = s.toLowerCase();
      if(seen.has(key)) return;
      seen.add(key);
      out.push(s);
    });
    return out;
  }

  function _asNum(v){
    const n = Number(v);
    return (Number.isFinite(n) ? n : null);
  }

  function fromAlert(a){
    if(!a || typeof a !== 'object') return [];
    const kind = String(a.kind || '').toLowerCase();
    const payload = (a.payload && typeof a.payload === 'object') ? a.payload : {};
    const rec = [];

    switch(kind){
      case 'net_offline':
        rec.push(L('Проверьте интернет (Wi‑Fi/моб. данные), отключите режим полёта',
                   'Check internet (Wi‑Fi/mobile data), disable airplane mode'));
        rec.push(L('Разрешите фоновую передачу данных для DutyTracker',
                   'Allow background data for DutyTracker'));
        break;
      case 'gps_off':
        rec.push(L('Включите геолокацию (GPS) и режим «Высокая точность»',
                   'Enable location (GPS) and “High accuracy” mode'));
        rec.push(L('Проверьте разрешение геолокации «Всегда» для DutyTracker',
                   'Ensure “Always allow location” for DutyTracker'));
        break;
      case 'low_accuracy':
        rec.push(L('Перейдите на открытое место, подальше от плотной застройки',
                   'Move to open sky (away from dense buildings)'));
        rec.push(L('Включите «Высокая точность» (GPS + Wi‑Fi/BT сканирование)',
                   'Enable “High accuracy” (GPS + Wi‑Fi/BT scanning)'));
        rec.push(L('Отключите энергосбережение / battery optimization для DutyTracker',
                   'Disable battery optimization for DutyTracker'));
        break;
      case 'tracking_off':
        rec.push(L('Откройте DutyTracker и включите трекинг',
                   'Open DutyTracker and enable tracking'));
        rec.push(L('Проверьте, что смена запущена (если требуется)',
                   'Ensure the duty/shift is started (if required)'));
        break;
      case 'stale_points':
        rec.push(L('Нет свежих точек: проверьте сеть и ограничения фоновой работы',
                   'No fresh points: check network and background restrictions'));
        rec.push(L('Убедитесь, что Foreground Service активен и трекинг включён',
                   'Ensure foreground service is running and tracking is ON'));
        break;
      case 'stale_health':
        rec.push(L('Heartbeat не приходит: откройте приложение и проверьте сеть',
                   'Heartbeat missing: open the app and check network'));
        rec.push(L('Отключите battery optimization для DutyTracker',
                   'Disable battery optimization for DutyTracker'));
        break;
      case 'queue_growing':
        rec.push(L('Очередь растёт: плохая сеть или ограничения фоновой работы',
                   'Queue is growing: bad network or background restrictions'));
        rec.push(L('Смените сеть (Wi‑Fi/моб. данные) или дождитесь восстановления',
                   'Switch network (Wi‑Fi/mobile) or wait until it recovers'));
        break;
      case 'battery_low':
        rec.push(L('Низкий заряд: подключите зарядку',
                   'Low battery: connect a charger'));
        rec.push(L('Отключите энергосбережение для DutyTracker (может ломать фон)',
                   'Disable power saving for DutyTracker (may break background)'));
        break;
      case 'app_error':
        rec.push(L('Откройте DutyTracker и посмотрите текст ошибки',
                   'Open DutyTracker and check the error text'));
        rec.push(L('Проверьте BASE_URL/доступность сервера и токен',
                   'Check BASE_URL/server reachability and token'));
        rec.push(L('Перезапустите приложение (или переустановите при повторении)',
                   'Restart the app (or reinstall if it repeats)'));
        break;
      default:
        break;
    }

    // лёгкие подсказки по payload (если есть)
    const acc = _asNum(payload.accuracy_m);
    if(acc != null && acc > 0){
      rec.push(L('Текущая точность: ~' + Math.round(acc) + ' м',
                 'Current accuracy: ~' + Math.round(acc) + ' m'));
    }
    const age = _asNum(payload.age_sec);
    if(age != null && age > 0){
      rec.push(L('Возраст данных: ~' + Math.round(age/60) + ' мин',
                 'Data age: ~' + Math.round(age/60) + ' min'));
    }
    const qs = _asNum(payload.queue_size);
    if(qs != null){
      rec.push(L('Очередь: ' + Math.round(qs),
                 'Queue: ' + Math.round(qs)));
    }

    return uniq(rec);
  }

  function fromHealth(h){
    if(!h || typeof h !== 'object') return [];
    const rec = [];

    const extra = (h.extra && typeof h.extra === 'object') ? h.extra : {};

    const net = String(h.net || h.network || '').toLowerCase();
    if(net && (net.includes('off') || net.includes('none') || net.includes('no') || net === '0')){
      rec.push(L('Нет сети: включите Wi‑Fi/моб. данные (в т.ч. в фоне)',
                 'No network: enable Wi‑Fi/mobile data (including background)'));
    }

    const gps = String(h.gps || h.gps_on || '').toLowerCase();
    if(gps && (gps.includes('off') || gps.includes('disabled') || gps.includes('no') || gps === '0' || gps === 'false')){
      rec.push(L('GPS выключен: включите геолокацию и разрешения «Всегда»',
                 'GPS is OFF: enable location and “Always allow” permission'));
    }

    // Android extra flags (best-effort)
    if(extra && typeof extra === 'object'){
      if(extra.location_enabled === false){
        rec.push(L('Геолокация отключена: включите Location/GPS в настройках телефона',
                   'Location is disabled: enable Location/GPS in system settings'));
      }
      if(extra.fine_location_granted === false){
        rec.push(L('Нет разрешения геолокации: разрешите доступ к местоположению для DutyTracker',
                   'Missing location permission: grant location access to DutyTracker'));
      }
      if(extra.bg_location_granted === false){
        rec.push(L('Нет фоновой геолокации: установите «Всегда разрешать» для DutyTracker',
                   'Missing background location: set “Allow all the time” for DutyTracker'));
      }
      if(extra.battery_opt_ignored === false){
        rec.push(L('Отключите оптимизацию батареи для DutyTracker (иначе ломает фон)',
                   'Disable battery optimization for DutyTracker (may break background)'));
      }
      if(extra.power_save === true){
        rec.push(L('Выключите режим энергосбережения (может мешать трекингу в фоне)',
                   'Disable battery saver (may affect background tracking)'));
      }
      if(extra.notif_granted === false){
        rec.push(L('Разрешите уведомления для DutyTracker (для алёртов и статусов)',
                   'Allow notifications for DutyTracker (alerts/status)'));
      }
      if(extra.wifi_scan_always === false){
        rec.push(L('Включите «Wi‑Fi scanning» (поиск Wi‑Fi всегда) — улучшает indoor',
                   'Enable “Wi‑Fi scanning (always)” — improves indoor positioning'));
      }
      if(extra.ble_scan_always === false){
        rec.push(L('Включите «Bluetooth scanning» — улучшает «Высокую точность»',
                   'Enable “Bluetooth scanning” — helps High accuracy mode'));
      }
    }

    if(h.tracking_on === false || h.trackingOn === false){
      rec.push(L('Трекинг выключен: включите в приложении DutyTracker',
                 'Tracking is OFF: enable it in DutyTracker'));
    }

    const acc = _asNum(h.accuracy_m);
    if(acc != null){
      if(acc > 120){
        rec.push(L('Очень низкая точность: выйдите на открытое место, включите «Высокая точность»',
                   'Very low accuracy: move to open sky and enable “High accuracy”'));
      } else if(acc > 50){
        rec.push(L('Низкая точность: проверьте GPS/режим точности',
                   'Low accuracy: check GPS/accuracy mode'));
      }
    }

    const q = _asNum(h.queue_size != null ? h.queue_size : h.queue_len);
    if(q != null){
      if(q >= 150){
        rec.push(L('Очередь точек большая: плохая сеть или ограничения в фоне',
                   'Large queue: bad network or background restrictions'));
      } else if(q >= 50){
        rec.push(L('Очередь точек растёт: проверьте сеть',
                   'Queue is growing: check network'));
      }
    }

    const bat = _asNum(h.battery_pct);
    if(bat != null){
      if(bat <= 7){
        rec.push(L('Критически низкий заряд: подключите зарядку',
                   'Critically low battery: connect a charger'));
      } else if(bat <= 15){
        rec.push(L('Низкий заряд: подключите зарядку или отключите энергосбережение',
                   'Low battery: connect charger or disable power saving'));
      }
    }

    return uniq(rec);
  }

  // Shift summary as it comes from dashboard (/api/duty/admin/dashboard)
  function fromShiftSummary(sh){
    if(!sh || typeof sh !== 'object') return [];
    const rec = [];
    // health suggestions
    if(sh.health) rec.push.apply(rec, fromHealth(sh.health));

    const pa = _asNum(sh.last_point_age_sec);
    if(pa != null && pa > 300){
      rec.push.apply(rec, fromAlert({ kind: 'stale_points', payload: { age_sec: pa } }));
    } else {
      // derive from last.ts if present
      try{
        if(sh.last && sh.last.ts){
          const age = Math.max(0, (Date.now() - Date.parse(sh.last.ts))/1000);
          if(age > 300) rec.push.apply(rec, fromAlert({ kind: 'stale_points', payload: { age_sec: age } }));
        }
      }catch(_){}
    }

    const ha = _asNum(sh.health_age_sec);
    if(ha != null && ha > 180){
      rec.push.apply(rec, fromAlert({ kind: 'stale_health', payload: { age_sec: ha } }));
    }

    const acc = _asNum(sh.last && sh.last.accuracy_m);
    if(acc != null && acc > 60){
      rec.push.apply(rec, fromAlert({ kind: 'low_accuracy', payload: { accuracy_m: acc } }));
    }

    // Indoor hints (estimate points)
    try{
      const last = sh.last || {};
      const flags = Array.isArray(last.flags) ? last.flags : [];
      const src = String(last.source || last.src || '').toLowerCase();
      const isEst = (flags.indexOf('est') >= 0) || (src === 'wifi_est') || (src.indexOf('wifi_est') >= 0) || (src.indexOf('radio') >= 0);
      const conf = _asNum(last.confidence);
      if(isEst){
        if(conf != null && conf < 0.60){
          rec.push(L('Indoor confidence низкий: включите Wi‑Fi/BT scanning и пройдите 10–20 м для калибровки',
                     'Low indoor confidence: enable Wi‑Fi/BT scanning and walk 10–20 m to calibrate'));
        }
        const mw = _asNum((last.matches_wifi != null) ? last.matches_wifi : last.matches);
        if(mw != null && mw < 4){
          rec.push(L('Мало совпадений Wi‑Fi: включите Wi‑Fi и разрешите «Wi‑Fi scanning»',
                     'Few Wi‑Fi matches: turn Wi‑Fi on and enable “Wi‑Fi scanning”'));
        }
      }
    }catch(_){ }

    return uniq(rec);
  }

  // Shift detail as it comes from /api/duty/admin/shift/<id>/detail
  function fromShiftDetail(detail){
    if(!detail || typeof detail !== 'object') return [];
    const rec = [];
    if(detail.health) rec.push.apply(rec, fromHealth(detail.health));

    const la = _asNum(detail.last_age_sec);
    if(la != null && la > 300){
      rec.push.apply(rec, fromAlert({ kind: 'stale_points', payload: { age_sec: la } }));
    }
    const ha = _asNum(detail.health_age_sec);
    if(ha != null && ha > 180){
      rec.push.apply(rec, fromAlert({ kind: 'stale_health', payload: { age_sec: ha } }));
    }

    const last = detail.last || {};
    const acc = _asNum(last.accuracy_m);
    if(acc != null && acc > 60){
      rec.push.apply(rec, fromAlert({ kind: 'low_accuracy', payload: { accuracy_m: acc } }));
    }

    // queue hints
    const q = _asNum(detail.health && (detail.health.queue_size ?? detail.health.queue_len));
    if(q != null && q >= 50){
      rec.push.apply(rec, fromAlert({ kind: 'queue_growing', payload: { queue_size: q } }));
    }

    // Indoor hints (estimate points)
    try{
      const lastP = detail.last || {};
      const flags = Array.isArray(lastP.flags) ? lastP.flags : [];
      const src = String(lastP.source || lastP.src || '').toLowerCase();
      const isEst = (flags.indexOf('est') >= 0) || (src === 'wifi_est') || (src.indexOf('wifi_est') >= 0) || (src.indexOf('radio') >= 0);
      const conf = _asNum(lastP.confidence);
      if(isEst){
        if(conf != null && conf < 0.60){
          rec.push(L('Indoor confidence низкий: включите Wi‑Fi/BT scanning и пройдите 10–20 м (помогает радиокарте)',
                     'Low indoor confidence: enable Wi‑Fi/BT scanning and walk 10–20 m (helps radio-map)'));
        }
        const mw = _asNum((lastP.matches_wifi != null) ? lastP.matches_wifi : lastP.matches);
        if(mw != null && mw < 4){
          rec.push(L('Мало совпадений Wi‑Fi: включите Wi‑Fi и разрешите «Wi‑Fi scanning»',
                     'Few Wi‑Fi matches: turn Wi‑Fi on and enable “Wi‑Fi scanning”'));
        }
      }
    }catch(_){ }

    return uniq(rec);
  }

  function chips(list){
    const arr = uniq(list);
    if(!arr.length) return '';
    const title = L('Рекомендация', 'Recommendation');
    return arr.map((s) => (
      '<span class="adm-chip adm-chip--hint" title="' + escapeHtml(title) + '">' +
      '<i class="fa-solid fa-wand-magic-sparkles"></i> ' + escapeHtml(s) +
      '</span>'
    )).join(' ');
  }

  function block(list, label){
    const arr = uniq(list);
    const html = chips(arr);
    if(!html) return '';
    const lbl = label ? escapeHtml(label) : escapeHtml(L('Рекомендуется', 'Recommended'));
    return (
      '<div class="adm-recs">' +
        '<div class="adm-recs__lbl"><i class="fa-solid fa-wand-magic-sparkles"></i> ' + lbl + '</div>' +
        '<div class="adm-recs__chips">' + html + '</div>' +
      '</div>'
    );
  }

  window.Recs = {
    escapeHtml: escapeHtml,
    uniq: uniq,
    fromAlert: fromAlert,
    fromHealth: fromHealth,
    fromShiftSummary: fromShiftSummary,
    fromShiftDetail: fromShiftDetail,
    chips: chips,
    block: block,
    L: L,
    getLang: getLang,
  };
})();
