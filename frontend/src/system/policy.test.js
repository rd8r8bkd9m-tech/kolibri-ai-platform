
import { describe, it, expect } from 'vitest';
import { manifest } from '../test/manifest.js';
import { resolveTurn } from './policy.js';

describe('Vista policy', () => {
  it('does not render server windows for client', () => {
    const turn = resolveTurn(manifest, { roleId:'client', text:'покажи метрики серверов', deviceId:'desktop' });
    expect(turn.components.map(c=>c.id)).not.toContain('server.metrics');
    expect(turn.denied_capabilities.map(c=>c.id)).toContain('server.metrics.read');
  });
  it('renders server windows for server admin', () => {
    const turn = resolveTurn(manifest, { roleId:'server_admin', text:'покажи метрики серверов', deviceId:'desktop' });
    expect(turn.components.map(c=>c.id)).toContain('server.metrics');
    expect(turn.components.map(c=>c.id)).toContain('server.logs');
  });
  it('owner sees full contour', () => {
    const turn = resolveTurn(manifest, { roleId:'owner', text:'полный контур Vista', deviceId:'desktop' });
    expect(turn.components.length).toBeGreaterThan(5);
  });
});
