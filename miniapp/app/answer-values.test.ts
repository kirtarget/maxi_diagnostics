import { describe, expect, it } from "vitest";

import {
  isValidNumericInput,
  updateMatchingAnswer,
  updateNumericInputAnswer,
} from "./answer-values";

describe("shared answer value helpers", () => {
  it("validates bounded numeric drafts consistently", () => {
    expect(isValidNumericInput("-1.5")).toBe(true);
    expect(isValidNumericInput("1e999")).toBe(true);
    expect(isValidNumericInput("1e1000")).toBe(false);
    expect(isValidNumericInput(" 42")).toBe(false);
  });

  it("updates and clears matching answers without mutating the source", () => {
    const current = { a: "1", b: "2" };
    expect(updateMatchingAnswer(current, "a", "3")).toEqual({ a: "3", b: "2" });
    expect(updateMatchingAnswer(current, "a", "")).toEqual({ b: "2" });
    expect(current).toEqual({ a: "1", b: "2" });
  });

  it("stores only complete valid numeric answers", () => {
    expect(updateNumericInputAnswer({ q1: "7" }, "q2", "-2,5")).toEqual({ q1: "7", q2: "-2,5" });
    expect(updateNumericInputAnswer({ q1: "7", q2: "4" }, "q2", "-")).toEqual({ q1: "7" });
  });
});
