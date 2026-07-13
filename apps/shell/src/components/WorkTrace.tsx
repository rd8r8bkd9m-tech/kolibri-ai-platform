type Props={ open:boolean; stages:string[]; status:string; onClose:()=>void }
export function WorkTrace({open,stages,status,onClose}:Props){
  if(!open) return null
  return <aside className="trace" role="dialog" aria-modal="false" aria-label="Ход работы">
    <div className="trace__head"><div><span className="eyebrow">Безопасный ход работы</span><strong>{status}</strong></div><button onClick={onClose} aria-label="Закрыть">×</button></div>
    <ol>{stages.map((stage,index)=><li key={`${stage}-${index}`}><span>{index+1}</span><p>{stage}</p></li>)}</ol>
    <p className="trace__note">Скрытые рассуждения, секреты и внутренние prompts не отображаются.</p>
  </aside>
}
