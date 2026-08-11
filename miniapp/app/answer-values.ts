import type { AnswerMap } from "./types";

export function isValidNumericInput(value: unknown): value is string {
  if (typeof value !== "string" || value.length < 1 || value.length > 64 || value !== value.trim()) {
    return false;
  }
  return /^[+-]?(?:[0-9]+(?:[.,][0-9]*)?|[.,][0-9]+)(?:[eE][+-]?[0-9]{1,3})?$/.test(value);
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
