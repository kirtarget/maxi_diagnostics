import { parseSequenceMatchingPrompt } from "./sequence-matching";
import { parseTableGapPrompt } from "./table-gap-matching";
import { splitPromptSentences } from "./math-text";
import type { Question } from "./types";

export type PromptBlock =
  | { kind: "stem" | "heading" | "instruction" | "paragraph"; text: string }
  | { kind: "item"; marker: string; text: string }
  | { kind: "table"; rows: string[][] };

const ITEM_PATTERN = /^([А-ЯЁA-Z]|\d{1,2})\)\s*(.+)$/u;
const INSTRUCTION_PATTERN = /^(?:ответ(?:ы|ом)?(?:\s+(?:запишите|запиши|укажите|дайте))?|в\s+ответ(?:е|ом)?(?:\s+(?:запишите|запиши|укажите|дайте))?|запишите(?:\s+(?:ответ|последовательность|число|слово|цифры))?|запиши(?:\s+(?:ответ|последовательность|число|слово|цифры))?|введите(?:\s+(?:ответ|последовательность|число|слово|цифры))?|введи(?:\s+(?:ответ|последовательность|число|слово|цифры))?|в\s+таблиц(?:у|е)|укажите\s+ответ)(?:\s|$)/iu;
const LETTER_PATTERN = /\p{Lu}/gu;
const HEADING_OPERATOR_PATTERN = /[\p{Ll}\p{Nd}+\-−×÷*/=≤≥<>⇄→√^·∙:≠_]/u;
const STEM_PATTERN = /^(?:какой|какая|какие|каково|каким|какую|сколько|чему|что|почему|зачем|где|когда|как|установите|определите|выберите|найдите|решите|сопоставьте|назовите|укажите|расставьте|отредактируйте|выпишите|запишите|среди|в\s+тексте|из\s+предложенного)(?:\s|$)/iu;

type StemMatch = { lineIndex: number; start: number; text: string };

function splitTrailingInstruction(line: string): string[] {
  const sentences = splitPromptSentences(line);
  const instruction = sentences.at(-1);
  if (!instruction || !INSTRUCTION_PATTERN.test(instruction)) return [line];
  const instructionStart = line.lastIndexOf(instruction);
  if (instructionStart <= 0) return [line];
  return [line.slice(0, instructionStart).trim(), instruction].filter(Boolean);
}

function findStem(lines: string[]): StemMatch | null {
  const questions: StemMatch[] = [];
  const actions: StemMatch[] = [];
  lines.forEach((line, lineIndex) => {
    for (const sentence of splitPromptSentences(line)) {
      const start = line.indexOf(sentence);
      if (start < 0 || INSTRUCTION_PATTERN.test(sentence)) continue;
      const citation = /^\([^)]{1,200}\)\s*/u.exec(sentence)?.[0] ?? "";
      const candidateStart = start + citation.length;
      const candidateText = sentence.slice(citation.length);
      const match = { lineIndex, start: candidateStart, text: candidateText };
      if (/[?]\s*$/u.test(candidateText)) questions.push(match);
      if (STEM_PATTERN.test(candidateText)) actions.push(match);
    }
  });
  const lastQuestion = questions.at(-1);
  const actionAfterQuestion = lastQuestion
    ? actions.filter((match) => match.lineIndex > lastQuestion.lineIndex
      || (match.lineIndex === lastQuestion.lineIndex && match.start > lastQuestion.start))
    : [];
  return actionAfterQuestion.at(-1) ?? lastQuestion ?? actions[0] ?? null;
}

function isHeading(value: string): boolean {
  if (value.length >= 60 || HEADING_OPERATOR_PATTERN.test(value)) return false;
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
  const promptLines = lines.flatMap(splitTrailingInstruction);

  const stem = findStem(promptLines);
  const orderedLines = stem
    ? [
      stem.text,
      ...promptLines.flatMap((line, lineIndex) => {
        if (lineIndex !== stem.lineIndex) return [line];
        return [line.slice(0, stem.start).trim(), line.slice(stem.start + stem.text.length).trim()]
          .filter(Boolean);
      }),
    ]
    : promptLines;

  const blocks: PromptBlock[] = [];
  for (let index = 0; index < orderedLines.length; index += 1) {
    const line = orderedLines[index];
    if (index === 0) {
      blocks.push({ kind: "stem", text: line });
      continue;
    }

    // The converter flattens a source table to one `cell | cell` line per row.
    // Two such lines in a row are a table, and reading one as prose is the
    // difference between a grid and a wall of vertical bars.
    const rows: string[][] = [];
    while (index < orderedLines.length) {
      const row = tableRow(orderedLines[index]);
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
  if (question.type === "input" && parseTableGapPrompt(question.prompt, question)) return "таблица с пропусками";
  if (question.type === "input" && parseSequenceMatchingPrompt(question.prompt, question)) return "сопоставление";
  return "короткий ответ";
}

export function questionTitleClassName(text: string): string {
  if (text.length >= 360) return "question-title question-title-long";
  if (text.length >= 180) return "question-title question-title-medium";
  return "question-title";
}
