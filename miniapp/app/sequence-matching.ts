import { parseQuestionPrompt } from "./question-prompt";

export type SequenceMatchingPrompt = {
  left: Array<{ marker: string; label: string }>;
  options: Array<{ marker: string; label: string }>;
  allowReuse: boolean;
};

export function parseSequenceMatchingPrompt(prompt: string): SequenceMatchingPrompt | null {
  const items = parseQuestionPrompt(prompt).filter((block) => block.kind === "item");
  const left = items
    .filter((item) => /^[А-ЯЁ]$/u.test(item.marker))
    .map((item) => ({ marker: item.marker, label: item.text }));
  const options = items
    .filter((item) => /^\d$/u.test(item.marker))
    .map((item) => ({ marker: item.marker, label: item.text }));

  if (left.length < 2 || options.length < 2) return null;
  if (new Set(left.map((item) => item.marker)).size !== left.length) return null;
  if (new Set(options.map((item) => item.marker)).size !== options.length) return null;
  return {
    left,
    options,
    allowReuse: /цифры\s+в\s+ответе\s+могут\s+повторяться/iu.test(prompt),
    ...(options.length < left.length ? { allowReuse: true } : {}),
  };
}

export function isCompleteSequenceMatchingAnswer(
  matching: SequenceMatchingPrompt,
  answer: unknown,
): boolean {
  if (typeof answer !== "string" || answer.length !== matching.left.length) return false;
  const allowed = new Set(matching.options.map((item) => item.marker));
  const values = [...answer];
  return values.every((value) => allowed.has(value))
    && (
      matching.allowReuse
      || matching.options.length < matching.left.length
      || new Set(values).size === values.length
    );
}
