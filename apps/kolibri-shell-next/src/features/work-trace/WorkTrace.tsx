import { completedStageCount, type SafeWorkTrace } from "@domain/shell";
import { Calculator, Check, ChevronDown, ChevronUp, ShieldCheck } from "lucide-react";
import { useState } from "react";

interface WorkTraceProps {
  trace: SafeWorkTrace;
}

export function WorkTrace({ trace }: WorkTraceProps) {
  const [expanded, setExpanded] = useState(true);
  const completed = completedStageCount(trace);
  const total = trace.stages.length;

  return (
    <section className={`work-trace ${expanded ? "is-expanded" : ""}`} aria-label="Ход работы">
      <div className="trace-desktop">
        <button
          className="trace-toggle"
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded((open) => !open)}
        >
          {expanded ? <ChevronUp aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}
          <strong>Ход работы</strong>
        </button>
        <span className="trace-count">{completed}/{total} завершено</span>
        {expanded ? (
          <ol className="trace-stages">
            {trace.stages.map((stage) => (
              <li key={stage.id} className={`stage-${stage.state}`}>
                <span className="stage-dot">{stage.state === "done" ? <Check aria-hidden="true" /> : null}</span>
                <span>{stage.label}</span>
              </li>
            ))}
          </ol>
        ) : null}
      </div>

      <div className="trace-mobile">
        <button
          className="mobile-trace-heading"
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded((open) => !open)}
        >
          <span><strong>{trace.status === "completed" ? "Kolibri завершил" : "Kolibri работает"}</strong></span>
          <i aria-hidden="true" />
          <span>{completed} из {total} этапов</span>
          {expanded ? <ChevronUp aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}
        </button>
        {expanded ? (
          <>
            {trace.agents.length > 0 ? (
              <div className="trace-agents">
                {trace.agents.map((agent, index) => (
                  <span className="trace-agent" key={agent.id}>
                    <span className={`agent-icon tone-${agent.tone}`}>
                      {agent.icon === "calculator" ? <Calculator aria-hidden="true" /> : <ShieldCheck aria-hidden="true" />}
                    </span>
                    {agent.label} — {agent.stateLabel}
                    {index < trace.agents.length - 1 ? <b aria-hidden="true">|</b> : null}
                  </span>
                ))}
              </div>
            ) : (
              <ol className="mobile-safe-stages">
                {trace.stages.map((stage) => <li key={stage.id} className={`stage-${stage.state}`}>{stage.label}</li>)}
              </ol>
            )}
            <button className="trace-details" type="button" onClick={() => setExpanded(false)}>Подробнее</button>
          </>
        ) : null}
      </div>
    </section>
  );
}
