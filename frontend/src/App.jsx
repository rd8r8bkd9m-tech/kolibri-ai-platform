import { useEffect, useMemo, useState } from 'react';
import { api } from './api/client.js';
import { Bird } from './components/Bird.jsx';
import { appCatalog, AppFrame, AssistantComposer, ChatDrawer, CommandPalette, Dock, SystemBar } from './components/SystemShell.jsx';
import { HomeApp } from './apps/HomeApp.jsx';
import { EstimateApp } from './apps/EstimateApp.jsx';
import { DocumentsApp } from './apps/DocumentsApp.jsx';
import { FactoryApp } from './apps/FactoryApp.jsx';
import { ServersApp } from './apps/ServersApp.jsx';
import { DeveloperApp } from './apps/DeveloperApp.jsx';
import { SettingsApp } from './apps/SettingsApp.jsx';
import { PublicShare } from './apps/PublicShare.jsx';

const roleApps={
 client:['home','estimate','documents','settings'],client_pro:['home','estimate','documents','settings'],
 operator:['home','factory','settings'],server_admin:['home','servers','factory','settings'],
 developer:['home','developer','settings'],owner:['home','estimate','documents','factory','servers','developer','settings']
};
const suggestions={
 client_pro:['создай новую смету','сформируй документы','открой мои документы'],
 client:['создай новую смету','открой документы'],operator:['покажи фабрику','очередь задач'],
 server_admin:['покажи серверы','покажи фабрику'],developer:['открой API','создай API key'],
 owner:['создай новую смету','покажи фабрику','покажи серверы']
};
const componentApp={'estimate.workspace':'estimate','proposal.preview':'documents','artifact.vault':'documents','documents.pack':'documents','task.queue':'factory','factory.console':'factory','agent.registry':'factory','server.metrics':'servers','server.logs':'servers','node.registry':'servers','api.portal':'developer','model.lab':'developer','system.settings':'settings'};
const makeId=()=>crypto.randomUUID?.()||`${Date.now()}_${Math.random()}`;
function boot(){const p=new URLSearchParams(location.search);return{entered:p.get('entered')==='1'||localStorage.getItem('vista.entered')==='1',role:p.get('role')||'client_pro',device:p.get('device')||'auto',adminToken:p.get('admin')||'',reset:p.get('reset')==='1'}}
function isConnectionError(error){return error instanceof TypeError||/network|fetch failed|failed to fetch|connection/i.test(String(error?.message||''))}

export function App(){
 const shareMatch=location.pathname.match(/^\/share\/([^/]+)/); if(shareMatch)return <PublicShare token={shareMatch[1]}/>;
 const initial=useMemo(boot,[]);
 const [entered,setEntered]=useState(initial.entered);
 const [role,setRole]=useState(initial.role);
 const [session,setSession]=useState(api.session());
 const [apiStatus,setApiStatus]=useState('connecting');
 const [activeApp,setActiveApp]=useState('home');
 const [minimized,setMinimized]=useState([]);
 const [commandOpen,setCommandOpen]=useState(false);
 const [chatOpen,setChatOpen]=useState(false);
 const [messages,setMessages]=useState([]);
 const [command,setCommand]=useState('');
 const [estimate,setEstimate]=useState(null);
 const [estimates,setEstimates]=useState([]);
 const [artifacts,setArtifacts]=useState([]);
 const [toast,setToast]=useState(null);
 const apps=(roleApps[role]||roleApps.client).map(appId=>appCatalog[appId]);
 const roleSuggestions=suggestions[role]||suggestions.client;
 const lastAssistant=[...messages].reverse().find(message=>message.kind==='assistant')?.text;
 function notify(text,type='ok'){setToast({text,type});window.setTimeout(()=>setToast(null),3500)}
 function upsertEstimate(next){
   setEstimate(next);
   setArtifacts(next?.artifacts||[]);
   if(!next)return;
   setEstimates(current=>[next,...current.filter(item=>item.id!==next.id)]);
 }
 function startNewEstimate(){setEstimate(null);setArtifacts([]);setActiveApp('estimate');setMinimized(value=>value.filter(item=>item!=='estimate'))}
 async function selectEstimate(estimateId){
   try{const next=await api.getEstimate(estimateId);upsertEstimate(next);setActiveApp('estimate')}
   catch(error){notify(error.message,'error')}
 }
 function documentsReady(nextArtifacts){setArtifacts(nextArtifacts||[]);setActiveApp('documents')}

 useEffect(()=>{if(!entered)return;let alive=true;(async()=>{try{
   if(initial.reset)api.clearSession();
   let current=api.session();
   if(current&&api.token()){
     try{current=await api.getSession(current.id)}catch{api.clearSession();current=null}
   }
   if(!current){const created=await api.createSession({role,device:initial.device,adminToken:initial.adminToken||undefined});current=created.session}
   if(!alive)return;
   setSession(current);setRole(current.role);setMessages(Array.isArray(current.chat)?current.chat:[]);setApiStatus('online');
   const allowed=roleApps[current.role]||roleApps.client;
   const saved=current.windows?.[0]?.component_id;
   if(saved&&allowed.includes(saved))setActiveApp(saved);
   const list=await api.listEstimates();
   if(!alive)return;
   setEstimates(list);
   const preferredId=current.active_estimate_id||list[0]?.id;
   if(preferredId){
     try{const active=await api.getEstimate(preferredId);if(alive){setEstimate(active);setArtifacts(active.artifacts||[])}}
     catch{if(alive){setEstimate(null);setArtifacts([])}}
   }
  }catch(error){if(alive){setApiStatus('offline');notify(error.message,'error')}}})();return()=>{alive=false}},[entered]);

 useEffect(()=>{if(!entered||!session?.id||apiStatus!=='online')return;const timer=window.setTimeout(()=>{
   api.patchSession(session.id,{active_estimate_id:estimate?.id||null,windows:[{component_id:activeApp}],chat:messages.slice(-100)})
    .then(next=>setSession(current=>current?.id===next.id?next:current)).catch(()=>{});
 },450);return()=>window.clearTimeout(timer)},[entered,session?.id,apiStatus,activeApp,estimate?.id,messages]);

 useEffect(()=>{const handler=event=>{
   if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==='k'){event.preventDefault();setCommandOpen(true)}
   if(event.key==='Escape'){setCommandOpen(false);setChatOpen(false)}
 };window.addEventListener('keydown',handler);return()=>window.removeEventListener('keydown',handler)},[]);

 async function runCommand(text){
   const clean=String(text||'').trim();if(!clean)return;
   setCommand('');setMessages(value=>[...value,{id:makeId(),kind:'user',text:clean}]);
   try{
     const result=await api.resolve({text:clean,device:initial.device});
     const next=result.components?.map(component=>componentApp[component.id]).find(Boolean);
     const wantsNewEstimate=/(?:созд|сдел|нов)[^\n]{0,24}смет/i.test(clean);
     if(wantsNewEstimate&&apps.some(app=>app.id==='estimate'))startNewEstimate();
     else if(next&&apps.some(app=>app.id===next))setActiveApp(next);
     if(/сформ|документ|\bкп\b/i.test(clean)&&estimate?.items?.length){
       const docs=await api.generateDocuments(estimate.id);setArtifacts(docs.artifacts);setActiveApp('documents');
     }
     setMessages(value=>[...value,{id:makeId(),kind:'assistant',text:result.assistant||'Готово',meta:next?`Открыто: ${appCatalog[next]?.label}`:''}]);
     setApiStatus('online');
   }catch(error){
     if(isConnectionError(error))setApiStatus('offline');
     setMessages(value=>[...value,{id:makeId(),kind:'assistant',text:'Не удалось выполнить команду',meta:error.message}]);
     notify(error.message,'error');
   }
 }

 async function generateDocs(){
   if(!estimate?.items?.length){notify('Добавьте работы в смету','error');setActiveApp('estimate');return}
   try{const result=await api.generateDocuments(estimate.id);const current=await api.getEstimate(estimate.id);upsertEstimate(current);setArtifacts(result.artifacts);setActiveApp('documents');notify('Документы сформированы и проверены')}
   catch(error){notify(error.message,'error')}
 }
 function selectApp(appId){setActiveApp(appId);setMinimized(value=>value.filter(item=>item!==appId))}
 function minimize(){if(activeApp==='home')return;setMinimized(value=>[...new Set([...value,activeApp])]);setActiveApp('home')}
 function close(){setActiveApp('home')}
 function renderApp(){
   const common={onToast:notify};
   switch(activeApp){
     case'estimate':return <EstimateApp estimate={estimate} onEstimate={upsertEstimate} onDocuments={documentsReady} {...common}/>;
     case'documents':return <DocumentsApp estimate={estimate} artifacts={artifacts} onArtifacts={setArtifacts} onGenerate={generateDocs} {...common}/>;
     case'factory':return <FactoryApp {...common}/>;
     case'servers':return <ServersApp {...common}/>;
     case'developer':return <DeveloperApp {...common}/>;
     case'settings':return <SettingsApp role={role} session={session} apiStatus={apiStatus}/>;
     default:return <HomeApp estimate={estimate} estimates={estimates} onCreate={startNewEstimate} onOpenEstimate={()=>setActiveApp('estimate')} onOpenDocuments={()=>setActiveApp('documents')} onSelectEstimate={selectEstimate}/>;
   }
 }

 if(!entered)return <main className="vistaBoot"><div className="bootGlow one"/><div className="bootGlow two"/><button aria-label="Открыть Vista" onClick={()=>{localStorage.setItem('vista.entered','1');setEntered(true)}}><Bird size="hero"/></button><span>Нажмите, чтобы начать</span></main>;
 return <main className="vistaOS">
  <SystemBar activeApp={activeApp} apiStatus={apiStatus} role={role} onCommand={()=>setCommandOpen(true)} onChat={()=>setChatOpen(true)} onProfile={()=>selectApp('settings')}/>
  <section className="osStage"><AppFrame appId={activeApp} onMinimize={minimize} onClose={close}>{renderApp()}</AppFrame></section>
  <Dock apps={apps} activeApp={activeApp} minimized={minimized} onSelect={selectApp}/>
  <AssistantComposer value={command} setValue={setCommand} onSubmit={runCommand} onChat={()=>setChatOpen(true)} lastMessage={lastAssistant} suggestions={roleSuggestions}/>
  <ChatDrawer open={chatOpen} onClose={()=>setChatOpen(false)} messages={messages} suggestions={roleSuggestions}/>
  <CommandPalette open={commandOpen} onClose={()=>setCommandOpen(false)} apps={apps} onSelect={selectApp} onRun={runCommand}/>
  {toast?<div className={`vistaToast ${toast.type}`} role="status" aria-live="polite"><IconFallback type={toast.type}/><span>{toast.text}</span></div>:null}
 </main>;
}
function IconFallback({type}){return <span className="toastMark">{type==='error'?'!':'✓'}</span>}
