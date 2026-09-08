import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { parseQuestionPrompt } from "./question-prompt";
import { createPromptAnchorAllocator, promptLayout } from "./prompt-layout";
import { QuestionView } from "./question-screen";
import type { Brand, Question } from "./types";

describe("promptLayout", () => {
  it("collapses a long reference while keeping the question stem separate", () => {
    const blocks = parseQuestionPrompt([
      "Какие высказывания соответствуют содержанию текста?",
      ...Array.from({ length: 9 }, (_, index) => `(${index + 1}) Длинный фрагмент текста для чтения и анализа.`),
    ].join("\n"));
    const layout = promptLayout(blocks);
    expect(layout.stem).toBe("Какие высказывания соответствуют содержанию текста?");
    expect(layout.isLongReference).toBe(true);
    expect(layout.sentenceAnchors).toEqual(["1", "2", "3", "4", "5", "6", "7", "8", "9"]);
  });

  it("recognizes the real Russian EGE q22 reading reference", () => {
    const path = resolve(fileURLToPath(new URL("../../school/diagnostics/ege-russian-language-1213.json", import.meta.url)));
    const catalog = JSON.parse(readFileSync(path, "utf8")) as { questions: Array<{ id: string; prompt: string }> };
    const question = catalog.questions.find((item) => item.id === "sp-russian-language-ege-2022-q22");
    expect(question).toBeDefined();
    const layout = promptLayout(parseQuestionPrompt(question!.prompt));
    expect(layout.isLongReference).toBe(true);
    expect(layout.stem).toContain("Какие высказывания");
    expect(layout.sentenceAnchors).toContain("1");
    expect(layout.sentenceAnchors).toContain("56");
  });

  it("keeps the real q22 heading outside the collapsible reference", () => {
    const path = resolve(fileURLToPath(new URL("../../school/diagnostics/ege-russian-language-1213.json", import.meta.url)));
    const catalog = JSON.parse(readFileSync(path, "utf8")) as { questions: Question[] };
    const question = catalog.questions.find((item) => item.id === "sp-russian-language-ege-2022-q22");
    const html = renderToStaticMarkup(<QuestionView
      question={question!}
      subject="Русский язык"
      index={0}
      total={1}
      answer={undefined}
      labels={{} as Brand["interface"]}
      onAnswer={() => undefined}
      onBack={() => undefined}
      onNext={() => undefined}
    />);
    expect(html.match(/<h1\b/g)).toHaveLength(1);
    expect(html).toContain("prompt-reference-long");
    expect(html).toContain("Развернуть текст");
    expect(html).toContain("question-stem-repeat");
    expect(html).toContain("prompt-sentence-1");
    expect(html).toContain("prompt-sentence-56");
  });

  it("allocates unique anchors across repeated markers in separate blocks", () => {
    const anchors = createPromptAnchorAllocator();
    expect(anchors.sentenceSegments("(1) Первый блок")[0]?.anchorId).toBe("prompt-sentence-1");
    expect(anchors.sentenceSegments("(1) Повторный блок")[0]?.anchorId).toBe("prompt-sentence-1-2");
    expect(anchors.sentenceSegments("(2) Новый блок")[0]?.anchorId).toBe("prompt-sentence-2");
  });
});
