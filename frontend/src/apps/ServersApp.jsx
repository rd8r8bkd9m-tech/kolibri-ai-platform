import { useEffect, useState } from 'react';
import { api } from '../api/client.js';

export function ServersApp({ onToast }) {
  const [nodes,setNodes]=useState([]); const [health,setHealth]=useState(null); const [loading,setLoading]=useState(true);
  useEffect(()=>{Promise.all([api.nodes(),api.fleetHealth()]).then(([n,h])=>{setNodes(n);setHealth(h)}).catch(e=>onToast(e.message,'error')).finally(()=>setLoading(false))},[]);
  if(loading) return <div className="appLoading">Собираю состояние серверов…</div>;
  return <section className="serversApp"><header className="appSectionHeader"><div><span className="eyebrow">FLEET</span><h1>Серверы и ноды</h1><p>Состояние, нагрузка и доступная worker-ёмкость.</p></div><span className="healthPill">{health?.summary?.online || 0} online</span></header>
    <div className="serverCards">{nodes.map(n=><article key={n.id}><header><div><span className={`nodeDot node-${n.status}`}/><strong>{n.id}</strong></div><em>{n.mode}</em></header><p>{n.hostname} · {n.role}</p><div className="resourceBars"><Resource label="CPU" value={n.cpu}/><Resource label="RAM" value={n.ram}/><Resource label="DISK" value={n.disk}/></div><footer><span>Workers {n.workers_busy}/{n.workers_total}</span><span>{n.status}</span></footer></article>)}</div>
  </section>;
}
function Resource({label,value=0}){return <div><span>{label}</span><i><b style={{width:`${Math.min(100,Math.max(0,value))}%`}}/></i><em>{Math.round(value)}%</em></div>}
