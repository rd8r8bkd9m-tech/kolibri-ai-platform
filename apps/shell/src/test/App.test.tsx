import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from '../App'

const project={id:'proj_1',title:'Первый проект',updated_at:'2026-07-13T00:00:00Z',deleted_at:null}
const estimate={id:'est_1',project_id:'proj_1',title:'Смета: квартира',client_name:'',region:'Москва',status:'needs_input',revision:1,subtotal:'0',total:'0',overhead_pct:'0',margin_pct:'0',discount_pct:'0',tax_pct:'0',items:[],sources:[]}

function json(data:unknown,status=200){return Promise.resolve(new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}}))}

describe('Kolibri Shell',()=>{
 beforeEach(()=>{
  vi.stubGlobal('fetch',vi.fn((input:RequestInfo|URL,init?:RequestInit)=>{
   const url=String(input)
   if(url==='/v1/shell/bootstrap')return json({session:{id:'sess_1',role:'client'},active_project:project,projects:[project],capabilities:[{id:'chat',label:'Диалог',available:true},{id:'estimates',label:'Сметы',available:true},{id:'documents',label:'Документы',available:true}]})
   if(url==='/v1/projects/proj_1/messages')return json({data:[]})
   if(url.startsWith('/v1/estimates?'))return json({data:[]})
   if(url==='/v1/estimates'&&init?.method==='POST')return json(estimate)
   return json({data:[]})
  }))
 })
 afterEach(()=>{cleanup();vi.unstubAllGlobals()})
 it('renders one bird and no permanent vertical navigation',async()=>{
  render(<App/>)
  await screen.findByText('Что создадим?')
  expect(screen.getAllByTestId('bird')).toHaveLength(1)
  expect(screen.queryByText('Фабрика')).not.toBeInTheDocument()
  expect(screen.queryByText('Серверы')).not.toBeInTheDocument()
 })
 it('opens the estimate only from contextual tools',async()=>{
  render(<App/>)
  await screen.findByText('Что создадим?')
  fireEvent.click(screen.getByLabelText('Инструменты'))
  fireEvent.click(screen.getByText('Смета'))
  await waitFor(()=>expect(screen.getByTestId('estimate-canvas')).toBeInTheDocument())
  expect(screen.getByText('Деньги пересчитывает сервер, а не модель.')).toBeInTheDocument()
 })
})
