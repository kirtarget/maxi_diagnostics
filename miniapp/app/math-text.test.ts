import { describe, expect, it } from "vitest";

import {
  answerInputConfig,
  isImportantPromptSentence,
  mathDisplayParts,
  splitPromptSentences,
  tokenizeMathText,
} from "./math-text";

describe("tokenizeMathText", () => {
  it("highlights expressions, values, and variables", () => {
    expect(tokenizeMathText("Для букв К, Л и M заданы коды 111, 0 и 3A₁₆."))
      .toEqual(expect.arrayContaining([
        { text: "К", isMath: true, isVariable: true },
        { text: "M", isMath: true, isVariable: true },
        { text: "111", isMath: true },
        { text: "0", isMath: true },
        { text: "3A₁₆", isMath: true },
      ]));
  });

  it("keeps an imported exponential equation in one formula token", () => {
    expect(tokenizeMathText("6^(3−x)=0,6∙10^(3−x)")).toEqual([
      { text: "6^(3−x)=0,6∙10^(3−x)", isMath: true },
    ]);
  });

  it("turns imported power notation into display superscripts", () => {
    expect(mathDisplayParts("6^(3−x)=10^(3−x)")).toEqual([
      { text: "6", isSuperscript: false },
      { text: "3−x", isSuperscript: true },
      { text: "=10", isSuperscript: false },
      { text: "3−x", isSuperscript: true },
    ]);
  });

  it("keeps ordinary text intact", () => {
    expect(tokenizeMathText("Выберите признаки государства.")).toEqual([
      { text: "Выберите признаки государства.", isMath: false },
    ]);
  });

  it("does not format chronicle years and sentence initials as formulas", () => {
    const excerpt = "В год 6745 пришёл царь Батый. И прислал послов на Рязань.";

    expect(tokenizeMathText(excerpt)).toEqual([
      { text: excerpt, isMath: false },
    ]);
  });
});

describe("prompt emphasis", () => {
  it("splits long prompts into readable sentences", () => {
    expect(splitPromptSentences("Даны три числа. Найдите их сумму.")).toEqual([
      "Даны три числа.",
      "Найдите их сумму.",
    ]);
  });

  it("marks only the action sentence as important", () => {
    expect(isImportantPromptSentence("Даны три числа.")).toBe(false);
    expect(isImportantPromptSentence("Если ответов несколько, укажите наибольший.")).toBe(true);
  });
});

describe("answerInputConfig", () => {
  it("opens a numeric keyboard for digit sequences", () => {
    expect(answerInputConfig("Ответ запишите без пробелов.")).toEqual({
      inputMode: "decimal",
      hint: "Введите ответ слитно, без пробелов и лишних знаков.",
    });
  });

  it("explains the input format for a binary code", () => {
    expect(answerInputConfig("Укажите двоичное кодовое слово.")).toEqual({
      inputMode: "numeric",
      hint: "Введите только цифры 0 и 1, без пробелов.",
    });
  });

  it("keeps a text keyboard for word answers", () => {
    expect(answerInputConfig("Запишите термин.").inputMode).toBe("text");
  });

  it("opens a decimal keyboard for an equation answer", () => {
    expect(answerInputConfig("Решите уравнение.").inputMode).toBe("decimal");
  });
});
