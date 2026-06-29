# Frontend lint readiness

Дата среза: 2026-06-29  
Агент: `Frontend lint ревизор`  
Область: `frontend/package.json`, ESLint 10 flat config, текущий lint failure.
Этой ревизией код приложения не менялся.

## 1. Что найдено в package.json

`frontend/package.json` запускает lint одной командой:

```bash
npm run lint
```

Фактический script:

```json
"lint": "eslint ."
```

Зависимости уже рассчитаны на flat config:

- `eslint`: package range `^10.3.0`, установлен локально `10.6.0`;
- `@eslint/js`: package range `^10.0.1`, установлен локально `10.0.1`;
- `globals`: package range `^17.6.0`, установлен локально `17.7.0`;
- `eslint-plugin-react-hooks`: package range `^7.1.1`, установлен локально `7.1.1`;
- `eslint-plugin-react-refresh`: package range `^0.5.2`, установлен локально `0.5.3`.

В `frontend/package.json` стоит `"type": "module"`, поэтому
`frontend/eslint.config.js` может быть обычным ESM-файлом с `import` /
`export default`.

## 2. Текущая причина lint failure

Первичный локальный прогон до появления конфига:

```bash
cd frontend
npm run lint
```

Результат:

```text
ESLint: 10.6.0
ESLint couldn't find an eslint.config.(js|mjs|cjs) file.
```

Exit code был `2`. Причина не в исходниках, а в отсутствии flat config.
Начиная с ESLint 9, файл конфигурации по умолчанию - `eslint.config.js`;
ESLint 10 продолжает этот режим и не ищет `.eslintrc.*` как основной путь.

Во время ревизии в рабочем дереве появился `frontend/eslint.config.js`
как untracked-файл. Я его не менял и не заменял, чтобы не конфликтовать с
работой главного агента. После появления этого файла `npm run lint` уже
завершается с exit code `0`, но оставляет предупреждения.

## 3. Какой eslint.config нужен для ESLint 10

Минимально достаточный конфиг для текущего JavaScript/React/Vite состояния:

```js
import js from "@eslint/js"
import { defineConfig, globalIgnores } from "eslint/config"
import globals from "globals"
import reactHooks from "eslint-plugin-react-hooks"
import reactRefresh from "eslint-plugin-react-refresh"

export default defineConfig([
  globalIgnores(["dist/**", "node_modules/**", "coverage/**"]),

  js.configs.recommended,

  {
    files: ["**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
      globals: {
        ...globals.browser,
        ...globals.es2024,
      },
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    },
  },

  {
    files: ["vite.config.js", "tests/**/*.mjs"],
    languageOptions: {
      globals: {
        ...globals.node,
      },
    },
  },
])
```

Если `frontend/eslint.config.js` уже есть, лучше не переписывать его
механически. Достаточно сверить, что в нем есть эти контракты:

- global ignores для `dist/**`, `node_modules/**` и будущего `coverage/**`;
- `@eslint/js` recommended;
- JSX parsing для `*.jsx`;
- browser + ES globals для приложения;
- Node globals для `vite.config.js` и `tests/**/*.mjs`;
- `react-hooks/rules-of-hooks`, `react-hooks/exhaustive-deps`;
- `react-refresh/only-export-components` в режиме warning для Vite.

Официальные справки:

- https://eslint.org/docs/latest/use/configure/configuration-files
- https://eslint.org/docs/latest/use/configure/migration-guide
- https://eslint.org/docs/latest/use/configure/ignore

## 4. Важный пробел: TypeScript/TSX

В `frontend/src` есть три `.tsx` файла:

- `frontend/src/components/KolibriAvatar.tsx`;
- `frontend/src/components/MessageBubble.tsx`;
- `frontend/src/components/ThinkingIndicator.tsx`.

Сейчас в `frontend/package.json` нет `typescript`, `typescript-eslint`,
`@typescript-eslint/parser` или `@typescript-eslint/eslint-plugin`.
Текущий `eslint .` с JavaScript-only config не покрывает эти файлы.
Целевая проверка подтвердила:

```text
File ignored because no matching configuration was supplied
```

Если команда хочет реально lint-ить `.ts/.tsx`, нужен отдельный шаг:

```bash
npm install -D typescript typescript-eslint
```

И отдельный config block для `**/*.{ts,tsx}` через `typescript-eslint`.
Не стоит просто добавлять `**/*.{ts,tsx}` к текущему JS-блоку: стандартный
parser ESLint не рассчитан на TypeScript syntax.

Если TSX-файлы пока являются заготовками и не должны входить в lint gate,
это нужно зафиксировать явно: либо оставить их вне `files`, либо добавить
временный ignore с комментарием в задаче. Молчаливое прохождение `npm run lint`
может создать ложное ощущение полного покрытия.

## 5. Риски после включения lint

Текущий `npm run lint` проходит, потому что предупреждения не считаются
ошибками. Более строгая команда уже падает:

```bash
npm exec eslint -- --max-warnings=0 .
```

Результат сейчас: exit code `1`, три warning.

Основные риски:

- CI может стать красным, если включить `--max-warnings=0` или перевести
  текущие warnings в errors.
- `react-hooks/exhaustive-deps` нельзя чинить вслепую: добавление callback
  dependencies может менять memoization и частоту перерендеров.
- `react-refresh/only-export-components` обычно требует небольшой раскладки
  модулей: константы и компоненты лучше разделять, если правило остается
  включенным.
- `eslint .` смотрит не только `src`, но и `public/*.js`, `vite.config.js`,
  `tests/**/*.mjs`. Для разных runtime нужны разные globals.
- `dist` обязательно должен быть ignored, иначе generated bundle превратит
  lint в шумную и медленную проверку.
- Полное TSX-покрытие добавит новую область риска: TypeScript parser,
  дополнительные devDependencies и возможные предупреждения в заготовочных
  компонентах.

## 6. Файлы, которые вероятно придется поправить

Подтверждено текущим lint-выводом:

| Файл | Текущий сигнал | Вероятное действие |
| --- | --- | --- |
| `frontend/public/service-worker.js:65` | `no-unused-vars`: `error` в `catch (error)` не используется | Убрать binding в catch или использовать его осознанно для диагностики. |
| `frontend/src/App.jsx:306` | `react-hooks/exhaustive-deps`: у `useMemo` не хватает `fetchCluster`, `handleCheckout`, `handleFileUpload`, `handleSearch`, `setTheme` | Проверить стабильность callback/state setters и поправить dependency array без изменения поведения Control Panel. |
| `frontend/src/components/chat/QuickActions.jsx:3` | `react-refresh/only-export-components`: файл экспортирует `DEFAULT_QUICK_ACTIONS` вместе с компонентом | Вынести constant в отдельный модуль или принять локальное исключение, если hot refresh поведение устраивает. |

Вероятно после включения TSX lint:

| Файл | Почему в зоне риска |
| --- | --- |
| `frontend/src/components/KolibriAvatar.tsx` | Сейчас не покрывается ESLint; после добавления TS parser попадет в lint surface. |
| `frontend/src/components/MessageBubble.tsx` | Сейчас не покрывается ESLint; внутри есть TypeScript syntax, JSX и переменная `lang` в разборе code block, которую стоит проверить на unused после включения TS rules. |
| `frontend/src/components/ThinkingIndicator.tsx` | Сейчас не покрывается ESLint; использует alias imports и внешние UI/store зависимости, которые могут всплыть при расширении lint/import правил. |

Отдельное замечание: в `MessageBubble.tsx` и `ThinkingIndicator.tsx` есть
импорты вида `@/components/kolibri/KolibriAvatar`, `@/store/useChatStore`,
`@/lib/markdown`, а также пакеты `lucide-react`,
`class-variance-authority`, `react-textarea-autosize`. Текущий ESLint без
import resolver это не проверяет. Это не текущий lint failure, но возможный
следующий пласт, если добавить import/no-unresolved или подключить эти TSX
компоненты к сборке.

## 7. Команды проверки

Базовая проверка текущего gate:

```bash
cd frontend
npm run lint
```

Строгая проверка без warning budget:

```bash
cd frontend
npm exec eslint -- --max-warnings=0 .
```

Проверить, что JSX-файл реально получает config:

```bash
cd frontend
npm exec eslint -- --print-config src/App.jsx
```

Проверить, что TSX-файл не остался вне покрытия после будущего TS config:

```bash
cd frontend
npm exec eslint -- --print-config src/components/MessageBubble.tsx
```

Если вывод `undefined`, TSX по-прежнему не покрыт.

Целевая проверка текущих TSX-заготовок:

```bash
cd frontend
npm exec eslint -- src/components/KolibriAvatar.tsx src/components/MessageBubble.tsx src/components/ThinkingIndicator.tsx
```

Инвентарь lint-зависимостей:

```bash
cd frontend
npm ls eslint @eslint/js eslint-plugin-react-hooks eslint-plugin-react-refresh globals --depth=0
npm ls typescript typescript-eslint @typescript-eslint/parser @typescript-eslint/eslint-plugin --depth=0
```

## 8. Проверки, выполненные в этой ревизии

```text
cd frontend && npm run lint
```

До появления `frontend/eslint.config.js`: failed, exit code `2`, причина -
ESLint 10 не нашел `eslint.config.(js|mjs|cjs)`.

После появления untracked `frontend/eslint.config.js`: passed, exit code `0`,
но с тремя warnings:

```text
frontend/public/service-worker.js:65:12 no-unused-vars
frontend/src/App.jsx:306:7 react-hooks/exhaustive-deps
frontend/src/components/chat/QuickActions.jsx:3:14 react-refresh/only-export-components
```

```text
cd frontend && npm exec eslint -- --max-warnings=0 .
```

Результат: failed, exit code `1`, те же три warnings стали blocking из-за
`--max-warnings=0`.

```text
cd frontend && npm exec eslint -- src/components/KolibriAvatar.tsx src/components/MessageBubble.tsx src/components/ThinkingIndicator.tsx
```

Результат: exit code `0`, но каждый `.tsx` файл выдал warning
`File ignored because no matching configuration was supplied`.

```text
cd frontend && npm ls typescript typescript-eslint @typescript-eslint/parser @typescript-eslint/eslint-plugin --depth=0
```

Результат: exit code `1`, `(empty)`. TypeScript lint toolchain пока не
установлен.
