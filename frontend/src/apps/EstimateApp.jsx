import { useMemo, useState } from 'react';
import { Icon } from '../ui/Icons.jsx';
import { api } from '../api/client.js';

const money = (value = 0) => new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(value);
const emptyDraft = { section: 'Работы', name: '', unit: 'м²', qty: 1, price: 0, coef: 1 };
const statusLabels = { draft:'Черновик', review:'На проверке', approved:'Согласовано', sent:'Отправлено', archived:'Архив' };
const number = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
const percent = (project, key, fallback) => Math.min(100, Math.max(0, number(project?.[key], fallback)));

function calculatePreview(items, project) {
  const subtotal = Math.round(items.reduce((sum, item) => sum + number(item.qty) * number(item.price) * number(item.coef, 1), 0));
  const overheadPercent = percent(project, 'overhead_percent', 12);
  const marginPercent = percent(project, 'margin_percent', 18);
  const discountPercent = percent(project, 'discount_percent', 0);
  const vatPercent = percent(project, 'vat_percent', 0);
  const overhead = Math.round(subtotal * overheadPercent / 100);
  const margin = Math.round((subtotal + overhead) * marginPercent / 100);
  const beforeDiscount = subtotal + overhead + margin;
  const discount = Math.round(beforeDiscount * discountPercent / 100);
  const taxable = Math.max(0, beforeDiscount - discount);
  const tax = Math.round(taxable * vatPercent / 100);
  return { subtotal, overhead, margin, discount, tax, total: taxable + tax, overhead_percent: overheadPercent, margin_percent: marginPercent, discount_percent: discountPercent, vat_percent: vatPercent };
}

export function EstimateApp({ estimate, onEstimate, onDocuments, onToast }) {
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [draft, setDraft] = useState(emptyDraft);
  const [brief, setBrief] = useState({ project: 'Ремонт квартиры', client: '', phone: '', city: 'Москва', address: '', area: 72 });
  const totalItems = useMemo(() => estimate?.items?.length || 0, [estimate]);

  async function createEstimate(event) {
    event.preventDefault();
    if (!brief.project.trim()) { onToast('Укажите название объекта', 'error'); return; }
    setCreating(true);
    try {
      const next = await api.createEstimate({
        city: brief.city,
        client: { name: brief.client || 'Новый клиент', phone: brief.phone, email: '' },
        project: { name: brief.project, area: number(brief.area), address: brief.address, overhead_percent: 12, margin_percent: 18, discount_percent: 0, vat_percent: 0 },
        assumptions: ['Цены действительны 14 дней', 'Фактические объёмы уточняются после замера'],
        items: [],
      });
      onEstimate(next); onToast('Смета создана');
    } catch (error) { onToast(error.message, 'error'); }
    finally { setCreating(false); }
  }

  async function patchEstimate(patch) {
    if (!estimate) return;
    try { onEstimate(await api.updateEstimate(estimate.id, patch)); }
    catch (error) { onToast(error.message, 'error'); }
  }

  function localItem(itemId, patch) {
    const items = estimate.items.map(item => item.id === itemId ? { ...item, ...patch } : item);
    onEstimate({ ...estimate, items, summary: calculatePreview(items, estimate.project) });
  }

  function localProject(patch) {
    const project = { ...estimate.project, ...patch };
    onEstimate({ ...estimate, project, summary: calculatePreview(estimate.items, project) });
  }

  async function persistItem(itemId, patch) {
    try { onEstimate(await api.updateEstimateItem(estimate.id, itemId, patch)); }
    catch (error) { onToast(error.message, 'error'); }
  }

  async function addItem() {
    if (!draft.name.trim()) { onToast('Введите название работы', 'error'); return; }
    setSaving(true);
    try { onEstimate(await api.addEstimateItem(estimate.id, draft)); setDraft(emptyDraft); }
    catch (error) { onToast(error.message, 'error'); }
    finally { setSaving(false); }
  }

  async function removeItem(itemId) {
    try { onEstimate(await api.deleteEstimateItem(estimate.id, itemId)); }
    catch (error) { onToast(error.message, 'error'); }
  }

  async function generate() {
    if (!totalItems) { onToast('Сначала добавьте хотя бы одну работу', 'error'); return; }
    setGenerating(true);
    try {
      const result = await api.generateDocuments(estimate.id);
      onEstimate(await api.getEstimate(estimate.id));
      onDocuments(result.artifacts);
      onToast('Документы сформированы и проверены');
    } catch (error) { onToast(error.message, 'error'); }
    finally { setGenerating(false); }
  }

  async function saveVersion() {
    try { await api.saveEstimateVersion(estimate.id, 'Ручное сохранение'); onToast('Версия сметы сохранена'); }
    catch (error) { onToast(error.message, 'error'); }
  }

  if (!estimate) return <section className="createEstimate">
    <div className="createIntro"><div className="eyebrow">НОВЫЙ ОБЪЕКТ</div><h1>Смета начинается с короткого брифа</h1><p>Заполните базовые данные. Все поля можно изменить позже.</p></div>
    <form className="briefForm" onSubmit={createEstimate}>
      <label><span>Название объекта</span><input value={brief.project} onChange={event => setBrief({ ...brief, project: event.target.value })} placeholder="Ремонт квартиры" required/></label>
      <label><span>Клиент</span><input value={brief.client} onChange={event => setBrief({ ...brief, client: event.target.value })} placeholder="Имя или компания"/></label>
      <div className="formRow"><label><span>Телефон</span><input value={brief.phone} onChange={event => setBrief({ ...brief, phone: event.target.value })} placeholder="+7 900 000-00-00"/></label><label><span>Площадь, м²</span><input type="number" min="0" value={brief.area} onChange={event => setBrief({ ...brief, area: event.target.value })}/></label></div>
      <label><span>Адрес</span><input value={brief.address} onChange={event => setBrief({ ...brief, address: event.target.value })} placeholder="Улица, дом, квартира"/></label>
      <label><span>Город</span><input value={brief.city} onChange={event => setBrief({ ...brief, city: event.target.value })}/></label>
      <button className="primaryButton wide" disabled={creating}><Icon name="add"/>{creating ? 'Создаю…' : 'Создать смету'}</button>
    </form>
  </section>;

  return <section className="estimateApp">
    <header className="estimateHeader">
      <div className="projectIdentity">
        <span className="eyebrow">СМЕТА · ВЕРСИЯ {estimate.version}</span>
        <input aria-label="Название объекта" className="projectTitle" value={estimate.project?.name || ''} onChange={event => onEstimate({ ...estimate, project: { ...estimate.project, name: event.target.value } })} onBlur={event => patchEstimate({ project: { name: event.target.value } })}/>
        <div className="projectMeta">
          <input aria-label="Клиент" value={estimate.client?.name || ''} placeholder="Клиент" onChange={event => onEstimate({ ...estimate, client: { ...estimate.client, name: event.target.value } })} onBlur={event => patchEstimate({ client: { name: event.target.value } })}/>
          <span>•</span><input aria-label="Город" value={estimate.city || ''} onChange={event => onEstimate({ ...estimate, city: event.target.value })} onBlur={event => patchEstimate({ city: event.target.value })}/>
          <span>•</span><input aria-label="Площадь" className="areaInput" type="number" min="0" value={estimate.project?.area || 0} onChange={event => onEstimate({ ...estimate, project: { ...estimate.project, area: number(event.target.value) } })} onBlur={event => patchEstimate({ project: { area: number(event.target.value) } })}/><span>м²</span>
        </div>
      </div>
      <div className="estimateActions"><button className="ghostButton" onClick={saveVersion}><Icon name="save"/>Сохранить версию</button><button className="primaryButton" onClick={generate} disabled={generating}><Icon name="documents"/>{generating ? 'Формирую…' : 'Сформировать документы'}</button></div>
    </header>

    <div className="estimateWorkspace">
      <div className="lineItems">
        <div className="itemsHeader"><span>Раздел</span><span>Работа</span><span>Ед.</span><span>Кол-во</span><span>Цена</span><span>Коэф.</span><span>Сумма</span><span/></div>
        {estimate.items.map(item => <div className="itemRow" key={item.id}>
          <input aria-label={`Раздел ${item.name}`} value={item.section} onChange={event => localItem(item.id, { section: event.target.value })} onBlur={event => persistItem(item.id, { section: event.target.value })}/>
          <input aria-label="Название работы" className="itemName" value={item.name} onChange={event => localItem(item.id, { name: event.target.value })} onBlur={event => persistItem(item.id, { name: event.target.value })}/>
          <input aria-label={`Единица ${item.name}`} value={item.unit} onChange={event => localItem(item.id, { unit: event.target.value })} onBlur={event => persistItem(item.id, { unit: event.target.value })}/>
          <input aria-label={`Количество ${item.name}`} type="number" min="0" value={item.qty} onChange={event => localItem(item.id, { qty: number(event.target.value) })} onBlur={event => persistItem(item.id, { qty: number(event.target.value) })}/>
          <input aria-label={`Цена ${item.name}`} type="number" min="0" value={item.price} onChange={event => localItem(item.id, { price: number(event.target.value) })} onBlur={event => persistItem(item.id, { price: number(event.target.value) })}/>
          <input aria-label={`Коэффициент ${item.name}`} type="number" min="0" step="0.05" value={item.coef} onChange={event => localItem(item.id, { coef: number(event.target.value, 1) })} onBlur={event => persistItem(item.id, { coef: number(event.target.value, 1) })}/>
          <strong>{money(number(item.qty) * number(item.price) * number(item.coef, 1))}</strong>
          <button className="rowAction" aria-label="Удалить позицию" onClick={() => removeItem(item.id)}><Icon name="close" size={16}/></button>
        </div>)}
        <div className="itemRow addItemRow">
          <input aria-label="Раздел новой работы" value={draft.section} onChange={event => setDraft({ ...draft, section: event.target.value })}/>
          <input aria-label="Новая работа" className="itemName" value={draft.name} onChange={event => setDraft({ ...draft, name: event.target.value })} placeholder="Новая работа" onKeyDown={event => event.key === 'Enter' && addItem()}/>
          <input aria-label="Единица новой работы" value={draft.unit} onChange={event => setDraft({ ...draft, unit: event.target.value })}/>
          <input aria-label="Количество новой работы" type="number" min="0" value={draft.qty} onChange={event => setDraft({ ...draft, qty: number(event.target.value) })}/>
          <input aria-label="Цена новой работы" type="number" min="0" value={draft.price} onChange={event => setDraft({ ...draft, price: number(event.target.value) })}/>
          <input aria-label="Коэффициент новой работы" type="number" min="0" step="0.05" value={draft.coef} onChange={event => setDraft({ ...draft, coef: number(event.target.value, 1) })}/>
          <strong>{money(number(draft.qty) * number(draft.price) * number(draft.coef, 1))}</strong>
          <button aria-label="Добавить работу" className="addRowButton" onClick={addItem} disabled={saving}><Icon name="add" size={16}/></button>
        </div>
        {!totalItems ? <div className="emptyItems"><Icon name="estimate" size={28}/><strong>Добавьте первую работу</strong><span>Например: «Демонтаж — снятие покрытий, 72 м² × 350 ₽»</span></div> : null}
      </div>
      <aside className="summaryPanel">
        <div className="summaryTop"><div><span className="eyebrow">ИТОГ ОБЪЕКТА</span><strong className="grandTotal">{money(estimate.summary?.total)}</strong></div><label className="statusControl"><span>Статус</span><select value={estimate.status} onChange={event => patchEstimate({ status: event.target.value })}>{Object.entries(statusLabels).map(([value,label])=><option value={value} key={value}>{label}</option>)}</select></label></div>
        <dl><div><dt>Работы</dt><dd>{money(estimate.summary?.subtotal)}</dd></div><div><dt>Накладные · {estimate.summary?.overhead_percent ?? 12}%</dt><dd>{money(estimate.summary?.overhead)}</dd></div><div><dt>Прибыль · {estimate.summary?.margin_percent ?? 18}%</dt><dd>{money(estimate.summary?.margin)}</dd></div>{estimate.summary?.discount ? <div><dt>Скидка · {estimate.summary?.discount_percent}%</dt><dd>−{money(estimate.summary.discount)}</dd></div>:null}{estimate.summary?.tax ? <div><dt>НДС · {estimate.summary?.vat_percent}%</dt><dd>{money(estimate.summary.tax)}</dd></div>:null}<div className="summaryFinal"><dt>Итого</dt><dd>{money(estimate.summary?.total)}</dd></div></dl>
        <div className="costSettings" aria-label="Настройки расчёта">
          {[['overhead_percent','Накладные',12],['margin_percent','Прибыль',18],['discount_percent','Скидка',0],['vat_percent','НДС',0]].map(([key,label,fallback])=><label key={key}><span>{label}</span><div><input aria-label={`${label}, процент`} type="number" min="0" max="100" step="0.5" value={percent(estimate.project,key,fallback)} onChange={event=>localProject({[key]:number(event.target.value)})} onBlur={event=>patchEstimate({project:{[key]:number(event.target.value)}})}/><em>%</em></div></label>)}
        </div>
        <div className="summaryNote"><Icon name="check"/><p>Итоги рассчитываются сервером и повторно проверяются при формировании документов.</p></div>
      </aside>
    </div>
  </section>;
}
