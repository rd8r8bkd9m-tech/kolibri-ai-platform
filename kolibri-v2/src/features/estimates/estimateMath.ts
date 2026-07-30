import type { Estimate, EstimateTotals, Position } from '@/lib/api'

export type EstimateNumericField = 'quantity' | 'price'
export type EstimateRateField =
  | 'overhead_rate'
  | 'profit_rate'
  | 'contingency_rate'
  | 'general_contractor_rate'
  | 'discount_rate'
  | 'vat_rate'

interface ExactDecimal {
  coefficient: bigint
  scale: number
}

const DECIMAL_INPUT = /^\d+(?:\.\d+)?$/

function power10(exponent: number): bigint {
  return 10n ** BigInt(exponent)
}

function parseDecimal(value: string): ExactDecimal {
  const normalized = value.trim().replace(',', '.')
  if (!DECIMAL_INPUT.test(normalized)) throw new Error('invalid_decimal')
  const [integer, fraction = ''] = normalized.split('.')
  return {
    coefficient: BigInt(`${integer}${fraction}`),
    scale: fraction.length,
  }
}

function divideRoundHalfUp(numerator: bigint, denominator: bigint): bigint {
  if (denominator <= 0n) throw new Error('invalid_denominator')
  const negative = numerator < 0n
  const absolute = negative ? -numerator : numerator
  const quotient = absolute / denominator
  const remainder = absolute % denominator
  const rounded = remainder * 2n >= denominator ? quotient + 1n : quotient
  return negative ? -rounded : rounded
}

function decimalToMinor(decimal: ExactDecimal): bigint {
  if (decimal.scale <= 2) return decimal.coefficient * power10(2 - decimal.scale)
  return divideRoundHalfUp(decimal.coefficient, power10(decimal.scale - 2))
}

function lineTotalMinor(quantity: string, price: string): bigint {
  const left = parseDecimal(quantity)
  const right = parseDecimal(price)
  const product = { coefficient: left.coefficient * right.coefficient, scale: left.scale + right.scale }
  return decimalToMinor(product)
}

function percentageMinor(baseMinor: bigint, rate: string): bigint {
  const parsedRate = parseDecimal(rate)
  return divideRoundHalfUp(
    baseMinor * parsedRate.coefficient,
    100n * power10(parsedRate.scale),
  )
}

function minorToMoney(value: bigint): string {
  const negative = value < 0n
  const absolute = negative ? -value : value
  const integer = absolute / 100n
  const fraction = String(absolute % 100n).padStart(2, '0')
  return `${negative ? '-' : ''}${integer}.${fraction}`
}

export function normalizeEditableDecimal(value: string): string | null {
  const normalized = value.trim().replace(',', '.')
  if (!DECIMAL_INPUT.test(normalized)) return null
  const [integer, fraction] = normalized.split('.')
  const normalizedInteger = integer.replace(/^0+(?=\d)/, '') || '0'
  return fraction === undefined ? normalizedInteger : `${normalizedInteger}.${fraction}`
}

export function calculatePositionSum(position: Pick<Position, 'quantity' | 'price'>): string {
  try {
    return minorToMoney(lineTotalMinor(position.quantity, position.price))
  } catch {
    return '0.00'
  }
}

export function calculateEstimateTotals(
  sections: readonly { positions?: readonly Pick<Position, 'quantity' | 'price'>[] }[],
  overheadRate: string,
  profitRate: string,
  contingencyRate: string,
  generalContractorRate: string,
  discountRate: string,
  vatRate: string,
): EstimateTotals {
  let subtotalMinor = 0n
  for (const section of sections) {
    for (const position of section.positions ?? []) {
      try {
        subtotalMinor += lineTotalMinor(position.quantity, position.price)
      } catch {
        // Invalid rows contribute zero and remain visible for correction.
      }
    }
  }
  let overheadMinor = 0n
  let profitMinor = 0n
  let contingencyMinor = 0n
  let generalContractorMinor = 0n
  let discountMinor = 0n
  let vatMinor = 0n
  try {
    overheadMinor = percentageMinor(subtotalMinor, overheadRate || '0')
    const profitBase = subtotalMinor + overheadMinor
    profitMinor = percentageMinor(profitBase, profitRate || '0')
    const contingencyBase = profitBase + profitMinor
    contingencyMinor = percentageMinor(contingencyBase, contingencyRate || '0')
    const contractorBase = contingencyBase + contingencyMinor
    generalContractorMinor = percentageMinor(contractorBase, generalContractorRate || '0')
    const grossBeforeDiscount = contractorBase + generalContractorMinor
    discountMinor = percentageMinor(grossBeforeDiscount, discountRate || '0')
    const vatBase = grossBeforeDiscount > discountMinor ? grossBeforeDiscount - discountMinor : 0n
    vatMinor = percentageMinor(vatBase, vatRate || '0')
  } catch {
    // Malformed rates fail closed exactly as in recalculateEstimate.
  }
  return {
    subtotal: minorToMoney(subtotalMinor),
    overhead_amount: minorToMoney(overheadMinor),
    profit_amount: minorToMoney(profitMinor),
    contingency_amount: minorToMoney(contingencyMinor),
    general_contractor_amount: minorToMoney(generalContractorMinor),
    discount_amount: minorToMoney(discountMinor),
    vat_amount: minorToMoney(vatMinor),
    total: minorToMoney(
      subtotalMinor + overheadMinor + profitMinor + contingencyMinor
      + generalContractorMinor - discountMinor + vatMinor,
    ),
  }
}

export function recalculateEstimate(estimate: Estimate): Estimate {
  const sections = estimate.sections.map(section => {
    let sectionMinor = 0n
    const positions = section.positions.map(position => {
      let sum = '0.00'
      try {
        const totalMinor = lineTotalMinor(position.quantity, position.price)
        sectionMinor += totalMinor
        sum = minorToMoney(totalMinor)
      } catch {
        // Invalid in-progress input is deliberately worth zero until the user
        // commits a valid decimal. It is never propagated as NaN.
      }
      return { ...position, sum }
    })
    return { ...section, positions, subtotal: minorToMoney(sectionMinor) }
  })

  const totals = calculateEstimateTotals(
    sections,
    estimate.overhead_rate,
    estimate.profit_rate || '0',
    estimate.contingency_rate || '0',
    estimate.general_contractor_rate || '0',
    estimate.discount_rate || '0',
    estimate.vat_rate,
  )

  return {
    ...estimate,
    sections,
    ...totals,
  }
}

export function updateEstimatePosition(
  estimate: Estimate,
  sectionId: string,
  positionId: string,
  field: EstimateNumericField,
  rawValue: string,
): Estimate | null {
  const value = normalizeEditableDecimal(rawValue)
  if (value === null) return null
  const sections = estimate.sections.map(section => section.id !== sectionId ? section : {
    ...section,
    positions: section.positions.map(position => position.id !== positionId
      ? position
      : { ...position, [field]: value }),
  })
  return recalculateEstimate({ ...estimate, sections })
}

export function updateEstimatePositionName(
  estimate: Estimate,
  sectionId: string,
  positionId: string,
  rawValue: string,
): Estimate | null {
  const value = rawValue.replace(/\s+/g, ' ').trim()
  if (!value || value.length > 500) return null
  return {
    ...estimate,
    sections: estimate.sections.map(section => section.id !== sectionId ? section : {
      ...section,
      positions: section.positions.map(position => position.id !== positionId
        ? position
        : { ...position, name: value }),
    }),
  }
}

export function deleteEstimatePosition(
  estimate: Estimate,
  sectionId: string,
  positionId: string,
): Estimate {
  const sections = estimate.sections.map(section => section.id !== sectionId ? section : {
    ...section,
    positions: section.positions.filter(position => position.id !== positionId),
  })
  return recalculateEstimate({ ...estimate, sections })
}

export function updateEstimateRate(
  estimate: Estimate,
  field: EstimateRateField,
  rawValue: string,
): Estimate | null {
  const value = normalizeEditableDecimal(rawValue)
  if (value === null) return null
  try {
    const parsed = Number(value)
    if (!Number.isFinite(parsed) || parsed < 0 || parsed > 999) return null
  } catch {
    return null
  }
  return recalculateEstimate({ ...estimate, [field]: value })
}

export function estimateTotalsEqual(left: Estimate, right: Estimate): boolean {
  const fields = [
    'subtotal',
    'overhead_amount',
    'profit_amount',
    'contingency_amount',
    'general_contractor_amount',
    'discount_amount',
    'vat_amount',
    'total',
  ] as const
  return fields.every(field => (left[field] || '0.00') === (right[field] || '0.00'))
    && left.sections.length === right.sections.length
    && left.sections.every((section, sectionIndex) => (
      section.subtotal === right.sections[sectionIndex]?.subtotal
      && section.positions.every((position, positionIndex) => (
        position.sum === right.sections[sectionIndex]?.positions[positionIndex]?.sum
      ))
    ))
}
