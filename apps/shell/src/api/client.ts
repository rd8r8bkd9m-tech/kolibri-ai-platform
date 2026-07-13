export type Project = { id: string; title: string; updated_at: string; deleted_at?: string | null }
export type Message = { id: string; role: 'user' | 'assistant' | 'system'; content: string; created_at: string }
export type Source = { id: string; title: string; url: string; region: string; price_date: string; unit: string; verification_status: string }
export type EstimateItem = { id: string; section: string; name: string; unit: string; quantity: string; unit_price: string; coefficient: string; source_id?: string | null; line_total?: string; verified?: boolean; source?: Source | null }
export type Estimate = { id: string; project_id: string; title: string; client_name: string; region: string; status: 'needs_input'|'preliminary'|'verified'; revision: number; subtotal: string; total: string; overhead_pct: string; margin_pct: string; discount_pct: string; tax_pct: string; items: EstimateItem[]; sources: Source[] }
export type Artifact = { id: string; name: string; mime_type: string; size: number; sha256: string; revision?: number }
export type Capability = { id: string; label: string; available: boolean }

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    credentials: 'include',
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init.headers || {}) },
  })
  const contentType = response.headers.get('content-type') || ''
  const body = contentType.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) {
    const message = typeof body === 'object' && body?.error?.message ? body.error.message : `HTTP ${response.status}`
    throw new Error(message)
  }
  return body as T
}

export async function bootstrap() {
  return request<{session:{id:string;role:string}; active_project:Project; projects:Project[]; capabilities:Capability[]}>(
    '/v1/shell/bootstrap', { method: 'POST', body: JSON.stringify({ role: 'client' }) }
  )
}
export async function listMessages(projectId: string) { return request<{data:Message[]}>(`/v1/projects/${projectId}/messages`) }
export async function listProjects() { return request<{data:Project[]}>('/v1/projects') }
export async function createProject(title='Новый проект') { return request<Project>('/v1/projects',{method:'POST',body:JSON.stringify({title})}) }
export async function renameProject(id:string,title:string){ return request<Project>(`/v1/projects/${id}`,{method:'PATCH',body:JSON.stringify({title})}) }
export async function deleteProject(id:string){ return request(`/v1/projects/${id}`,{method:'DELETE'}) }
export async function restoreProject(id:string){ return request<Project>(`/v1/projects/${id}/restore`,{method:'POST'}) }
export async function listEstimates(projectId:string){ return request<{data:Estimate[]}>(`/v1/estimates?project_id=${encodeURIComponent(projectId)}`) }
export async function createEstimate(projectId:string,title='Смета проекта'){ return request<Estimate>('/v1/estimates',{method:'POST',body:JSON.stringify({project_id:projectId,title})}) }
export async function patchEstimate(id:string,data:Partial<Estimate>,revision?:number){ return request<Estimate>(`/v1/estimates/${id}`,{method:'PATCH',headers: revision!==undefined?{'If-Match':String(revision)}:{},body:JSON.stringify(data)}) }
export async function addItem(id:string,data:Partial<EstimateItem> & {name:string}){ return request<Estimate>(`/v1/estimates/${id}/items`,{method:'POST',body:JSON.stringify(data)}) }
export async function patchItem(id:string,itemId:string,data:Partial<EstimateItem>){ return request<Estimate>(`/v1/estimates/${id}/items/${itemId}`,{method:'PATCH',body:JSON.stringify(data)}) }
export async function deleteItem(id:string,itemId:string){ return request<Estimate>(`/v1/estimates/${id}/items/${itemId}`,{method:'DELETE'}) }
export async function addSource(id:string,data:Omit<Source,'id'>){ return request<{source:Source;estimate:Estimate}>(`/v1/estimates/${id}/sources`,{method:'POST',body:JSON.stringify(data)}) }
export async function exportEstimate(id:string,formats=['pdf','xlsx','docx','json','md']){ return request<{artifacts:Artifact[]}>(`/v1/estimates/${id}/exports`,{method:'POST',body:JSON.stringify({formats})}) }
export async function listArtifacts(id:string){ return request<{data:Artifact[]}>(`/v1/estimates/${id}/artifacts`) }

export type StreamEvent = { type:string; sequence_number:number; delta?:string; estimate_id?:string; status?:string; output_text?:string; [key:string]:unknown }
export async function createStreamingResponse(projectId:string,input:string,onEvent:(event:StreamEvent)=>void):Promise<void>{
  const response = await fetch('/v1/responses',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify({model:'kolibri',project_id:projectId,input,stream:true})})
  if(!response.ok || !response.body){ const body=await response.text(); throw new Error(body || `HTTP ${response.status}`) }
  const reader=response.body.getReader(); const decoder=new TextDecoder(); let buffer=''
  while(true){
    const {done,value}=await reader.read(); if(done) break
    buffer += decoder.decode(value,{stream:true})
    const blocks=buffer.split('\n\n'); buffer=blocks.pop() || ''
    for(const block of blocks){
      const dataLine=block.split('\n').find(line=>line.startsWith('data: ')); if(!dataLine) continue
      const raw=dataLine.slice(6); if(raw==='[DONE]') return
      try{ onEvent(JSON.parse(raw)) }catch{ /* ignore keep-alive */ }
    }
  }
}
