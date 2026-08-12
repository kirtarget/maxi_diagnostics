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
