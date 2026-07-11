import { useEffect, useState } from 'react';
import { api } from '../api/client.js';
import { Icon } from '../ui/Icons.jsx';

export function FactoryApp({ onToast }) {
  const [stats, setStats] = useState(null); const [tasks, setTasks] = useState([]); const [loading, setLoading] = useState(true);
  const load = () => Promise.all([api.factoryStats(), api.factoryTasks()]).then(([s,t]) => { setStats(s); setTasks(t); }).catch(e => onToast(e.message,'error')).finally(()=>setLoading(false));
  useEffect(() => { load(); }, []);
  async function createTask() { try { await api.createFactoryTask({ title:'Проверка Vista runtime', kind:'health_probe', required_capabilities:['health.probe'], required_artifacts:['RESULT.md'] }); await load(); onToast('Задача поставлена в очередь'); } catch(e){ onToast(e.message,'error'); } }
  if (loading) return <div className="appLoading">Загружаю фабрику…</div>;
  return <section className="factoryApp">
    <header className="appSectionHeader"><div><span className="eyebrow">FACTORY CONTROL</span><h1>Исполнение задач</h1><p>Persistent queue, lease, worker artifact и verifier.</p></div><button className="primaryButton" onClick={createTask}><Icon name="add"/>Новая проверка</button></header>
    <div className="metricGrid"><article><span>Ноды</span><strong>{stats?.nodes || 0}</strong></article><article><span>В очереди</span><strong>{stats?.states?.queued || 0}</strong></article><article><span>Выполнено</span><strong>{stats?.states?.completed || 0}</strong></article><article><span>События</span><strong>{stats?.events || 0}</strong></article></div>
    <div className="dataList"><header><span>Задача</span><span>Статус</span><span>Исполнитель</span><span>Артефакт</span></header>{tasks.slice(0,20).map(task => <div key={task.id}><strong>{task.title}</strong><span className={`state state-${task.state}`}>{task.state}</span><span>{task.assigned_node_id || '—'}</span><span>{task.artifact_path || '—'}</span></div>)}</div>
  </section>;
}
