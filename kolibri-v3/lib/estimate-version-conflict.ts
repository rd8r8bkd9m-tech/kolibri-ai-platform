export type EstimateDraftRow = {
  id: string;
  description: string;
  unit: string;
  quantity: string;
  unitPrice: string;
};

export type EstimateDraftSnapshot = {
  title: string;
  rows: readonly EstimateDraftRow[];
};

export type EstimateVersionConflict = {
  expectedVersion: number;
  currentVersion: number;
};

export type EstimateDraftConflictDiff = {
  localChanges: readonly string[];
  remoteChanges: readonly string[];
  conflicts: readonly string[];
};

const EDITABLE_ROW_FIELDS = [
  "description",
  "unit",
  "quantity",
  "unitPrice",
] as const;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const positiveInteger = (value: unknown) =>
  typeof value === "number" &&
  Number.isSafeInteger(value) &&
  value > 0
    ? value
    : null;

export function parseEstimateVersionConflict(
  status: number,
  payload: unknown,
): EstimateVersionConflict | null {
  if (status !== 409 || !isRecord(payload)) return null;
  const detail = isRecord(payload.detail) ? payload.detail : payload;
  if (detail.code !== "estimate_version_conflict") return null;
  const expectedVersion = positiveInteger(detail.expected_version);
  const currentVersion = positiveInteger(detail.current_version);
  if (expectedVersion === null || currentVersion === null) return null;
  return { expectedVersion, currentVersion };
}

const rowLabel = (
  base: EstimateDraftRow | undefined,
  local: EstimateDraftRow | undefined,
  remote: EstimateDraftRow | undefined,
) => {
  const description =
    local?.description.trim() ||
    remote?.description.trim() ||
    base?.description.trim();
  return description ? `Позиция «${description.slice(0, 80)}»` : "Позиция";
};

const changedFields = (
  baseline: EstimateDraftRow,
  candidate: EstimateDraftRow,
) =>
  EDITABLE_ROW_FIELDS.filter(
    (field) => baseline[field] !== candidate[field],
  );

const rowsEqual = (left: EstimateDraftRow, right: EstimateDraftRow) =>
  EDITABLE_ROW_FIELDS.every((field) => left[field] === right[field]);

export function diffEstimateDrafts(
  baseline: EstimateDraftSnapshot,
  local: EstimateDraftSnapshot,
  remote: EstimateDraftSnapshot,
): EstimateDraftConflictDiff {
  const localChanges: string[] = [];
  const remoteChanges: string[] = [];
  const conflicts: string[] = [];

  const localTitleChanged = local.title !== baseline.title;
  const remoteTitleChanged = remote.title !== baseline.title;
  if (localTitleChanged) localChanges.push("Название сметы");
  if (remoteTitleChanged) remoteChanges.push("Название сметы");
  if (
    localTitleChanged &&
    remoteTitleChanged &&
    local.title !== remote.title
  ) {
    conflicts.push("Название сметы");
  }

  const baselineRows = new Map(baseline.rows.map((row) => [row.id, row]));
  const localRows = new Map(local.rows.map((row) => [row.id, row]));
  const remoteRows = new Map(remote.rows.map((row) => [row.id, row]));
  const rowIds = new Set([
    ...baselineRows.keys(),
    ...localRows.keys(),
    ...remoteRows.keys(),
  ]);

  for (const rowId of rowIds) {
    const baseRow = baselineRows.get(rowId);
    const localRow = localRows.get(rowId);
    const remoteRow = remoteRows.get(rowId);
    const label = rowLabel(baseRow, localRow, remoteRow);

    if (!baseRow) {
      if (localRow) localChanges.push(`${label}: добавлена локально`);
      if (remoteRow) remoteChanges.push(`${label}: добавлена на сервере`);
      if (localRow && remoteRow && !rowsEqual(localRow, remoteRow)) {
        conflicts.push(`${label}: разные новые данные`);
      }
      continue;
    }

    if (!localRow) localChanges.push(`${label}: удалена локально`);
    if (!remoteRow) remoteChanges.push(`${label}: удалена на сервере`);
    if (!localRow || !remoteRow) {
      const survivingRow = localRow ?? remoteRow;
      if (
        survivingRow &&
        changedFields(baseRow, survivingRow).length > 0
      ) {
        conflicts.push(`${label}: удаление пересекается с изменениями`);
      }
      continue;
    }

    const localFields = changedFields(baseRow, localRow);
    const remoteFields = changedFields(baseRow, remoteRow);
    if (localFields.length > 0) localChanges.push(label);
    if (remoteFields.length > 0) remoteChanges.push(label);
    if (
      localFields.some(
        (field) =>
          remoteFields.includes(field) &&
          localRow[field] !== remoteRow[field],
      )
    ) {
      conflicts.push(`${label}: изменены одни и те же поля`);
    }
  }

  return { localChanges, remoteChanges, conflicts };
}
