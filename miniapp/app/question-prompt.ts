export type PromptBlock =
  | { kind: "stem" | "heading" | "instruction" | "paragraph"; text: string }
  | { kind: "item"; marker: string; text: string };

const ITEM_PATTERN = /^([А-ЯЁA-Z]|\d{1,2})\)\s*(.+)$/u;
const INSTRUCTION_PATTERN = /^(?:ответ|в ответе|запишите|введите|укажите ответ)(?:\s|$)/iu;
const LETTER_PATTERN = /[A-ZА-ЯЁ]/gu;

function isHeading(value: string): boolean {
  if (value.length > 96) return false;
  const letters = value.match(LETTER_PATTERN)?.join("") ?? "";
  return letters.length >= 3 && letters === letters.toLocaleUpperCase("ru-RU");
}

export function parseQuestionPrompt(prompt: string): PromptBlock[] {
  const lines = prompt
    .split(/\n+/u)
    .map((line) => line.trim())
    .filter(Boolean);

  return lines.flatMap((line, index): PromptBlock[] => {
    if (index === 0) return [{ kind: "stem", text: line }];

    const item = ITEM_PATTERN.exec(line);
    if (item) {
      if (/^\d+$/u.test(item[1]) && item[2].trim() === item[1]) return [];
      return [{ kind: "item", marker: item[1], text: item[2] }];
    }
    if (INSTRUCTION_PATTERN.test(line)) return [{ kind: "instruction", text: line }];
    if (isHeading(line)) return [{ kind: "heading", text: line }];
    return [{ kind: "paragraph", text: line }];
  });
}

export function cleanAnswerLabel(label: string): string {
  const cleaned = label.replace(/^\s*(?:[А-ЯЁA-Z]|\d{1,2})\)\s*/u, "").trim();
  return cleaned || label;
}

export function questionTitleClassName(text: string): string {
  if (text.length > 360) return "question-title question-title-long";
  if (text.length > 180) return "question-title question-title-medium";
  return "question-title";
}
