import { parseSequenceMatchingPrompt } from "./sequence-matching";
import { parseTableGapPrompt } from "./table-gap-matching";
import type { Question } from "./types";

export type PromptBlock =
  | { kind: "stem" | "heading" | "instruction" | "paragraph"; text: string }
  | { kind: "item"; marker: string; text: string }
  | { kind: "table"; rows: string[][] };

const ITEM_PATTERN = /^([А-ЯЁA-Z]|\d{1,2})\)\s*(.+)$/u;
const INSTRUCTION_PATTERN = /^(?:ответ|в ответе|запишите|введите|укажите ответ)(?:\s|$)/iu;
const LETTER_PATTERN = /[A-ZА-ЯЁ]/gu;

function isHeading(value: string): boolean {
  if (value.length > 96) return false;
  const letters = value.match(LETTER_PATTERN)?.join("") ?? "";
  return letters.length >= 3 && letters === letters.toLocaleUpperCase("ru-RU");
}

function tableRow(line: string): string[] | null {
  if (!line.includes("|")) return null;
  const cells = line.split("|").map((cell) => cell.trim());
  return cells.length >= 2 ? cells : null;
}

export function parseQuestionPrompt(prompt: string): PromptBlock[] {
  const lines = prompt
    .split(/\n+/u)
    .map((line) => line.trim())
    .filter(Boolean);

  const blocks: PromptBlock[] = [];
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (index === 0) {
      blocks.push({ kind: "stem", text: line });
      continue;
    }

    // The converter flattens a source table to one `cell | cell` line per row.
    // Two such lines in a row are a table, and reading one as prose is the
    // difference between a grid and a wall of vertical bars.
    const rows: string[][] = [];
    while (index < lines.length) {
      const row = tableRow(lines[index]);
      if (!row) break;
      rows.push(row);
      index += 1;
    }
    if (rows.length >= 2) {
      const width = Math.max(...rows.map((row) => row.length));
      blocks.push({
        kind: "table",
        rows: rows.map((row) => [...row, ...Array(width - row.length).fill("")]),
      });
      index -= 1;
      continue;
    }
    index -= rows.length;

    const item = ITEM_PATTERN.exec(line);
    if (item) {
      if (/^\d+$/u.test(item[1]) && item[2].trim() === item[1]) continue;
      blocks.push({ kind: "item", marker: item[1], text: item[2] });
      continue;
    }
    if (INSTRUCTION_PATTERN.test(line)) {
      blocks.push({ kind: "instruction", text: line });
      continue;
    }
    blocks.push(isHeading(line) ? { kind: "heading", text: line } : { kind: "paragraph", text: line });
  }
  return blocks;
}

export function cleanAnswerLabel(label: string): string {
  const cleaned = label.replace(/^\s*(?:[А-ЯЁA-Z]|\d{1,2})[.)]\s*/u, "").trim();
  return cleaned || label;
}

export function answerTypeLabel(question: Question): string {
  if (question.type === "single") return "один ответ";
  if (question.type === "multiple") return "несколько ответов";
  if (question.type === "matching") return "сопоставление";
  if (question.type === "text") return "короткий ответ словом";
  if (parseTableGapPrompt(question.prompt)) return "таблица с пропусками";
  if (parseSequenceMatchingPrompt(question.prompt)) return "сопоставление";
  return "короткий ответ";
}

export function questionTitleClassName(text: string): string {
  if (text.length > 360) return "question-title question-title-long";
  if (text.length > 180) return "question-title question-title-medium";
  return "question-title";
}
