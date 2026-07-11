import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

const { estimate, mockApi } = vi.hoisted(() => {
  const estimate = {
    id:'est_test',version:1,status:'draft',city:'Москва',client:{name:'Иван'},project:{name:'Квартира 72 м²',area:72},
    items:[{id:'item_1',section:'Демонтаж',name:'Снятие покрытий',unit:'м²',qty:72,price:350,coef:1}],
    summary:{subtotal:25200,overhead:3024,margin:5080,total:33304},artifacts:[]
  };
  return { estimate, mockApi: {
    session: vi.fn(()=>null),
    token: vi.fn(()=>''),
    clearSession: vi.fn(),
    getSession: vi.fn(async id=>({id,role:'client_pro',plan:'pro_construction',device:'desktop',windows:[],chat:[],active_estimate_id:null})),
    patchSession: vi.fn(async (id,patch)=>({id,role:'client_pro',plan:'pro_construction',device:'desktop',...patch})),
    createSession: vi.fn(async ({role='client_pro',device='auto'})=>({session:{id:'sess_test',role,plan:role==='owner'?'owner_full':'pro_construction',device},token:'token'})),
    listEstimates: vi.fn(async()=>[estimate]),
    resolve: vi.fn(async ({text})=>({assistant:'Открываю доступную функцию.',components:text.includes('документ')?[{id:'documents.pack'}]:[{id:'estimate.workspace'}]})),
    generateDocuments: vi.fn(async()=>({artifacts:[]})),
    getEstimate: vi.fn(async()=>estimate),
    artifacts: vi.fn(async()=>[]),
    listShares: vi.fn(async()=>[]),
    revokeShare: vi.fn(async()=>({status:'revoked'})),
    health: vi.fn(async()=>({status:'ok'})),
  }};
});
vi.mock('../api/client.js',()=>({api:mockApi}));

import { App } from '../App.jsx';

beforeEach(()=>{cleanup();sessionStorage.clear();localStorage.clear();history.replaceState(null,'','/');vi.clearAllMocks();mockApi.session.mockReturnValue(null);mockApi.token.mockReturnValue('');});

describe('Vista OS product shell',()=>{
  it('starts with one bird-first entry point',()=>{
    render(<App/>);
    expect(screen.getByRole('button',{name:'Открыть Vista'})).toBeInTheDocument();
    expect(screen.queryByText('Factory Control')).not.toBeInTheDocument();
  });

  it('renders one active application for a client without admin noise',async()=>{
    history.replaceState(null,'','/?entered=1&role=client_pro');
    render(<App/>);
    await waitFor(()=>expect(screen.getByTestId('app-home')).toBeInTheDocument());
    expect(screen.getAllByText('Смета').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Документы').length).toBeGreaterThan(0);
    expect(screen.queryByText('Фабрика')).not.toBeInTheDocument();
    expect(screen.queryByText('Серверы')).not.toBeInTheDocument();
  });

  it('opens the real estimate editor from the dock',async()=>{
    history.replaceState(null,'','/?entered=1&role=client_pro');
    render(<App/>);
    await waitFor(()=>expect(screen.getByTestId('app-home')).toBeInTheDocument());
    fireEvent.click(screen.getByTitle('Смета'));
    expect(await screen.findByTestId('app-estimate')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Квартира 72 м²')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Снятие покрытий')).toBeInTheDocument();
  });

  it('shows real estimate status and configurable calculation controls',async()=>{
    history.replaceState(null,'','/?entered=1&role=client_pro');
    render(<App/>);
    await waitFor(()=>expect(screen.getByTestId('app-home')).toBeInTheDocument());
    fireEvent.click(screen.getByTitle('Смета'));
    expect(await screen.findByTestId('app-estimate')).toBeInTheDocument();
    expect(screen.getByLabelText('Накладные, процент')).toHaveValue(12);
    expect(screen.getByLabelText('Прибыль, процент')).toHaveValue(18);
    expect(screen.getByDisplayValue('Черновик')).toBeInTheDocument();
  });

  it('opens the command palette with only role-allowed apps',async()=>{
    history.replaceState(null,'','/?entered=1&role=client_pro');
    render(<App/>);
    await waitFor(()=>expect(screen.getByTestId('app-home')).toBeInTheDocument());
    fireEvent.click(screen.getByText('⌘K'));
    expect(screen.getByPlaceholderText('Команда или приложение…')).toBeInTheDocument();
    expect(screen.queryByText('Factory Control')).not.toBeInTheDocument();
  });

  it('shows the full product surface for owner role',async()=>{
    history.replaceState(null,'','/?entered=1&role=owner&admin=vista-local-owner');
    render(<App/>);
    await waitFor(()=>expect(screen.getByTestId('app-home')).toBeInTheDocument());
    expect(screen.getByText('Фабрика')).toBeInTheDocument();
    expect(screen.getByText('Серверы')).toBeInTheDocument();
    expect(screen.getByText('API')).toBeInTheDocument();
  });

  it('opens settings from the working profile control',async()=>{
    history.replaceState(null,'','/?entered=1&role=client_pro');
    render(<App/>);
    await waitFor(()=>expect(screen.getByTestId('app-home')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button',{name:'Открыть настройки'}));
    expect(await screen.findByTestId('app-settings')).toBeInTheDocument();
  });

  it('does not expose placeholder attachment or voice controls',async()=>{
    history.replaceState(null,'','/?entered=1&role=client_pro');
    render(<App/>);
    await waitFor(()=>expect(screen.getByTestId('app-home')).toBeInTheDocument());
    expect(screen.queryByTitle('Добавить файл')).not.toBeInTheDocument();
    expect(screen.queryByTitle('Голос')).not.toBeInTheDocument();
    expect(screen.getByRole('textbox',{name:'Команда Vista'})).toBeInTheDocument();
  });

  it('starts a genuinely new estimate instead of reopening the active one',async()=>{
    history.replaceState(null,'','/?entered=1&role=client_pro');
    render(<App/>);
    await waitFor(()=>expect(screen.getByTestId('app-home')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button',{name:'Новый объект'}));
    expect(await screen.findByText('Смета начинается с короткого брифа')).toBeInTheDocument();
  });

  it('restores a stored session instead of creating a new workspace',async()=>{
    history.replaceState(null,'','/?entered=1');
    const restored={id:'sess_saved',role:'client_pro',plan:'pro_construction',device:'desktop',windows:[{component_id:'estimate'}],chat:[{id:'m1',kind:'user',text:'открой смету'}],active_estimate_id:estimate.id};
    mockApi.session.mockReturnValue(restored);mockApi.token.mockReturnValue('stored-token');mockApi.getSession.mockResolvedValue(restored);
    render(<App/>);
    expect(await screen.findByTestId('app-estimate')).toBeInTheDocument();
    expect(mockApi.createSession).not.toHaveBeenCalled();
    expect(mockApi.getSession).toHaveBeenCalledWith('sess_saved');
  });

});
