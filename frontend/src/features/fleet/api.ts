import { FleetClassification } from './types';

const FLEET_API = 'http://192.168.88.210:9102';

export async function fetchFleetClassification(): Promise<FleetClassification> {
  const resp = await fetch(`${FLEET_API}/v1/fleet/classification`);
  if (!resp.ok) throw new Error(`Fleet API error: ${resp.status}`);
  return resp.json();
}

export async function fetchHealth(): Promise<{ status: string; servers: number; subnets: number }> {
  const resp = await fetch(`${FLEET_API}/v1/health`);
  return resp.json();
}
