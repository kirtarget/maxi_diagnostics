import { describe, expect, it } from "vitest";

import { estimateCaption, estimateHeadline, forecastUnitLabel, normalizedEstimate } from "./score-estimate";

function estimate(overrides: Record<string, unknown> = {}) {
  return {
    kind: "test_score",
    value: 62,
    scaled_primary: 24,
    exam_max_primary: 45,
    sample_max_primary: 12,
    sample_size: 12,
    min_pass: 36,
    ...overrides,
  };
}

describe("score estimate wording", () => {
  it.each([
    [1, "≈ 1 балл ЕГЭ"],
    [2, "≈ 2 балла ЕГЭ"],
    [11, "≈ 11 баллов ЕГЭ"],
    [62, "≈ 62 балла ЕГЭ"],
    [100, "≈ 100 баллов ЕГЭ"],
  ])("declines the point noun for %i", (value, expected) => {
    expect(estimateHeadline(estimate({ value }), "ЕГЭ")).toBe(expected);
  });

  it("names the grade without an exam", () => {
    expect(estimateHeadline(estimate({ kind: "grade", value: 4 }), "ОГЭ")).toBe("отметка 4");
  });

  it("drops a missing exam name", () => {
    expect(estimateHeadline(estimate(), null)).toBe("≈ 62 балла");
  });

  it.each([
    [1, "ориентировочно, по 1 заданию"],
    [12, "ориентировочно, по 12 заданиям"],
  ])("reports a sample of %i", (sample_size, expected) => {
    expect(estimateCaption(estimate({ sample_size }))).toBe(expected);
  });

  it.each([
    undefined,
    null,
    {},
    { kind: "test_score", value: 62 },
    { kind: "unknown", value: 62, sample_size: 12 },
    { kind: "test_score", value: "62", sample_size: 12 },
    { kind: "test_score", value: 6.5, sample_size: 12 },
    { kind: "test_score", value: 62, sample_size: 0 },
    [estimate()],
    "estimate",
  ])("says nothing for an unusable estimate %#", (value) => {
    expect(normalizedEstimate(value)).toBeNull();
    expect(estimateHeadline(value, "ЕГЭ")).toBeNull();
    expect(estimateCaption(value)).toBeNull();
  });

  it("labels forecast numbers in the unit they are measured in", () => {
    expect(forecastUnitLabel("grade", 4)).toBe("отметка");
    expect(forecastUnitLabel("test_score", 62)).toBe("балла");
    expect(forecastUnitLabel("accuracy_percent", 50)).toBe("баллов");
    expect(forecastUnitLabel(undefined, 1)).toBe("балл");
  });
});
