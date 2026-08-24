import { describe, expect, it } from "vitest";

import { subjectIconKind } from "./subject-illustration";

describe("subjectIconKind", () => {
  it.each([
    ["Биология", "biology"],
    ["Химия", "chemistry"],
    ["Английский язык", "english"],
    ["История", "history"],
    ["Информатика", "informatics"],
    ["Литература", "literature"],
    ["Математика", "mathematics"],
    ["Физика", "physics"],
    ["Русский язык", "russian"],
    ["Обществознание", "social"],
  ])("maps %s to its illustration", (subject, expected) => {
    expect(subjectIconKind(subject)).toBe(expected);
  });

  it("uses a neutral illustration for a new subject", () => {
    expect(subjectIconKind("Астрономия")).toBe("general");
  });
});
