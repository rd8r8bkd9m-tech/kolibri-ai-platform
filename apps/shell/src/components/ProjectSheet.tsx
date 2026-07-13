import type { Project } from '../api/client'
type Props={open:boolean;projects:Project[];activeId:string;onSelect:(p:Project)=>void;onCreate:()=>void;onDelete:(p:Project)=>void;onClose:()=>void}
export function ProjectSheet({open,projects,activeId,onSelect,onCreate,onDelete,onClose}:Props){
 if(!open) return null
 return <div className="sheet-backdrop" onMouseDown={onClose}><section className="project-sheet" role="dialog" aria-modal="true" aria-label="Проекты" onMouseDown={e=>e.stopPropagation()}>
  <header><div><span className="eyebrow">История</span><h2>Проекты</h2></div><button className="icon-button" onClick={onClose}>×</button></header>
  <button className="primary wide" onClick={onCreate}>Новый проект</button>
  <div className="project-list">{projects.map(project=><article key={project.id} className={project.id===activeId?'active':''}>
   <button className="project-main" onClick={()=>onSelect(project)}><strong>{project.title}</strong><span>{new Date(project.updated_at).toLocaleString('ru-RU')}</span></button>
   <button className="danger-ghost" onClick={()=>onDelete(project)} aria-label={`Удалить ${project.title}`}>Удалить</button>
  </article>)}</div>
 </section></div>
}
