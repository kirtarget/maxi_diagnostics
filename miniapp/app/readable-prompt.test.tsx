import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { FormattedMathText } from "./math-display";
import { mathDisplayParts, tokenizeMathText } from "./math-text";
import { promptLayout } from "./prompt-layout";
import { parseQuestionPrompt, questionTitleClassName } from "./question-prompt";
import { QuestionView } from "./question-screen";
import type { Brand, Question } from "./types";

function catalog(file: string): Question[] {
  const path = resolve(fileURLToPath(new URL(`../../school/diagnostics/${file}.json`, import.meta.url)));
  return (JSON.parse(readFileSync(path, "utf8")) as { questions: Question[] }).questions;
}

function question(file: string, id: string): Question {
  const found = catalog(file).find((item) => item.id === id);
  expect(found, `${id} missing from ${file}`).toBeDefined();
  return found!;
}

function layoutOf(item: Question) {
  return promptLayout(parseQuestionPrompt(item.prompt));
}

function instructions(item: Question): string[] {
  return parseQuestionPrompt(item.prompt).flatMap((block) => block.kind === "instruction" ? [block.text] : []);
}

describe("stem selection keeps the task in the heading", () => {
  it("titles chemistry EGE q20 by the concentrations task, not by the answer method", () => {
    const layout = layoutOf(question("ege-chemistry-1208", "sp-chemistry-ege-2022-q23"));
    expect(layout.stem).toContain("концентрацию");
    expect(layout.stem).not.toContain("Выберите из списка");
  });

  it("keeps the matching mechanics out of the heading", () => {
    const item = question("ege-chemistry-1208", "sp-chemistry-ege-2022-q20");
    expect(layoutOf(item).stem).not.toContain("к каждой позиции");
    expect(instructions(item).join(" ")).toContain("к каждой позиции");
  });

  it("does not promote the long English instruction wall to the heading", () => {
    for (const id of ["sp-english-language-ege-2022-q10", "sp-english-language-ege-2022-q11"]) {
      const layout = layoutOf(question("ege-english-language-1204", id));
      expect(layout.stem).not.toContain("Прочитайте приведённый ниже текст");
      expect(layout.stem!.length).toBeLessThan(180);
      expect(questionTitleClassName(layout.stem!)).not.toBe("question-title");
    }
  });

  it("titles biology EGE q20 by the table it asks about", () => {
    const layout = layoutOf(question("ege-biology-1207", "sp-biology-ege-2022-q20"));
    expect(layout.stem).toContain("Проанализируйте таблицу");
    expect(layout.stem).not.toContain("Запишите в таблицу");
  });
});

describe("N-35 the heading is not printed twice", () => {
  it("drops the stem repeat when the collapsed body is a short option list", () => {
    const item = question("ege-chemistry-1208", "sp-chemistry-ege-2022-q5");
    const layout = layoutOf(item);
    expect(layout.isLongReference).toBe(true);
    expect(layout.stemRepeat).toBeNull();
    const html = renderToStaticMarkup(<QuestionView
      question={item}
      subject="Химия"
      index={0}
      total={1}
      answer={undefined}
      labels={{} as Brand["interface"]}
      onAnswer={() => undefined}
      onBack={() => undefined}
      onNext={() => undefined}
    />);
    expect(html).toContain("Развернуть текст");
    expect(html).not.toContain("question-stem-repeat");
  });

  it("keeps the repeat for a genuine wall of reading text", () => {
    const layout = layoutOf(question("ege-russian-language-1213", "sp-russian-language-ege-2022-q22"));
    expect(layout.stemRepeat).toBe(layout.stem);
  });
});

describe("one instruction plaque above the field", () => {
  it("merges the biology EGE q20 instructions into a single block", () => {
    const merged = instructions(question("ege-biology-1207", "sp-biology-ege-2022-q20"));
    expect(merged).toHaveLength(1);
    expect(merged[0]).toContain("Запишите в таблицу");
    expect(merged[0]).toContain("последовательность цифр");
  });

  it("never stacks instruction blocks in any diagnostic", () => {
    const files = [
      "ege-biology-1207", "ege-chemistry-1208", "ege-physics-1206",
      "oge-chemistry-192", "oge-physics-197", "oge-mathematics-198",
    ];
    for (const file of files) {
      for (const item of catalog(file)) {
        expect(instructions(item).length, `${file}/${item.id}`).toBeLessThanOrEqual(1);
      }
    }
  });
});

describe("formulas are formatted as one whole token", () => {
  it("keeps H2O and a unit fraction in a single expression", () => {
    const water = tokenizeMathText("Массовая доля H_(2)O равна", "Химия").filter((part) => part.isMath);
    expect(water).toHaveLength(1);
    expect(water[0]?.text).toBe("H_(2)O");

    const molar = tokenizeMathText("равна 0,16 моль/л в растворе", "Химия").filter((part) => part.isMath);
    expect(molar).toHaveLength(1);
    expect(molar[0]?.text).toBe("0,16 моль/л");
  });

  it("renders a state annotation at body type, not as an index", () => {
    expect(mathDisplayParts("KOH(р-р)")).toEqual([
      { text: "KOH", isSuperscript: false, isSubscript: false },
      { text: "(р-р)", isSuperscript: false, isSubscript: false, isAnnotation: true },
    ]);
    const html = renderToStaticMarkup(<FormattedMathText text="KOH(р-р)" subject="Химия" />);
    expect(html).toContain('<span class="math-annotation">(р-р)</span>');
    expect(html).not.toContain("<sub>(р-р)</sub>");
  });

  it("does not split a formula that carries an index in the middle", () => {
    const parts = tokenizeMathText("Б) HCl (р-р) и Na_(2)S", "Химия").filter((part) => part.isMath);
    expect(parts.map((part) => part.text)).toContain("Na_(2)S");
  });
});
