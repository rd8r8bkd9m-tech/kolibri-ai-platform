import { useEffect, useState } from 'react';
import { Icon } from '../ui/Icons.jsx';
import { api } from '../api/client.js';

const kinds = {
  proposal_pdf: { label: 'Коммерческое предложение', format: 'PDF' },
  estimate_xlsx: { label: 'Смета с формулами', format: 'XLSX' },
  proposal_docx: { label: 'Редактируемое предложение', format: 'DOCX' },
  estimate_json: { label: 'Данные сметы', format: 'JSON' },
  assumptions_md: { label: 'Допущения и риски', format: 'MD' },
};
const bytes = value => value > 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} МБ` : `${Math.max(1, Math.round((value || 0) / 1024))} КБ`;
const activeShare = share => share && !share.revoked_at && new Date(share.expires_at).getTime() > Date.now();

export function DocumentsApp({ estimate, artifacts, onArtifacts, onToast, onGenerate }) {
  const [sharing, setSharing] = useState(false);
  const [share, setShare] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!estimate?.id) return;
    let alive = true;
    setLoading(true);
    Promise.all([api.artifacts(estimate.id), api.listShares(estimate.id)])
      .then(([nextArtifacts, shares]) => {
        if (!alive) return;
        onArtifacts(nextArtifacts);
        const current = shares.find(activeShare);
        setShare(current ? { ...current, link: `${location.origin}/share/${current.token}` } : null);
      })
      .catch(error => onToast(error.message, 'error'))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [estimate?.id]);

  async function createShare() {
    setSharing(true);
    try {
      const result = await api.createShare(estimate.id);
      const link = `${location.origin}/share/${result.token}`;
      setShare({ ...result, link });
      await navigator.clipboard?.writeText(link);
      onToast('Защищённая ссылка скопирована');
    } catch (error) { onToast(error.message, 'error'); }
    finally { setSharing(false); }
  }

  async function revokeShare() {
    if (!share?.token) return;
    setSharing(true);
    try {
      await api.revokeShare(estimate.id, share.token);
      setShare(null);
      onToast('Клиентская ссылка отозвана');
    } catch (error) { onToast(error.message, 'error'); }
    finally { setSharing(false); }
  }

  if (!estimate) return <section className="emptyApp"><Icon name="documents" size={34}/><h2>Сначала создайте смету</h2><p>Документы формируются на основе рассчитанного объекта.</p></section>;

  return <section className="documentsApp">
    <header className="documentsHeader">
      <div><span className="eyebrow">ДОКУМЕНТЫ ОБЪЕКТА</span><h1>{estimate.project?.name}</h1><p>{estimate.client?.name} · версия {estimate.version}</p></div>
      <div className="estimateActions"><button className="ghostButton" onClick={share ? revokeShare : createShare} disabled={!artifacts.length || sharing}><Icon name="link"/>{sharing ? 'Обновляю…' : share ? 'Отозвать ссылку' : 'Ссылка клиенту'}</button><button className="primaryButton" onClick={onGenerate}><Icon name="documents"/>Обновить пакет</button></div>
    </header>
    {share ? <div className="shareBanner"><div><Icon name="link"/><span>Клиентская ссылка действует до {new Date(share.expires_at).toLocaleString('ru-RU')}</span></div><a href={share.link} target="_blank" rel="noreferrer">Открыть</a><button onClick={() => navigator.clipboard?.writeText(share.link)}>Копировать</button></div> : null}
    {loading ? <div className="skeletonList"><i/><i/><i/></div> : artifacts.length ? <div className="documentGrid">
      {artifacts.map(artifact => {
        const meta = kinds[artifact.kind] || { label: artifact.name, format: artifact.kind?.toUpperCase() };
        return <article className="documentCard" key={artifact.id}>
          <div className={`fileBadge file-${meta.format?.toLowerCase()}`}>{meta.format}</div>
          <div className="fileBody"><strong>{meta.label}</strong><span>{bytes(artifact.size_bytes)} · SHA-256 {artifact.sha256?.slice(0, 10)}…</span><small>{new Date(artifact.created_at).toLocaleString('ru-RU')}</small></div>
          <button className="downloadButton" onClick={() => api.downloadArtifact(artifact).catch(error => onToast(error.message, 'error'))}><Icon name="download"/>Скачать</button>
        </article>;
      })}
    </div> : <section className="emptyApp documentsEmpty"><Icon name="documents" size={34}/><h2>Пакет документов ещё не сформирован</h2><p>Vista создаст PDF, XLSX, DOCX, JSON и файл допущений через проверенную фабричную задачу.</p><button className="primaryButton" onClick={onGenerate}><Icon name="documents"/>Сформировать документы</button></section>}
  </section>;
}
