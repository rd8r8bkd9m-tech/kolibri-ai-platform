import "@features/wallboard/program-wallboard.css";
import type {
  ProgramAvailability,
  ProgramGate,
  ProgramGateStatus,
  ProgramStatusClient,
  ProgramStatusSnapshot,
} from "@services/programStatusClient";
import { ProgramStatusClientError } from "@services/programStatusClient";
import { AlertTriangle, Check, Clock3, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

interface ProgramWallboardProps {
  client: ProgramStatusClient;
  refreshIntervalMs?: number;
}

const gateLabel: Record<ProgramGateStatus, string> = {
  completed: "Готово",
  in_progress: "В работе",
  blocked: "Заблокировано",
  not_started: "Не начато",
};

const availabilityLabel: Record<ProgramAvailability, string> = {
  live: "Данные актуальны",
  partial: "Работа продолжается",
  stale: "Данные устарели",
  unavailable: "Источник недоступен",
};

function dateLabel(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "время не подтверждено";
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Moscow",
  }).format(parsed);
}

function safeReason(error: unknown): string {
  if (error instanceof ProgramStatusClientError) {
    if (error.status === 401) return "Требуется защищённая сессия владельца.";
    if (error.reason === "program_status_source_unavailable") return "Program Ledger на Home недоступен.";
    if (error.reason === "program_status_sensitive_data_rejected") return "Ledger отклонён политикой безопасности.";
  }
  return "Не удалось получить подтверждённый Program Ledger.";
}

function GateRow({ gate }: { gate: ProgramGate }) {
  return (
    <article className={`wallboard-gate gate-${gate.status}`}>
      <div className="wallboard-gate-number">{gate.gate}</div>
      <div className="wallboard-gate-copy">
        <div className="wallboard-gate-heading">
          <h2>{gate.name}</h2>
          <span>{gateLabel[gate.status]}</span>
        </div>
        <p>{gate.nextAction}</p>
        {gate.blockers.length > 0 ? (
          <details>
            <summary>{gate.blockers.length} блокирующих условия</summary>
            <ul>{gate.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>
          </details>
        ) : null}
        <small>{gate.evidenceIds.length} evidence · обновлено {dateLabel(gate.updatedAt)}</small>
      </div>
    </article>
  );
}

export function ProgramWallboard({ client, refreshIntervalMs = 30_000 }: ProgramWallboardProps) {
  const [snapshot, setSnapshot] = useState<ProgramStatusSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (signal: AbortSignal) => {
    try {
      const next = await client.load(signal);
      setSnapshot(next);
      setError(null);
    } catch (reason) {
      if (signal.aborted) return;
      setError(safeReason(reason));
    } finally {
      if (!signal.aborted) setLoading(false);
    }
  }, [client]);

  useEffect(() => {
    const controller = new AbortController();
    const initial = window.setTimeout(() => void load(controller.signal), 0);
    const timer = window.setInterval(() => void load(controller.signal), refreshIntervalMs);
    return () => {
      controller.abort();
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, [load, refreshIntervalMs]);

  const availability: ProgramAvailability = error ? "unavailable" : snapshot?.availability ?? "unavailable";

  return (
    <div className="program-wallboard">
      <header className="wallboard-header">
        <div className="wallboard-brand">
          <img src="/kolibri-bird.png" alt="" />
          <div>
            <p>Kolibri AI OS</p>
            <h1>Разработка на Home</h1>
          </div>
        </div>
        <div className={`wallboard-availability availability-${availability}`} role="status">
          {availability === "live" ? <Check aria-hidden="true" /> : <Clock3 aria-hidden="true" />}
          {availabilityLabel[availability]}
        </div>
      </header>

      {loading && !snapshot ? (
        <main className="wallboard-empty" aria-live="polite">
          <RefreshCw className="spin" aria-hidden="true" />
          <h2>Читаю Program Ledger</h2>
          <p>Значения появятся только после проверки источника.</p>
        </main>
      ) : null}

      {error && !snapshot ? (
        <main className="wallboard-empty wallboard-unavailable" role="alert">
          <AlertTriangle aria-hidden="true" />
          <h2>Прогресс нельзя подтвердить</h2>
          <p>{error}</p>
          <button type="button" onClick={() => {
            setLoading(true);
            void load(new AbortController().signal);
          }}>
            <RefreshCw aria-hidden="true" />
            Повторить
          </button>
        </main>
      ) : null}

      {snapshot ? (
        <main className="wallboard-content">
          {error ? <div className="wallboard-warning" role="alert">{error} Показан последний подтверждённый срез.</div> : null}
          <section className="wallboard-overview" aria-labelledby="program-progress-title">
            <div>
              <p className="wallboard-kicker">Приёмочные гейты</p>
              <h2 id="program-progress-title">
                {snapshot.progress.completed} из {snapshot.progress.total} завершены
              </h2>
              <p>Fleet campaign и готовность продукта учитываются раздельно.</p>
            </div>
            <strong>{(snapshot.progress.completedRatio * 100).toLocaleString("ru-RU", { maximumFractionDigits: 1 })}%</strong>
          </section>
          <div className="wallboard-progress" aria-label={`${snapshot.progress.completed} из ${snapshot.progress.total} гейтов завершены`}>
            <span style={{ width: `${snapshot.progress.completedRatio * 100}%` }} />
          </div>

          <section className="wallboard-counts" aria-label="Сводка статусов">
            <div><strong>{snapshot.progress.completed}</strong><span>Готово</span></div>
            <div><strong>{snapshot.progress.inProgress}</strong><span>В работе</span></div>
            <div><strong>{snapshot.progress.blocked}</strong><span>Заблокировано</span></div>
            <div><strong>{snapshot.progress.notStarted}</strong><span>Не начато</span></div>
          </section>

          <section className="wallboard-gates" aria-label="Гейты программы">
            {snapshot.gates.map((gate) => <GateRow gate={gate} key={gate.id} />)}
          </section>

          <footer className="wallboard-footer">
            <span>Источник: Home Program Ledger</span>
            <span>Срез: {dateLabel(snapshot.asOf)}</span>
            <span>Commit: {snapshot.sourceCommit.slice(0, 8)}</span>
            <span>{snapshot.sourceSha256.slice(0, 20)}…</span>
          </footer>
        </main>
      ) : null}
    </div>
  );
}
