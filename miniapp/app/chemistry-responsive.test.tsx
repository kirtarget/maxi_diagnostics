import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { FormattedMathText } from "./math-display";
import { MatchingAnswer, matchingModelFromQuestion } from "./matching-answer";
import { parseQuestionPrompt } from "./question-prompt";
import { PromptTable } from "./prompt-table";
import type { MatchingQuestion } from "./types";

const chemistry = JSON.parse(readFileSync(new URL("../../school/diagnostics/ege-chemistry-1208.json", import.meta.url), "utf8")) as {
  questions: Array<Record<string, unknown>>;
};
const ogeChemistry = JSON.parse(readFileSync(new URL("../../school/diagnostics/oge-chemistry-192.json", import.meta.url), "utf8")) as {
  questions: Array<Record<string, unknown>>;
};
const question = (id: string) => chemistry.questions.find((candidate) => candidate.id === id)!;

describe("real chemistry responsive rendering", () => {
  it("keeps the reagent/product condition readable as stacked pairs on a narrow screen and formats subscripts", () => {
    const blocks = parseQuestionPrompt(question("sp-chemistry-ege-2022-q8").prompt as string);
    const table = blocks.find((block) => block.kind === "table");
    expect(table?.kind).toBe("table");
    if (!table || table.kind !== "table") return;

    const html = renderToStaticMarkup(<PromptTable {...table} subject="Химия" />);
    expect(html).toContain('class="question-table-scroll" data-columns="2"');
    expect(html).toContain("РЕАГИРУЮЩИЕ ВЕЩЕСТВА");
    expect(html).toContain("ПРОДУКТЫ ВЗАИМОДЕЙСТВИЯ");
    expect(html).toContain("<sub>2</sub>");
    expect(html).toContain("(p-p)");
    expect(html).toContain("<sub>2</sub>(изб.)");
    expect(html).toContain("question-table-card-value");
  });

  it("keeps five long real chemistry options readable in the matching list", () => {
    const matchingQuestion = ogeChemistry.questions.find((candidate) => candidate.id === "sp-chemistry-oge-2022-q9")!;
    const model = matchingModelFromQuestion(matchingQuestion as unknown as MatchingQuestion);
    const html = renderToStaticMarkup(<MatchingAnswer model={model} subject="Химия" value={{}} onChange={() => undefined} />);
    expect(model.options).toHaveLength(5);
    expect(html).toContain("Fe");
    expect(html).toContain("<sub>3</sub>");
    expect(html).toContain('class="matching-answer-option-list"');
  });

  it("uses bounded wrapping rules for formula-heavy content and long choices", () => {
    const css = readFileSync(new URL("./globals.css", import.meta.url), "utf8");
    expect(css).toMatch(/\.question-table-card-cell\s*\{[\s\S]*min-width:\s*0;[\s\S]*overflow-wrap:\s*anywhere;/u);
    expect(css).toMatch(/\.question-table-scroll\[data-columns="2"\] \.question-table-card\s*\{[\s\S]*grid-template-columns:\s*minmax\(0,\s*1fr\)/u);
    expect(css).toMatch(/\.matching-answer-option-reference\s*\{[\s\S]*min-width:\s*0;[\s\S]*overflow-wrap:\s*anywhere;/u);
    expect(css).toMatch(/\.matching-answer-option\s*>\s*span\s*\{[\s\S]*overflow-wrap:\s*anywhere;/u);
    expect(css).toMatch(/@media\s*\(max-width:\s*479px\)[\s\S]*\.matching-answer-option-list[\s\S]*grid-template-columns:\s*minmax\(0,\s*1fr\)/u);
    expect(css).toMatch(/@media\s*\(max-width:\s*479px\)[\s\S]*\.matching-answer-options\s*\{[\s\S]*grid-template-columns:\s*minmax\(0,\s*1fr\)/u);
  });

  it("renders chemistry formula subscripts without relying on subject-specific markup", () => {
    const html = renderToStaticMarkup(<FormattedMathText text="С_(2)H_(4(г)) + H_(2)" subject="Химия" />);
    expect(html).toContain("<sub>2</sub>");
    expect(html).not.toContain("chemistry");
  });
});
