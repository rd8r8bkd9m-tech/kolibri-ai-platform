import { estimateGroups, estimateTotal, lineTotal, replaceEstimateLine, type EstimateArtifact } from "@domain/shell";
import { describe, expect, it } from "vitest";

const estimate: EstimateArtifact = {
  id: "estimate-test",
  title: "Смета",
  location: "Лениногорск",
  pricedAt: "12.07.2026",
  sourceSummary: "Проверенные источники",
  fileName: "estimate.pdf",
  fileSizeLabel: "PDF · 1 КБ",
  lines: [
    { id: "foundation", kind: "foundation", label: "Фундамент", unit: "м³", quantity: 24, unitPrice: 9_500 },
    { id: "walls", kind: "shell", label: "Стены", unit: "м²", quantity: 240, unitPrice: 2_755 },
    { id: "roof", kind: "roof", label: "Кровля", unit: "м²", quantity: 120, unitPrice: 2_750 },
    { id: "openings", kind: "openings", label: "Окна", unit: "м²", quantity: 24, unitPrice: 12_500 },
    { id: "systems", kind: "systems", label: "Сети", unit: "компл.", quantity: 1, unitPrice: 481_000 },
  ],
};

describe("estimate arithmetic", () => {
  it("derives line, grouped and grand totals from line items", () => {
    expect(lineTotal(estimate.lines[0]!)).toBe(228_000);
    expect(estimateGroups(estimate).map((group) => group.total)).toEqual([228_000, 991_200, 781_000]);
    expect(estimateTotal(estimate)).toBe(2_000_200);
  });

  it("recalculates after an edit without mutating the previous artifact", () => {
    const changed = replaceEstimateLine(estimate, "foundation", { unitPrice: 10_000 });
    expect(estimateTotal(changed)).toBe(2_012_200);
    expect(estimateTotal(estimate)).toBe(2_000_200);
  });
});
