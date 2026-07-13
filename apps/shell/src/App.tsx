import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { Bird } from './components/Bird'
import { ProjectSheet } from './components/ProjectSheet'
import { WorkTrace } from './components/WorkTrace'
import { FilesIcon, HistoryIcon } from './components/Icons'
import { DocumentsCanvas } from './features/DocumentsCanvas'
import { EstimateCanvas } from './features/EstimateCanvas'
import { Artifact, Capability, Estimate, Message, Project, bootstrap, createEstimate, createProject, createStreamingResponse, deleteProject, listArtifacts, listEstimates, listMessages, listProjects } from './api/client'

type Surface='estimate'|'documents'|null

export function App(){
 const [ready,setReady]=useState(false);const [error,setError]=useState('');const [projects,setProjects]=useState<Project[]>([]);const [active,setActive]=useState<Project|null>(null);const [messages,setMessages]=useState<Message[]>([]);const [capabilities,setCapabilities]=useState<Capability[]>([]);const [input,setInput]=useState('');const [status,setStatus]=useState('idle');const [trace,setTrace]=useState<string[]>([]);const [traceOpen,setTraceOpen]=useState(false);const [projectsOpen,setProjectsOpen]=useState(false);const [toolOpen,setToolOpen]=useState(false);const [surface,setSurface]=useState<Surface>(null);const [estimate,setEstimate]=useState<Estimate|null>(null);const [artifacts,setArtifacts]=useState<Artifact[]>([]);const [streamingText,setStreamingText]=useState('');const scrollRef=useRef<HTMLDivElement>(null)
 const empty=messages.length===0&&!surface
 useEffect(()=>{void initialize()},[])
 useEffect(()=>{const node=scrollRef.current;if(!node)return;if(typeof node.scrollTo==='function')node.scrollTo({top:node.scrollHeight,behavior:'smooth'});else node.scrollTop=node.scrollHeight},[messages,streamingText])
 async function initialize(){try{const boot=await bootstrap();setProjects(boot.projects);setActive(boot.active_project);setCapabilities(boot.capabilities);setMessages((await listMessages(boot.active_project.id)).data);setReady(true)}catch(e){setError(e instanceof Error?e.message:String(e))}}
 async function refreshProject(project:Project){setActive(project);setMessages((await listMessages(project.id)).data);const estimates=(await listEstimates(project.id)).data;setEstimate(estimates[0]||null);setSurface(null);setProjectsOpen(false)}
 async function ensureEstimate(){if(!active)throw new Error('Нет активного проекта');let next=(await listEstimates(active.id)).data[0];if(!next)next=await createEstimate(active.id,`Смета: ${active.title}`);setEstimate(next);return next}
 async function openEstimate(){try{await ensureEstimate();setSurface('estimate');setToolOpen(false)}catch(e){setError(e instanceof Error?e.message:String(e))}}
 async function openDocuments(){try{const next=estimate||await ensureEstimate();setArtifacts((await listArtifacts(next.id)).data);setEstimate(next);setSurface('documents');setToolOpen(false)}catch(e){setError(e instanceof Error?e.message:String(e))}}
 async function submit(event?:FormEvent){event?.preventDefault();const text=input.trim();if(!text||!active||status==='working')return;setInput('');setError('');setStatus('working');setTrace(['Задача принята','Проверяю доступные capability engines']);setStreamingText('');setMessages(prev=>[...prev,{id:`local-${Date.now()}`,role:'user',content:text,created_at:new Date().toISOString()}]);try{await createStreamingResponse(active.id,text,(ev)=>{if(ev.type==='response.work_summary.updated'&&typeof ev.summary==='string')setTrace(prev=>[...prev,ev.summary as string]);if(ev.type==='response.output_text.delta'&&typeof ev.delta==='string')setStreamingText(prev=>prev+ev.delta);if(ev.type==='response.artifact.ready'&&ev.kind==='estimate'){void openEstimate()}if(ev.type==='response.artifact.ready'&&ev.kind==='estimate_documents'){void openDocuments()}if(ev.type==='response.completed'){setStatus('ready')}});setMessages((await listMessages(active.id)).data);setStreamingText('');setTrace(prev=>[...prev,'Результат сохранён в проекте']);setStatus('ready')}catch(e){setError(e instanceof Error?e.message:String(e));setStatus('idle')}}
 const quick=useMemo(()=>capabilities.map(c=>c.id).includes('estimates')?['Сделай смету на ремонт квартиры 72 м²','Открой документы проекта']:['Продолжи текущую задачу'],[capabilities])
 if(!ready)return <div className="boot"><Bird state="planning"/><p>{error||'Открываю проект…'}</p></div>
 return <div className={`kolibri-app ${surface?'kolibri-app--surface':''}`}>
  <header className="system-bar"><div className="control-slot">{empty?<button className="hamburger" onClick={()=>setProjectsOpen(true)} aria-label="Открыть проекты"><span/><span/></button>:<Bird compact state={status==='working'?'working':status==='ready'?'ready':'idle'} onClick={()=>setTraceOpen(true)}/>}</div><button className="project-title" onClick={()=>setProjectsOpen(true)}><strong>{active?.title}</strong><span>Один проект · один диалог</span></button><div className="system-actions"><span className={`live-dot live-dot--${status}`}/><button className="ghost" onClick={()=>setTraceOpen(true)}>Ход работы</button></div></header>
  <main className="workspace">
   <aside className="rail" aria-label="Системная панель"><button onClick={()=>setProjectsOpen(true)} aria-label="История проектов"><HistoryIcon/></button><button onClick={openDocuments} aria-label="Файлы проекта"><FilesIcon/></button></aside>
   <section className="conversation">
    <div className="conversation-scroll" ref={scrollRef}>
     {empty?<div className="empty-state"><Bird state="idle" onClick={()=>document.getElementById('composer')?.focus()}/><h1>Что создадим?</h1><p>Kolibri продолжает одну работу внутри проекта и показывает только доказанные инструменты.</p><div className="suggestions">{quick.map(text=><button key={text} onClick={()=>setInput(text)}>{text}</button>)}</div></div>:<div className="messages">{messages.map(message=><article className={`message message--${message.role}`} key={message.id}><span>{message.role==='user'?'Вы':'Kolibri'}</span><p>{message.content}</p></article>)}{streamingText&&<article className="message message--assistant"><span>Kolibri</span><p>{streamingText}<i className="caret"/></p></article>}</div>}
    </div>
    <form className="composer" onSubmit={submit}><div className="tool-anchor"><button type="button" className="plus" onClick={()=>setToolOpen(v=>!v)} aria-label="Инструменты">+</button>{toolOpen&&<div className="tool-menu"><button type="button" onClick={openEstimate}>Смета</button><button type="button" onClick={openDocuments}>Документы</button><p>Показываются только работающие инструменты.</p></div>}</div><textarea id="composer" value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();void submit()}}} placeholder="Сообщение для Kolibri" rows={1}/><button className="send" disabled={!input.trim()||status==='working'} aria-label="Отправить">↑</button></form>
   </section>
   {surface&&<div className="surface-host">{surface==='estimate'&&estimate&&<EstimateCanvas estimate={estimate} onChange={setEstimate} onDocuments={openDocuments} onClose={()=>setSurface(null)}/>} {surface==='documents'&&estimate&&<DocumentsCanvas estimate={estimate} artifacts={artifacts} onClose={()=>setSurface(null)}/>}</div>}
  </main>
  <ProjectSheet open={projectsOpen} projects={projects} activeId={active?.id||''} onSelect={p=>void refreshProject(p)} onCreate={()=>void createProject().then(async p=>{setProjects((await listProjects()).data);await refreshProject(p)})} onDelete={p=>void deleteProject(p.id).then(async()=>{const next=(await listProjects()).data;setProjects(next);if(p.id===active?.id&&next[0])await refreshProject(next[0])})} onClose={()=>setProjectsOpen(false)}/>
  <WorkTrace open={traceOpen} stages={trace} status={status==='working'?'Работаю':status==='ready'?'Готово':'Ожидаю'} onClose={()=>setTraceOpen(false)}/>
  {error&&<div className="global-error" role="alert">{error}<button onClick={()=>setError('')}>×</button></div>}
 </div>
}
