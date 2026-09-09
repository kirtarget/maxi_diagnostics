import { readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  answerTypeLabel,
  cleanAnswerLabel,
  parseQuestionPrompt,
  questionTitleClassName,
} from "./question-prompt";
import type { Question } from "./types";
import { isCompleteSequenceMatchingAnswer, parseSequenceMatchingPrompt } from "./sequence-matching";
import { parseTableGapPrompt } from "./table-gap-matching";

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

  it("does not promote mixed-case, numbered, or formula lines to headings", () => {
    expect(parseQuestionPrompt("Задание.\nПРИЗНАК 2")[1]).toEqual({ kind: "paragraph", text: "ПРИЗНАК 2" });
    expect(parseQuestionPrompt("Задание.\nПРИЗНАК: X")[1]).toEqual({ kind: "paragraph", text: "ПРИЗНАК: X" });
    expect(parseQuestionPrompt(`Задание.\n${"А".repeat(60)}`)[1]).toEqual({ kind: "paragraph", text: "А".repeat(60) });
  });

  it("drops duplicated numeric markers introduced by source exports", () => {
    expect(parseQuestionPrompt("Установите соответствие.\n1) 1\n2) 2")).toEqual([
      { kind: "stem", text: "Установите соответствие." },
    ]);
  });

  it("keeps question actions in the stem and moves only answer directions", () => {
    expect(parseQuestionPrompt([
      "Выберите два вещества.",
      "Укажите варианты ответов, в которых есть формулы.",
      "Ответ запишите в виде последовательности цифр.",
    ].join("\n"))).toEqual([
      { kind: "stem", text: "Выберите два вещества." },
      { kind: "paragraph", text: "Укажите варианты ответов, в которых есть формулы." },
      { kind: "instruction", text: "Ответ запишите в виде последовательности цифр." },
    ]);
  });

  it("recognizes narrow answer-instruction prefixes without stealing task questions", () => {
    for (const instruction of [
      "Ответом запишите число.",
      "Запиши ответ.",
      "Введи слово.",
      "В таблицу внесите ответ.",
    ]) {
      expect(parseQuestionPrompt(`Определите значение.\n${instruction}`).at(-1)).toEqual({ kind: "instruction", text: instruction });
    }
    expect(parseQuestionPrompt("Выберите два вещества.")).toEqual([{ kind: "stem", text: "Выберите два вещества." }]);
    expect(parseQuestionPrompt("Решите уравнение.")).toEqual([{ kind: "stem", text: "Решите уравнение." }]);
    expect(parseQuestionPrompt("Укажите варианты ответов.")).toEqual([{ kind: "stem", text: "Укажите варианты ответов." }]);
  });

  it("splits the trailing instruction from real English q10 prose", () => {
    const diagnosticsDir = resolve(dirname(fileURLToPath(import.meta.url)), "../../school/diagnostics");
    const diagnostic = JSON.parse(readFileSync(resolve(diagnosticsDir, "ege-english-language-1204.json"), "utf8")) as {
      questions?: Array<{ id?: string; prompt?: string }>;
    };
    const question = diagnostic.questions?.find((item) => item.id === "sp-english-language-ege-2022-q10");
    expect(question?.prompt).toBeTruthy();
    const blocks = parseQuestionPrompt(question?.prompt ?? "");
    expect(blocks[0]).toEqual({
      kind: "stem",
      text: "Преобразуйте, если необходимо, слово, напечатанное заглавными буквами в конце строки так, чтобы оно грамматически соответствовало содержанию текста.",
    });
    expect(blocks).toContainEqual({ kind: "instruction", text: "В ответ запишите полученное слово (без пробелов)." });
    expect(blocks.some((block) => block.kind === "stem" && block.text.includes("В ответ"))).toBe(false);
  });

  it("uses a final question as the single stem after a source passage", () => {
    const blocks = parseQuestionPrompt([
      "Прочитайте текст и выполните задания.",
      "Текст источника.",
      "Какие высказывания соответствуют содержанию текста?",
    ].join("\n"));
    expect(blocks[0]).toEqual({ kind: "stem", text: "Какие высказывания соответствуют содержанию текста?" });
    expect(blocks.filter((block) => block.kind === "stem")).toHaveLength(1);
  });

  it("ignores dialogue questions when selecting a literature stem", () => {
    const blocks = parseQuestionPrompt([
      "— Какая же тебе нравится? — спросил Штольц.",
      "— Что ж здесь именно так не понравилось?",
      "(И. А. Гончаров «Обломов») Укажите литературное направление, принципы которого воплощены в данном произведении.",
    ].join("\n"));
    expect(blocks[0]).toEqual({
      kind: "stem",
      text: "Укажите литературное направление, принципы которого воплощены в данном произведении.",
    });
  });

  it("keeps a poem passage before the Russian punctuation action", () => {
    const blocks = parseQuestionPrompt([
      "Расставьте знаки препинания: укажите цифру(-ы), на месте которой(-ых) должна(-ы) стоять запятая(-ые).",
      "Не шуми ты (1) рожь (2)",
      "Спелым колосом!",
      "Введите последовательность цифр без пробелов.",
    ].join("\n"));
    expect(blocks[0]?.kind).toBe("stem");
    expect(blocks[0]?.kind === "stem" && blocks[0].text).toContain("Расставьте знаки препинания");
  });

  it("retains all rows of the real biology q21 table", () => {
    const blocks = parseQuestionPrompt([
      "Проанализируйте таблицу «Число устьиц на 1 мм² листа».",
      "Число устьиц на 1 мм² листа",
      "___ | Верхняя поверхность | Нижняя поверхность",
      "Название растения | Число устьиц | Число устьиц",
      "Кувшинка белая | 406 | 0",
      "Пшеница | 47 | 32",
      "Овес | 40 | 27",
      "Выберите предложения, которые можно сформулировать на основании анализа представленных данных.",
    ].join("\n"));
    const table = blocks.find((block) => block.kind === "table");
    expect(table && table.kind === "table" ? table.headerRows : null).toEqual([
      ["___", "Верхняя поверхность", "Нижняя поверхность"],
      ["Название растения", "Число устьиц", "Число устьиц"],
    ]);
    expect(table && table.kind === "table" ? table.rows : []).toEqual([
      ["Кувшинка белая", "406", "0"],
      ["Пшеница", "47", "32"],
      ["Овес", "40", "27"],
    ]);
  });

  it("retains both real chemistry q23 tables and their instructions", () => {
    const blocks = parseQuestionPrompt([
      "В реактор постоянного объема поместили некоторое количество этилена и водорода.",
      "Реагент | С_(2)Н_(4) | Н_(2) | С_(2)Н_(6)",
      "Исходная концентрация, моль/л | X | 0,4 | 0",
      "Равновесная концентрация, моль/л | 0,15 | Y | 0,1",
      "Выберите из списка правильные варианты.",
      "1. 0,30 моль/л",
      "Х | Y",
      "(А)_______ | (Б)_______",
      "В ответ запишите последовательность цифр, соответствующую буквам АБ.",
      "Введите последовательность цифр без пробелов.",
    ].join("\n"));
    const tables = blocks.filter((block): block is Extract<typeof blocks[number], { kind: "table" }> => block.kind === "table");
    expect(tables).toHaveLength(2);
    expect(tables[0].headerRows).toEqual([["Реагент", "С_(2)Н_(4)", "Н_(2)", "С_(2)Н_(6)"]]);
    expect(tables[0].rows).toHaveLength(2);
    expect(tables[1].headerRows).toEqual([["Х", "Y"]]);
    expect(tables[1].rows).toEqual([["(А)_______", "(Б)_______"]]);
    expect(blocks.some((block) => block.kind === "instruction"
      && "text" in block
      && block.text.startsWith("В ответ"))).toBe(true);
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
    expect(table && table.kind === "table" && table.headerRows).toEqual([["Метод", "Применение метода"]]);
    expect(table && table.kind === "table" && table.rows).toEqual([
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

  it("does not create invalid headings in the school catalog", () => {
    const diagnosticsDir = resolve(dirname(fileURLToPath(import.meta.url)), "../../school/diagnostics");
    const violations: string[] = [];
    for (const file of readdirSync(diagnosticsDir).filter((name) => name.endsWith(".json"))) {
      const diagnostic = JSON.parse(readFileSync(resolve(diagnosticsDir, file), "utf8")) as {
        questions?: Array<{ id?: string; prompt?: string }>;
      };
      for (const question of diagnostic.questions ?? []) {
        for (const block of parseQuestionPrompt(question.prompt ?? "")) {
          if (block.kind === "heading" && /[\p{Ll}\p{Nd}+\-−×÷*/=≤≥<>⇄→√^·∙:≠_]/u.test(block.text)) {
            violations.push(`${file}:${question.id ?? "?"}:${block.text}`);
          }
        }
      }
    }
    expect(violations).toEqual([]);
  });
});

describe("catalog table contracts", () => {
  const diagnosticsDir = resolve(dirname(fileURLToPath(import.meta.url)), "../../school/diagnostics");
  function catalogQuestion(id: string): { prompt: string; type: string; answer_format?: string; allow_reuse?: boolean; markers?: string[] } {
    for (const file of readdirSync(diagnosticsDir).filter((name) => name.endsWith(".json"))) {
      const diagnostic = JSON.parse(readFileSync(resolve(diagnosticsDir, file), "utf8")) as {
        questions?: Array<{ id?: string; prompt?: string; type?: string; answer_format?: string; allow_reuse?: boolean; markers?: string[] }>;
      };
      const question = diagnostic.questions?.find((candidate) => candidate.id === id);
      if (question?.prompt) return {
        prompt: question.prompt,
        type: question.type ?? "",
        answer_format: question.answer_format,
        allow_reuse: question.allow_reuse,
        markers: question.markers,
      };
    }
    throw new Error(`Missing catalog question ${id}`);
  }

  it("normalizes ordinary catalog tables and the English matching source", () => {
    for (const id of [
      "sp-biology-ege-2022-q1",
      "sp-biology-ege-2022-q21",
    ]) {
      const blocks = parseQuestionPrompt(catalogQuestion(id).prompt);
      expect(blocks.some((block) => block.kind === "table"), id).toBe(true);
      expect(blocks.flatMap((block) => block.kind === "table" ? [...block.headerRows.flat(), ...block.rows.flat()] : [])
        .some((cell) => cell.includes("|")), id).toBe(false);
    }
    // A two-column table that maps or names answer cells is the widget rather
    // than part of the wording, so it no longer prints in the prompt.
    const mapping = catalogQuestion("sp-chemistry-ege-2022-q8");
    expect(parseQuestionPrompt(mapping.prompt).some((block) => block.kind === "table")).toBe(false);
    expect(mapping.type).toBe("matching");

    const drawnCells = catalogQuestion("sp-chemistry-oge-2022-q7");
    expect(parseQuestionPrompt(drawnCells.prompt).some((block) => block.kind === "table")).toBe(false);
    expect(drawnCells.markers).toEqual(["Кислотный оксид", "Соль"]);

    const englishQuestion = catalogQuestion("sp-english-language-ege-2022-q1");
    const english = parseSequenceMatchingPrompt(englishQuestion.prompt);
    expect(english?.left.map((item) => item.marker)).toEqual(["A", "B", "C", "D", "E", "F", "G"]);
    expect(english?.options).toHaveLength(8);
    expect(english?.allowReuse).toBe(false);
    const ogeEnglish = parseSequenceMatchingPrompt(catalogQuestion("sp-english-language-oge-2022-q1").prompt);
    expect(ogeEnglish?.left.map((item) => item.marker)).toEqual(["A", "B", "C", "D", "E", "F"]);
    expect(ogeEnglish?.options).toHaveLength(7);
    expect(ogeEnglish?.allowReuse).toBe(false);
    expect(ogeEnglish && isCompleteSequenceMatchingAnswer(ogeEnglish, "624371")).toBe(true);
    const ogeStatements = parseSequenceMatchingPrompt(catalogQuestion("sp-english-language-oge-2022-q2").prompt);
    expect(ogeStatements?.left).toHaveLength(7);
    expect(ogeStatements?.options.map((option) => option.marker)).toEqual(["1", "2", "3"]);
    expect(ogeStatements?.allowReuse).toBe(true);
    expect(ogeStatements && isCompleteSequenceMatchingAnswer(ogeStatements, "1231231")).toBe(true);
  });

  it("does not synthesize a table for the OGE chemistry q2 answer scaffold", () => {
    const question = catalogQuestion("sp-chemistry-oge-2022-q2");
    const blocks = parseQuestionPrompt(question.prompt);
    expect(blocks.some((block) => block.kind === "table")).toBe(false);
    expect(blocks.some((block) => "text" in block && /\s\|\s/u.test(block.text))).toBe(false);
  });

  it("keeps biology and history gaps structured and respects explicit numeric physics metadata", () => {
    const biologyQuestion = catalogQuestion("sp-biology-ege-2022-q20");
    const biology = parseTableGapPrompt(biologyQuestion.prompt, biologyQuestion as never);
    expect(biology?.headers).toHaveLength(3);
    expect(biology?.markers).toEqual(["А", "Б", "В"]);
    const history = parseTableGapPrompt(catalogQuestion("sp-history-ege-2022-q4").prompt);
    expect(history?.headers).toHaveLength(3);
    expect(history?.rows).toHaveLength(4);
    expect(history?.markers).toEqual(["А", "Б", "В", "Г", "Д", "Е"]);
    expect(history?.options.map((option) => option.marker)).toEqual(["1", "2", "3", "4", "5", "6", "7", "8", "9"]);
    const physics = catalogQuestion("sp-physics-ege-2022-q13");
    expect(parseTableGapPrompt(physics.prompt, physics as never)).toBeNull();
  });

  it("leaves English reading prose without a synthetic table", () => {
    const blocks = parseQuestionPrompt(catalogQuestion("sp-english-language-ege-2022-q23").prompt);
    expect(blocks.some((block) => block.kind === "table")).toBe(false);
  });

  it("keeps all dotted literature list markers, including 10 and 11", () => {
    const blocks = parseQuestionPrompt(catalogQuestion("sp-literature-ege-2025-pamatnik-q4").prompt);
    expect(blocks.filter((block) => block.kind === "item").map((block) => block.marker)).toEqual(
      Array.from({ length: 11 }, (_, index) => String(index + 1)),
    );
  });

  it("consumes structural delimiters across the full catalog", () => {
    const violations: string[] = [];
    for (const file of readdirSync(diagnosticsDir).filter((name) => name.endsWith(".json"))) {
      const diagnostic = JSON.parse(readFileSync(resolve(diagnosticsDir, file), "utf8")) as {
        questions?: Array<{ id?: string; prompt?: string }>;
      };
      for (const question of diagnostic.questions ?? []) {
        for (const block of parseQuestionPrompt(question.prompt ?? "")) {
          if (block.kind === "table") continue;
          if (/\s\|\s/u.test(block.text)) violations.push(`${file}:${question.id ?? "?"}`);
        }
      }
    }
    expect(violations).toEqual([]);
  });
});
