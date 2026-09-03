import { describe, expect, it } from "vitest";

import {
  isValidNumericInput,
  isValidTextInput,
  updateCompactAnswer,
  updateMatchingAnswer,
  updateNumericInputAnswer,
  updateTextInputAnswer,
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

  it("accepts free text that survives trimming and trailing punctuation", () => {
    expect(isValidTextInput("однако")).toBe(true);
    expect(isValidTextInput("  ОДНАКО.  ")).toBe(true);
    expect(isValidTextInput("")).toBe(false);
    expect(isValidTextInput("   ")).toBe(false);
    expect(isValidTextInput("...")).toBe(false);
    expect(isValidTextInput(["но"])).toBe(false);
    expect(isValidTextInput("с".repeat(80))).toBe(true);
    expect(isValidTextInput("с".repeat(81))).toBe(false);
    expect(isValidTextInput("с".repeat(41), 40)).toBe(false);
  });

  it("stores only usable free-text answers", () => {
    expect(updateTextInputAnswer({ q1: "7" }, "q5", " Однако ")).toEqual({ q1: "7", q5: " Однако " });
    expect(updateTextInputAnswer({ q1: "7", q5: "но" }, "q5", "  ")).toEqual({ q1: "7" });
    expect(updateTextInputAnswer({ q1: "7", q5: "но" }, "q5", "с".repeat(5), 3)).toEqual({ q1: "7" });
  });

  it("truncates later compact selections when the middle is cleared, then allows refill", () => {
    const cleared = updateCompactAnswer("123", 1, "");
    expect(cleared).toBe("1");

    const refilledMiddle = updateCompactAnswer(cleared, 1, "2");
    expect(refilledMiddle).toBe("12");
    expect(updateCompactAnswer(refilledMiddle, 2, "3")).toBe("123");
  });
});
