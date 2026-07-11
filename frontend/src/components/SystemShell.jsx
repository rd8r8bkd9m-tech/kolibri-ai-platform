import { useEffect, useMemo, useRef, useState } from 'react';
import { Bird } from './Bird.jsx';
import { Icon } from '../ui/Icons.jsx';

export const appCatalog = {
  home: { id:'home', label:'Главная', icon:'home', title:'Рабочее пространство' },
  estimate: { id:'estimate', label:'Смета', icon:'estimate', title:'Смета объекта' },
  documents: { id:'documents', label:'Документы', icon:'documents', title:'Документы объекта' },
  factory: { id:'factory', label:'Фабрика', icon:'factory', title:'Factory Control' },
  servers: { id:'servers', label:'Серверы', icon:'servers', title:'Серверы и ноды' },
  developer: { id:'developer', label:'API', icon:'developer', title:'Developer Platform' },
  settings: { id:'settings', label:'Настройки', icon:'settings', title:'Настройки Vista' },
};
const roleLabels={client:'Клиент',client_pro:'Клиент Pro',operator:'Оператор',server_admin:'Администратор',developer:'Разработчик',owner:'Владелец'};

export function SystemBar({ activeApp, apiStatus, role, onCommand, onChat, onProfile }) {
  return <header className="systemBar">
    <div className="systemBrand"><Bird size="xs"/><div><strong>Vista</strong><span>Единое рабочее пространство</span></div></div>
    <div className="systemContext"><strong>{appCatalog[activeApp]?.title || 'Vista'}</strong><span>{roleLabels[role]||role}</span></div>
    <div className="systemActions"><span className={`connection connection-${apiStatus}`}><i/>{apiStatus === 'online' ? 'Синхронизировано' : apiStatus === 'connecting' ? 'Подключение…' : 'Нет связи'}</span><button onClick={onChat} title="Диалог" aria-label="Открыть диалог"><Icon name="chat"/></button><button onClick={onCommand} className="commandKey" title="Команды" aria-label="Открыть команды"><Icon name="command"/><kbd>⌘K</kbd></button><button className="profileButton" onClick={onProfile} title="Настройки профиля" aria-label="Открыть настройки"><Icon name="settings"/></button></div>
  </header>;
}

export function Dock({ apps, activeApp, minimized = [], onSelect }) {
  return <nav className="vistaDock" aria-label="Приложения Vista">
    {apps.map(app => <button key={app.id} className={`${activeApp===app.id?'active':''} ${minimized.includes(app.id)?'minimized':''}`} onClick={()=>onSelect(app.id)} title={app.label} aria-current={activeApp===app.id?'page':undefined}><Icon name={app.icon}/><span>{app.label}</span></button>)}
  </nav>;
}

export function AppFrame({ appId, children, onMinimize, onClose }) {
  const app = appCatalog[appId] || appCatalog.home;
  return <article className="appFrame" data-testid={`app-${appId}`}>
    <header className="appFrameBar"><div className="appFrameIdentity"><div className="appIcon"><Icon name={app.icon}/></div><div><strong>{app.title}</strong><span>Vista · {app.label}</span></div></div>{appId!=='home'?<div className="appFrameTools"><button onClick={onMinimize} title="Свернуть" aria-label="Свернуть приложение"><Icon name="minimize"/></button><button onClick={onClose} title="Закрыть" aria-label="Закрыть приложение"><Icon name="close"/></button></div>:null}</header>
    <div className="appFrameBody">{children}</div>
  </article>;
}

export function AssistantComposer({ value, setValue, onSubmit, onChat, lastMessage, suggestions }) {
  function submit(event){event?.preventDefault();const clean=value.trim();if(clean)onSubmit(clean)}
  return <div className="assistantComposer">
    <button className="assistantButton" onClick={onChat} title="Открыть диалог" aria-label="Открыть диалог с Vista"><Bird size="xs"/></button>
    <form onSubmit={submit} className="composerForm">
      <input aria-label="Команда Vista" value={value} onChange={event=>setValue(event.target.value)} placeholder="Что нужно сделать?" autoComplete="off"/>
      <button type="submit" className="sendButton" aria-label="Отправить" disabled={!value.trim()}><Icon name="send"/></button>
    </form>
    {lastMessage ? <button className="assistantHint" onClick={onChat}><span>Vista</span><strong>{lastMessage}</strong></button> : null}
    {suggestions?.length ? <div className="composerSuggestions">{suggestions.slice(0,3).map(suggestion=><button key={suggestion} onClick={()=>onSubmit(suggestion)}>{suggestion}</button>)}</div>:null}
  </div>;
}

export function ChatDrawer({ open, onClose, messages, suggestions = [] }) {
  const ref=useRef(null);
  useEffect(()=>{if(open&&ref.current)ref.current.scrollTop=ref.current.scrollHeight},[open,messages]);
  if(!open)return null;
  return <div className="drawerBackdrop" onMouseDown={event=>event.target===event.currentTarget&&onClose()}>
    <aside className="chatDrawer" role="dialog" aria-modal="true" aria-label="Диалог с Vista"><header><div><Bird size="xs"/><div><strong>Диалог с Vista</strong><span>Команды управляют текущим рабочим пространством</span></div></div><button onClick={onClose} aria-label="Закрыть диалог"><Icon name="close"/></button></header><div className="chatMessages" ref={ref}>{messages.length?messages.map(message=><div className={`chatMessage ${message.kind}`} key={message.id}><span>{message.kind==='user'?'Вы':'Vista'}</span><p>{message.text}</p>{message.meta?<small>{message.meta}</small>:null}</div>):<div className="chatWelcome"><Bird size="md"/><strong>Чем помочь?</strong><span>{suggestions.length?`Например: «${suggestions.slice(0,2).join('» или «')}».`:'Опишите задачу своими словами.'}</span></div>}</div></aside>
  </div>;
}

export function CommandPalette({ open, onClose, apps, onSelect, onRun }) {
  const [query,setQuery]=useState('');
  useEffect(()=>{if(open)setQuery('')},[open]);
  const items=useMemo(()=>apps.filter(app=>`${app.label} ${app.title}`.toLowerCase().includes(query.toLowerCase())),[apps,query]);
  if(!open)return null;
  return <div className="paletteBackdrop" onMouseDown={event=>event.target===event.currentTarget&&onClose()}><section className="commandPalette" role="dialog" aria-modal="true" aria-label="Команды Vista"><header><Icon name="command"/><input autoFocus value={query} onChange={event=>setQuery(event.target.value)} onKeyDown={event=>{if(event.key==='Enter'&&query.trim()){onRun(query);onClose()}if(event.key==='Escape')onClose()}} placeholder="Команда или приложение…"/><kbd>esc</kbd></header><div className="paletteItems"><span className="paletteLabel">Доступно вам</span>{items.map(app=><button key={app.id} onClick={()=>{onSelect(app.id);onClose()}}><div className="appIcon"><Icon name={app.icon}/></div><div><strong>{app.label}</strong><span>{app.title}</span></div><em>Открыть</em></button>)}{!items.length&&query?<button className="paletteRun" onClick={()=>{onRun(query);onClose()}}><div className="appIcon"><Icon name="send"/></div><div><strong>Выполнить команду</strong><span>{query}</span></div><em>Enter</em></button>:null}</div></section></div>;
}
