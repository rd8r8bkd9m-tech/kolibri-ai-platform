import { useEffect, useState } from 'react';
import { api } from '../api/client.js';
import { Bird } from '../components/Bird.jsx';
import { Icon } from '../ui/Icons.jsx';

const money=v=>new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',maximumFractionDigits:0}).format(v||0);
const labels={proposal_pdf:'Коммерческое предложение',estimate_xlsx:'Смета XLSX',proposal_docx:'Предложение DOCX',estimate_json:'Данные JSON',assumptions_md:'Допущения'};
export function PublicShare({token}){
 const [data,setData]=useState(null);const [error,setError]=useState('');const [downloading,setDownloading]=useState('');
 useEffect(()=>{api.publicShare(token).then(setData).catch(e=>setError(e.message))},[token]);
 async function download(artifact){setDownloading(artifact.id);try{await api.publicDownloadArtifact(token,artifact)}catch(e){setError(e.message)}finally{setDownloading('')}}
 if(error)return <main className="publicPage"><div className="publicError"><Bird size="md"/><h1>Ссылка недоступна</h1><p>{error}</p></div></main>;
 if(!data)return <main className="publicPage"><div className="publicLoading">Открываю предложение…</div></main>;
 const e=data.estimate;
 return <main className="publicPage"><header className="publicBrand"><Bird size="xs"/><strong>Vista</strong><span>Проверенное предложение</span></header><article className="publicProposal"><span className="eyebrow">КОММЕРЧЕСКОЕ ПРЕДЛОЖЕНИЕ</span><h1>{e.project.name}</h1><p>{e.client.name} · {e.city} · версия {e.version}</p><strong className="publicTotal">{money(e.summary.total)}</strong><div className="publicTable"><header><span>Работа</span><span>Кол-во</span><span>Цена</span><span>Сумма</span></header>{e.items.map(i=><div key={i.id}><strong>{i.name}</strong><span>{i.qty} {i.unit}</span><span>{money(i.price)}</span><span>{money(i.qty*i.price*i.coef)}</span></div>)}</div>{data.artifacts?.length?<section className="publicDocuments"><h2>Документы</h2><div>{data.artifacts.map(a=><button key={a.id} onClick={()=>download(a)} disabled={downloading===a.id}><Icon name="download"/><span><strong>{labels[a.kind]||a.name}</strong><small>{a.name}</small></span><em>{downloading===a.id?'Загрузка…':'Скачать'}</em></button>)}</div></section>:null}<footer><span>Документы созданы и проверены в Vista OS</span><strong>Ссылка до {new Date(data.expires_at).toLocaleDateString('ru-RU')}</strong></footer></article></main>
}
