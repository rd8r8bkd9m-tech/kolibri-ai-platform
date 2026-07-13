import { AlertCircle, RotateCw } from 'lucide-react';
import { useEffect, useRef } from 'react';
import type { ConversationMessage } from '../model/conversation';
import { ArtifactCard } from './ArtifactCard';
import { EstimateWorkspace } from './EstimateWorkspace';
import { WorkTrace } from './WorkTrace';

interface ConversationStageProps {
  messages: ConversationMessage[];
  connectionError?: string;
  presentation: 'mobile' | 'desktop';
  onRetryConnection(): void;
}

function formatTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ''
    : new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit' }).format(date);
}

function MessageTurn({
  message,
  presentation,
}: {
  message: ConversationMessage;
  presentation: 'mobile' | 'desktop';
}) {
  const timestamp = formatTime(message.createdAt);
  if (message.role === 'user') {
    return (
      <article className="message-turn user-turn">
        <div className="user-message-meta">Вы, сегодня в {timestamp}</div>
        <div className="user-message">{message.content}<time>{timestamp}</time></div>
      </article>
    );
  }

  return (
    <article className={`message-turn assistant-turn is-${message.status}`} aria-live={message.status === 'streaming' ? 'polite' : undefined}>
      <div className="assistant-label">Kolibri, сегодня в {timestamp}</div>
      {message.content ? <div className="assistant-copy">{message.content}</div> : null}
      <time className="assistant-time">{timestamp}</time>
      <WorkTrace
        trace={message.trace}
        streaming={message.status === 'streaming'}
        presentation={presentation}
      />
      {message.artifacts.length ? (
        <div className="artifact-list">
          {message.artifacts.map((artifact) => artifact.kind === 'estimate' && artifact.estimate ? (
            <EstimateWorkspace
              key={artifact.id}
              artifact={artifact as typeof artifact & { estimate: NonNullable<typeof artifact.estimate> }}
              presentation={presentation}
            />
          ) : <ArtifactCard key={artifact.id} artifact={artifact} />)}
        </div>
      ) : null}
      {message.status === 'cancelled' ? <p className="message-note">Ответ остановлен.</p> : null}
    </article>
  );
}

export function ConversationStage({
  messages,
  connectionError,
  presentation,
  onRetryConnection,
}: ConversationStageProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const mountedRef = useRef(false);

  useEffect(() => {
    if (!mountedRef.current) {
      mountedRef.current = true;
      return;
    }
    bottomRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' });
  }, [messages]);

  return (
    <main className="stage" id="main-content">
      <div className="conversation-scroll" data-testid="conversation-scroll">
        <div className="conversation-column">
          {connectionError ? (
            <section className="connection-banner" role="alert">
              <AlertCircle aria-hidden="true" />
              <div><strong>Kolibri не подключён</strong><p>{connectionError}</p></div>
              <button type="button" onClick={onRetryConnection}><RotateCw aria-hidden="true" /> Повторить</button>
            </section>
          ) : null}

          {!messages.length ? (
            <section className="empty-stage">
              <p>Начните новый диалог с Kolibri.</p>
            </section>
          ) : (
            <section className="message-list" aria-label="Диалог">
              {messages.map((message) => (
                <MessageTurn key={message.id} message={message} presentation={presentation} />
              ))}
            </section>
          )}
          <div ref={bottomRef} aria-hidden="true" />
        </div>
      </div>
    </main>
  );
}
