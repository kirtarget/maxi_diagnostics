// The Mini App speaks to the student in one voice: informal "ty", never the
// formal "vy". This mirrors the guard in the backend
// (tests/test_message_tone.py / diagnostic.message_validation) so the two
// surfaces cannot drift back apart.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import * as ts from "typescript";
import { describe, expect, test } from "vitest";

const FORMAL_ADDRESS_VERBS = [
  "откройте", "выберите", "пройдите", "нажмите", "продолжите",
  "посмотрите", "проверьте", "попробуйте", "введите", "запишите",
  "используйте", "начните", "продолжайте", "повторите",
];
const FORMAL_ADDRESS_PATTERN = new RegExp(
  `(?<!\\p{L})(?:вы|вас|вам|вами|ваш\\p{L}*|${FORMAL_ADDRESS_VERBS.join("|")})(?!\\p{L})`,
  "iu",
);
const UI_OWNED_SOURCE_FILES = [
  "answer-editor.tsx",
  "assessment-header.tsx",
  "confirm-sheet.tsx",
  "gameplay-profile-model.ts",
  "image-viewer.tsx",
  "layout.tsx",
  "league-screen.tsx",
  "matching-answer.tsx",
  "math-text.ts",
  "navigation-model.ts",
  "navigation-screens.tsx",
  "offer-ux.tsx",
  "page.tsx",
  "prompt-table.tsx",
  "question-metadata.tsx",
  "question-screen.tsx",
  "result-flow-model.ts",
  "result-flow.tsx",
  "score-estimate.ts",
  "trainer-model.ts",
  "trainer-screen.tsx",
  "use-bootstrap.ts",
  "use-diagnostic-session.ts",
  "use-trainer.ts",
  "text-utils.ts",
].map((name) => join(__dirname, name));
const UI_OWNED_BRAND_FILES = [
  "../../school/brand.json",
  "../../tests/fixtures/pristine_brand.json",
  "../../tests/fixtures/sample-school/brand.json",
].map((name) => join(__dirname, name));

export function extractUiText(source: string): string[] {
  const file = ts.createSourceFile("ui.tsx", source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const fragments: string[] = [];
  const visit = (node: ts.Node) => {
    if (ts.isJsxText(node)) {
      fragments.push(node.getText(file));
    } else if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
      fragments.push(node.text);
    } else if (ts.isTemplateExpression(node)) {
      fragments.push(node.head.text);
      for (const span of node.templateSpans) fragments.push(span.literal.text);
    }
    ts.forEachChild(node, visit);
  };
  visit(file);
  return fragments;
}

describe("bot/miniapp tone parity: informal address only", () => {
  test("detects formal markers with Cyrillic-safe boundaries", () => {
    for (const marker of ["Ваш ответ", "Введите ответ", "Выберите вариант", "Запишите ответ"]) {
      expect(FORMAL_ADDRESS_PATTERN.test(marker)).toBe(true);
    }
  });

  test("extracts formal JSX text, not only quoted literals", () => {
    expect(extractUiText("<dt>Ваш ответ</dt>")).toContain("Ваш ответ");
    expect(extractUiText("<p>Выберите вариант</p>")).toContain("Выберите вариант");
  });

  test("extracts formal fragments around JSX expressions", () => {
    for (const source of [
      "<p>Введите {count} ответов</p>",
      "<p>Ваш ответ: {answer}</p>",
      "<p>{count} вариантов. Выберите один.</p>",
    ]) {
      expect(extractUiText(source).some((fragment) => FORMAL_ADDRESS_PATTERN.test(fragment))).toBe(true);
    }
  });

  for (const path of UI_OWNED_BRAND_FILES) {
    test(`${path} interface labels have no formal-address markers`, () => {
      const source = JSON.parse(readFileSync(path, "utf-8")) as { interface?: Record<string, unknown> };
      const offenders = Object.values(source.interface ?? {})
        .filter((value): value is string => typeof value === "string")
        .filter((literal) => FORMAL_ADDRESS_PATTERN.test(literal));
      expect(offenders).toEqual([]);
    });
  }

  for (const path of UI_OWNED_SOURCE_FILES) {
    test(`${path} has no formal-address markers`, () => {
      const source = readFileSync(path, "utf-8");
      const offenders: string[] = [];
      for (const literal of extractUiText(source)) {
        if (FORMAL_ADDRESS_PATTERN.test(literal)) {
          offenders.push(literal);
        }
      }
      expect(offenders).toEqual([]);
    });
  }
});
