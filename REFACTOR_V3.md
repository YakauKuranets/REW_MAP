# 🔄 Map v12 — Полный рефакторинг v3 (2026-02)

## Что сделано

### 📱 Android (DutyTracker)

#### Архитектура и код
| Файл | Изменения |
|------|-----------|
| `App.kt` | Два канала уведомлений (TRACKING + SOS), чистый companion object, runCatching |
| `JournalAdapter.kt` | Полностью переписан: **ListAdapter + DiffUtil** вместо `notifyDataSetChanged()`, маппинг emoji-иконок, цветные индикаторы по типу события |
| `JournalActivity.kt` | `lifecycleScope` вместо CoroutineScope с SupervisorJob, фильтр-чипы |
| `build.gradle.kts` | KSP вместо KAPT, compileSdk/targetSdk=35, kotlin 2.0, все deps обновлены, minify в release |

#### Дизайн (Material 3 / You)
| Ресурс | Изменения |
|--------|-----------|
| `values/themes.xml` | Material3 базовая тема, кастомные Shape (16-24dp), стили SOS и StartStop кнопок |
| `values/colors.xml` | Полная палитра Material 3: primary/container/on+, semantic статусы (ok/warn/error), tile backgrounds |
| `values-night/colors.xml` | Полная тёмная тема: deep navy (#0F1117), яркие акценты |
| `values-night/themes.xml` | Dark theme override с правильным `windowLightStatusBar=false` |
| `values/strings.xml` | Все строки вынесены в ресурсы, расширен словарь |
| `activity_main.xml` | **Полностью переписан** (898 строк): CoordinatorLayout, экран привязки с card, экран профиля с toolbar, главный экран с: badge-трекинга, 6 tiles 88dp, SOS 64dp, mode toggle, navigation buttons, section problems |
| `activity_journal.xml` | AppBarLayout + filter chips (HorizontalScrollView) + RecyclerView + empty state |
| `activity_diagnostics.xml` | CoordinatorLayout, карточки с цветным error container, grid кнопок |
| `item_journal.xml` | Цветной индикатор слева, тип+статус, detail, время справа |
| `drawables/` | bg_badge с colorSurfaceVariant, bg_circle_primary с colorPrimaryContainer |
| `ic_arrow_back.xml` | Back icon для toolbar |
| `AndroidManifest.xml` | `enableOnBackInvokedCallback`, `@string/app_name` |

---

### 🌐 Веб (Map v12)

#### style.css — полная переработка (2036→930 строк, -54%)
- **Новый шрифт**: Inter + JetBrains Mono (вместо Poppins)
- **Цветовая схема**: морской синий (#1a56db) вместо фиолетового — соответствует теме "командный/оперативный"
- **Токены**: расширены и упорядочены: `--primary-light`, `--accent`, `--t` (transition), `--fs-*`, `--font-mono`
- **Тёмная тема**: deep navy (#090e1a), правильные rgb-based тени
- **Кнопки**: box-shadow на primary, hover с transform (-1px), focus-visible с outline
- **Input**: bg-alt фон, focus ring 3px, dark mode
- **Sidebar карточки**: border-radius 14dp, hover с translateY + border-color анимацией
- **Dropdown**: border-radius 14dp, плавная анимация `menuAppear`
- **Modals**: backdrop-filter blur, border-radius 18dp, border 1px
- **Chat**: современные bubble-стили, bg-alt фон, themed
- **Toast**: сдвиг translateX вместо translateY, border-left color-coded
- **Animations**: `fadeIn` и `menuAppear` переработаны
- **Responsive**: правильные breakpoints 900/640px

#### admin_common.css — рефакторинг
- `color-mix(in srgb, ...)` — современный CSS для смешивания цветов
- Skeleton loader с правильными переменными
- `.adm-chip` с вариантами `--crit/--ok/--hint`
- Sticky header с backdrop-filter
- WebSocket pill с плавным transition

#### admin_panel.css — рефакторинг
- `.ap-badge` унифицированный компонент
- `.ap-kpi-pill` — компактная альтернатива KPI карточкам
- Responsive breakpoints 920/640px
- Sidebar `position:fixed` на мобильных

---

### 🔐 Backend (Python)

Без изменений кода — изменения из предыдущего сессии (v2) уже включены:
- `models.py`: datetime.now(timezone.utc), lazy='selectin', TrackerDevice.to_dict()
- `config.py`: безопасный SECRET_KEY
- `__init__.py`: root redirect с проверкой сессии
- `map_core.js`: localStorage для позиции карты

---

## Технические метрики

| Метрика | До | После |
|---------|-----|-------|
| style.css | 2036 строк | 930 строк (-54%) |
| Android layouts | legacy Material 2 | Material 3 |
| Android deps | KAPT, targetSdk 34 | KSP, targetSdk 35, Kotlin 2.0 |
| JournalAdapter | notifyDataSetChanged() | DiffUtil ListAdapter |
| Dark mode | базовый | полный dark palette |
| CSS tokens | частичные | полные (шрифт, цвет, тени, transitions) |
| Тема | фиолетовая | морской синий (operational) |

---

## Требования к запуску

### Веб: без изменений
```bash
pip install -r requirements.txt
flask run
```

### Android: обновить плагины в settings.gradle.kts
```kotlin
id("com.google.devtools.ksp") version "2.0.21-1.0.28" apply false
```
