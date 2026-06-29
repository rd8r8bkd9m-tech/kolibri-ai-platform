# Живая птица Kolibri

Птица Kolibri — брендовый персонаж продукта. Она должна оживлять интерфейс,
реагировать на состояние приложения и иметь индивидуальный характер для каждого
клиента.

## Исходник

В качестве текущего брендового исходника выбран локальный asset:

`/Users/kolibri/Downloads/Kimi_Agent_КолибриФин/kolibri-v2/public/kolibri-bird.png`

Это прозрачная крупная птичка, подходящая для лендинга, onboarding,
профиля пользователя и будущего Rive-прототипа.

## Технический стандарт

Основной путь: Rive state machine.

Детальная спецификация v1:
[Living Bird Rive Spec](agent-work/living-bird-rive-spec.md). Этот документ
сохраняет короткий продуктовый контракт, а пакет описывает Rive artboard,
View Model inputs, SVG fallback, personality presets, performance budgets,
accessibility и QA matrix.

Почему:

- это интерактивный runtime, а не линейная CSS-анимация;
- можно задавать inputs и состояния;
- можно подключить реакции на события приложения;
- подходит для персонажа с характером.

Fallback:

- текущий SVG/React-компонент для лёгкого режима;
- PixiJS sprite/runtime, если нужен более игровой персонаж;
- Lottie только для коротких линейных анимаций.

## Состояния

| Состояние | Когда включается |
| --- | --- |
| `idle` | пользователь читает или ждёт |
| `greeting` | первое приветствие в сессии или onboarding |
| `listening` | фокус в composer, голос или ввод |
| `thinking` | AI думает |
| `writing` | AI уже начал отвечать |
| `working` | фабрика выполняет задачу |
| `learning` | система обновляет контекст или knowledge artifact |
| `success` | задача успешно завершена |
| `warning` | есть нефатальное предупреждение |
| `error` | ошибка или блокер |
| `offline` | нет соединения |
| `sleepy` | долгий простой |
| `celebrating` | оплата, готовый отчёт, успешный deploy |

## Характер клиента

У каждого клиента может быть профиль характера:

- спокойный;
- энергичный;
- деловой;
- дружелюбный;
- минималистичный.

Характер влияет на:

- амплитуду движений;
- частоту микрореакций;
- скорость переходов;
- эмоции при успехе/ошибке;
- тон приветствий.

Характер не должен:

- мешать чтению текста;
- перекрывать рабочие элементы;
- ухудшать performance;
- нарушать accessibility;
- раздражать пользователя постоянным движением.

## Rive contract v1

Canonical runtime: `LivingKolibri` controller -> Rive renderer -> SVG fallback.

Обязательные принципы из `agent-work/living-bird-rive-spec.md`:

- Rive грузится lazy и не является обязательным для работы продукта.
- SVG fallback покрывает все canonical states и используется при Rive load
  error, reduced motion, маленьких аватарах и low-power сценариях.
- View Model inputs описывают semantic state, mood, energy, attention,
  taskState и personality traits; UI отправляет события, а controller решает
  priority.
- Safe bounds фиксируются заранее, чтобы птица не создавала layout shift и не
  перекрывала рабочие элементы.
- Клиентские данные не отправляются в Rive-файл или внешние сервисы.

## Контракт frontend

Будущий компонент:

```tsx
<LivingKolibri
  state={appState}
  taskState={factoryTaskState}
  personality={clientPersonality}
  reducedMotion={prefersReducedMotion}
/>
```

Минимальные события:

- `app:booted`;
- `chat:focus`;
- `chat:send`;
- `ai:thinking`;
- `ai:first_token`;
- `ai:complete`;
- `factory:task_started`;
- `factory:task_progress`;
- `factory:task_completed`;
- `factory:task_failed_soft`;
- `factory:task_failed_hard`;
- `billing:success`;
- `network:offline`;
- `network:online`.
- `idle:timeout`.

## Проверки

- desktop 1440px;
- mobile 360px;
- iOS safe area;
- Android PWA;
- low-power mode;
- `prefers-reduced-motion`;
- отсутствие layout shift;
- FPS и размер bundle.
- Rive load error -> SVG fallback;
- переключение personality preset без изменения semantic state;
- route с lazy Rive;
- состояния `working`, `warning`, `success`, `error` в Product QA.

Release checks для живой птицы входят в
[QA-пакет релиза](agent-work/product-qa-pack.md): персонаж не должен ломать
chat, Control Panel, billing, mobile layout и error states.

## Источники для реализации

- Rive React runtime: https://rive.app/docs/runtimes/react/react
- Rive state machines: https://rive.app/docs/editor/state-machine
- PixiJS sprites: https://pixijs.com/8.x/guides/components/scene-objects/sprite
- Lottie Web: https://airbnb.io/lottie/#/web
