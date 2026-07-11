
import { describe, it, expect } from 'vitest';
import { itemTotal, recalculateEstimate } from './estimateMath.js';

describe('estimate math', () => {
  it('calculates item totals with coefficient', () => {
    expect(itemTotal({ qty: 2, price: 100, coef: 1.5 })).toBe(300);
  });
  it('recalculates estimate summary', () => {
    const e = recalculateEstimate({ items:[{ qty: 10, price: 1000, coef: 1 }] });
    expect(e.summary.subtotal).toBe(10000);
    expect(e.summary.total).toBe(12000);
  });
});
