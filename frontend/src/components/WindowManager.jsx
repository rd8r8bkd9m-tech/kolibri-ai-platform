import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { WindowContent } from '../windows/WindowContent.jsx';
import { Bird } from './Bird.jsx';

function useStageBounds(ref) {
  const [bounds, setBounds] = useState({ width: 1280, height: 720 });
  useLayoutEffect(() => {
    if (!ref.current) return undefined;
    const measure = () => {
      const rect = ref.current.getBoundingClientRect();
      setBounds({ width: Math.max(560, Math.floor(rect.width)), height: Math.max(420, Math.floor(rect.height)) });
    };
    measure();
    const ResizeObserverCtor = globalThis.ResizeObserver;
    let ro = null;
    if (ResizeObserverCtor) {
      ro = new ResizeObserverCtor(measure);
      ro.observe(ref.current);
    }
    window.addEventListener('resize', measure);
    return () => { if (ro) ro.disconnect(); window.removeEventListener('resize', measure); };
  }, [ref]);
  return bounds;
}

export function Workbench({ windows, minimized, dispatch, device }) {
  const stageRef = useRef(null);
  const bounds = useStageBounds(stageRef);
  const mobile = device.id === 'mobile' || window.innerWidth < 760;
  const tv = device.id === 'tv' || window.innerWidth > 1800;

  if (tv) {
    return <section className="tvCanvas" data-testid="tv-canvas">
      <div className="tvTitle"><Bird size="md"/><div><strong>Vista OS</strong><span>TV/Kiosk board</span></div></div>
      <div className="tvCards">
        {windows.slice(0, 4).map((w) => <button key={w.uid} onClick={() => dispatch({ type: 'FOCUS', uid: w.uid })}><span>{w.component.owner}</span><strong>{w.title}</strong></button>)}
      </div>
    </section>;
  }

  if (mobile) {
    return <section className="mobileCanvas" data-testid="mobile-canvas">
      {windows.slice(-1).map((w) => <MobileSheet key={w.uid} win={w} dispatch={dispatch}/>)}
      {!windows.length ? <Empty/> : null}
    </section>;
  }

  const visible = windows.filter((w) => !w.minimized);
  return <section className="canvas" ref={stageRef} data-testid="workbench-canvas">
    <div className="stageGrid" aria-hidden="true" />
    {visible.map((w) => <WindowFrame key={w.uid} win={w} dispatch={dispatch} bounds={bounds} focused={w.z === Math.max(...visible.map(v => v.z))}/>) }
    {!visible.length ? <Empty/> : null}
    {minimized.length ? <MinimizedDock minimized={minimized} dispatch={dispatch}/> : null}
  </section>;
}

function Empty() {
  return <div className="empty"><Bird size="md"/><h1>Vista Workbench</h1><p>Скажите задачу или нажмите ⌘K — Vista откроет нужное окно внутри одной операционной среды.</p></div>;
}

function MinimizedDock({ minimized, dispatch }) {
  return <div className="dock" data-testid="minimized-dock">
    {minimized.map((w) => <button key={w.uid} onClick={() => dispatch({ type: 'FOCUS', uid: w.uid })}>{w.title}</button>)}
  </div>;
}

function WindowFrame({ win, dispatch, bounds, focused }) {
  const [gesture, setGesture] = useState(null);

  useEffect(() => {
    if (!gesture) return undefined;
    const move = (event) => {
      event.preventDefault();
      if (gesture.kind === 'drag') {
        dispatch({ type: 'MOVE', uid: win.uid, x: event.clientX - gesture.dx, y: event.clientY - gesture.dy, bounds });
      }
      if (gesture.kind === 'resize') {
        dispatch({ type: 'RESIZE', uid: win.uid, w: event.clientX - gesture.left, h: event.clientY - gesture.top, bounds });
      }
    };
    const up = () => setGesture(null);
    window.addEventListener('pointermove', move, { passive: false });
    window.addEventListener('pointerup', up);
    window.addEventListener('pointercancel', up);
    return () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      window.removeEventListener('pointercancel', up);
    };
  }, [gesture, win.uid, dispatch, bounds]);

  const style = win.maximized
    ? { left: 14, top: 14, width: 'calc(100% - 28px)', height: 'calc(100% - 28px)', zIndex: win.z }
    : { left: win.x, top: win.y, width: win.w, height: win.h, zIndex: win.z };

  function startDrag(event) {
    if (event.button !== 0 || win.maximized) return;
    const rect = event.currentTarget.closest('.window').getBoundingClientRect();
    setGesture({ kind: 'drag', dx: event.clientX - rect.left, dy: event.clientY - rect.top });
    dispatch({ type: 'FOCUS', uid: win.uid });
  }

  function startResize(event) {
    if (event.button !== 0 || win.maximized) return;
    event.stopPropagation();
    const rect = event.currentTarget.closest('.window').getBoundingClientRect();
    setGesture({ kind: 'resize', left: rect.left, top: rect.top });
    dispatch({ type: 'FOCUS', uid: win.uid });
  }

  return <article
    className={`window ${win.maximized ? 'max' : ''} ${focused ? 'focused' : ''}`}
    style={style}
    onPointerDown={() => dispatch({ type: 'FOCUS', uid: win.uid })}
    data-testid={`window-${win.componentId}`}
  >
    <header className="windowBar" onPointerDown={startDrag} onDoubleClick={() => dispatch({ type: 'MAXIMIZE', uid: win.uid })}>
      <div className="traffic" aria-hidden="true"><i/><i/><i/></div>
      <div className="windowTitle"><strong>{win.title}</strong><span>{win.componentId}</span></div>
      <nav className="windowTools" aria-label="Window controls">
        <button title="Snap left" onClick={(e) => { e.stopPropagation(); dispatch({ type: 'SNAP', uid: win.uid, snap: 'left', bounds }); }}>◧</button>
        <button title="Snap right" onClick={(e) => { e.stopPropagation(); dispatch({ type: 'SNAP', uid: win.uid, snap: 'right', bounds }); }}>◨</button>
        <button title="Minimize" onClick={(e) => { e.stopPropagation(); dispatch({ type: 'MINIMIZE', uid: win.uid }); }}>—</button>
        <button title="Maximize" onClick={(e) => { e.stopPropagation(); dispatch({ type: 'MAXIMIZE', uid: win.uid }); }}>□</button>
        <button title="Close" onClick={(e) => { e.stopPropagation(); dispatch({ type: 'CLOSE', uid: win.uid }); }}>×</button>
      </nav>
    </header>
    <div className="windowBody"><WindowContent id={win.componentId}/></div>
    {!win.maximized ? <button aria-label="resize" className="resize" onPointerDown={startResize}>◢</button> : null}
  </article>;
}

function MobileSheet({ win, dispatch }) {
  return <article className="sheet" data-testid={`window-${win.componentId}`}>
    <header><strong>{win.title}</strong><button onClick={() => dispatch({ type: 'CLOSE', uid: win.uid })}>Закрыть</button></header>
    <WindowContent id={win.componentId}/>
  </article>;
}
