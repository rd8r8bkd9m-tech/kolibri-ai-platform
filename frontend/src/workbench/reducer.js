const DEFAULT_BOUNDS = { width: 1280, height: 720 };
const MIN_WIDTH = 360;
const MIN_HEIGHT = 260;
const PADDING = 16;

const GEOMETRY = {
  workspace: [48, 28, 1040, 670],
  response: [120, 54, 780, 560],
  pdf: [90, 36, 960, 650],
  estimate: [70, 38, 960, 640],
  artifacts: [690, 190, 510, 390],
  document: [130, 54, 820, 580],
  site: [90, 42, 980, 620],
  app: [90, 42, 980, 620],
};

function makeId(prefix = "window") {
  return `${prefix}_${globalThis.crypto?.randomUUID?.() || `${Date.now()}_${Math.random().toString(16).slice(2)}`}`;
}

function normalizedBounds(bounds) {
  return {
    width: Math.max(560, Number(bounds?.width) || DEFAULT_BOUNDS.width),
    height: Math.max(420, Number(bounds?.height) || DEFAULT_BOUNDS.height),
  };
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), Math.max(min, max));
}

export function clampWindow(windowState, bounds = DEFAULT_BOUNDS) {
  if (windowState.maximized) return windowState;
  const stage = normalizedBounds(bounds);
  const width = clamp(Number(windowState.width) || MIN_WIDTH, MIN_WIDTH, stage.width - PADDING * 2);
  const height = clamp(Number(windowState.height) || MIN_HEIGHT, MIN_HEIGHT, stage.height - PADDING * 2);
  const x = clamp(Number(windowState.x) || PADDING, PADDING, stage.width - width - PADDING);
  const y = clamp(Number(windowState.y) || PADDING, PADDING, stage.height - height - PADDING);
  return { ...windowState, x, y, width, height };
}

function createWindow(payload, index, clock, bounds) {
  const [x, y, width, height] = GEOMETRY[payload.kind] || [96 + index * 34, 58 + index * 28, 720, 500];
  return clampWindow({
    id: payload.id || makeId(payload.kind),
    kind: payload.kind,
    title: payload.title,
    payload,
    x,
    y,
    width,
    height,
    z: clock,
    minimized: false,
    maximized: Boolean(payload.maximized),
  }, bounds);
}

function topWindowId(windows) {
  const visible = windows.filter((item) => !item.minimized);
  return visible.length ? visible.reduce((left, right) => left.z > right.z ? left : right).id : null;
}

function belongsToProject(windowState, projectId) {
  const payload = windowState.payload || {};
  return payload.projectId === projectId
    || payload.parentProjectId === projectId
    || windowState.id === `workspace:${projectId}`
    || windowState.id === `estimate:${projectId}`;
}

export const initialWorkbench = {
  windows: [],
  focusedId: null,
  clock: 100,
};

export function workbenchReducer(state, action) {
  switch (action.type) {
    case "OPEN": {
      const payload = action.window;
      const existing = state.windows.find((item) => payload.id && item.id === payload.id);
      const clock = state.clock + 10;
      if (existing) {
        return {
          ...state,
          clock,
          focusedId: existing.id,
          windows: state.windows.map((item) => item.id === existing.id
            ? { ...item, title: payload.title || item.title, payload, minimized: false, z: clock }
            : item),
        };
      }
      const next = createWindow(payload, state.windows.length, clock, action.bounds);
      return { ...state, windows: [...state.windows, next], focusedId: next.id, clock };
    }
    case "UPDATE":
      return {
        ...state,
        windows: state.windows.map((item) => item.id === action.id
          ? { ...item, title: action.window?.title || item.title, payload: { ...item.payload, ...action.window } }
          : item),
      };
    case "FOCUS": {
      const clock = state.clock + 10;
      return {
        ...state,
        focusedId: action.id,
        clock,
        windows: state.windows.map((item) => item.id === action.id ? { ...item, minimized: false, z: clock } : item),
      };
    }
    case "CLOSE":
    case "DEACTIVATE": {
      const windows = state.windows.filter((item) => item.id !== action.id);
      return { ...state, windows, focusedId: topWindowId(windows) };
    }
    case "REMOVE_PROJECT_WINDOWS": {
      const windows = state.windows.filter((item) => !belongsToProject(item, action.projectId));
      return { ...state, windows, focusedId: topWindowId(windows) };
    }
    case "MINIMIZE": {
      const windows = state.windows.map((item) => item.id === action.id ? { ...item, minimized: true } : item);
      return { ...state, windows, focusedId: topWindowId(windows) };
    }
    case "MAXIMIZE": {
      const clock = state.clock + 10;
      return {
        ...state,
        clock,
        focusedId: action.id,
        windows: state.windows.map((item) => item.id === action.id
          ? { ...item, maximized: !item.maximized, minimized: false, z: clock }
          : item),
      };
    }
    case "MOVE":
      return {
        ...state,
        windows: state.windows.map((item) => item.id === action.id
          ? clampWindow({ ...item, x: action.x, y: action.y, maximized: false }, action.bounds)
          : item),
      };
    case "RESIZE":
      return {
        ...state,
        windows: state.windows.map((item) => item.id === action.id
          ? clampWindow({ ...item, width: action.width, height: action.height, maximized: false }, action.bounds)
          : item),
      };
    case "RESTORE_ALL":
      return {
        ...state,
        windows: state.windows.map((item, index) => clampWindow({
          ...item,
          minimized: false,
          maximized: false,
          x: PADDING + index * 34,
          y: PADDING + index * 28,
          z: 100 + index,
        }, action.bounds)),
      };
    case "CLEAR":
      return initialWorkbench;
    default:
      return state;
  }
}
