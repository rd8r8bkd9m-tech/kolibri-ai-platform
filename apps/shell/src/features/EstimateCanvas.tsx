import { useMemo, useState } from 'react'
import type { Estimate, EstimateItem, Source } from '../api/client'
import { addItem, addSource, deleteItem, exportEstimate, patchEstimate, patchItem } from '../api/client'

type Props={estimate:Estimate;onChange:(e:Estimate)=>void;onDocuments:()=>void;onClose:()=>void}

function money(value:string){return new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB',maximumFractionDigits:0}).format(Number(value||0))}

export function EstimateCanvas({estimate,onChange,onDocuments,onClose}:Props){
 const [busy,setBusy]=useState(''); const [error,setError]=useState('');
 const [source,setSource]=useState({title:'',url:'',region:estimate.region||'',price_date:new Date().toISOString().slice(0,10),unit:'шт.',verification_status:'verified'})
 const totalVerified=useMemo(()=>estimate.items.length>0 && estimate.items.every(item=>item.verified),[estimate.items])
 async function action(label:string,fn:()=>Promise<Estimate>){setBusy(label);setError('');try{onChange(await fn())}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy('')}}
 async function saveHeader(field:string,value:string){await action('Сохраняю',()=>patchEstimate(estimate.id,{[field]:value},estimate.revision))}
 async function addRow(){await action('Добавляю строку',()=>addItem(estimate.id,{section:'Работы',name:'Новая работа',unit:'шт.',quantity:'1',unit_price:'0',coefficient:'1'}))}
 async function updateRow(item:EstimateItem,field:keyof EstimateItem,value:string){await action('Пересчитываю',()=>patchItem(estimate.id,item.id,{[field]:value}))}
 async function removeRow(itemId:string){await action('Удаляю строку',()=>deleteItem(estimate.id,itemId))}
 async function attachSource(){
  if(!source.title||!source.url||!source.region){setError('Заполните название, URL и регион источника.');return}
  const result=await addSource(estimate.id,source as Omit<Source,'id'>)
  let next=result.estimate
  const target=next.items.find(item=>!item.source_id)
  if(target) next=await patchItem(estimate.id,target.id,{source_id:result.source.id})
  onChange(next);setSource({...source,title:'',url:''})
 }
 async function exports(){setBusy('Формирую документы');setError('');try{await exportEstimate(estimate.id);onDocuments()}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy('')}}
 return <section className="canvas estimate-canvas" aria-label="Редактор сметы" data-testid="estimate-canvas">
  <header className="canvas__header"><div><span className="eyebrow">Смета · revision {estimate.revision}</span><input className="title-input" defaultValue={estimate.title} onBlur={e=>saveHeader('title',e.currentTarget.value)} aria-label="Название сметы"/></div><button className="icon-button" onClick={onClose}>×</button></header>
  <div className="estimate-status-row"><span className={`status status--${estimate.status}`}>{estimate.status==='verified'?'Проверено':estimate.status==='preliminary'?'Предварительно':'Нужны данные'}</span><span>{estimate.region||'Регион не указан'}</span><strong>{money(estimate.total)}</strong></div>
  <div className="estimate-grid">
   <div className="estimate-main">
    <div className="brief-grid"><label>Клиент<input defaultValue={estimate.client_name} onBlur={e=>saveHeader('client_name',e.currentTarget.value)}/></label><label>Регион<input defaultValue={estimate.region} onBlur={e=>saveHeader('region',e.currentTarget.value)}/></label><label>Накладные, %<input inputMode="decimal" defaultValue={estimate.overhead_pct} onBlur={e=>saveHeader('overhead_pct',e.currentTarget.value)}/></label><label>Маржа, %<input inputMode="decimal" defaultValue={estimate.margin_pct} onBlur={e=>saveHeader('margin_pct',e.currentTarget.value)}/></label></div>
    <div className="table-toolbar"><div><h3>Работы и материалы</h3><p>Деньги пересчитывает сервер, а не модель.</p></div><button className="secondary" onClick={addRow}>Добавить строку</button></div>
    <div className="estimate-table" role="table">
     <div className="estimate-row estimate-row--head" role="row"><span>Работа</span><span>Ед.</span><span>Кол-во</span><span>Цена</span><span>Сумма</span><span/></div>
     {estimate.items.length===0?<div className="empty-row">Добавьте объёмы работ. Пока итог не придуман.</div>:estimate.items.map(item=><div className="estimate-row" role="row" key={item.id}>
      <label className="estimate-cell estimate-cell--work"><span className="mobile-label">Работа</span><input defaultValue={item.name} onBlur={e=>updateRow(item,'name',e.currentTarget.value)} aria-label="Работа"/></label>
      <label className="estimate-cell"><span className="mobile-label">Единица</span><input defaultValue={item.unit} onBlur={e=>updateRow(item,'unit',e.currentTarget.value)} aria-label="Единица"/></label>
      <label className="estimate-cell"><span className="mobile-label">Количество</span><input inputMode="decimal" defaultValue={item.quantity} onBlur={e=>updateRow(item,'quantity',e.currentTarget.value)} aria-label="Количество"/></label>
      <label className="estimate-cell"><span className="mobile-label">Цена</span><input inputMode="decimal" defaultValue={item.unit_price} onBlur={e=>updateRow(item,'unit_price',e.currentTarget.value)} aria-label="Цена"/></label>
      <div className="estimate-cell estimate-cell--total"><span className="mobile-label">Сумма</span><strong>{money(item.line_total||'0')}</strong></div>
      <button className="row-action" onClick={()=>removeRow(item.id)} aria-label="Удалить строку">×</button>
      <div className="source-binding">{item.source?<a href={item.source.url} target="_blank" rel="noreferrer">{item.source.title} · {item.source.price_date}</a>:<span>Источник цены не подтверждён</span>}</div>
     </div>)}
    </div>
   </div>
   <aside className="estimate-side">
    <div className="totals"><span>Работы и материалы<strong>{money(estimate.subtotal)}</strong></span><span>Итого<strong>{money(estimate.total)}</strong></span></div>
    <div className="source-form"><div><h3>Источник цены</h3><p>Verified возможен только с датированными источниками.</p></div><label>Название<input value={source.title} onChange={e=>setSource({...source,title:e.target.value})}/></label><label>URL<input type="url" value={source.url} onChange={e=>setSource({...source,url:e.target.value})}/></label><label>Регион<input value={source.region} onChange={e=>setSource({...source,region:e.target.value})}/></label><label>Дата<input type="date" value={source.price_date} onChange={e=>setSource({...source,price_date:e.target.value})}/></label><button className="secondary wide" onClick={attachSource}>Сохранить и привязать</button></div>
    <button className="primary wide" onClick={exports} disabled={busy!==''}>Сформировать PDF и XLSX</button>
    {!totalVerified&&<p className="honesty-note">Документы можно сформировать в preliminary-статусе, но они будут явно помечены как предварительные.</p>}
   </aside>
  </div>
  {(busy||error)&&<div className={`toast ${error?'toast--error':''}`}>{error||busy}</div>}
 </section>
}
