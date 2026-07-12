import { formatEstimateMoney } from "./estimateModel";

export function EstimateTotals({ currency, minorUnit, totals }) {
  const items = [
    ["Работы и материалы", totals.subtotalMinor],
    ["Накладные", totals.overheadMinor],
    ["Налог", totals.taxMinor],
    ["Итого", totals.grandTotalMinor],
  ];
  return (
    <section className="estimate-summary" aria-label="Детерминированные итоги сметы">
      {items.map(([label, value]) => (
        <span key={label}>
          {label}
          <strong>{formatEstimateMoney(value, minorUnit, currency)}</strong>
        </span>
      ))}
    </section>
  );
}
