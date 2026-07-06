export interface ServerClassification {
  node_id: string;
  canonical_name: string;
  tier: 'control' | 'execution' | 'model' | 'hybrid' | 'reserve';
  tier_ru: string;
  internal_ip: string | null;
  external_ip: string | null;
  ssh_alias: string | null;
  lifecycle: string;
  api_port: number | null;
  api_endpoint: string | null;
}

export interface SubnetDefinition {
  tag: string;
  cidr: string;
  description_ru: string;
  gateway: string | null;
  member_count: number;
}

export interface FleetClassification {
  servers: Record<string, ServerClassification>;
  subnets: Record<string, SubnetDefinition>;
  generated_at: string;
}
