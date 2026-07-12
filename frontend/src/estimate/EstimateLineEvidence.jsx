import { CircleAlert, CircleCheck, ExternalLink } from "lucide-react";
import { provenanceLabel } from "./estimateModel";

export function EstimateLineEvidence({ currency, line, minorUnit }) {
  const evidence = line.evidence || {};
  const hasSource = Boolean(
    evidence.sourceUrl
      || (line.provenance?.source && !["manual", "assumption"].includes(line.provenance.source)),
  );
  const status = evidence.independentlyVerified
    ? "Проверен"
    : hasSource ? "Источник указан, не проверен нормативно" : "Источник требует уточнения";
  const Icon = evidence.independentlyVerified ? CircleCheck : CircleAlert;

  return (
    <div className={`estimate-line-evidence ${evidence.independentlyVerified ? "is-verified" : "is-preliminary"}`}>
      <span>
        <Icon aria-hidden="true" size={13} />
        <span title={evidence.sourceQuote || ""}>{provenanceLabel(line, minorUnit, currency)}</span>
        {evidence.sourceUrl && (
          <a aria-label={`Открыть источник для позиции «${line.description}»`} href={evidence.sourceUrl} rel="noreferrer" target="_blank">
            <ExternalLink aria-hidden="true" size={13} />
          </a>
        )}
      </span>
      <small>{status}</small>
      {evidence.sourceQuote && <p>«{evidence.sourceQuote}»</p>}
    </div>
  );
}
