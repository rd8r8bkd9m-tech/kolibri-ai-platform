import { Icon } from '../ui/Icons.jsx';

const money = (value = 0) => new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(value);

export function HomeApp({ estimate, estimates = [], onCreate, onOpenEstimate, onOpenDocuments, onSelectEstimate }) {
  const recent = estimates.slice(0, 4);
  function keyboardOpen(event, action) {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); action(); }
  }
  return <section className="homeApp">
    <div className="homeHero">
      <div className="eyebrow">VISTA WORKSPACE</div>
      <h1>{estimate ? 'Продолжим работу с объектом?' : 'Создайте первую смету вместе с Vista'}</h1>
      <p>{estimate ? 'Расчёты, документы и версии объекта хранятся в одном рабочем пространстве.' : 'Укажите объект и клиента. Vista рассчитает работы, сформирует коммерческое предложение и подготовит документы.'}</p>
      <div className="heroActions">
        <button className="primaryButton" onClick={estimate ? onOpenEstimate : onCreate}><Icon name={estimate ? 'estimate' : 'add'}/>{estimate ? 'Открыть смету' : 'Новая смета'}</button>
        {estimate ? <button className="secondaryButton" onClick={onCreate}><Icon name="add"/>Новый объект</button> : null}
        {estimate?.artifacts?.length ? <button className="secondaryButton" onClick={onOpenDocuments}><Icon name="documents"/>Документы</button> : null}
      </div>
    </div>

    {recent.length ? <section className="recentProjects" aria-labelledby="recent-projects-title">
      <header><div><span className="eyebrow">ПРОЕКТЫ</span><h2 id="recent-projects-title">Последние объекты</h2></div><span>{estimates.length}</span></header>
      <div className="recentProjectGrid">
        {recent.map(project => <article className={`recentProject ${project.id===estimate?.id?'active':''}`} key={project.id} role="button" tabIndex="0" onClick={()=>onSelectEstimate(project.id)} onKeyDown={event=>keyboardOpen(event,()=>onSelectEstimate(project.id))}>
          <div><span className="statusDot"/><small>{project.id===estimate?.id?'Открыт сейчас':`Версия ${project.version}`}</small></div>
          <h3>{project.project?.name || 'Новая смета'}</h3>
          <p>{project.client?.name || 'Новый клиент'} · {project.city}</p>
          <footer><strong>{money(project.summary?.total)}</strong><Icon name="arrow"/></footer>
        </article>)}
      </div>
    </section> : <div className="homeGrid" aria-label="Что умеет Vista">
      <article className="homeCard featureCard"><span>01</span><strong>Смета</strong><p>Работы, материалы, коэффициенты и итоговый расчёт.</p></article>
      <article className="homeCard featureCard"><span>02</span><strong>Коммерческое предложение</strong><p>PDF и DOCX с условиями оплаты и составом работ.</p></article>
      <article className="homeCard featureCard"><span>03</span><strong>Документы</strong><p>XLSX, JSON, версии и защищённая клиентская ссылка.</p></article>
    </div>}
  </section>;
}
