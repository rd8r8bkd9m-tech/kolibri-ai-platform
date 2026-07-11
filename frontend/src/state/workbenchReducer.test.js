import { describe, it, expect } from 'vitest';
import { workbenchReducer, initialWorkbench, clampWindow } from './workbenchReducer.js';

const comp = { id:'estimate.workspace', label:'Смета', kind:'window', owner:'client', required:[], intents:['estimate_start'] };
const comp2 = { id:'proposal.preview', label:'КП', kind:'window', owner:'client', required:[], intents:['proposal_open'] };
const bounds = { width: 1000, height: 700 };

describe('workbench reducer', () => {
  it('opens one window and prevents duplicate component windows', () => {
    const a = workbenchReducer(initialWorkbench, { type:'OPEN_COMPONENTS', components:[comp], bounds });
    const b = workbenchReducer(a, { type:'OPEN_COMPONENTS', components:[comp], bounds });
    expect(a.windows).toHaveLength(1);
    expect(b.windows).toHaveLength(1);
    expect(b.windows[0].minimized).toBe(false);
  });

  it('moves, minimizes and closes windows', () => {
    let s = workbenchReducer(initialWorkbench, { type:'OPEN_COMPONENTS', components:[comp], bounds });
    const uid = s.windows[0].uid;
    s = workbenchReducer(s, { type:'MOVE', uid, x: 100, y: 120, bounds });
    expect(s.windows[0].x).toBeGreaterThanOrEqual(14);
    expect(s.windows[0].x).toBeLessThanOrEqual(bounds.width - s.windows[0].w - 14);
    s = workbenchReducer(s, { type:'MINIMIZE', uid });
    expect(s.windows[0].minimized).toBe(true);
    s = workbenchReducer(s, { type:'CLOSE', uid });
    expect(s.windows).toHaveLength(0);
  });

  it('keeps windows inside the stage bounds', () => {
    let s = workbenchReducer(initialWorkbench, { type:'OPEN_COMPONENTS', components:[comp], bounds });
    const uid = s.windows[0].uid;
    s = workbenchReducer(s, { type:'MOVE', uid, x: -999, y: -999, bounds });
    expect(s.windows[0].x).toBeGreaterThanOrEqual(14);
    expect(s.windows[0].y).toBeGreaterThanOrEqual(14);
    s = workbenchReducer(s, { type:'RESIZE', uid, w: 5000, h: 5000, bounds });
    expect(s.windows[0].w).toBeLessThanOrEqual(bounds.width - 28);
    expect(s.windows[0].h).toBeLessThanOrEqual(bounds.height - 28);
  });

  it('snaps windows left and right', () => {
    let s = workbenchReducer(initialWorkbench, { type:'OPEN_COMPONENTS', components:[comp], bounds });
    const uid = s.windows[0].uid;
    s = workbenchReducer(s, { type:'SNAP', uid, snap:'left', bounds });
    expect(s.windows[0].x).toBe(14);
    expect(s.windows[0].snap).toBe('left');
    s = workbenchReducer(s, { type:'SNAP', uid, snap:'right', bounds });
    expect(s.windows[0].x).toBeGreaterThan(400);
    expect(s.windows[0].snap).toBe('right');
  });

  it('tiles multiple windows', () => {
    let s = workbenchReducer(initialWorkbench, { type:'OPEN_COMPONENTS', components:[comp, comp2], bounds });
    s = workbenchReducer(s, { type:'TILE', bounds });
    expect(s.windows).toHaveLength(2);
    expect(s.windows[0].w).toBeGreaterThan(300);
    expect(s.windows[1].x).toBeGreaterThan(s.windows[0].x);
  });

  it('clamps raw window geometry utility', () => {
    const win = clampWindow({ x:-100, y:-100, w:10000, h:10000 }, bounds);
    expect(win.x).toBe(14);
    expect(win.y).toBe(14);
    expect(win.w).toBeLessThanOrEqual(972);
  });
});
