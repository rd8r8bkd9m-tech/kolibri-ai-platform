import { buildEstimateTitle } from "./estimateTitle";

const CATEGORY_ALIASES = Object.freeze({
  work: "labor",
  works: "labor",
  labor: "labor",
  material: "material",
  materials: "material",
  equipment: "equipment",
  service: "service",
  services: "service",
  other: "other",
});

const PRICE_SOURCES = new Set([
  "manual",
  "assumption",
  "normative",
  "catalog",
  "contract",
  "supplier",
  "measurement",
]);

const SUCCESS_SOURCE_STATUSES = new Set(["verified", "passed"]);
const MAX_SAFE_MINOR = BigInt(Number.MAX_SAFE_INTEGER);

function record(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function boundedText(value, fallback = "") {
  const text = typeof value === "string" ? value.trim() : "";
  return text || fallback;
}

function nonNegativeInteger(value) {
  if (typeof value === "number" && Number.isSafeInteger(value) && value >= 0) return value;
  if (typeof value === "string" && /^\d+$/.test(value)) {
    const parsed = Number(value);
    return Number.isSafeInteger(parsed) ? parsed : null;
  }
  return null;
}

function minorFactor(minorUnit) {
  return 10n ** BigInt(minorUnit);
}

function decimalFraction(value) {
  const normalized = String(value ?? "").trim().replace(",", ".");
  const match = /^(?:0|[1-9]\d*)(?:\.(\d{1,12}))?$/.exec(normalized);
  if (!match) return null;
  const fraction = match[1] || "";
  const digits = normalized.replace(".", "");
  return {
    numerator: BigInt(digits),
    denominator: 10n ** BigInt(fraction.length),
  };
}

function roundHalfUp(numerator, denominator) {
  if (denominator <= 0n) return 0n;
  const quotient = numerator / denominator;
  const remainder = numerator % denominator;
  return quotient + (remainder * 2n >= denominator ? 1n : 0n);
}

function majorPriceToMinorBigInt(value, minorUnit) {
  const fraction = decimalFraction(value);
  if (!fraction) return null;
  return roundHalfUp(fraction.numerator * minorFactor(minorUnit), fraction.denominator);
}

function minorBigInt(value) {
  if (typeof value === "bigint" && value >= 0n) return value;
  const integer = nonNegativeInteger(value);
  return integer === null ? null : BigInt(integer);
}

function lineTotalMinor(quantity, unitPriceMinor) {
  const amount = minorBigInt(unitPriceMinor);
  const factor = decimalFraction(quantity);
  if (amount === null || !factor || factor.numerator <= 0n) return 0n;
  return roundHalfUp(amount * factor.numerator, factor.denominator);
}

function lineCollection(estimate) {
  if (Array.isArray(estimate.lines) && estimate.lines.length) {
    return estimate.lines.map((line) => ({ sectionName: line.section, line }));
  }
  if (!Array.isArray(estimate.sections)) return [];
  return estimate.sections.flatMap((section) => {
    const sectionRecord = record(section);
    const items = Array.isArray(sectionRecord.items)
      ? sectionRecord.items
      : Array.isArray(sectionRecord.lines) ? sectionRecord.lines : [];
    return items.map((line) => ({
      sectionName: sectionRecord.name || sectionRecord.title,
      line,
    }));
  });
}

function researchLines(value) {
  const research = record(value);
  for (const key of ["lines", "items", "proofs", "line_proofs"]) {
    if (Array.isArray(research[key])) return research[key];
  }
  for (const key of ["by_line_id", "lines_by_id"]) {
    const mapping = record(research[key]);
    if (Object.keys(mapping).length) {
      return Object.entries(mapping).map(([lineId, proof]) => ({ line_id: lineId, ...record(proof) }));
    }
  }
  return [];
}

function researchIndex(value) {
  return new Map(researchLines(value).map((item) => [
    boundedText(item.line_id || item.id),
    record(item),
  ]).filter(([lineId]) => lineId));
}

function safeHttpUrl(value) {
  if (typeof value !== "string") return "";
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password
      ? url.toString()
      : "";
  } catch {
    return "";
  }
}

function rangeMinor(value, minorUnit) {
  const direct = nonNegativeInteger(value);
  if (direct !== null) return direct;
  const converted = majorPriceToMinorBigInt(value, minorUnit);
  return converted !== null && converted <= MAX_SAFE_MINOR ? Number(converted) : null;
}

function normalizePriceEvidence(line, provenance, research, minorUnit, unitPriceMinor) {
  const directSource = record(line.source);
  const range = record(line.price_range || line.range);
  const priceMinMinor = rangeMinor(
    research.price_min_minor
      ?? provenance.price_min_minor
      ?? line.price_min_minor
      ?? range.min_minor
      ?? range.min,
    minorUnit,
  );
  const priceMaxMinor = rangeMinor(
    research.price_max_minor
      ?? provenance.price_max_minor
      ?? line.price_max_minor
      ?? range.max_minor
      ?? range.max,
    minorUnit,
  );
  const status = boundedText(
    research.status
      || line.source_status
      || directSource.status
      || provenance.validation_status,
    "unverified",
  ).toLowerCase();
  const sourceUrl = safeHttpUrl(
    research.source_url
      || line.source_url
      || directSource.url
      || provenance.source_url,
  );
  return {
    status,
    independentlyVerified: SUCCESS_SOURCE_STATUSES.has(status),
    sourceRef: boundedText(
      research.source_title
        || research.source_ref
        || line.source_ref
        || directSource.title
        || provenance.source_ref
        || provenance.source,
      "Источник не указан",
    ),
    sourceHost: boundedText(research.source_host || directSource.host),
    sourceUrl,
    sourceDate: boundedText(
      research.source_retrieved_at
        || research.source_date
        || line.source_date
        || directSource.date
        || provenance.captured_at
        || provenance.price_level_date,
    ),
    sourceQuote: boundedText(
      research.source_quote
        || line.source_quote
        || directSource.quote
        || provenance.source_quote,
    ),
    sourceContentSha256: boundedText(research.source_content_sha256),
    selectionRule: boundedText(research.selection_rule),
    priceMinMinor,
    priceMaxMinor,
    selectedUnitPriceMinor: nonNegativeInteger(
      research.selected_unit_price_minor ?? unitPriceMinor,
    ),
  };
}

function normalizeLine(entry, index, minorUnit, research, calculationLines) {
  const line = record(entry.line);
  const id = boundedText(line.id, `line-${index + 1}`);
  const priceProvenance = {
    ...record(line.price_provenance),
    ...record(line.provenance),
  };
  const sourceType = boundedText(
    priceProvenance.source || (typeof line.source === "string" ? line.source : ""),
    "manual",
  ).toLowerCase();
  const provenance = {
    ...priceProvenance,
    source: PRICE_SOURCES.has(sourceType) ? sourceType : "manual",
    source_ref: boundedText(
      priceProvenance.source_ref,
      sourceType !== "manual" ? sourceType : "Ручной ввод",
    ),
    validation_status: boundedText(priceProvenance.validation_status, "unverified"),
  };
  const proof = research.get(id) || {};
  const unitPriceMinor = nonNegativeInteger(
    line.unit_price_minor
      ?? proof.selected_unit_price_minor,
  ) ?? rangeMinor(line.unit_price, minorUnit) ?? 0;
  const calculationLine = calculationLines.get(id) || {};
  const calculatedTotal = nonNegativeInteger(
    calculationLine.line_total_minor
      ?? line.line_total_minor
      ?? line.total_minor,
  );

  return {
    id,
    section: boundedText(entry.sectionName || line.section, "Основные работы"),
    description: boundedText(line.description || line.name, `Позиция ${index + 1}`),
    category: CATEGORY_ALIASES[boundedText(line.category || line.type, "other").toLowerCase()] || "other",
    unit: boundedText(line.unit, "шт"),
    quantity: String(line.quantity ?? "1"),
    price: minorToMajorInput(unitPriceMinor, minorUnit),
    unitPriceMinor,
    initialLineTotalMinor: calculatedTotal,
    provenance,
    evidence: normalizePriceEvidence(line, provenance, proof, minorUnit, unitPriceMinor),
  };
}

function materializedPdf(payload) {
  const task = record(payload.task);
  const artifacts = Array.isArray(payload.artifacts) && payload.artifacts.length
    ? payload.artifacts
    : Array.isArray(task.artifacts) ? task.artifacts : [];
  return artifacts.find((artifact) => {
    const item = record(artifact);
    const kind = item.deliverable_type || item.kind;
    return item.status === "materialized"
      && kind === "pdf"
      && item.media_type === "application/pdf"
      && typeof item.locator === "string";
  }) || null;
}

export function normalizeEstimatePayload(payload = {}) {
  const task = record(payload.task);
  const result = record(task.result);
  const nestedEstimate = record(result.estimate);
  const estimate = Array.isArray(payload.lines) || Array.isArray(payload.sections)
    ? record(payload)
    : Object.keys(nestedEstimate).length ? nestedEstimate : record(payload.estimate);
  const calculation = record(result.calculation || payload.calculation);
  const calculationLines = new Map(
    (Array.isArray(calculation.lines) ? calculation.lines : [])
      .map((line) => [boundedText(line?.id), record(line)])
      .filter(([lineId]) => lineId),
  );
  const priceResearch = result.price_research || payload.price_research;
  const minorUnit = [0, 2, 3].includes(estimate.minor_unit)
    ? estimate.minor_unit
    : [0, 2, 3].includes(calculation.minor_unit) ? calculation.minor_unit : 2;
  const research = researchIndex(priceResearch);
  const lines = lineCollection(estimate).map((entry, index) => (
    normalizeLine(entry, index, minorUnit, research, calculationLines)
  ));
  const verification = record(result.verification || payload.verification);
  const status = ["preliminary", "verified"].includes(result.status)
    ? result.status
    : ["preliminary", "verified"].includes(verification.status)
      ? verification.status
      : "preliminary";
  const pricedLineCount = lines.filter((line) => line.unitPriceMinor > 0).length;
  const sourcedLineCount = lines.filter((line) => (
    line.evidence.sourceUrl
      || (line.provenance.source && !["manual", "assumption"].includes(line.provenance.source))
  )).length;
  const sourceCoverageComplete = verification.source_coverage_complete === true
    || (lines.length > 0 && sourcedLineCount === lines.length);

  return {
    title: buildEstimateTitle({
      objectName: estimate.object_name ?? payload.object_name,
      objectTypeLabel: estimate.object_type_label ?? payload.object_type_label,
      areaM2: estimate.gross_area_m2 ?? payload.gross_area_m2,
      locality: estimate.locality ?? payload.locality,
      region: estimate.region || payload.metadata?.region || payload.region,
    }),
    currency: boundedText(estimate.currency || calculation.currency, "RUB"),
    minorUnit,
    region: boundedText(estimate.region || payload.metadata?.region || payload.region, "Не указан"),
    clientName: estimate.client_name ?? payload.client_name ?? null,
    objectName: estimate.object_name ?? payload.object_name ?? null,
    objectAddress: estimate.object_address ?? payload.object_address ?? null,
    sourceSummary: boundedText(
      estimate.source_summary || payload.metadata?.provenance || payload.source_summary,
      "Цены требуют проверки",
    ),
    normativeBasis: estimate.normative_basis || payload.normative_basis || null,
    assumptions: Array.isArray(estimate.assumptions) ? estimate.assumptions.filter(Boolean) : [],
    questions: Array.isArray(estimate.questions) ? estimate.questions.filter(Boolean) : [],
    overheadRateBps: nonNegativeInteger(estimate.overhead_rate_bps) ?? 0,
    taxRateBps: nonNegativeInteger(estimate.tax_rate_bps) ?? 0,
    lines,
    pricedLineCount,
    sourcedLineCount,
    sourceCoverageComplete,
    status,
    confidenceLabel: status === "verified"
      ? "Источники независимо проверены"
      : lines.length
        ? sourcedLineCount > 0
          ? `Внешние источники: ${sourcedLineCount} из ${lines.length} позиций`
          : "Цены модели · требуют проверки"
        : "Источники требуют проверки",
    calculation,
    pdfArtifact: materializedPdf(payload),
  };
}

export function minorToMajorInput(value, minorUnit = 2) {
  const amount = minorBigInt(value) ?? 0n;
  const factor = minorFactor(minorUnit);
  const whole = amount / factor;
  if (minorUnit === 0) return whole.toString();
  const fraction = (amount % factor).toString().padStart(minorUnit, "0");
  return `${whole}.${fraction}`;
}

export function priceInputToMinor(value, minorUnit = 2) {
  const amount = majorPriceToMinorBigInt(value, minorUnit);
  if (amount === null || amount > MAX_SAFE_MINOR) return null;
  return Number(amount);
}

export function validEstimateQuantity(value) {
  const fraction = decimalFraction(value);
  return Boolean(fraction && fraction.numerator > 0n);
}

export function calculateEstimateTotals(
  lines,
  { minorUnit = 2, overheadRateBps = 0, taxRateBps = 0 } = {},
) {
  const categories = new Map();
  const lineTotals = new Map();
  let subtotal = 0n;
  for (const line of lines || []) {
    const priceMinor = priceInputToMinor(line.price, minorUnit) ?? 0;
    const total = lineTotalMinor(line.quantity, priceMinor);
    lineTotals.set(line.id, total);
    categories.set(line.category, (categories.get(line.category) || 0n) + total);
    subtotal += total;
  }
  const overhead = roundHalfUp(subtotal * BigInt(overheadRateBps || 0), 10_000n);
  const taxable = subtotal + overhead;
  const tax = roundHalfUp(taxable * BigInt(taxRateBps || 0), 10_000n);
  return {
    lineTotals,
    categories,
    subtotalMinor: subtotal,
    overheadMinor: overhead,
    taxMinor: tax,
    grandTotalMinor: taxable + tax,
  };
}

export function formatEstimateMoney(value, minorUnit = 2, currency = "RUB") {
  let amount = typeof value === "bigint" ? value : minorBigInt(value) ?? 0n;
  const negative = amount < 0n;
  if (negative) amount = -amount;
  const factor = minorFactor(minorUnit);
  const whole = amount / factor;
  const grouped = whole.toString().replace(/\B(?=(\d{3})+(?!\d))/g, "\u00a0");
  const fraction = minorUnit > 0
    ? `,${(amount % factor).toString().padStart(minorUnit, "0")}`
    : "";
  const symbol = currency === "RUB" ? "₽" : currency;
  return `${negative ? "−" : ""}${grouped}${fraction}\u00a0${symbol}`;
}

export function provenanceLabel(line, minorUnit = 2, currency = "RUB") {
  const evidence = line.evidence || {};
  const parts = [evidence.sourceRef];
  if (evidence.sourceDate) parts.push(`цены ${evidence.sourceDate.slice(0, 10)}`);
  if (evidence.priceMinMinor !== null && evidence.priceMaxMinor !== null) {
    parts.push(
      `${formatEstimateMoney(evidence.priceMinMinor, minorUnit, currency)}–${formatEstimateMoney(evidence.priceMaxMinor, minorUnit, currency)}`,
    );
  }
  return parts.filter(Boolean).join(" · ");
}
