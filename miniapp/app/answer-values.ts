import type { AnswerMap } from "./types";

export function isValidNumericInput(value: unknown): value is string {
  if (typeof value !== "string" || value.length < 1 || value.length > 64 || value !== value.trim()) {
    return false;
  }
  return /^[+-]?(?:[0-9]+(?:[.,][0-9]*)?|[.,][0-9]+)(?:[eE][+-]?[0-9]{1,3})?$/.test(value);
}

const CONTROL_MAX = 0x1f;
const DELETE_CODE = 0x7f;
const CONTROL_HIGH_MAX = 0x9f;

function isControlCharacter(character: string): boolean {
  const code = character.codePointAt(0) ?? 0;
  return code <= CONTROL_MAX || (code >= DELETE_CODE && code <= CONTROL_HIGH_MAX);
}

export const DEFAULT_TEXT_ANSWER_LENGTH = 80;

/** Mirrors the server: a stored text answer is a non-blank string within `maxLength`. */
export function isValidTextInput(
  value: unknown, maxLength: number = DEFAULT_TEXT_ANSWER_LENGTH,
): value is string {
  if (typeof value !== "string" || value.length < 1 || value.length > maxLength) return false;
  if ([...value].some(isControlCharacter)) return false;
  return value.trim().replace(/[.,;!?]+$/u, "").trim().length > 0;
}

export function updateMatchingAnswer(
  current: Record<string, string>, itemId: string, value: string,
): Record<string, string> {
  if (value) return { ...current, [itemId]: value };
  const next = { ...current };
  delete next[itemId];
  return next;
}

export function updateCompactAnswer(
  current: string, index: number, value: string,
): string {
  const selections = [...current];
  if (index < 0 || index > selections.length) return current;
  if (!value) return selections.slice(0, index).join("");
  selections[index] = value;
  return selections.join("");
}

export function updateNumericInputAnswer(
  current: AnswerMap, questionId: string, draft: string,
): AnswerMap {
  if (isValidNumericInput(draft)) return { ...current, [questionId]: draft };
  const next = { ...current };
  delete next[questionId];
  return next;
}

export function updateTextInputAnswer(
  current: AnswerMap, questionId: string, draft: string, maxLength?: number,
): AnswerMap {
  if (isValidTextInput(draft, maxLength)) return { ...current, [questionId]: draft };
  const next = { ...current };
  delete next[questionId];
  return next;
}
