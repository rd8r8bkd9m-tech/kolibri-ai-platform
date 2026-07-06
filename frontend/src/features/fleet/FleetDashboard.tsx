import { useState, useEffect } from 'react';
import { fetchFleetClassification } from './api';
import { FleetClassification, ServerClassification } from './types';

const TIER_COLORS: Record<string, string> = {
  control: 'bg-blue-500',
  hybrid: 'bg-purple-500',
  model: 'bg-green-500',
  execution: 'bg-orange-500',
  reserve: 'bg-gray-500',
};

function ServerCard({ server }: { server: ServerClassification }) {
  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-center gap-3 mb-3">
        <div className={`w-3 h-3 rounded-full ${TIER_COLORS[server.tier]}`} />
        <div>
          <h3 className="font-semibold text-sm">{server.node_id}</h3>
          <p className="text-xs text-gray-500">{server.canonical_name}</p>
        </div>
      </div>
      <div className="space-y-1 text-xs">
        <div className="flex justify-between">
          <span className="text-gray-500">Tier:</span>
          <span className="font-medium">{server.tier_ru}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">VPN:</span>
          <span className="font-mono">{server.internal_ip || '—'}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Public:</span>
          <span className="font-mono">{server.external_ip || '—'}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">Status:</span>
          <span className={`font-medium ${server.lifecycle === 'active' ? 'text-green-600' : 'text-red-600'}`}>
            {server.lifecycle}
          </span>
        </div>
      </div>
    </div>
  );
}

export default function FleetDashboard() {
  const [fleet, setFleet] = useState<FleetClassification | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await fetchFleetClassification();
        setFleet(data);
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };
    load();
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div className="p-8 text-center">Loading fleet...</div>;
  if (error) return <div className="p-8 text-center text-red-500">Error: {error}</div>;
  if (!fleet) return null;

  const servers = Object.values(fleet.servers);
  const tierCounts = servers.reduce((acc, s) => { acc[s.tier] = (acc[s.tier] || 0) + 1; return acc; }, {} as Record<string, number>);

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-2">Kolibri Fleet</h1>
        <div className="flex gap-4 text-sm">
          <span className="font-semibold">{servers.length} servers</span>
          {Object.entries(tierCounts).map(([tier, count]) => (
            <span key={tier} className="flex items-center gap-1">
              <div className={`w-2 h-2 rounded-full ${TIER_COLORS[tier]}`} />
              {count} {tier}
            </span>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {servers.map(s => <ServerCard key={s.node_id} server={s} />)}
      </div>
    </div>
  );
}
