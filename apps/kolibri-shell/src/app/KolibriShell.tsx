import { useCallback, useEffect, useMemo, useState } from 'react';
import type { BootstrapSnapshot, KolibriClient, ProjectSummary } from '../api/types';
import { Composer } from '../components/Composer';
import { ConversationStage } from '../components/ConversationStage';
import { HistoryOverlay } from '../components/HistoryOverlay';
import { ShellHeader } from '../components/ShellHeader';
import { useConversation } from '../hooks/useConversation';
import { useResponsiveSurface } from '../hooks/useResponsiveSurface';
import { useVisualViewport } from '../hooks/useVisualViewport';
import type { ConversationState } from '../model/conversation';

export interface ShellInitialView {
  project?: ProjectSummary;
  conversation?: ConversationState;
}

interface KolibriShellProps {
  client: KolibriClient;
  initialView?: ShellInitialView;
}

type BootstrapState =
  | { status: 'loading'; data?: undefined; error?: undefined }
  | { status: 'ready'; data: BootstrapSnapshot; error?: undefined }
  | { status: 'error'; data?: undefined; error: string };

export function KolibriShell({ client, initialView }: KolibriShellProps) {
  const [bootstrap, setBootstrap] = useState<BootstrapState>({ status: 'loading' });
  const [historyOpen, setHistoryOpen] = useState(false);
  const [activeProject, setActiveProject] = useState<ProjectSummary | undefined>(initialView?.project);
  const surface = useResponsiveSurface();
  const conversation = useConversation(client, activeProject?.id, initialView?.conversation);
  useVisualViewport();

  const connect = useCallback(async () => {
    const controller = new AbortController();
    setBootstrap({ status: 'loading' });
    try {
      const data = await client.bootstrap(controller.signal);
      setBootstrap({ status: 'ready', data });
      setActiveProject((current) => current ?? data.projects[0]);
    } catch (error) {
      setBootstrap({
        status: 'error',
        error: error instanceof Error ? error.message : 'Не удалось установить безопасную сессию.',
      });
    }
  }, [client]);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    client.bootstrap(controller.signal).then(
      (data) => {
        if (!active) return;
        setBootstrap({ status: 'ready', data });
        setActiveProject((current) => current ?? data.projects[0]);
      },
      (error: unknown) => {
        if (!active || controller.signal.aborted) return;
        setBootstrap({
          status: 'error',
          error: error instanceof Error ? error.message : 'Не удалось установить безопасную сессию.',
        });
      },
    );
    return () => {
      active = false;
      controller.abort();
    };
  }, [client]);

  const projects = bootstrap.status === 'ready' ? bootstrap.data.projects : [];
  const capabilities = bootstrap.status === 'ready' ? bootstrap.data.capabilities : [];
  const projectTitle = activeProject?.title ?? 'Новый диалог';

  const newConversation = useCallback(() => {
    conversation.clear();
    setActiveProject(undefined);
    setHistoryOpen(false);
  }, [conversation]);

  const selectProject = useCallback(
    (project: ProjectSummary) => {
      conversation.clear();
      setActiveProject(project);
      setHistoryOpen(false);
    },
    [conversation],
  );

  const shellClass = useMemo(() => `kolibri-shell is-${surface}`, [surface]);

  return (
    <div className={shellClass} data-surface={surface}>
      <a className="skip-link" href="#main-content">К содержимому</a>
      <ShellHeader
        presentation={surface}
        projectTitle={projectTitle}
        historyOpen={historyOpen}
        onToggleHistory={() => setHistoryOpen((open) => !open)}
        onNewConversation={newConversation}
      />

      <ConversationStage
        messages={conversation.state.messages}
        presentation={surface}
        connectionError={bootstrap.status === 'error' ? bootstrap.error : undefined}
        onRetryConnection={() => void connect()}
      />

      <Composer
        capabilities={capabilities}
        presentation={surface}
        busy={conversation.busy}
        disabled={bootstrap.status !== 'ready'}
        onSend={(input, tools) => void conversation.send(input, tools)}
        onStop={() => void conversation.stop()}
      />

      <HistoryOverlay
        open={historyOpen}
        presentation={surface}
        projects={projects}
        activeProjectId={activeProject?.id}
        onClose={() => setHistoryOpen(false)}
        onNewConversation={newConversation}
        onSelectProject={selectProject}
      />
    </div>
  );
}
