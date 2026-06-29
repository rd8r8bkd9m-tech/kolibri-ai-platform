# Интеграция брендового ассета Kolibri

Дата: 2026-06-29  
Роль: инженер брендового актива Kolibri  
Статус: безопасное предложение без изменения frontend-кода

## 1. Исходник

Локальное изображение:

`/var/folders/jq/2t_cj7ns76sbdkcc3rb0l_6h0000gn/T/codex-clipboard-1f25d069-34bc-4834-a91e-a2f47b1d400f.png`

Проверенные свойства:

| Свойство | Значение |
| --- | --- |
| Формат | PNG |
| Размер | 1254 x 1254 |
| Цвет | 8-bit/color RGBA |
| Alpha | есть |
| Визуальный тип | объёмная дружелюбная птица на прозрачном фоне |

Ассет хорошо подходит как hero/character image, onboarding mascot,
future Rive reference и источник для PWA/logo derivatives. Его не стоит
подставлять напрямую как maskable PWA icon без отдельного кадрирования,
паддинга и проверки safe zone: у птицы длинный клюв, хвост и крылья, которые
легко обрезаются launcher-масками.

## 2. Текущее состояние проекта

Уже есть:

| Файл | Текущая роль |
| --- | --- |
| `docs/living-bird.md` | продуктовый стандарт живой птицы |
| `docs/agent-work/living-bird-rive-spec.md` | Rive/state-machine спецификация |
| `frontend/src/components/KolibriBird.jsx` | SVG fallback + framer-motion |
| `frontend/src/components/LivingKolibri.jsx` | controller/fallback слой для событий приложения |
| `frontend/public/manifest.webmanifest` | PWA manifest с 192/512 maskable icons |
| `frontend/public/icons/icon-192.png` | текущая Android/PWA иконка |
| `frontend/public/icons/icon-512.png` | текущая Android/PWA иконка |
| `frontend/public/icons/apple-touch-icon.png` | текущая iOS Home Screen иконка |

Рабочее дерево уже содержит много чужих изменений, включая PWA manifest,
`KolibriBird.jsx`, `LivingKolibri.jsx`, `App.jsx` и стили. Поэтому этот pass
не меняет код и не заменяет иконки: сначала нужен согласованный маленький PR
только под брендовый ассет.

## 3. Рекомендуемая стратегия

### 3.1 Source asset

Сохранить исходный PNG как канонический raster source:

`frontend/src/assets/kolibri-bird-source.png`

Правила:

- файл хранится в `src/assets`, потому что это исходник для UI-компонентов и
  сборки Vite, а не обязательный публичный URL;
- исходник не сжимать destructive-оптимизацией;
- не импортировать его сразу в существующие экраны без visual QA;
- не использовать temp path из `/var/folders/...` в коде, документах релиза или
  manifest.

### 3.2 Logo/UI asset

Сделать отдельную производную картинку для обычного UI:

`frontend/src/assets/kolibri-bird-ui.png`

Рекомендуемые параметры:

- 1024 x 1024 или 768 x 768 PNG/WebP;
- прозрачный фон;
- птица вписана в кадр с 6-10% свободного поля;
- клюв и хвост не касаются краёв;
- визуальная резкость сохранена на 56, 72, 96 и 144 px.

Подключение в UI делать через новый opt-in prop в `KolibriBird` или отдельный
renderer внутри `LivingKolibri`, а не заменять существующий SVG fallback
безусловно.

Минимальный безопасный контракт:

```jsx
<LivingKolibri
  state={appState}
  taskState={factoryTaskState}
  renderer="image"
  imageSrc={kolibriBirdUi}
/>
```

Fallback:

- если `imageSrc` не загружен, остаётся текущий SVG;
- при `prefers-reduced-motion` картинка статична;
- aria-label остаётся semantic: `Колибри думает`, `Колибри работает`,
  `Колибри без сети`.

### 3.3 PWA icons

Для PWA нужны не прямые копии исходника, а отдельные maskable-safe derivatives:

| Файл | Размер | Назначение |
| --- | --- | --- |
| `frontend/public/icons/icon-192.png` | 192 x 192 | Android install icon |
| `frontend/public/icons/icon-512.png` | 512 x 512 | Android splash/launcher |
| `frontend/public/icons/apple-touch-icon.png` | 180 x 180 | iOS Home Screen |

Правила кадрирования:

- использовать однотонный или мягкий брендовый фон, потому что iOS icon не
  сохраняет прозрачность как “свободную” прозрачную пиктограмму;
- держать важные элементы внутри maskable safe area примерно 80% от размера;
- уменьшить птицу так, чтобы клюв, хвост и крылья не попадали в обрезку
  circle/squircle masks;
- сделать отдельную проверку на light/dark launcher backgrounds;
- обновлять `frontend/public/manifest.webmanifest` только вместе с
  перегенерированными PNG и visual evidence.

Из-за текущих ограничений задачи и dirty manifest замену public icons лучше
делать отдельным согласованным PR. Это затрагивает PWA installability и требует
Android/iOS проверки.

### 3.4 Живая птица

Использовать PNG как reference/base layer для будущей Rive-птицы, а не как
замену Rive-контракта.

Безопасная последовательность:

1. Сохранить source PNG в `frontend/src/assets`.
2. Сгенерировать UI derivative с устойчивым bounding box.
3. Добавить image renderer в `LivingKolibri` за prop/feature flag.
4. Оставить текущий SVG renderer canonical fallback.
5. Отдельно подготовить Rive artboard по
   `docs/agent-work/living-bird-rive-spec.md`.

State mapping для статичного PNG:

| Semantic state | PNG-поведение |
| --- | --- |
| `idle`, `calm` | статичная птица, мягкая тень |
| `listening` | лёгкий scale/tilt, взгляд не менять в raster |
| `thinking`, `working`, `learning` | медленный hover только если motion allowed |
| `success`, `celebrating` | короткий scale + CSS sparkle вне PNG |
| `warning`, `error`, `offline` | не перекрашивать птицу агрессивно; показывать текстовый/status UI рядом |
| `sleepy` | лучше оставить SVG/Rive, потому что raster не умеет менять веки |

## 4. Границы безопасного PR

Разрешённый минимальный PR:

- добавить `frontend/src/assets/kolibri-bird-source.png`;
- добавить `frontend/src/assets/kolibri-bird-ui.png`;
- добавить image renderer только в `frontend/src/components/KolibriBird.jsx` и
  `frontend/src/components/LivingKolibri.jsx`;
- не менять `App.jsx`, routing, billing, chat workflow, service worker и
  control panel;
- не менять PWA icons в этом же PR, если нет device evidence.

Отдельный PWA PR:

- перегенерировать `frontend/public/icons/icon-192.png`;
- перегенерировать `frontend/public/icons/icon-512.png`;
- перегенерировать `frontend/public/icons/apple-touch-icon.png`;
- проверить `frontend/public/manifest.webmanifest`;
- приложить Android/iOS visual evidence.

Не делать:

- не ссылаться на `/var/folders/...` из frontend;
- не заменять SVG fallback на PNG без rollback path;
- не добавлять тяжёлый animation runtime ради одного PNG;
- не класть source asset в `public`, если он не должен быть стабильным
  публичным URL;
- не менять чужие незавершённые правки в текущей ветке.

## 5. Проверки перед merge

Static checks:

```bash
file frontend/src/assets/kolibri-bird-source.png
file frontend/src/assets/kolibri-bird-ui.png
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend run test:mobile-layout
```

PWA icon checks, если меняются public icons:

```bash
file frontend/public/icons/apple-touch-icon.png frontend/public/icons/icon-192.png frontend/public/icons/icon-512.png
node -e "const fs=require('fs'); const m=JSON.parse(fs.readFileSync('frontend/public/manifest.webmanifest','utf8')); if (!m.icons.some(i => i.sizes === '192x192' && i.purpose.includes('maskable'))) throw new Error('missing 192 maskable'); if (!m.icons.some(i => i.sizes === '512x512' && i.purpose.includes('maskable'))) throw new Error('missing 512 maskable'); console.log('manifest icon guard passed')"
```

Visual checks:

- desktop 1440 x 1000: птица не перекрывает header/chat/control;
- mobile 390 x 844 и 360 x 740: нет horizontal scroll, птица не закрывает
  composer и FAB;
- `prefers-reduced-motion: reduce`: нет бесконечного hover/scale;
- light/system/dark themes: птица читается и не даёт грязный ореол;
- installed Android PWA: launcher icon не обрезает клюв/хвост/крылья;
- iOS Home Screen: apple touch icon выглядит как полноценная иконка, а не как
  мелкая прозрачная наклейка.

## 6. Решение этого pass

Код и ассеты не менялись. Причина: текущая ветка уже содержит незавершённые
изменения в PWA manifest, bird components, `App.jsx` и CSS. Безопаснее
зафиксировать интеграционный контракт и выполнить фактическую замену отдельным
узким PR после согласования, чтобы не потереть работу других агентов.

Рекомендованный следующий шаг: отдельная задача “Brand asset PR” с разрешением
на добавление двух файлов в `frontend/src/assets` и точечный opt-in renderer в
компонентах птицы. PWA icons выносить во второй шаг после maskable proof.
