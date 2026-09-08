import type { AnswerMap, AnswerValue, Question } from "./types";

export function emptyAnswerFor(question: Question): AnswerValue {
  switch (question.type) {
    case "single":
    case "input":
    case "text":
      return "";
    case "multiple":
      return [];
    case "matching":
      return {};
    default: {
      const exhaustiveQuestion: never = question;
      return exhaustiveQuestion;
    }
  }
}

export function isEmptyAnswer(question: Question, answer: unknown): boolean {
  switch (question.type) {
    case "single":
    case "input":
    case "text":
      return answer === "";
    case "multiple":
      return Array.isArray(answer) && answer.length === 0;
    case "matching":
      return typeof answer === "object"
        && answer !== null
        && !Array.isArray(answer)
        && Object.keys(answer).length === 0;
    default: {
      const exhaustiveQuestion: never = question;
      return exhaustiveQuestion;
    }
  }
}

export function updateAnswerFromEditor(
  current: AnswerMap, question: Question, value: AnswerValue,
): AnswerMap {
  const next = { ...current };
  if (isEmptyAnswer(question, value)) {
    delete next[question.id];
  } else {
    next[question.id] = value;
  }
  return next;
}

export function isValidNumericInput(value: unknown): value is string {
  if (typeof value !== "string" || value.length < 1 || value.length > 64 || value !== value.trim()) {
    return false;
  }
  const normalized = normalizeNumericInput(value);
  return /^[+-]?(?:[0-9]+(?:[.,][0-9]*)?|[.,][0-9]+)(?:[eE][+-]?[0-9]{1,3})?$/.test(normalized);
}

export function normalizeNumericInput(value: string): string {
  return value.replace(/−/gu, "-");
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
  const normalized = normalizeNumericInput(draft);
  if (isValidNumericInput(normalized)) return { ...current, [questionId]: normalized };
  if (Object.hasOwn(current, questionId) && current[questionId] === "") return current;
  const next = { ...current };
  delete next[questionId];
  return next;
}

export function updateTextInputAnswer(
  current: AnswerMap, questionId: string, draft: string, maxLength?: number,
): AnswerMap {
  if (isValidTextInput(draft, maxLength)) return { ...current, [questionId]: draft };
  if (Object.hasOwn(current, questionId) && current[questionId] === "") return current;
  const next = { ...current };
  delete next[questionId];
  return next;
}
