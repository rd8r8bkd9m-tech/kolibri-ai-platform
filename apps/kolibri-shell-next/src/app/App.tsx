import "@app/styles.css";
import type { ShellClient } from "@services/shellClient";
import { Conversation } from "@features/chat/Conversation";
import { Composer } from "@features/composer/Composer";
import { EstimateArtifact } from "@features/estimate/EstimateArtifact";
import { ProjectHeader } from "@features/project/ProjectHeader";
import { useShellController } from "@features/shell/useShellController";
import { WorkTrace } from "@features/work-trace/WorkTrace";
import { LoaderCircle, RefreshCw, X } from "lucide-react";

interface AppProps {
  client: ShellClient;
}

export function App({ client }: AppProps) {
  const { state, retry, send, updateEstimateLine, setNotice } = useShellController(client);

  return (
    <div className="kolibri-shell">
      <ProjectHeader
        project={state.project}
        runtimeStatus={state.runtimeStatus}
        onRetry={retry}
        onNotice={(message) => setNotice(message)}
      />

      <main className="shell-main">
        {state.runtimeStatus === "connecting" ? (
          <section className="runtime-state" aria-live="polite">
            <LoaderCircle className="spin" aria-hidden="true" />
            <h1>Подключаем Kolibri</h1>
            <p>Создаём безопасную сессию для этого чата.</p>
          </section>
        ) : null}

        {state.runtimeStatus === "unavailable" ? (
          <section className="runtime-state runtime-error" role="alert">
            <h1>Kolibri сейчас недоступен</h1>
            <p>{state.errorMessage}</p>
            <button type="button" onClick={retry}>
              <RefreshCw aria-hidden="true" />
              Повторить
            </button>
          </section>
        ) : null}

        {state.runtimeStatus === "ready" ? (
          <>
            <Conversation messages={state.messages} />
            {state.trace ? <WorkTrace trace={state.trace} /> : null}
            {state.estimate ? (
              <EstimateArtifact
                estimate={state.estimate}
                onLineChange={updateEstimateLine}
                onNotice={(message) => setNotice(message)}
              />
            ) : null}
          </>
        ) : null}
      </main>

      <div className="composer-dock">
        <Composer
          runtimeStatus={state.runtimeStatus}
          sending={state.isSending}
          onSend={send}
          onNotice={(message) => setNotice(message)}
        />
      </div>

      {state.notice ? (
        <div className="toast" role="status">
          <span>{state.notice}</span>
          <button type="button" aria-label="Закрыть уведомление" onClick={() => setNotice(null)}>
            <X aria-hidden="true" />
          </button>
        </div>
      ) : null}
    </div>
  );
}
