import { readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  answerInputConfig,
  isImportantPromptSentence,
  mathDisplayParts,
  plainMathText,
  splitPromptSentences,
  tokenizeMathText,
} from "./math-text";

describe("tokenizeMathText", () => {
  it("highlights expressions, values, and variables", () => {
    expect(tokenizeMathText("Для букв К, Л и M заданы коды 111, 0 и 3A₁₆."))
      .toEqual(expect.arrayContaining([
        { text: "M", isMath: true, isVariable: true },
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
      { text: "6", isSuperscript: false, isSubscript: false },
      { text: "3−x", isSuperscript: true, isSubscript: false },
      { text: "=10", isSuperscript: false, isSubscript: false },
      { text: "3−x", isSuperscript: true, isSubscript: false },
    ]);
  });

  it("renders nested chemical subscripts and ions", () => {
    expect(mathDisplayParts("Fe_(2)(SO_(4))_(3) + Fe^(3+)")).toEqual([
      { text: "Fe", isSuperscript: false, isSubscript: false },
      { text: "2", isSuperscript: false, isSubscript: true },
      { text: "(SO", isSuperscript: false, isSubscript: false },
      { text: "4", isSuperscript: false, isSubscript: true },
      { text: ")", isSuperscript: false, isSubscript: false },
      { text: "3", isSuperscript: false, isSubscript: true },
      { text: " + Fe", isSuperscript: false, isSubscript: false },
      { text: "3+", isSuperscript: true, isSubscript: false },
    ]);
    expect(mathDisplayParts("SO_(2)(г)")).toEqual([
      { text: "SO", isSuperscript: false, isSubscript: false },
      { text: "2", isSuperscript: false, isSubscript: true },
      { text: "(г)", isSuperscript: false, isSubscript: false },
    ]);
    expect(mathDisplayParts("SO_(2(г))")).toEqual([
      { text: "SO", isSuperscript: false, isSubscript: false },
      { text: "2", isSuperscript: false, isSubscript: true },
      { text: "(г)", isSuperscript: false, isSubscript: false },
    ]);
    expect(tokenizeMathText("(NH_(4))_(2)CO_(3)")).toEqual([
      { text: "(NH_(4))_(2)", isMath: true },
      { text: "CO_(3)", isMath: true },
    ]);
    expect(tokenizeMathText("(CH_(3)COO)_(2)Pb")).toEqual([
      { text: "(CH_(3)COO)_(2)", isMath: true },
      { text: "Pb", isMath: false },
    ]);
  });

  it("provides Unicode fallback for native select options", () => {
    expect(plainMathText("Fe_(2)(SO_(4))_(3)")).toBe("Fe₂(SO₄)₃");
  });

  it("does not badge standalone numbers, prepositions, or an atom without a numeric suffix", () => {
    expect(tokenizeMathText("В 2022 году Fe- и К встретились."))
      .toEqual([{ text: "В 2022 году Fe- и К встретились.", isMath: false }]);
    expect(tokenizeMathText("Fe-2 и 10 кг")).toEqual([
      { text: "Fe-2", isMath: true },
      { text: " и ", isMath: false },
      { text: "10 кг", isMath: true },
    ]);
  });

  it("supports radical, inequality, ratio, and unit expressions", () => {
    expect(tokenizeMathText("√4 ≠ 3:2, 10 кг")).toEqual([
      { text: "√4 ≠ 3:2", isMath: true },
      { text: ", ", isMath: false },
      { text: "10 кг", isMath: true },
    ]);
    expect(tokenizeMathText("Площадь равна 156 м^(2)")).toEqual([
      { text: "Площадь равна ", isMath: false },
      { text: "156 м^(2)", isMath: true },
    ]);
    expect(tokenizeMathText("A:B и A≠B")).toEqual([
      { text: "A:B", isMath: true },
      { text: " и ", isMath: false },
      { text: "A≠B", isMath: true },
    ]);
    expect(tokenizeMathText("А:Б и А≠Б")).toEqual([{ text: "А:Б и А≠Б", isMath: false }]);
  });

  it("disables math badges for language, history, and social studies", () => {
    const text = "В 2022 году К и M: 3A₁₆.";
    for (const subject of ["Русский язык", "История", "Обществознание", "ege-russian-language-1213", "social-studies"]) {
      expect(tokenizeMathText(text, subject)).toEqual([{ text, isMath: false }]);
    }
    expect(plainMathText("Fe_(2)", "ege-russian-language-1213")).toBe("Fe_(2)");
  });

  it("covers the real chemistry q20 and q25 answer labels", () => {
    expect(tokenizeMathText("А) MgI_(2)")).toEqual([
      { text: "А) ", isMath: false },
      { text: "MgI_(2)", isMath: true },
    ]);
    expect(tokenizeMathText("Ректификационная колонна")).toEqual([
      { text: "Ректификационная колонна", isMath: false },
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

  it("keeps raw formula markers out of plain parts across the math-aware catalog", () => {
    const diagnosticsDir = resolve(dirname(fileURLToPath(import.meta.url)), "../../school/diagnostics");
    const violations: string[] = [];
    for (const file of readdirSync(diagnosticsDir).filter((name) => name.endsWith(".json"))) {
      const diagnostic = JSON.parse(readFileSync(resolve(diagnosticsDir, file), "utf8")) as {
        subject?: string;
        questions?: Array<{
          id?: string;
          title?: string;
          prompt?: string;
          options?: Array<{ label?: string }>;
          items?: Array<{ label?: string }>;
        }>;
      };
      const subject = diagnostic.subject ?? file;
      for (const question of diagnostic.questions ?? []) {
        const values = [
          question.title,
          question.prompt,
          ...(question.options ?? []).map((option) => option.label),
          ...(question.items ?? []).map((item) => item.label),
        ].filter((value): value is string => Boolean(value));
        for (const value of values) {
          for (const part of tokenizeMathText(value, subject)) {
            if (!part.isMath && /[_^]\(/u.test(part.text)) {
              violations.push(`${file}:${question.id ?? "?"}:${part.text}`);
            }
          }
        }
      }
    }
    expect(violations).toEqual([]);
  });
});

describe("prompt emphasis", () => {
  it("splits long prompts into readable sentences", () => {
    expect(splitPromptSentences("Даны три числа. Найдите их сумму.")).toEqual([
      "Даны три числа.",
      "Найдите их сумму.",
    ]);
  });

  it("splits after punctuation only before a capital letter", () => {
    expect(splitPromptSentences("Это вопрос? да, ещё часть. Ответ готов.")).toEqual([
      "Это вопрос? да, ещё часть.",
      "Ответ готов.",
    ]);
    expect(splitPromptSentences("И. А. Бунин написал 2.5 страницы. Ответ готов.")).toEqual([
      "И. А. Бунин написал 2.5 страницы.",
      "Ответ готов.",
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
      hint: "Введи ответ слитно, без пробелов и лишних знаков.",
    });
  });

  it("explains the input format for a binary code", () => {
    expect(answerInputConfig("Укажите двоичное кодовое слово.")).toEqual({
      inputMode: "numeric",
      hint: "Введи только цифры 0 и 1, без пробелов.",
    });
  });

  it("keeps a text keyboard for word answers", () => {
    expect(answerInputConfig("Запишите термин.").inputMode).toBe("text");
  });

  it("opens a decimal keyboard for an equation answer", () => {
    expect(answerInputConfig("Решите уравнение.").inputMode).toBe("decimal");
  });
});
