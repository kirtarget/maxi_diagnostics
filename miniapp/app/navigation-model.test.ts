// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import { examPreferenceKey, formatDiagnosticMeta, readExamPreference, resultFact, shouldShowBottomNav, submitPresentation, writeExamPreference } from "./navigation-model";

describe("navigation model", () => {
  const diagnostic = {
    id: "math", content_version: "v1", exam: "ЕГЭ", subject: "Математика", mark: "М",
    quick_count: 3, full_count: 18, question_count: 18,
  };

  it("models subject before format and documents count/duration", () => {
    expect(formatDiagnosticMeta("quick", diagnostic)).toBe("3 задания · ~5 мин");
    expect(formatDiagnosticMeta("full", diagnostic)).toBe("18 заданий · ~30 мин");
    expect(formatDiagnosticMeta("full", { ...diagnostic, full_count: 11 })).toBe("11 заданий · ~18 мин");
    expect(formatDiagnosticMeta("quick", { ...diagnostic, quick_count: 6 })).toBe("6 заданий · ~10 мин");
  });

  it("uses the school-scoped preference key and result facts", () => {
    expect(examPreferenceKey("north-school")).toBe("diagnostic-exam-preference:north-school");
    expect(resultFact({
      attempt_id: "attempt-1", diagnostic_id: "math", content_version: "v1", mode: "full", status: "completed",
      question_index: 18, question_count: 18, progress_revision: 1,
      result: { diagnostic_id: "math", mode: "full", question_count: 18, correct_count: 1, skipped_count: 0, score: 1, max_score: 18, score_unit: "балл", strong_topics: [], growth_topics: [] },
    })).toBe("1 из 18 · 6 %");
  });

  it("persists only the selected exam in the school-scoped preference", () => {
    const storage = new Map<string, string>();
    const adapter = {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => { storage.set(key, value); },
    } as unknown as Storage;
    writeExamPreference("school-a", "ОГЭ", adapter);
    expect(readExamPreference("school-a", adapter)).toBe("ОГЭ");
    expect(readExamPreference("school-b", adapter)).toBeNull();
    expect([...storage.keys()]).toEqual([examPreferenceKey("school-a")]);
  });

  it("contains localStorage acquisition failures inside the preference guard", () => {
    const descriptor = Object.getOwnPropertyDescriptor(window, "localStorage");
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get: () => { throw new Error("storage unavailable"); },
    });
    try {
      expect(readExamPreference("school-a")).toBeNull();
      expect(() => writeExamPreference("school-a", "ЕГЭ")).not.toThrow();
    } finally {
      if (descriptor) Object.defineProperty(window, "localStorage", descriptor);
    }
  });

  it("keeps a fast submit surface for 300ms and warns only for slow pending work", () => {
    expect(submitPresentation(40)).toEqual({ remainingMs: 260, showWarning: false });
    expect(submitPresentation(300)).toEqual({ remainingMs: 0, showWarning: true });
  });

  it("hides bottom navigation only during active assessment screens", () => {
    expect(shouldShowBottomNav("today")).toBe(true);
    expect(shouldShowBottomNav("question")).toBe(false);
    expect(shouldShowBottomNav("trainer")).toBe(false);
    expect(shouldShowBottomNav("submitting")).toBe(false);
  });
});
