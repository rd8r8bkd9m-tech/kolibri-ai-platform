import type { Artifact, Estimate } from '../api/client'
type Props={estimate:Estimate;artifacts:Artifact[];onClose:()=>void}
function size(value:number){return value>1024?`${(value/1024).toFixed(1)} КБ`:`${value} Б`}
export function DocumentsCanvas({estimate,artifacts,onClose}:Props){return <section className="canvas documents-canvas" aria-label="Документы проекта" data-testid="documents-canvas">
 <header className="canvas__header"><div><span className="eyebrow">Материализованные артефакты</span><h2>Документы · revision {estimate.revision}</h2></div><button className="icon-button" onClick={onClose}>×</button></header>
 <div className="documents-intro"><div><span className={`status status--${estimate.status}`}>{estimate.status}</span><h3>{estimate.title}</h3><p>Каждый файл имеет реальные bytes, MIME, размер и SHA-256.</p></div><strong>{new Intl.NumberFormat('ru-RU').format(Number(estimate.total))} ₽</strong></div>
 <div className="artifact-list">{artifacts.length===0?<div className="empty-documents">Документы ещё не сформированы.</div>:artifacts.map(artifact=><article key={artifact.id}><div className="file-mark">{artifact.name.split('.').pop()?.toUpperCase()}</div><div><strong>{artifact.name}</strong><span>{artifact.mime_type} · {size(artifact.size)}</span><code>{artifact.sha256.slice(0,20)}…</code></div><a className="secondary" href={`/v1/artifacts/${artifact.id}/content`} download={artifact.name}>Скачать</a></article>)}</div>
 </section>}
