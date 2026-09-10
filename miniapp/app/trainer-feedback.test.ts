import { describe, expect, it } from "vitest";

import { correctOptionIds, lifeNote } from "./trainer-feedback";
import type { MultipleQuestion, Question, SingleQuestion } from "./types";

const source = {
  provider: "maximum",
  official_year: 2026,
  approval_status: "approved",
  source_kind: "original",
  source_url: "https://maximumtest.ru/",
  rights_status: "original",
  verified_at: "2026-09-01",
} as const;

const single: SingleQuestion = {
  id: "q1",
  type: "single",
  topic: "Общество",
  title: "Задание 1",
  prompt: "Чем человек отличается от животного?",
  max_primary_score: 1,
  source,
  options: [
    { id: "a", label: "Темпераментом" },
    { id: "b", label: "Инстинктами" },
    { id: "c", label: "Сознанием" },
  ],
};

const multiple: MultipleQuestion = {
  id: "q2",
  type: "multiple",
  topic: "Химия",
  title: "Задание 2",
  prompt: "Выбери два элемента.",
  max_primary_score: 1,
  selection_limit: 2,
  source,
  options: [
    { id: "a", label: "Co" },
    { id: "b", label: "As" },
    { id: "c", label: "He" },
  ],
};

describe("correctOptionIds", () => {
  it("resolves the server's label back to the option the screen drew", () => {
    expect(correctOptionIds(single, "Сознанием")).toEqual(["c"]);
  });

  it("resolves every label of a multiple choice answer", () => {
    expect(correctOptionIds(multiple, "Co, He")).toEqual(["a", "c"]);
  });

  it("ignores case, ё and stray spacing", () => {
    expect(correctOptionIds(single, "  сознанием ")).toEqual(["c"]);
  });

  it("drops the stress annotation the review appends to a single choice", () => {
    expect(correctOptionIds(single, "Сознанием · ударение: созна́нием")).toEqual(["c"]);
  });

  it("marks nothing when the label does not match, rather than guessing", () => {
    expect(correctOptionIds(single, "Разумом")).toEqual([]);
    expect(correctOptionIds(single, null)).toEqual([]);
  });

  it("marks nothing for a question that has no options to colour", () => {
    const input = { ...single, type: "input", answer_format: "number" } as unknown as Question;
    expect(correctOptionIds(input, "42")).toEqual([]);
  });
});

describe("lifeNote", () => {
  it("announces the spend and what is left", () => {
    expect(lifeNote({ life_delta: -1, lives_remaining: 3 }, "normal"))
      .toEqual({ text: "−1 жизнь · осталось 3 жизни", isWarning: false });
  });

  it("raises a warning on the last life", () => {
    expect(lifeNote({ life_delta: -1, lives_remaining: 1 }, "normal"))
      .toEqual({ text: "−1 жизнь · осталось 1 жизнь", isWarning: true });
  });

  it("says so when that was the last one", () => {
    expect(lifeNote({ life_delta: -1, lives_remaining: 0 }, "normal"))
      .toEqual({ text: "−1 жизнь · жизни закончились", isWarning: true });
  });

  it("stays quiet when no life was spent", () => {
    expect(lifeNote({ life_delta: 0, lives_remaining: 5 }, "normal")).toBeNull();
  });

  it("stays quiet in the mistakes replay, where lives are not charged", () => {
    expect(lifeNote({ life_delta: -1, lives_remaining: 4 }, "mistakes")).toBeNull();
  });
});
