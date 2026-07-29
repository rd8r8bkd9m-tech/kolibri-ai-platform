import {
  KOLIBRI_GENERATIVE_UI_COMPONENT_NAMES,
  KOLIBRI_GENERATIVE_UI_CONTAINER_NAMES,
  KOLIBRI_GENERATIVE_UI_LIMITS,
  isKolibriGenerativeUIComponentName,
  kolibriGenerativeUIComponentSchemas,
  type KolibriGenerativeUIComponentName,
} from "./schema";

export type SanitizedGenerativeUINode =
  | string
  | number
  | boolean
  | null
  | SanitizedGenerativeUIElement
  | SanitizedGenerativeUINode[];

export type SanitizedGenerativeUIElement = {
  readonly $type: KolibriGenerativeUIComponentName;
  readonly $key?: string | number;
  readonly children?: SanitizedGenerativeUINode;
  readonly [prop: string]: unknown;
};

export type GenerativeUISanitizationResult =
  | { readonly ok: true; readonly value: SanitizedGenerativeUINode }
  | {
      readonly ok: false;
      readonly error: {
        readonly code:
          | "not-json"
          | "unsafe-key"
          | "invalid-tree"
          | "unknown-component"
          | "invalid-props"
          | "limit-exceeded";
        readonly message: string;
      };
    };

export type GenerativeUISanitizationErrorCode =
  | "not-json"
  | "unsafe-key"
  | "invalid-tree"
  | "unknown-component"
  | "invalid-props"
  | "limit-exceeded";

type ValidationState = {
  nodes: number;
  textCharacters: number;
  readonly seen: WeakSet<object>;
};

class SanitizationFailure extends Error {
  readonly code: GenerativeUISanitizationErrorCode;

  constructor(
    code: GenerativeUISanitizationErrorCode,
    message: string,
  ) {
    super(message);
    this.name = "SanitizationFailure";
    this.code = code;
  }
}

const FORBIDDEN_KEYS = new Set([
  "__proto__",
  "prototype",
  "constructor",
  "dangerouslySetInnerHTML",
  "innerHTML",
  "outerHTML",
  "className",
  "style",
  "href",
  "src",
  "url",
  "uri",
  "target",
  "action",
  "formAction",
]);

const RESERVED_NODE_KEYS = new Set(["$type", "$key", "children"]);
const CONTROL_CHARACTERS = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g;

const fail = (
  code: GenerativeUISanitizationErrorCode,
  message: string,
): never => {
  throw new SanitizationFailure(code, message);
};

function isForbiddenKey(key: string): boolean {
  return (
    FORBIDDEN_KEYS.has(key) ||
    /^on/i.test(key) ||
    (key.startsWith("$") && !RESERVED_NODE_KEYS.has(key))
  );
}

function assertSafeOwnProperties(value: object): string[] {
  let prototype: object | null;
  let descriptors: PropertyDescriptorMap;
  let keys: (string | symbol)[];

  try {
    prototype = Object.getPrototypeOf(value);
    descriptors = Object.getOwnPropertyDescriptors(value);
    keys = Reflect.ownKeys(value);
  } catch {
    return fail("not-json", "Значение нельзя безопасно прочитать как JSON.");
  }

  if (Array.isArray(value)) {
    if (prototype !== Array.prototype) {
      return fail("not-json", "Массив должен быть обычным JSON-массивом.");
    }
    for (const key of keys) {
      const descriptor = typeof key === "string" ? descriptors[key] : undefined;
      if (
        typeof key !== "string" ||
        (key !== "length" && !/^(0|[1-9]\d*)$/.test(key)) ||
        (key !== "length" &&
          (!descriptor ||
            !descriptor.enumerable ||
            descriptor.get !== undefined ||
            descriptor.set !== undefined))
      ) {
        return fail("not-json", "Массив содержит не-JSON свойство.");
      }
    }
    return keys.filter((key): key is string => key !== "length");
  }

  if (prototype !== Object.prototype && prototype !== null) {
    return fail("not-json", "Объект должен быть обычным JSON-объектом.");
  }

  const stringKeys: string[] = [];
  for (const key of keys) {
    if (typeof key !== "string") {
      return fail("not-json", "Символьные свойства не разрешены.");
    }
    const descriptor = descriptors[key];
    if (
      !descriptor ||
      !descriptor.enumerable ||
      descriptor.get !== undefined ||
      descriptor.set !== undefined
    ) {
      return fail("not-json", "Объект содержит не-JSON свойство.");
    }
    if (key.length > KOLIBRI_GENERATIVE_UI_LIMITS.maxKeyLength) {
      return fail("limit-exceeded", "Имя свойства слишком длинное.");
    }
    if (isForbiddenKey(key)) {
      return fail("unsafe-key", "Небезопасное свойство интерфейса запрещено.");
    }
    stringKeys.push(key);
  }
  return stringKeys;
}

function assertJSONValue(
  value: unknown,
  depth: number,
  state: ValidationState,
): void {
  if (depth > KOLIBRI_GENERATIVE_UI_LIMITS.maxDepth + 2) {
    return fail("limit-exceeded", "JSON-структура слишком глубокая.");
  }

  if (value === null || typeof value === "boolean") return;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      return fail("not-json", "Числа должны быть конечными.");
    }
    return;
  }
  if (typeof value === "string") {
    if (value.length > KOLIBRI_GENERATIVE_UI_LIMITS.maxTextLength) {
      return fail("limit-exceeded", "Текст интерфейса слишком длинный.");
    }
    return;
  }
  if (
    value === undefined ||
    typeof value === "function" ||
    typeof value === "symbol" ||
    typeof value === "bigint"
  ) {
    return fail("not-json", "Интерфейс должен состоять только из JSON-значений.");
  }
  if (typeof value !== "object") {
    return fail("not-json", "Интерфейс должен состоять только из JSON-значений.");
  }
  if (state.seen.has(value)) {
    return fail("not-json", "Циклические или повторно используемые объекты запрещены.");
  }
  state.seen.add(value);

  const keys = assertSafeOwnProperties(value);
  if (
    !Array.isArray(value) &&
    keys.length > KOLIBRI_GENERATIVE_UI_LIMITS.maxObjectEntries
  ) {
    return fail("limit-exceeded", "Объект содержит слишком много свойств.");
  }

  if (Array.isArray(value)) {
    if (value.length > KOLIBRI_GENERATIVE_UI_LIMITS.maxChildrenPerNode) {
      return fail("limit-exceeded", "В узле слишком много дочерних элементов.");
    }
    for (let index = 0; index < value.length; index += 1) {
      if (!Object.hasOwn(value, index)) {
        return fail("not-json", "Разреженные массивы не разрешены.");
      }
      assertJSONValue(value[index], depth + 1, state);
    }
    return;
  }

  for (const key of keys) {
    assertJSONValue(
      (value as Record<string, unknown>)[key],
      depth + 1,
      state,
    );
  }
}

function sanitizeString(
  value: string,
  state: ValidationState,
): string {
  state.textCharacters += value.length;
  if (
    state.textCharacters >
    KOLIBRI_GENERATIVE_UI_LIMITS.maxTotalTextLength
  ) {
    return fail("limit-exceeded", "Общий объём текста интерфейса слишком велик.");
  }
  return value.replace(CONTROL_CHARACTERS, "");
}

function sanitizeNode(
  value: unknown,
  depth: number,
  state: ValidationState,
): SanitizedGenerativeUINode {
  if (depth > KOLIBRI_GENERATIVE_UI_LIMITS.maxDepth) {
    return fail("limit-exceeded", "Дерево интерфейса слишком глубокое.");
  }
  state.nodes += 1;
  if (state.nodes > KOLIBRI_GENERATIVE_UI_LIMITS.maxNodes) {
    return fail("limit-exceeded", "Дерево интерфейса содержит слишком много узлов.");
  }

  if (value === null || typeof value === "boolean") return value;
  if (typeof value === "string") return sanitizeString(value, state);
  if (typeof value === "number") return value;

  if (Array.isArray(value)) {
    return value.map((child) => sanitizeNode(child, depth + 1, state));
  }

  if (typeof value !== "object" || value === null) {
    return fail("invalid-tree", "Узел интерфейса имеет неверный формат.");
  }

  const source = value as Record<string, unknown>;
  const type = source["$type"];
  if (typeof type !== "string") {
    return fail("invalid-tree", "У компонента отсутствует строковый $type.");
  }
  if (!isKolibriGenerativeUIComponentName(type)) {
    return fail("unknown-component", "Компонент не входит в библиотеку Kolibri.");
  }

  const allowedProps = new Set(
    Object.keys(kolibriGenerativeUIComponentSchemas[type].shape),
  );
  const rawProps: Record<string, unknown> = {};
  for (const key of Object.keys(source)) {
    if (RESERVED_NODE_KEYS.has(key)) continue;
    if (!allowedProps.has(key)) {
      return fail("invalid-props", "Компонент содержит неподдерживаемое свойство.");
    }
    rawProps[key] = source[key];
  }

  const parsedProps =
    kolibriGenerativeUIComponentSchemas[type].safeParse(rawProps);
  if (!parsedProps.success) {
    return fail("invalid-props", "Свойства компонента не прошли проверку.");
  }

  const sanitized: Record<string, unknown> = { $type: type };
  for (const [key, propValue] of Object.entries(parsedProps.data)) {
    sanitized[key] =
      typeof propValue === "string"
        ? sanitizeString(propValue, state)
        : propValue;
  }

  const stableKey = source["$key"];
  if (stableKey !== undefined) {
    if (
      !(
        (typeof stableKey === "string" &&
          stableKey.length > 0 &&
          stableKey.length <=
            KOLIBRI_GENERATIVE_UI_LIMITS.maxStableKeyLength) ||
        (typeof stableKey === "number" && Number.isSafeInteger(stableKey))
      )
    ) {
      return fail("invalid-tree", "Стабильный ключ узла имеет неверный формат.");
    }
    sanitized["$key"] =
      typeof stableKey === "string"
        ? sanitizeString(stableKey, state)
        : stableKey;
  }

  const children = source["children"];
  if (children !== undefined) {
    if (!KOLIBRI_GENERATIVE_UI_CONTAINER_NAMES.has(type)) {
      return fail("invalid-tree", "Этот компонент не принимает дочерние узлы.");
    }
    sanitized["children"] = sanitizeNode(children, depth + 1, state);
  }

  return sanitized as SanitizedGenerativeUIElement;
}

export function sanitizeKolibriGenerativeUI(
  input: unknown,
): GenerativeUISanitizationResult {
  const jsonState: ValidationState = {
    nodes: 0,
    textCharacters: 0,
    seen: new WeakSet(),
  };

  try {
    assertJSONValue(input, 0, jsonState);
    const value = sanitizeNode(input, 0, {
      nodes: 0,
      textCharacters: 0,
      seen: new WeakSet(),
    });
    return { ok: true, value };
  } catch (error) {
    if (error instanceof SanitizationFailure) {
      return {
        ok: false,
        error: { code: error.code, message: error.message },
      };
    }
    return {
      ok: false,
      error: {
        code: "invalid-tree",
        message: "Дерево интерфейса не удалось безопасно проверить.",
      },
    };
  }
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function canonicalizeNativeNode(input: unknown): unknown {
  if (
    input === null ||
    typeof input === "string" ||
    typeof input === "number" ||
    typeof input === "boolean"
  ) {
    return input;
  }
  if (Array.isArray(input)) {
    return input.map(canonicalizeNativeNode);
  }
  if (!isPlainRecord(input)) {
    return fail("invalid-tree", "Нативный узел имеет неверный формат.");
  }

  const component = input["component"];
  if (typeof component !== "string") {
    return fail("invalid-tree", "У нативного узла отсутствует component.");
  }
  const allowedKeys = new Set(["component", "props", "children", "key"]);
  if (Object.keys(input).some((key) => !allowedKeys.has(key))) {
    return fail("invalid-tree", "Нативный узел содержит лишнее свойство.");
  }

  const props = input["props"];
  if (props !== undefined && !isPlainRecord(props)) {
    return fail("invalid-props", "Свойства нативного узла имеют неверный формат.");
  }

  const canonical: Record<string, unknown> = { $type: component };
  for (const [key, value] of Object.entries(props ?? {})) {
    if (
      RESERVED_NODE_KEYS.has(key) ||
      key.startsWith("$") ||
      isForbiddenKey(key)
    ) {
      return fail("unsafe-key", "Небезопасное свойство интерфейса запрещено.");
    }
    canonical[key] = value;
  }

  if (input["key"] !== undefined) canonical["$key"] = input["key"];
  if (input["children"] !== undefined) {
    canonical["children"] = canonicalizeNativeNode(input["children"]);
  }
  return canonical;
}

/**
 * Converts assistant-ui core's native `{ component, props, children }` spec
 * (or a complete `generative-ui` part) to Kolibri's canonical `$type` tree,
 * then applies the same strict validation used by the present-tool renderer.
 */
export function parseNativeKolibriGenerativeUI(
  input: unknown,
): GenerativeUISanitizationResult {
  try {
    assertJSONValue(input, 0, {
      nodes: 0,
      textCharacters: 0,
      seen: new WeakSet(),
    });

    let root: unknown = input;
    if (isPlainRecord(input) && input["type"] === "generative-ui") {
      const allowedPartKeys = new Set(["type", "spec", "id", "parentId"]);
      if (Object.keys(input).some((key) => !allowedPartKeys.has(key))) {
        return fail("invalid-tree", "Нативная часть содержит лишнее свойство.");
      }
      const spec = input["spec"];
      if (
        !isPlainRecord(spec) ||
        Object.keys(spec).length !== 1 ||
        !Object.hasOwn(spec, "root")
      ) {
        return fail("invalid-tree", "Нативная спецификация имеет неверный формат.");
      }
      root = spec["root"];
    } else if (
      isPlainRecord(input) &&
      Object.keys(input).length === 1 &&
      Object.hasOwn(input, "root")
    ) {
      root = input["root"];
    }

    return sanitizeKolibriGenerativeUI(canonicalizeNativeNode(root));
  } catch (error) {
    if (error instanceof SanitizationFailure) {
      return {
        ok: false,
        error: { code: error.code, message: error.message },
      };
    }
    return {
      ok: false,
      error: {
        code: "invalid-tree",
        message: "Нативное дерево интерфейса не удалось безопасно проверить.",
      },
    };
  }
}

export const KOLIBRI_GENERATIVE_UI_ALLOWED_TYPES =
  KOLIBRI_GENERATIVE_UI_COMPONENT_NAMES;
