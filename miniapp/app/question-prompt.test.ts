import { describe, expect, it } from "vitest";

import {
  cleanAnswerLabel,
  parseQuestionPrompt,
  questionTitleClassName,
} from "./question-prompt";

describe("parseQuestionPrompt", () => {
  it("preserves a readable stem, headings, enumerated items, and instructions", () => {
    expect(parseQuestionPrompt([
      "Установите соответствие.",
      "ПРИЗНАК",
      "А) последовательность аминокислот",
      "1) первичная структура",
      "Ответ запишите в виде последовательности цифр.",
    ].join("\n"))).toEqual([
      { kind: "stem", text: "Установите соответствие." },
      { kind: "heading", text: "ПРИЗНАК" },
      { kind: "item", marker: "А", text: "последовательность аминокислот" },
      { kind: "item", marker: "1", text: "первичная структура" },
      { kind: "instruction", text: "Ответ запишите в виде последовательности цифр." },
    ]);
  });

  it("drops duplicated numeric markers introduced by source exports", () => {
    expect(parseQuestionPrompt("Установите соответствие.\n1) 1\n2) 2")).toEqual([
      { kind: "stem", text: "Установите соответствие." },
    ]);
  });
});

describe("cleanAnswerLabel", () => {
  it("removes duplicated source numbering from answer buttons", () => {
    expect(cleanAnswerLabel("3) расщепление углеводов")).toBe("расщепление углеводов");
  });

  it("keeps ordinary answer text unchanged", () => {
    expect(cleanAnswerLabel("хемосинтез")).toBe("хемосинтез");
  });
});

describe("questionTitleClassName", () => {
  it("uses reading typography for long one-block prompts", () => {
    expect(questionTitleClassName("а".repeat(181))).toContain("question-title-medium");
    expect(questionTitleClassName("а".repeat(361))).toContain("question-title-long");
  });

  it("keeps concise prompts prominent", () => {
    expect(questionTitleClassName("Краткое условие")).toBe("question-title");
  });
});
