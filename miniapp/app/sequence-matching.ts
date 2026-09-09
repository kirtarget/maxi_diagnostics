import { parseQuestionPrompt } from "./question-prompt";
import type { InputQuestion } from "./types";

export type SequenceMatchingPrompt = {
  left: Array<{ marker: string; label: string }>;
  options: Array<{ marker: string; label: string }>;
  allowReuse: boolean;
  answerLength: number;
};

type SequenceMetadata = Pick<InputQuestion, "answer_format" | "answer_length" | "allow_reuse" | "markers">;

const TABLE_OPTION_PATTERN = /(?:^|\s)(\d)[.)]\s*(.*?)(?=\s+\d[.)]\s+|$)/gu;
const LETTER_MARKER = /^[А-ЯЁA-Z]$/u;
const NUMBER_MARKER = /^\d$/u;
const INLINE_OPTION_PATTERN = /(?:^|[,;(]\s*)(\d)\s*[–—-]\s*(True|False|Not stated)\b/gu;
const LOOKALIKE_LATIN: Record<string, string> = { А: "A", В: "B", С: "C", Е: "E", К: "K", М: "M", Н: "H", О: "O", Р: "P", Т: "T", Х: "X" };

function markerScaffold(promptBlocks: ReturnType<typeof parseQuestionPrompt>): string[] {
  for (const block of promptBlocks) {
    if (block.kind !== "table") continue;
    for (const row of [ ...block.headerRows, ...block.rows ]) {
      if (row.length >= 2 && row.every((cell) => LETTER_MARKER.test(cell.trim()))) return row.map((cell) => cell.trim());
    }
  }
  return [];
}

// Headings with nothing under them are the paper answer form. Their cells name the
// answer slots, so they belong on the cells instead of in the reference text.
function blankCaptions(promptBlocks: ReturnType<typeof parseQuestionPrompt>): string[] {
  for (const block of promptBlocks) {
    if (block.kind !== "table" || block.rows.length > 0 || block.headerRows.length !== 1) continue;
    const cells = block.headerRows[0].map((cell) => cell.trim());
    if (cells.every((cell) => cell && !LETTER_MARKER.test(cell))) return cells;
  }
  return [];
}

function parseTableLeft(promptBlocks: ReturnType<typeof parseQuestionPrompt>): Array<{ marker: string; label: string }> {
  const left: Array<{ marker: string; label: string }> = [];
  for (const block of promptBlocks) {
    if (block.kind !== "table") continue;
    for (const row of [ ...block.headerRows, ...block.rows ]) {
      if (row.length >= 2 && row.every((cell) => LETTER_MARKER.test(cell.trim()))) continue;
      const marker = row[0]?.trim() ?? "";
      const label = row.slice(1).join(" ").trim();
      if (LETTER_MARKER.test(marker) && label) left.push({ marker, label });
    }
  }
  return left;
}

function parseTableOptions(promptBlocks: ReturnType<typeof parseQuestionPrompt>): Array<{ marker: string; label: string }> {
  const options: Array<{ marker: string; label: string }> = [];
  for (const block of promptBlocks) {
    if (block.kind !== "table") continue;
    for (const cell of [ ...block.headerRows.flat(), ...block.rows.flat() ]) {
      for (const match of cell.matchAll(TABLE_OPTION_PATTERN)) {
        const label = match[2].trim();
        if (label && label !== "___") options.push({ marker: match[1], label });
      }
    }
  }
  return options;
}

export function parseSequenceMatchingPrompt(
  prompt: string,
  metadata?: SequenceMetadata,
): SequenceMatchingPrompt | null {
  if (metadata?.answer_format === "number") return null;

  const promptBlocks = parseQuestionPrompt(prompt);
  const scaffold = markerScaffold(promptBlocks);
  const items = promptBlocks.filter((block) => block.kind === "item");
  const hasLatinItemMarker = items.some((item) => /^[A-Z]$/u.test(item.marker));
  const normalizeMarker = (marker: string) => scaffold.find((candidate) => candidate === marker)
    ?? scaffold.find((candidate) => LOOKALIKE_LATIN[marker] === candidate)
    ?? (scaffold.length === 0 && hasLatinItemMarker ? LOOKALIKE_LATIN[marker] ?? marker : marker);
  const parsedLeft = [
    ...items
      .filter((item) => LETTER_MARKER.test(item.marker))
      .map((item) => ({ marker: normalizeMarker(item.marker), label: item.text })),
    ...parseTableLeft(promptBlocks),
  ]
    .filter((item, index, all) => all.findIndex((candidate) => candidate.marker === item.marker) === index)
  const numberedItems = items
    .filter((item) => NUMBER_MARKER.test(item.marker))
    .map((item) => ({ marker: item.marker, label: item.text }));
  const inlineOptions = [...prompt.matchAll(INLINE_OPTION_PATTERN)].map((match) => ({ marker: match[1], label: match[2] }));

  const explicit = metadata?.answer_format === "sequence"
    || metadata?.answer_length !== undefined
    || metadata?.allow_reuse !== undefined
    || metadata?.markers !== undefined;
  const candidateOptions = metadata?.answer_format === "sequence"
    ? [...numberedItems, ...parseTableOptions(promptBlocks), ...inlineOptions]
    : numberedItems.length > 0 ? numberedItems : inlineOptions;
  const optionByMarker = new Map<string, { marker: string; label: string }>();
  for (const option of candidateOptions) {
    const previous = optionByMarker.get(option.marker);
    if (previous && previous.label !== option.label) return null;
    optionByMarker.set(option.marker, option);
  }
  const options = [...optionByMarker.values()];
  if (!explicit && (parsedLeft.length < 2 || options.length < 2)) return null;
  if (parsedLeft.length > 0 && new Set(parsedLeft.map((item) => item.marker)).size !== parsedLeft.length) return null;
  if (new Set(options.map((item) => item.marker)).size !== options.length) return null;

  const markers = metadata?.markers?.length
    ? [...metadata.markers]
    : scaffold.length > 0 ? scaffold : parsedLeft.map((item) => item.marker);
  const answerLength = metadata?.answer_length ?? markers.length;
  if (answerLength < 1 || options.length < 1) return null;

  const leftByMarker = new Map(parsedLeft.map((item) => [item.marker, item]));
  const captions = blankCaptions(promptBlocks);
  const left = Array.from({ length: answerLength }, (_, index) => {
    const marker = markers[index] ?? parsedLeft[index]?.marker ?? String(index + 1);
    // A cell named by a table heading has no separate wording of its own, so
    // repeating the name as a label would print it twice in the same row.
    return leftByMarker.get(marker)
      ?? { marker, label: captions.length === answerLength ? captions[index] : "" };
  });

  return {
    left,
    options,
    allowReuse: metadata?.allow_reuse
      ?? (/цифры\s+в\s+ответе\s+могут\s+повторяться/iu.test(prompt) || options.length < answerLength),
    answerLength,
  };
}

export function isCompleteSequenceMatchingAnswer(
  matching: SequenceMatchingPrompt,
  answer: unknown,
): boolean {
  if (typeof answer !== "string" || [...answer].length !== matching.answerLength) return false;
  const allowed = new Set(matching.options.map((item) => item.marker));
  const values = [...answer];
  return values.every((value) => allowed.has(value))
    && (
      matching.allowReuse
      || matching.options.length < matching.left.length
      || new Set(values).size === values.length
    );
}
