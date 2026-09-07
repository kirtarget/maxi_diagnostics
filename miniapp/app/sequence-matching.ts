import { parseQuestionPrompt } from "./question-prompt";
import type { InputQuestion } from "./types";

export type SequenceMatchingPrompt = {
  left: Array<{ marker: string; label: string }>;
  options: Array<{ marker: string; label: string }>;
  allowReuse: boolean;
  answerLength: number;
};

type SequenceMetadata = Pick<InputQuestion, "answer_format" | "answer_length" | "allow_reuse" | "markers">;

const TABLE_OPTION_PATTERN = /(?:^|\s)(\d{1,2})[.)]\s*(.*?)(?=\s+\d{1,2}[.)]\s+|$)/gu;

function parseTableOptions(promptBlocks: ReturnType<typeof parseQuestionPrompt>): Array<{ marker: string; label: string }> {
  const options: Array<{ marker: string; label: string }> = [];
  for (const block of promptBlocks) {
    if (block.kind !== "table") continue;
    for (const cell of block.rows.flat()) {
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
  const items = promptBlocks.filter((block) => block.kind === "item");
  const parsedLeft = items
    .filter((item) => /^[А-ЯЁ]$/u.test(item.marker))
    .map((item) => ({ marker: item.marker, label: item.text }));
  const numberedItems = items
    .filter((item) => /^\d$/u.test(item.marker))
    .map((item) => ({ marker: item.marker, label: item.text }));

  const explicit = metadata?.answer_format === "sequence"
    || metadata?.answer_length !== undefined
    || metadata?.allow_reuse !== undefined
    || metadata?.markers !== undefined;
  const options = metadata?.answer_format === "sequence"
    ? [...numberedItems, ...parseTableOptions(promptBlocks)]
    : numberedItems;
  if (!explicit && (parsedLeft.length < 2 || options.length < 2)) return null;
  if (parsedLeft.length > 0 && new Set(parsedLeft.map((item) => item.marker)).size !== parsedLeft.length) return null;
  if (new Set(options.map((item) => item.marker)).size !== options.length) return null;

  const markers = metadata?.markers?.length
    ? [...metadata.markers]
    : parsedLeft.map((item) => item.marker);
  const answerLength = metadata?.answer_length ?? markers.length;
  if (answerLength < 1 || options.length < 1) return null;

  const leftByMarker = new Map(parsedLeft.map((item) => [item.marker, item]));
  const left = Array.from({ length: answerLength }, (_, index) => {
    const marker = markers[index] ?? parsedLeft[index]?.marker ?? String(index + 1);
    return leftByMarker.get(marker) ?? { marker, label: marker };
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
