import { describe, expect, it } from "vitest";

import { shouldShowResultMetrics } from "./result-display";

describe("shouldShowResultMetrics", () => {
  it("shows a valid zero result", () => {
    expect(shouldShowResultMetrics({ correct_count: 0, score: 0 })).toBe(true);
  });

  it("shows metrics when the test produced a positive result", () => {
    expect(shouldShowResultMetrics({ correct_count: 3, score: 60 })).toBe(true);
  });

  it("hides malformed metrics", () => {
    expect(shouldShowResultMetrics({ correct_count: -1, score: 60 })).toBe(false);
    expect(shouldShowResultMetrics({ correct_count: 3, score: Number.NaN })).toBe(false);
  });
});
