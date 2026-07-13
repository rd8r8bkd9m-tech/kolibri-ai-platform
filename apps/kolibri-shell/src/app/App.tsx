import { useMemo } from 'react';
import { KolibriHttpClient } from '../api/KolibriHttpClient';
import type { KolibriClient } from '../api/types';
import { KolibriShell, type ShellInitialView } from './KolibriShell';

interface AppProps {
  client?: KolibriClient;
  initialView?: ShellInitialView;
}

export function App({ client, initialView }: AppProps) {
  const runtimeClient = useMemo(() => client ?? new KolibriHttpClient(), [client]);
  return <KolibriShell client={runtimeClient} initialView={initialView} />;
}
