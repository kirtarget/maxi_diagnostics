import { describe, expect, it } from "vitest";

import {
  answerTypeLabel,
  cleanAnswerLabel,
  parseQuestionPrompt,
  questionTitleClassName,
} from "./question-prompt";
import type { Question } from "./types";

describe("answerTypeLabel", () => {
  const base = { id: "q", topic: "t", title: "1", prompt: "Вопрос" };

  it("names every answer kind the way the mock chips do", () => {
    expect(answerTypeLabel({ ...base, type: "single", options: [] } as unknown as Question)).toBe("один ответ");
    expect(answerTypeLabel({ ...base, type: "multiple", options: [], selection_limit: 2 } as unknown as Question)).toBe("несколько ответов");
    expect(answerTypeLabel({ ...base, type: "matching", items: [], options: [] } as unknown as Question)).toBe("сопоставление");
    expect(answerTypeLabel({ ...base, type: "input" } as Question)).toBe("короткий ответ");
    expect(answerTypeLabel({ ...base, type: "text" } as Question)).toBe("короткий ответ словом");
  });

  it("never mistakes a free-text prompt for a table or sequence layout", () => {
    const table = "Соотнеси событие и год.";
    expect(answerTypeLabel({ ...base, type: "text", prompt: table } as Question)).toBe("короткий ответ словом");
  });

  it("recognizes matching and table prompts hidden inside input questions", () => {
    const sequence = [
      "Соотнеси событие и год.",
      "СОБЫТИЕ",
      "А) Куликовская битва",
      "Б) Крещение Руси",
      "1) 1380",
      "2) 988",
      "Ответ запишите в виде последовательности цифр.",
    ].join("\n");
    expect(answerTypeLabel({ ...base, type: "input", prompt: sequence } as Question)).toBe("сопоставление");

    const table = [
      "Заполните пропуски в таблице «Свойства веществ».",
      "Вещество",
      "Формула",
      "Агрегатное состояние",
      "Кислород",
      "O2",
      "(А)",
      "(Б)",
      "H2O",
      "жидкость",
      "Пропущенные элементы:",
      "1) газ;",
      "2) вода;",
    ].join("\n");
    expect(answerTypeLabel({ ...base, type: "input", prompt: table } as Question)).toBe("таблица с пропусками");
  });
});

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
    expect(cleanAnswerLabel("А. Восстание декабристов")).toBe("Восстание декабристов");
    expect(cleanAnswerLabel("1. 1185 г.")).toBe("1185 г.");
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

describe("table blocks", () => {
  it("groups the converter's `cell | cell` lines into one table", () => {
    const blocks = parseQuestionPrompt([
      "Рассмотрите таблицу и заполните пустую ячейку.",
      "Метод | Применение метода",
      "___ | Изучение кариотипа под микроскопом.",
      "Популяционно-статистический | Изучение гена в популяции.",
      "Ответ запишите словом.",
    ].join("\n"));

    const table = blocks.find((block) => block.kind === "table");
    expect(table).toBeDefined();
    expect(table && table.kind === "table" && table.rows).toEqual([
      ["Метод", "Применение метода"],
      ["___", "Изучение кариотипа под микроскопом."],
      ["Популяционно-статистический", "Изучение гена в популяции."],
    ]);
    expect(blocks.filter((block) => block.kind === "table")).toHaveLength(1);
    expect(blocks[blocks.length - 1]).toEqual({ kind: "instruction", text: "Ответ запишите словом." });
  });

  it("leaves a lone line with a bar as prose", () => {
    const blocks = parseQuestionPrompt("Задание.\nВыберите a | b как обозначение.");
    expect(blocks.some((block) => block.kind === "table")).toBe(false);
  });
});
