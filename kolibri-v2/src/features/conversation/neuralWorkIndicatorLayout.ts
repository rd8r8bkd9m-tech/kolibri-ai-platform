/**
 * A compact pentagonal orbit. Keeping the points in data makes the visual
 * contract testable and prevents a future regression back to a horizontal
 * progress row.
 */
export const NEURAL_NODE_LAYOUT = [
  { x: '50%', y: '7%' },
  { x: '91%', y: '37%' },
  { x: '76%', y: '87%' },
  { x: '24%', y: '87%' },
  { x: '9%', y: '37%' },
] as const
