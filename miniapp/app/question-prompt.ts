import { parseSequenceMatchingPrompt } from "./sequence-matching";
import { parseTableGapPrompt } from "./table-gap-matching";
import { splitPromptSentences } from "./math-text";
import type { Question } from "./types";

export type PromptBlock =
  | { kind: "stem" | "heading" | "instruction" | "paragraph"; text: string }
  | { kind: "item"; marker: string; text: string }
  | TableBlock;

export type TableBlock = { kind: "table"; headerRows: string[][]; rows: string[][]; columns: number };

const ITEM_PATTERN = /^([А-ЯЁA-Z]|\d{1,2})[.)]\s*(.+)$/u;
const INSTRUCTION_PATTERN = /^(?:ответ(?:ы|ом)?(?:\s+(?:запишите|запиши|укажите|дайте))?|в\s+ответ(?:е|ом)?(?:\s+(?:запишите|запиши|укажите|дайте))?|запишите(?:\s+(?:ответ|последовательность|число|слово|цифры))?|запиши(?:\s+(?:ответ|последовательность|число|слово|цифры))?|введите(?:\s+(?:ответ|последовательность|число|слово|цифры))?|введи(?:\s+(?:ответ|последовательность|число|слово|цифры))?|в\s+таблиц(?:у|е)|укажите\s+ответ)(?:\s|$)/iu;
const LETTER_PATTERN = /\p{Lu}/gu;
const HEADING_OPERATOR_PATTERN = /[\p{Ll}\p{Nd}+\-−×÷*/=≤≥<>⇄→√^·∙:≠_]/u;
const STEM_PATTERN = /^(?:какой|какая|какие|каково|каким|какую|сколько|чему|что|почему|зачем|где|когда|как|установите|определите|выберите|найдите|решите|сопоставьте|назовите|укажите|расставьте|отредактируйте|выпишите|запишите|среди|в\s+тексте|из\s+предложенного)(?:\s|$)/iu;
const WORDS_INSTRUCTION_PATTERN = /^раскройте\s+скобки\s+и\s+выпишите\s+(?:это\s+слово|эти\s+два\s+слова)(?:\.|$)/iu;

type StemMatch = { lineIndex: number; start: number; text: string };

function splitTrailingInstruction(line: string): string[] {
  const sentences = splitPromptSentences(line);
  const instruction = sentences.at(-1);
  if (!instruction || (!INSTRUCTION_PATTERN.test(instruction) && !WORDS_INSTRUCTION_PATTERN.test(instruction))) return [line];
  const instructionStart = line.lastIndexOf(instruction);
  if (instructionStart <= 0) return [line];
  return [line.slice(0, instructionStart).trim(), instruction].filter(Boolean);
}

function findStem(lines: string[]): StemMatch | null {
  const questions: StemMatch[] = [];
  const actions: StemMatch[] = [];
  lines.forEach((line, lineIndex) => {
    if (/^(?:[А-ЯЁA-Z]|\d{1,2})[.)]\s/u.test(line)) return;
    if (/^[—–-]\s*/u.test(line)) return;
    for (const sentence of splitPromptSentences(line)) {
      const start = line.indexOf(sentence);
      if (start < 0 || /^[—–-]\s*/u.test(sentence) || INSTRUCTION_PATTERN.test(sentence) || WORDS_INSTRUCTION_PATTERN.test(sentence)) continue;
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
  if (!/\s\|\s/u.test(line)) return null;
  const cells = line.split("|").map((cell) => cell.trim());
  return cells.length >= 2 ? cells : null;
}

function isMarkerCell(value: string): boolean {
  return /^(?:[А-ЯЁA-Z]|\d{1,2})[.)]?$/u.test(value.trim());
}

function isOptionMatrixRow(row: string[]): boolean {
  return row.length >= 2 && row.every((cell) => /^\d[.)]?\s*(?:\S.*)?$/u.test(cell.trim()));
}

function tableGroups(rows: string[][]): string[][][] {
  const groups: string[][][] = [];
  let current: string[][] = [];
  let optionMatrix = false;
  for (const row of rows) {
    if (current.length > 0 && ((!isOptionMatrixRow(row) && optionMatrix) || (row.every((cell) => /^[А-ЯЁA-Z]$/u.test(cell.trim())) && current.length >= 2))) {
      groups.push(current);
      current = [];
      optionMatrix = false;
    }
    current.push(row);
    optionMatrix = isOptionMatrixRow(row);
  }
  if (current.length > 0) groups.push(current);
  return groups;
}

function isSingleRowTable(row: string[]): boolean {
  const first = row[0]?.trim() ?? "";
  if (/^(?:выберите|укажите|решите|заполните|сопоставьте|choose|select|solve)\b/iu.test(first)) return false;
  if (isMarkerCell(first)) return true;
  if (row.some((cell) => /[.!?]$/u.test(cell.trim()))) return false;
  return row.length >= 2 && row.every((cell) => cell.length > 0 && cell.length <= 40)
    && /^[\p{Lu}]/u.test(first);
}

function makeTableBlocks(rows: string[][]): TableBlock[] {
  return tableGroups(rows).map((group) => {
    const width = Math.max(...group.map((row) => row.length));
    const normalized = group.map((row) => [...row, ...Array(width - row.length).fill("")]);
    let headerCount = 0;
    const first = normalized[0] ?? [];
    const second = normalized[1] ?? [];
    const repeatedHeader = first.length > 1 && new Set(first.filter(Boolean)).size < first.filter(Boolean).length;
    const repeatedSecond = second.length > 1 && new Set(second.filter(Boolean)).size < second.filter(Boolean).length;
    const gapSecond = second.length > 0 && second.every((cell) => /\([А-ЯЁ]\)/u.test(cell));
    if (gapSecond && first.every((cell) => /^[А-ЯЁA-Z]$/u.test(cell.trim()))) headerCount = 1;
    else if (!isMarkerCell(first[0] ?? "") && !isOptionMatrixRow(first)) {
      headerCount = 1;
      if (second.length > 0 && !isMarkerCell(second[0] ?? "") && ((second[0] ?? "").trim() === "" || repeatedHeader || repeatedSecond)) headerCount = 2;
    }
    return {
      kind: "table" as const,
      headerRows: normalized.slice(0, headerCount),
      rows: normalized.slice(headerCount),
      columns: width,
    };
  });
}

export function parseQuestionPrompt(prompt: string): PromptBlock[] {
  const lines = prompt
    .split(/\n+/u)
    .map((line) => line.trim())
    .filter(Boolean);
  const promptLines = lines.flatMap((line) => tableRow(line) ? [line] : splitTrailingInstruction(line));

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
    // Delimited rows form a table group. A single row is accepted only when its
    // cells match the structural classifier below, keeping prose delimiters intact.
    const rows: string[][] = [];
    while (index < orderedLines.length) {
      const row = tableRow(orderedLines[index]);
      if (!row) break;
      rows.push(row);
      index += 1;
    }
    if (rows.length > 1 || isSingleRowTable(rows[0] ?? [])) {
      blocks.push(...makeTableBlocks(rows));
      index -= 1;
      continue;
    }
    index -= rows.length;

    if (index === 0) {
      blocks.push({ kind: "stem", text: line });
      continue;
    }

    const item = ITEM_PATTERN.exec(line);
    if (item) {
      if (/^\d+$/u.test(item[1]) && item[2].trim() === item[1]) continue;
      blocks.push({ kind: "item", marker: item[1], text: item[2] });
      continue;
    }
    if (INSTRUCTION_PATTERN.test(line) || WORDS_INSTRUCTION_PATTERN.test(line)) {
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
  if (question.type === "text") {
    return question.answer_format === "words"
      ? "короткий ответ двумя словами"
      : "короткий ответ словом";
  }
  if (question.type === "input" && parseTableGapPrompt(question.prompt, question)) return "таблица с пропусками";
  if (question.type === "input" && parseSequenceMatchingPrompt(question.prompt, question)) return "сопоставление";
  return "короткий ответ";
}

export function questionTitleClassName(text: string): string {
  if (text.length >= 360) return "question-title question-title-long";
  if (text.length >= 180) return "question-title question-title-medium";
  return "question-title";
}
