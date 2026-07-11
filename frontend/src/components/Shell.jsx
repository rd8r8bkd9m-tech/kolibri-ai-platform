import { useMemo, useState } from 'react';
import { Bird } from './Bird.jsx';

export function TopBar({ resolution, lab, setLab, role, setRole, device, setDevice, onCommand, onCascade, onTile, onRestore, onClear }) {
  const canShowDevTools = lab || role === 'owner';
  return <header className="topbar">
    <div className="brand"><Bird size="xs"/><div><strong>Vista OS</strong><span>single-window workbench</span></div></div>
    <div className="globalTitle"><strong>Рабочее пространство</strong><span>чат управляет · окна работают внутри stage</span></div>
    <nav className="topActions" aria-label="Vista controls">
      <span className={resolution.apiStatus === 'offline' ? 'status bad' : 'status ok'}>{resolution.apiStatus === 'offline' ? 'api offline' : 'api online'}</span>
      <button onClick={onCommand} title="Command Center">⌘K</button>
      <button className="iconOnly" onClick={onCascade} title="Каскад">▦</button>
      <button className="iconOnly" onClick={onTile} title="Плиткой">▤</button>
      <button className="iconOnly" onClick={onRestore} title="Восстановить окна">◇</button>
      <button className="iconOnly dangerSoft" onClick={onClear} title="Очистить stage">⌫</button>
      {canShowDevTools ? <button className="labToggle" onClick={() => setLab(!lab)}>DevTools</button> : null}
    </nav>
    {canShowDevTools ? <div className="labbar" data-testid="labbar">
      <label>role<select aria-label="role" value={role} onChange={(e) => setRole(e.target.value)}>{['client','client_pro','operator','server_admin','developer','owner'].map((v) => <option key={v}>{v}</option>)}</select></label>
      <label>device<select aria-label="device" value={device} onChange={(e) => setDevice(e.target.value)}>{['auto','desktop','macbook','ubuntu','mobile','tv'].map((v) => <option key={v}>{v}</option>)}</select></label>
    </div> : null}
  </header>;
}

export function Composer({ value, setValue, onSubmit, prompts }) {
  return <form className="composer" onSubmit={(e) => { e.preventDefault(); onSubmit(value); }}>
    <div className="promptStrip">{prompts.map((p) => <button type="button" key={p} onClick={() => onSubmit(p)}>{p}</button>)}</div>
    <div className="composerLine">
      <button type="button" title="Файлы">＋</button>
      <input aria-label="Vista command" value={value} onChange={(e) => setValue(e.target.value)} placeholder="Скажите, что нужно сделать…"/>
      <button type="button" title="Голос">🎙</button>
      <button type="submit" title="Отправить">↑</button>
    </div>
  </form>;
}

export function AssistantDock({ chat, value, setValue, onSubmit, prompts }) {
  const [open, setOpen] = useState(false);
  const last = chat[chat.length - 1];
  return <section className="assistantLayer" data-testid="assistant-layer" aria-label="Vista assistant control surface">
    {open ? <div className="assistantDrawer" data-testid="chat-timeline">
      <header><div><strong>Диалог Vista</strong><span>Скроллится только лента команд. Окна работают на рабочем столе.</span></div><button onClick={() => setOpen(false)}>Свернуть</button></header>
      <div className="chatTimeline">
        {chat.length ? chat.map((m) => <div key={m.id} className={`bubble ${m.kind}`}><p>{m.text}</p>{m.meta ? <small>{m.meta}</small> : null}</div>) : <div className="chatEmpty"><Bird size="sm"/><strong>Vista слушает</strong><span>Введите задачу — система откроет нужное окно.</span></div>}
      </div>
    </div> : null}
    <div className="assistantDock">
      <button className="assistantPulse" type="button" onClick={() => setOpen(!open)} title="Диалог Vista"><Bird size="xs"/></button>
      {last ? <button className="assistantLast" type="button" onClick={() => setOpen(true)}><span>{last.kind === 'user' ? 'Вы' : 'Vista'}</span><strong>{last.text}</strong></button> : null}
      <Composer value={value} setValue={setValue} onSubmit={onSubmit} prompts={prompts}/>
    </div>
  </section>;
}

function normalize(value) {
  return String(value || '').trim().toLowerCase();
}

export function CommandCenter({ manifest, resolution, role, setRole, device, setDevice, lab, onRun, onClose, commands = [] }) {
  const [query, setQuery] = useState('');
  const safeCommands = commands.length ? commands : ['сделай смету', 'собери КП', 'открой документы', 'помощь'];
  const filtered = useMemo(() => {
    const q = normalize(query);
    return safeCommands.filter((command) => !q || normalize(command).includes(q));
  }, [safeCommands, query]);
  return <div className="overlay" onMouseDown={onClose}>
    <section className="command" onMouseDown={(e) => e.stopPropagation()}>
      <header><div><strong>Vista Control</strong><span>Команды фильтруются по роли. Ctrl/Cmd+K.</span></div><button onClick={onClose}>×</button></header>
      <form onSubmit={(e) => { e.preventDefault(); if (query.trim()) { onRun(query); onClose(); } }}>
        <input className="commandSearch" autoFocus aria-label="Command search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Что открыть или сделать?"/>
      </form>
      <div className="commandGrid">{filtered.map((c) => <button key={c} onClick={() => { onRun(c); onClose(); }}>{c}</button>)}</div>
      {(lab || role === 'owner') ? <div className="labControls"><select value={role} onChange={(e) => setRole(e.target.value)}>{Object.keys(manifest.roles).map((r) => <option key={r}>{r}</option>)}</select><select value={device} onChange={(e) => setDevice(e.target.value)}>{Object.keys(manifest.devices).map((d) => <option key={d}>{d}</option>)}</select></div> : null}
      <footer>{resolution.role.label}: устройство меняет отображение, но не даёт прав.</footer>
    </section>
  </div>;
}
