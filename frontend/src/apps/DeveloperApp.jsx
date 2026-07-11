import { useEffect, useState } from 'react';
import { api } from '../api/client.js';
import { Icon } from '../ui/Icons.jsx';

export function DeveloperApp({ onToast }) {
  const [info,setInfo]=useState(null); const [keys,setKeys]=useState([]); const [created,setCreated]=useState(null);
  const load=()=>Promise.all([api.developerCompatibility(),api.developerKeys()]).then(([i,k])=>{setInfo(i);setKeys(k)}).catch(e=>onToast(e.message,'error'));
  useEffect(()=>{load()},[]);
  async function createKey(){try{const result=await api.createDeveloperKey({name:'Vista SDK key',scopes:['openai.proxy']});setCreated(result);await load();}catch(e){onToast(e.message,'error')}}
  if(!info) return <div className="appLoading">Открываю Developer Platform…</div>;
  return <section className="developerApp"><header className="appSectionHeader"><div><span className="eyebrow">DEVELOPER PLATFORM</span><h1>OpenAI-compatible API</h1><p>Единая точка доступа к OpenAI REST и Realtime через ключ Vista.</p></div><button className="primaryButton" onClick={createKey}><Icon name="add"/>Создать API key</button></header>
    {created?.key?<div className="secretBanner"><strong>Скопируйте ключ сейчас</strong><code>{created.key}</code></div>:null}
    <div className="apiHero"><span>Base URL</span><code>{location.origin}/v1</code><p>{info.rest}</p></div>
    <div className="developerGrid"><article><strong>Responses</strong><code>POST /v1/responses</code><p>Streaming и tool calls передаются upstream без изменения формата.</p></article><article><strong>Realtime</strong><code>WS /v1/realtime</code><p>WebSocket gateway с Vista session/API key.</p></article><article><strong>Models & Files</strong><code>GET /v1/models</code><p>Все OpenAI /v1 REST paths поддерживаются прозрачным proxy.</p></article></div>
    <div className="keysList"><h3>Ключи проекта</h3>{keys.map(k=><div key={k.id}><code>{k.key_prefix}••••••</code><span>{k.name}</span><em>{k.status}</em></div>)}</div>
  </section>;
}
