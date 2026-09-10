import { describe, expect, it } from "vitest";

import {
  isCompleteSequenceMatchingAnswer,
  parseSequenceMatchingPrompt,
} from "./sequence-matching";

const prompt = [
  "Установите соответствие между событиями и участниками.",
  "СОБЫТИЯ",
  "УЧАСТНИКИ",
  "А) подавление восстания",
  "1) Иван Калита",
  "Б) военная победа",
  "2) Василий III",
  "В) конференция",
  "3) Борис Годунов",
  "Запишите выбранные цифры под соответствующими буквами.",
].join("\n");

describe("parseSequenceMatchingPrompt", () => {
  it("separates lettered statements from numbered choices", () => {
    expect(parseSequenceMatchingPrompt(prompt)).toMatchObject({
      left: [
        { marker: "А", label: "подавление восстания" },
        { marker: "Б", label: "военная победа" },
        { marker: "В", label: "конференция" },
      ],
      options: [
        { marker: "1", label: "Иван Калита" },
        { marker: "2", label: "Василий III" },
        { marker: "3", label: "Борис Годунов" },
      ],
      allowReuse: false,
    });
  });

  it("does not treat an ordinary numeric prompt as matching", () => {
    expect(parseSequenceMatchingPrompt("Решите уравнение. Ответ: 2")).toBeNull();
  });

  it("recognizes matching with reusable choices when there are fewer choices than statements", () => {
    const reusable = [
      "Установите соответствие между органоидами и характеристиками.",
      "ХАРАКТЕРИСТИКА",
      "ОРГАНОИДЫ",
      "А) участвуют во внутриклеточном пищеварении",
      "Б) располагаются в цитоплазме",
      "В) формируются в комплексе Гольджи",
      "Г) формируются в ядре",
      "Д) осуществляют синтез белка",
      "1) рибосомы",
      "2) лизосомы",
      "Ответ запишите в виде последовательности цифр.",
    ].join("\n");

    expect(parseSequenceMatchingPrompt(reusable)).toMatchObject({
      left: [{ marker: "А" }, { marker: "Б" }, { marker: "В" }, { marker: "Г" }, { marker: "Д" }],
      options: [{ marker: "1", label: "рибосомы" }, { marker: "2", label: "лизосомы" }],
      allowReuse: true,
    });
  });
});

describe("isCompleteSequenceMatchingAnswer", () => {
  const matching = parseSequenceMatchingPrompt(prompt)!;

  it("requires one valid choice for every letter", () => {
    expect(isCompleteSequenceMatchingAnswer(matching, "12")).toBe(false);
    expect(isCompleteSequenceMatchingAnswer(matching, "123")).toBe(true);
    expect(isCompleteSequenceMatchingAnswer(matching, "113")).toBe(false);
  });

  it("accepts repeated choices when the prompt has fewer choices than statements", () => {
    const reusable = parseSequenceMatchingPrompt([
      "Установите соответствие.", "А) один", "Б) два", "В) три", "1) вариант", "2) другой вариант",
    ].join("\n"))!;

    expect(isCompleteSequenceMatchingAnswer(reusable, "212")).toBe(true);
  });
});

describe("contract-4 sequence metadata", () => {
  const chemistryPrompt = [
    "Установите соответствие между веществами и продуктами реакции.",
    "В) третье вещество",
    "Б) второе вещество",
    "А) первое вещество",
    "1) продукт один | 2) продукт два | 3) продукт три",
    "4) продукт четыре | 5) продукт пять | ___",
    "7) продукт семь | 8) продукт восемь | 9) продукт девять",
  ].join("\n");

  it("uses metadata markers as slot order and keeps explicit reusable choices", () => {
    const matching = parseSequenceMatchingPrompt(chemistryPrompt, {
      answer_format: "sequence",
      answer_length: 3,
      allow_reuse: true,
      markers: ["А", "Б", "В"],
    });

    expect(matching).toMatchObject({
      left: [
        { marker: "А", label: "первое вещество" },
        { marker: "Б", label: "второе вещество" },
        { marker: "В", label: "третье вещество" },
      ],
      options: [
        { marker: "1", label: "продукт один" },
        { marker: "2", label: "продукт два" },
        { marker: "3", label: "продукт три" },
        { marker: "4", label: "продукт четыре" },
        { marker: "5", label: "продукт пять" },
        { marker: "7", label: "продукт семь" },
        { marker: "8", label: "продукт восемь" },
        { marker: "9", label: "продукт девять" },
      ],
      answerLength: 3,
      allowReuse: true,
    });
    expect(isCompleteSequenceMatchingAnswer(matching!, "277")).toBe(true);
  });

  it("lets explicit numeric metadata disable prompt matching heuristics", () => {
    expect(parseSequenceMatchingPrompt(chemistryPrompt, { answer_format: "number" })).toBeNull();
  });

  it("names the answer cells after the paper blank instead of dropping it", () => {
    const physics = [
      "Как изменились давление в 1 сосуде и внутренняя энергия 2 газа?",
      "1) увеличилась",
      "2) уменьшилась",
      "3) не изменилась",
      "Давление в 1 сосуде | Внутренняя энергия 2 газа",
      "В ответ запишите последовательность цифр, соответствующую буквам АБ.",
    ].join("\n");
    expect(parseSequenceMatchingPrompt(physics, {
      answer_format: "sequence",
      answer_length: 2,
      allow_reuse: true,
      markers: ["А", "Б"],
    })).toMatchObject({
      left: [
        { marker: "А", label: "Давление в 1 сосуде" },
        { marker: "Б", label: "Внутренняя энергия 2 газа" },
      ],
    });
  });

  it("keeps a synthetic letter scaffold as the cell markers", () => {
    const scaffold = [
      "Установите соответствие.",
      "А) первое",
      "Б) второе",
      "1) один",
      "2) два",
      "А | Б",
    ].join("\n");
    expect(parseSequenceMatchingPrompt(scaffold)).toMatchObject({
      left: [
        { marker: "А", label: "первое" },
        { marker: "Б", label: "второе" },
      ],
    });
  });
});
