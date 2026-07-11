const baseGeometry = {
  'estimate.workspace': [72, 42, 900, 620],
  'proposal.preview': [520, 82, 560, 470],
  'artifact.vault': [760, 260, 480, 340],
  'documents.pack': [560, 112, 560, 440],
  'pricing.plans': [600, 132, 560, 390],
  'support.center': [640, 150, 500, 360],
  'task.queue': [76, 48, 760, 560],
  'factory.console': [160, 76, 820, 560],
  'agent.registry': [700, 96, 560, 460],
  'server.metrics': [76, 48, 840, 580],
  'server.logs': [680, 86, 620, 460],
  'node.registry': [780, 280, 520, 350],
  'verifier.gates': [620, 120, 600, 460],
  'api.portal': [92, 54, 860, 600],
  'model.lab': [690, 100, 520, 440],
  'sales.pipeline': [600, 104, 600, 440],
  'market.readiness': [112, 60, 760, 540],
  'system.settings': [620, 96, 560, 430]
};

const DEFAULT_BOUNDS = { width: 1280, height: 720 };
const MIN_W = 360;
const MIN_H = 260;
const PAD = 14;

function uid(prefix = 'w') {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

function boundsOf(bounds) {
  const width = Number(bounds?.width) || DEFAULT_BOUNDS.width;
  const height = Number(bounds?.height) || DEFAULT_BOUNDS.height;
  return { width: Math.max(560, width), height: Math.max(420, height) };
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), Math.max(min, max));
}

export function clampWindow(win, bounds = DEFAULT_BOUNDS) {
  if (win.maximized) return win;
  const b = boundsOf(bounds);
  const w = clamp(Number(win.w) || MIN_W, MIN_W, b.width - PAD * 2);
  const h = clamp(Number(win.h) || MIN_H, MIN_H, b.height - PAD * 2);
  const x = clamp(Number(win.x) || PAD, PAD, b.width - w - PAD);
  const y = clamp(Number(win.y) || PAD, PAD, b.height - h - PAD);
  return { ...win, x, y, w, h };
}

function createWindow(component, index = 0, bounds = DEFAULT_BOUNDS) {
  const [x, y, w, h] = baseGeometry[component.id] || [90 + index * 34, 70 + index * 28, 620, 420];
  return clampWindow({
    uid: uid(component.id.replace(/\W/g, '')),
    componentId: component.id,
    title: component.label,
    component,
    x,
    y,
    w,
    h,
    z: 100 + index,
    minimized: false,
    maximized: false,
    snap: null,
  }, bounds);
}

function topWindowUid(windows) {
  return windows.length ? windows.reduce((a, b) => (a.z > b.z ? a : b)).uid : null;
}

export const initialWorkbench = { windows: [], focused: null, clock: 100, chat: [] };

export function workbenchReducer(state, action) {
  switch (action.type) {
    case 'OPEN_COMPONENTS': {
      const bounds = boundsOf(action.bounds);
      const next = state.windows.map((w) => clampWindow(w, bounds));
      let clock = state.clock + 10;
      for (const component of action.components.filter((c) => c.kind === 'window')) {
        const existing = next.find((w) => w.componentId === component.id);
        if (existing) {
          existing.minimized = false;
          existing.z = clock++;
          existing.maximized = false;
          existing.snap = null;
          Object.assign(existing, clampWindow(existing, bounds));
          continue;
        }
        next.push(createWindow(component, next.length, bounds));
        next[next.length - 1].z = clock++;
      }
      return { ...state, windows: next, focused: topWindowUid(next), clock };
    }
    case 'CHAT':
      return { ...state, chat: [...state.chat.slice(-40), action.message] };
    case 'FOCUS':
      return {
        ...state,
        focused: action.uid,
        windows: state.windows.map((w) => w.uid === action.uid ? { ...w, minimized: false, z: state.clock + 10 } : w),
        clock: state.clock + 11,
      };
    case 'CLOSE':
      return { ...state, windows: state.windows.filter((w) => w.uid !== action.uid), focused: state.focused === action.uid ? null : state.focused };
    case 'CLOSE_FOCUSED': {
      const target = state.focused || topWindowUid(state.windows.filter((w) => !w.minimized));
      return target ? workbenchReducer(state, { type: 'CLOSE', uid: target }) : state;
    }
    case 'MINIMIZE':
      return { ...state, windows: state.windows.map((w) => w.uid === action.uid ? { ...w, minimized: true } : w), focused: state.focused === action.uid ? null : state.focused };
    case 'MINIMIZE_FOCUSED': {
      const target = state.focused || topWindowUid(state.windows.filter((w) => !w.minimized));
      return target ? workbenchReducer(state, { type: 'MINIMIZE', uid: target }) : state;
    }
    case 'MAXIMIZE':
      return {
        ...state,
        windows: state.windows.map((w) => w.uid === action.uid ? { ...w, maximized: !w.maximized, minimized: false, snap: null, z: state.clock + 10 } : w),
        focused: action.uid,
        clock: state.clock + 11,
      };
    case 'MAXIMIZE_FOCUSED': {
      const target = state.focused || topWindowUid(state.windows.filter((w) => !w.minimized));
      return target ? workbenchReducer(state, { type: 'MAXIMIZE', uid: target }) : state;
    }
    case 'MOVE':
      return {
        ...state,
        windows: state.windows.map((w) => w.uid === action.uid ? clampWindow({ ...w, x: action.x, y: action.y, maximized: false, snap: null }, action.bounds) : w),
      };
    case 'RESIZE':
      return {
        ...state,
        windows: state.windows.map((w) => w.uid === action.uid ? clampWindow({ ...w, w: action.w, h: action.h, maximized: false, snap: null }, action.bounds) : w),
      };
    case 'SNAP': {
      const b = boundsOf(action.bounds);
      return {
        ...state,
        focused: action.uid,
        windows: state.windows.map((w) => {
          if (w.uid !== action.uid) return w;
          const half = Math.floor((b.width - PAD * 3) / 2);
          if (action.snap === 'left') return { ...w, x: PAD, y: PAD, w: half, h: b.height - PAD * 2, minimized: false, maximized: false, snap: 'left', z: state.clock + 10 };
          if (action.snap === 'right') return { ...w, x: PAD * 2 + half, y: PAD, w: half, h: b.height - PAD * 2, minimized: false, maximized: false, snap: 'right', z: state.clock + 10 };
          if (action.snap === 'center') return clampWindow({ ...w, x: (b.width - w.w) / 2, y: (b.height - w.h) / 2, minimized: false, maximized: false, snap: null, z: state.clock + 10 }, b);
          return w;
        }),
        clock: state.clock + 11,
      };
    }
    case 'SNAP_FOCUSED': {
      const target = state.focused || topWindowUid(state.windows.filter((w) => !w.minimized));
      return target ? workbenchReducer(state, { type: 'SNAP', uid: target, snap: action.snap, bounds: action.bounds }) : state;
    }
    case 'RESTORE_ALL':
      return { ...state, windows: state.windows.map((w, i) => clampWindow({ ...w, minimized: false, maximized: false, snap: null, z: 100 + i }, action.bounds)), clock: state.clock + 10 };
    case 'CASCADE': {
      const b = boundsOf(action.bounds);
      return {
        ...state,
        windows: state.windows.map((w, i) => clampWindow({ ...w, x: PAD + i * 36, y: PAD + i * 30, z: 100 + i, maximized: false, minimized: false, snap: null }, b)),
        focused: topWindowUid(state.windows),
      };
    }
    case 'TILE': {
      const visible = state.windows.filter((w) => !w.minimized);
      const b = boundsOf(action.bounds);
      const columns = visible.length <= 1 ? 1 : 2;
      const rows = Math.max(1, Math.ceil(visible.length / columns));
      const cellW = Math.floor((b.width - PAD * (columns + 1)) / columns);
      const cellH = Math.floor((b.height - PAD * (rows + 1)) / rows);
      let cursor = 0;
      return {
        ...state,
        windows: state.windows.map((w) => {
          if (w.minimized) return w;
          const col = cursor % columns;
          const row = Math.floor(cursor / columns);
          cursor += 1;
          return { ...w, x: PAD + col * (cellW + PAD), y: PAD + row * (cellH + PAD), w: cellW, h: cellH, maximized: false, snap: null, z: 100 + cursor };
        }),
        clock: state.clock + visible.length + 1,
      };
    }
    case 'CLEAR':
      return { ...state, windows: [], focused: null };
    default:
      return state;
  }
}
