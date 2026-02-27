# DutyTracker Android – Stage 23 (Survivability + Health Extra)

## Что добавлено
1) **OemGuide**: кнопка "Разрешить работу в фоне (исключение)"
   - открывает системный диалог `ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS`
   - если уже разрешено — показывает уведомление.

2) **Health payload extra** (DeviceStatus.collect)
   - `battery_opt_ignored`
   - `notif_granted`
   - `bg_location_granted`
   - `fine_location_granted`
   - `location_enabled`

3) **Экран Home → "Проблемы"**
   - добавлены проверки: уведомления (Android 13+), сеть, stale GPS > 30s.

4) **Manifest**
   - добавлено разрешение `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS`.

## Версия
- versionCode: 3
- versionName: 1.2
