import {
  Calculator,
  CheckCircle2,
  ChevronDown,
  Circle,
  LoaderCircle,
  ShieldCheck,
  XCircle,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import type { WorkTraceUpdate } from '../api/types';

interface WorkTraceProps {
  trace: WorkTraceUpdate[];
  streaming: boolean;
  presentation: 'mobile' | 'desktop';
}

function StageIcon({ item }: { item: WorkTraceUpdate }) {
  if (item.status === 'failed') return <XCircle aria-hidden="true" />;
  if (item.status === 'complete') return <CheckCircle2 aria-hidden="true" />;
  if (item.stage === 'verifying') return <ShieldCheck aria-hidden="true" />;
  if (item.status === 'active') return <LoaderCircle className="spin" aria-hidden="true" />;
  return <Circle aria-hidden="true" />;
}

function Details({ trace }: { trace: WorkTraceUpdate[] }) {
  return (
    <ol className="work-trace-list">
      {trace.map((item) => (
        <li key={item.id} data-status={item.status}>
          <StageIcon item={item} />
          <div>
            <strong>{item.label}</strong>
            {item.summary ? <p>{item.summary}</p> : null}
          </div>
        </li>
      ))}
    </ol>
  );
}

export function WorkTrace({ trace, streaming, presentation }: WorkTraceProps) {
  const [expanded, setExpanded] = useState(false);
  const completed = useMemo(() => trace.filter((item) => item.status === 'complete').length, [trace]);
  const actors = trace.filter((item) => item.stage === 'tool' || item.stage === 'verifying').slice(-2);

  if (!trace.length && !streaming) return null;

  if (presentation === 'mobile') {
    return (
      <section className={`work-trace is-mobile${expanded ? ' is-expanded' : ''}`} aria-label="Ход работы">
        <button
          className="work-trace-mobile-summary"
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          <span><strong>Kolibri {streaming ? 'работает' : 'завершил'}</strong><i aria-hidden="true" />{completed} из {trace.length} этапов</span>
          <ChevronDown aria-hidden="true" />
        </button>
        <div className="work-trace-actors">
          {(actors.length ? actors : trace.slice(-2)).map((item, index) => (
            <div className="work-actor" key={item.id}>
              <span className={item.stage === 'verifying' ? 'is-verifier' : undefined}>
                {item.stage === 'verifying' ? <ShieldCheck aria-hidden="true" /> : <Calculator aria-hidden="true" />}
              </span>
              <p>{item.label}</p>
              {index === 0 && (actors.length || trace.slice(-2).length) > 1 ? <b aria-hidden="true" /> : null}
            </div>
          ))}
        </div>
        <button className="work-trace-more" type="button" onClick={() => setExpanded((value) => !value)}>
          {expanded ? 'Свернуть' : 'Подробнее'}
        </button>
        {expanded ? <Details trace={trace} /> : null}
      </section>
    );
  }

  return (
    <section className={`work-trace is-desktop${expanded ? ' is-expanded' : ''}`} aria-label="Ход работы">
      <div className="work-trace-band">
        <button
          className="work-trace-disclosure"
          type="button"
          aria-label={expanded ? 'Свернуть ход работы' : 'Показать ход работы'}
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          <ChevronDown aria-hidden="true" />
        </button>
        <strong>Ход работы</strong>
        <span className="work-trace-progress">{completed}/{trace.length} завершено</span>
        <div className="work-trace-stages">
          {trace.map((item) => (
            <div className="work-trace-stage" key={item.id} data-status={item.status}>
              <StageIcon item={item} />
              <span>{item.label}</span>
            </div>
          ))}
        </div>
      </div>
      {expanded ? <Details trace={trace} /> : null}
    </section>
  );
}
