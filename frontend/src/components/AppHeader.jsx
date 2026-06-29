import { KolibriBird } from "./KolibriBird"

export function AppHeader({ birdState, clusterStatus, providers, selectedProvider, onProviderChange, onOpenSettings }) {
  return (
    <header className="header chat-header">
      <div className="header-left">
        <KolibriBird size={36} state={birdState} />
        <div>
          <div className="header-title">Kolibri AI</div>
          <div className="header-subtitle">
            {clusterStatus ? (
              <span className="header-cluster">
                <span className="pulse-dot" />
                {clusterStatus.online_nodes} узлов · {clusterStatus.free_ram_gb} GB RAM
              </span>
            ) : "Загрузка..."}
          </div>
        </div>
      </div>
      <div className="header-right">
        <select className="model-select" value={selectedProvider} onChange={e => onProviderChange(e.target.value)} title="Модель">
          {providers.filter(p => p.available).map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
          {providers.length === 0 && <option value="mimo">mimo-auto</option>}
        </select>
        <button className="header-btn" onClick={onOpenSettings} title="Тема">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>
          </svg>
        </button>
      </div>
    </header>
  )
}
