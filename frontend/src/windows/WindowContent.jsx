
import { useEffect, useState } from 'react';
import { api } from '../api/client.js';
import { rub, recalculateEstimate } from './estimateMath.js';

export function WindowContent({ id }) {
  if (id === 'estimate.workspace') return <EstimateWindow/>;
  if (id === 'proposal.preview') return <ProposalWindow/>;
  if (id === 'artifact.vault') return <ArtifactsWindow/>;
  if (id === 'documents.pack') return <DocumentsWindow/>;
  if (id === 'pricing.plans') return <PricingWindow/>;
  if (id === 'support.center') return <SupportWindow/>;
  if (id === 'task.queue') return <FactoryQueueWindow/>;
  if (id === 'factory.console') return <FactoryConsoleWindow/>;
  if (id === 'agent.registry') return <AgentsWindow/>;
  if (id === 'server.metrics') return <ServerMetricsWindow/>;
  if (id === 'server.logs') return <ServerLogsWindow/>;
  if (id === 'node.registry') return <NodeRegistryWindow/>;
  if (id === 'verifier.gates') return <GatesWindow/>;
  if (id === 'api.portal') return <ApiPortalWindow/>;
  if (id === 'model.lab') return <ModelLabWindow/>;
  if (id === 'sales.pipeline') return <SalesPipelineWindow/>;
  if (id === 'market.readiness') return <MarketReadinessWindow/>;
  if (id === 'system.settings') return <SettingsWindow/>;
  return <OverviewWindow/>;
}

function useAsync(factory, initial, deps = []) {
  const [state, setState] = useState(initial);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  useEffect(()=>{ let ok=true; setLoading(true); setError(null); factory().then(v=>{ if(ok) setState(v); }).catch(err=>{ if(ok) setError(err); }).finally(()=>{ if(ok) setLoading(false); }); return ()=>{ ok=false; }; }, deps);
  return [state, setState, loading, error];
}
function ErrorBox({ error }) { return <section className="errorBox"><strong>Backend недоступен</strong><p>{error?.message || 'Не удалось загрузить данные.'}</p><small>Запустите ./scripts/dev-fone.sh, чтобы поднять Vista API и frontend вместе.</small></section>; }

function EstimateWindow() {
  const [estimate, setEstimate, loading, error] = useAsync(() => api.getActiveEstimate(), null);
  const [draft, setDraft] = useState({ section:'Работы', name:'Новая позиция', unit:'шт', qty:1, price:10000, coef:1 });
  if (error) return <ErrorBox error={error}/>;
  if (loading || !estimate) return <Loading/>;
  async function addItem() { const next = await api.addEstimateItem(estimate.id, draft); setEstimate(next); setDraft({ ...draft, name:'Новая позиция', qty:1, price:10000 }); }
  async function change(item, patch) { const optimistic = recalculateEstimate({ ...estimate, items: estimate.items.map(i => i.id === item.id ? { ...i, ...patch } : i) }); setEstimate(optimistic); const next = await api.updateEstimateItem(estimate.id, item.id, patch); setEstimate(next); }
  async function remove(item) { const next = await api.deleteEstimateItem(estimate.id, item.id); setEstimate(next); }
  return <section className="estimateWindow"><header className="total"><div><span>{estimate.project.name}</span><strong>{rub(estimate.summary.total)}</strong><em>{estimate.city} · версия {estimate.version} · {estimate.status}</em></div><button onClick={addItem}>Добавить позицию</button></header><div className="estimateTable"><div className="thead"><span>Раздел</span><span>Работа</span><span>Кол-во</span><span>Цена</span><span>Коэф.</span><span>Итого</span></div>{estimate.items.map(item => <div className="trow" key={item.id}><span>{item.section}</span><input value={item.name} onChange={e=>change(item,{name:e.target.value})}/><input type="number" value={item.qty} onChange={e=>change(item,{qty:Number(e.target.value)})}/><input type="number" value={item.price} onChange={e=>change(item,{price:Number(e.target.value)})}/><input type="number" step="0.05" value={item.coef} onChange={e=>change(item,{coef:Number(e.target.value)})}/><b>{rub(Number(item.qty)*Number(item.price)*Number(item.coef||1))}</b><button className="linkDanger" onClick={()=>remove(item)}>Удалить</button></div>)}</div><div className="addLine"><input value={draft.section} onChange={e=>setDraft({...draft,section:e.target.value})}/><input value={draft.name} onChange={e=>setDraft({...draft,name:e.target.value})}/><input type="number" value={draft.qty} onChange={e=>setDraft({...draft,qty:Number(e.target.value)})}/><input type="number" value={draft.price} onChange={e=>setDraft({...draft,price:Number(e.target.value)})}/></div><footer className="summary"><span>Работы: {rub(estimate.summary.subtotal)}</span><span>Накладные: {rub(estimate.summary.overhead)}</span><span>Прибыль: {rub(estimate.summary.margin)}</span><strong>Итого: {rub(estimate.summary.total)}</strong></footer></section>;
}
function ProposalWindow() { const [proposal,,loading] = useAsync(()=>api.proposal(), null); if (loading || !proposal) return <Loading/>; return <section className="cardStack"><header><strong>{proposal.title}</strong><span>{proposal.client} · действительно {proposal.valid_days} дней</span></header><div className="metricStrip"><div className="metric"><span>Итого</span><strong>{rub(proposal.total)}</strong></div><div className="metric"><span>Статус</span><strong>{proposal.status}</strong></div></div><Two title="Оплата" items={proposal.payment}/><Two title="Этапы" items={proposal.timeline}/><button className="primary">{proposal.cta}</button></section>; }
function ArtifactsWindow() { const [items,,loading,error] = useAsync(()=>api.artifacts(), []); if (error) return <ErrorBox error={error}/>; if (loading) return <Loading/>; return <section className="list"><h3>Клиентские артефакты</h3>{items.filter(a=>a.visibility==='client').map(a=><div key={a.id}><span>{a.kind}</span><strong>{a.name}</strong><a className="buttonLink" href={api.artifactDownloadUrl(a.id)}>Скачать</a></div>)}</section>; }
function DocumentsWindow() { return <section className="list"><h3>Документы</h3>{['Акт выполненных работ','Договор подряда','Коммерческое предложение','Список материалов'].map(x=><div key={x}><span>готово</span><strong>{x}</strong><button>Открыть</button></div>)}</section>; }
function PricingWindow() { return <section className="pricing"><article><span>Start</span><strong>29 000 ₽/мес</strong><p>До 10 смет, PDF и КП.</p></article><article><span>Pro</span><strong>79 000 ₽/мес</strong><p>До 100 смет, документы и оператор.</p></article><article><span>Factory</span><strong>от 249 000 ₽/мес</strong><p>Операторская станция, роли и серверный контур.</p></article></section>; }
function SupportWindow() { return <section className="cardStack"><header><strong>Поддержка</strong><span>Создать обращение или передать оператору</span></header><textarea defaultValue="Нужно уточнить смету по материалам"/><button className="primary">Создать обращение</button></section>; }
function ServerMetricsWindow() { const [data,,loading] = useAsync(api.serverMetrics, null); if (loading || !data) return <Loading/>; return <section><div className="metricStrip">{Object.entries(data.summary).map(([k,v])=><div className="metric" key={k}><span>{k}</span><strong>{v}</strong></div>)}</div><div className="serverGrid">{data.nodes.map(n=><article key={n.id} className="server"><header><strong>{n.id}</strong><em>{n.status}</em></header><span>CPU {n.cpu}%</span><span>RAM {n.ram}%</span><span>DISK {n.disk}%</span><span>{n.workers}</span></article>)}</div></section>; }
function ServerLogsWindow() { const [logs,,loading,error] = useAsync(api.serverLogs, []); if (error) return <ErrorBox error={error}/>; if (loading) return <Loading/>; return <section className="list"><h3>Логи / audit events</h3>{logs.map((l,i)=><div key={i}><span>{l.level}</span><strong>{l.service}</strong><em>{l.text}</em></div>)}</section>; }
function NodeRegistryWindow() { const [nodes,,loading,error] = useAsync(api.nodes, []); if (error) return <ErrorBox error={error}/>; if (loading) return <Loading/>; return <section className="list"><h3>Реестр нод</h3>{nodes.map(n=><div key={n.id}><span>{n.role} · {n.mode}</span><strong>{n.id}</strong><em>{n.status} · workers {n.workers_busy}/{n.workers_total}</em></div>)}</section>; }
function FactoryQueueWindow() { const [task,setTask] = useState(null); const [tasks,setTasks,loading] = useAsync(api.factoryTasks, []); async function run() { const result = await api.executeFactoryTask({ title:'Vista real factory health task', kind:'health_probe'}); setTask(result); setTasks(await api.factoryTasks()); } return <section className="cardStack"><header><strong>Очередь фабрики</strong><span>controlled pipeline</span></header><p>Задачи создаются в persistent queue, получают lease, пишут artifact и проходят verifier.</p><button className="primary" onClick={run}>Поставить и выполнить health task</button>{task ? <div className="eventLog">{task.events.map(e=><code key={`${e.event}-${e.id || e.ts}`}>{e.event}</code>)}<strong>{task.artifact?.name || task.task?.artifact_path || 'artifact uploaded'}</strong></div> : null}<div className="list compact"><h3>История задач</h3>{loading ? <Loading/> : tasks.slice(0,6).map(t=><div key={t.id}><span>{t.state}</span><strong>{t.title}</strong><em>{t.artifact_path}</em></div>)}</div></section>; }
function FactoryConsoleWindow() { const [stats,,loading,error] = useAsync(api.factoryStats, null); if (error) return <ErrorBox error={error}/>; if (loading || !stats) return <Loading/>; return <section className="cardStack"><header><strong>Factory Control</strong><span>persistent queue / lease manager</span></header><div className="metricStrip"><div className="metric"><span>nodes</span><strong>{stats.nodes}</strong></div><div className="metric"><span>queued</span><strong>{stats.states.queued || 0}</strong></div><div className="metric"><span>completed</span><strong>{stats.states.completed || 0}</strong></div><div className="metric"><span>events</span><strong>{stats.events}</strong></div></div></section>; }
function AgentsWindow() { const [roles,,loading] = useAsync(api.roles, {}); if (loading) return <Loading/>; return <section className="roleCloud"><h3>Роли агентов</h3>{Object.values(roles).map(r=><span key={r.id}>{r.label}</span>)}</section>; }
function GatesWindow() { const [gates,,loading] = useAsync(api.gates, []); if (loading) return <Loading/>; return <section className="list"><h3>Quality gates</h3>{gates.map(g=><div key={g.gate}><span>{g.state}</span><strong>{g.gate}</strong><em>tested</em></div>)}</section>; }
function ApiPortalWindow() { return <section className="api"><article><strong>OS</strong><code>POST /api/os/resolve</code><code>POST /api/os/session</code></article><article><strong>Estimates</strong><code>GET /api/estimates</code><code>POST /api/estimates/:id/items</code></article><article><strong>Factory</strong><code>POST /api/factory/tasks/execute</code><code>GET /api/factory/events</code></article></section>; }
function ModelLabWindow() { return <section className="cardStack"><header><strong>Model Lab</strong><span>LLM routing / FormulaLM / evals</span></header><div className="tileGrid"><span>routing policy</span><span>formula queue</span><span>eval runs</span><span>safety gates</span></div></section>; }
function SalesPipelineWindow() { return <section className="pipeline">{['Лид','Бриф','Смета','КП','Пилот','Оплата'].map((x,i)=><article key={x}><span>{i+1}</span><strong>{x}</strong><p>controlled MVP stage</p></article>)}</section>; }
function MarketReadinessWindow() { const [data,,loading] = useAsync(api.readiness, null); if (loading || !data) return <Loading/>; return <section className="cardStack"><header><strong>Готовность MVP</strong><span>{data.market_mvp}</span></header><div className="gateList">{data.checks.map(c=><div key={c}><strong>{c}</strong><em>green</em></div>)}<div className="yellow"><strong>live_fleet_canary</strong><em>{data.live_fleet_canary}</em></div></div></section>; }
function SettingsWindow() { return <section className="settings"><article><strong>Профиль</strong><span>роль, подписка, язык</span></article><article><strong>Устройство</strong><span>desktop / mobile / tv / tauri</span></article><article><strong>Безопасность</strong><span>capabilities, approvals, audit</span></article></section>; }
function OverviewWindow() { return <section className="cardStack"><header><strong>Vista OS</strong><span>state-driven workbench</span></header><p>Состояние решает всё; интерфейс показывает только разрешённую проекцию.</p></section>; }
function Loading(){ return <div className="loading">Загрузка…</div>; }
function Two({title, items}) { return <div className="two"><strong>{title}</strong>{items.map(x=><span key={x}>{x}</span>)}</div>; }
