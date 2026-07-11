
export function itemTotal(item) { return Math.round(Number(item.qty || 0) * Number(item.price || 0) * Number(item.coef || 1)); }
export function recalculateEstimate(estimate) {
  const subtotal = (estimate.items || []).reduce((sum, item) => sum + itemTotal(item), 0);
  const overhead = Math.round(subtotal * 0.08);
  const margin = Math.round(subtotal * 0.12);
  return { ...estimate, summary: { subtotal, overhead, margin, total: subtotal + overhead + margin } };
}
export function rub(value) { return new Intl.NumberFormat('ru-RU', { style:'currency', currency:'RUB', maximumFractionDigits:0 }).format(Number(value || 0)); }
