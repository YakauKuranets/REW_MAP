# DutyTracker Android (полный скелет)

Это готовый Android-проект для **живого трекинга** (Foreground Service + Room очередь + WorkManager отправка)
под backend из архива `TEST6_with_tracker_live_ws_v1.zip`.

## Что умеет
- Привязка устройства по коду: `POST /api/tracker/pair`
- Отправка профиля: `POST /api/tracker/profile`
- Старт/стоп сессии: `POST /api/tracker/start`, `POST /api/tracker/stop`
- Сбор GPS в фоне (Foreground Service)
- Очередь точек в SQLite (Room)
- Отправка очереди в 1-5 пачек (WorkManager) на `POST /api/tracker/points`

## Быстрый запуск
1) Открой проект в Android Studio.
2) В `Base URL` укажи:
   - эмулятор: `http://10.0.2.2:5000`
   - реальный телефон в одной Wi‑Fi сети: `http://<IP_ПК>:5000`
3) В админке/на сервере создай **код привязки** и введи его в приложении.
4) Заполни профиль.
5) Нажми "Включить трекинг".

## Карта (v11+)
В приложении добавлен экран **"Карта"** (хвост 5/15/60 минут, точка + круг точности).

Чтобы карта работала:
1) Создай Google Maps API key (Android Maps SDK) в Google Cloud Console.
2) Вставь ключ в файл `app/src/main/res/values/google_maps_api.xml` вместо `YOUR_API_KEY_HERE`.
3) Запусти приложение — кнопка **"Карта"** находится на главном экране.

## Важно про HTTP/HTTPS
- В **debug** сборке разрешён HTTP (cleartext) через `network_security_config.xml` в `src/debug/`.
- В **release** сборке HTTP запрещён — нужно HTTPS.

## Если Android Studio просит Gradle Wrapper
В этом архиве нет `gradlew`/`gradle-wrapper.jar`.
Самый простой путь:
1) Создай новый проект **Empty Activity** в Android Studio.
2) Выставь package `com.mapv12.dutytracker`.
3) Замени у нового проекта папку `app/src/` и `app/build.gradle.kts` на файлы из этого архива.

## SOS
В проекте backend сейчас SOS реализован для бота (`/api/duty/bot/sos`).
Для SOS из приложения рекомендую добавить endpoint `/api/tracker/sos` (с auth как у tracker).



## Что добавлено в v7 (техника)
### 1) Журнал событий (Event Journal)
- Любой API вызов (`pair/start/stop/points/health/sos/profile`) пишет строку в локальную БД `event_journal`.
- Worker отправки очереди тоже пишет события (успех/ошибка, session_inactive и т.д.).
- В приложении: **Диагностика → Журнал (последние 50)**.

Это нужно, чтобы быстро понять: **что именно отправлялось, когда, и чем закончилось** — без logcat.

### 2) AUTO режим трекинга (умная частота)
- Удержание на кнопке **"Норма"** включает/выключает **AUTO**.
- AUTO сам выбирает эффективный режим:
  - стоим → `eco`
  - движемся → `normal`
  - быстро и точность плохая → `precise`
- В статусе/нотификации будет видно `auto→eco/normal/precise`.

Дальше можно расширить правила (батарея/экран/сеть/качество GPS), но базовая автоматика уже решает 80% проблем.

## Быстрый запуск (Windows)

1) Открой проект в Android Studio, выбери Gradle JDK = 17.
2) Запуск: кнопка **Run ▶** (конфигурация `app`).

### Сборка из консоли (если нужно)
Если у тебя Android Studio установлена на диске D:, можно использовать её JBR как JDK:

PowerShell:
```powershell
setx JAVA_HOME "D:\Program Files\Android\Android Studio\jbr"
```

Далее (в новой консоли):
```powershell
cd android
.\gradlew.bat :app:assembleDebug
```

`gradlew.bat` сам скачает совместимый Gradle (8.7) и соберёт проект.
