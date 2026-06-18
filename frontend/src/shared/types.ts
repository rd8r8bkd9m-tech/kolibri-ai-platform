// Kolibri AI — Core Types

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  provider?: string;
  timestamp: number;
  streaming?: boolean;
  canvas?: CanvasCard[];
}

export interface CanvasCard {
  id: string;
  type: 'estimate' | 'document' | 'table' | 'code' | 'plan' | 'checklist' | 'memory' | 'action';
  title: string;
  data: any;
  status?: 'draft' | 'ready' | 'exported';
  created_at?: number;
}

export interface Estimate {
  estimate_id: string;
  title: string;
  client: Client;
  object: EstimateObject;
  items: EstimateItem[];
  totals: EstimateTotals;
  assumptions: string[];
  warnings: string[];
  version: number;
  created_at?: number;
  updated_at?: number;
}

export interface Client {
  name: string;
  phone: string;
  address: string;
}

export interface EstimateObject {
  type: string;
  area: number;
  location: string;
}

export interface EstimateItem {
  id: string;
  section: string;
  name: string;
  unit: string;
  quantity: number;
  unit_price: number;
  total: number;
  note: string;
}

export interface EstimateTotals {
  works: number;
  materials: number;
  delivery: number;
  discount: number;
  grand_total: number;
}

export interface Trace {
  trace_id: string;
  user_id: string;
  type: 'preference' | 'correction' | 'task' | 'document' | 'estimate' | 'code' | 'behavior';
  content: string;
  weight: number;
  confidence: number;
  created_at: string;
  links: string[];
}

export interface PersonalCoreVector {
  user_id: string;
  core_digits: number[];
  stability: number;
  curiosity: number;
  precision: number;
  creativity: number;
  practical_focus: number;
  memory_weight: number;
  trust_level: number;
  last_updated: string;
}

export interface ClusterNode {
  name: string;
  role: string;
  ip: string;
  cpu: number | string;
  ram: string;
  status: 'online' | 'offline';
}

export interface ClusterStatus {
  cluster: string;
  subnet: string;
  total_nodes: number;
  online_nodes: number;
  total_ram_gb: number;
  used_ram_gb: number;
  free_ram_gb: number;
  avg_cpu_percent: number;
  nodes: Record<string, ClusterNode>;
  queue_size?: number;
}

export interface Provider {
  name: string;
  available: boolean;
  status: string;
}

export interface DocumentExport {
  format: 'pdf' | 'docx' | 'xlsx' | 'json';
  filename: string;
  data: any;
}
