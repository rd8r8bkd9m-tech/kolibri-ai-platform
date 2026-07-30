const AREA_TOKEN = /\d+(?:[.,]\d+)?\s*(?:м(?:²|2)|кв\.?\s*м)(?=\s|$|[.,;:—-])/i;
const ADMINISTRATIVE_PART = /^(?:республика|область|край|автономн(?:ая|ый)\s+(?:область|округ)|город\s+федерального\s+значения)(?:\s|$)/i;

function clean(value, limit = 160) {
  return typeof value === "string"
    ? [...value].map((character) => {
      const code = character.codePointAt(0);
      return code < 32 || code === 127 ? " " : character;
    }).join("").replace(/\s+/g, " ").trim().slice(0, limit)
    : "";
}

function comparable(value) {
  return clean(value).toLocaleLowerCase("ru-RU").replace(/\s+/g, " ");
}

function displayArea(value) {
  const normalized = String(value ?? "").trim().replace(",", ".");
  if (!/^\d+(?:\.\d+)?$/.test(normalized)) return "";
  const amount = Number(normalized);
  if (!Number.isFinite(amount) || amount <= 0 || amount > 10_000_000) return "";
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(amount);
}

function normalizeRegionPart(value) {
  return clean(value, 80).replace(/^республика\s+/i, "").trim();
}

function locationLabel(locality, region) {
  const explicitLocality = clean(locality, 80);
  const parts = clean(region, 180).split(/[,;]+/).map((part) => ({
    administrative: ADMINISTRATIVE_PART.test(part.trim()),
    label: normalizeRegionPart(part),
  })).filter((part) => part.label);
  const seen = new Set();
  const unique = [];
  for (const part of [{ administrative: false, label: explicitLocality }, ...parts]) {
    const key = comparable(part.label);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    unique.push(part);
  }
  if (!explicitLocality && unique.length > 1) {
    unique.sort((left, right) => Number(left.administrative) - Number(right.administrative));
  }
  return unique.slice(0, 3).map((part) => part.label).join(", ");
}

export function buildEstimateTitle({ objectName, objectTypeLabel, areaM2, locality, region } = {}) {
  const area = displayArea(areaM2);
  const object = clean(objectName || objectTypeLabel, 180)
    .replace(/^смета\s*[:—-]?\s*/i, "")
    .replace(/^исходные\s+данные\s+для\s+(?:правдивой\s+)?сметы\s*[:—-]?\s*/i, "")
    || "строительные работы";
  const objectWithArea = area && !AREA_TOKEN.test(object) ? `${object} ${area} м²` : object;
  const location = locationLabel(locality, region);
  return `Смета: ${objectWithArea}${location ? ` — ${location}` : ""}`;
}

export function estimateTitleFromPayload(payload = {}) {
  const readiness = payload.readiness || payload.task?.result?.readiness || {};
  const facts = readiness.known_facts || {};
  const estimate = payload.task?.result?.estimate || payload.estimate || payload;
  return buildEstimateTitle({
    objectName: estimate.object_name || facts.object_name,
    objectTypeLabel: facts.object_type_label,
    areaM2: estimate.gross_area_m2 || facts.gross_area_m2,
    locality: estimate.locality || facts.locality,
    region: estimate.region || facts.region || payload.metadata?.region,
  });
}

export function estimateArtifactDisplayName(artifact, estimateTitle) {
  const title = clean(estimateTitle, 220) || buildEstimateTitle();
  const kind = clean(artifact?.deliverable_type || artifact?.kind, 20).toUpperCase();
  return kind ? `${kind} · ${title}` : title;
}
