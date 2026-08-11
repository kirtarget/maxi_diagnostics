export type MathTextPart = {
  text: string;
  isMath: boolean;
  isVariable?: boolean;
};

export type AnswerInputConfig = {
  inputMode: "decimal" | "numeric" | "text";
  hint: string;
};

export type MathDisplayPart = {
  text: string;
  isSuperscript: boolean;
};

const ATOM_BODY = String.raw`[A-Za-z0-9₀-₉⁰-⁹]+(?:[.,][A-Za-z0-9₀-₉⁰-⁹]+)?`;
const BASE_ATOM = String.raw`(?:${ATOM_BODY}(?:\([^)]*\))?|\([^)]*\)|\[[^\]]+\])`;
const MATH_ATOM = String.raw`(?:√\s*)?${BASE_ATOM}`;
const MATH_OPERATOR = String.raw`[+\-−×÷*/=≤≥<>⇄→√^·∙]`;
const MATH_EXPRESSION = new RegExp(
  String.raw`${MATH_ATOM}(?:\s*${MATH_OPERATOR}\s*${MATH_ATOM})+|√\s*${BASE_ATOM}|\b[A-Za-z0-9]+[₀-₉⁰-⁹]+[A-Za-z0-9₀-₉⁰-⁹]*|\b\d+(?:[.,]\d+)?°|\b\d+(?:[.,]\d+)?\b|\b[A-Za-z]\b|(?<![\p{L}\p{N}_])[А-ЯЁ](?![\p{L}\p{N}_])`,
  "gu",
);
const IMPORTANT_SENTENCE = /(?:^|[,;:]\s)(?:выберите|вычислите|запишите|найдите|назовите|определите|решите|сопоставьте|укажите|установите)(?:\s|$)|^(?:какой|какая|какие|каково|сколько|чему равен|чему равна)(?:\s|$)/iu;
const DIGIT_ANSWER = /(?:без пробелов|двоичн|кодовое слово|последовательност[ьи]\s+цифр|числов|цифр|решите\s+уравнение|ответ\s+дайте\s+в)/iu;
const VARIABLE_CONTEXT = /(?:букв|переменн|обознач|код|точк|отрез|прям|вектор|угол)/iu;

function isHistoricalDateToken(text: string, index: number, token: string): boolean {
  if (!/^\d{3,4}$/u.test(token)) return false;
  const before = text.slice(Math.max(0, index - 20), index);
  const after = text.slice(index + token.length, index + token.length + 12);
  return /(?:^|\s)год\s*$/iu.test(before)
    || /^\s*(?:г\.|год(?:а|у|ом)?\b|-е\b)/iu.test(after);
}

function appendPlain(parts: MathTextPart[], text: string): void {
  const previous = parts.at(-1);
  if (previous && !previous.isMath) previous.text += text;
  else parts.push({ text, isMath: false });
}

export function tokenizeMathText(text: string): MathTextPart[] {
  const parts: MathTextPart[] = [];
  let cursor = 0;

  for (const match of text.matchAll(MATH_EXPRESSION)) {
    const index = match.index ?? 0;
    if (index > cursor) appendPlain(parts, text.slice(cursor, index));
    const isVariable = /^[A-Za-zА-ЯЁ]$/u.test(match[0]);
    const shouldKeepPlain = isHistoricalDateToken(text, index, match[0])
      || (isVariable && !VARIABLE_CONTEXT.test(text));
    if (shouldKeepPlain) appendPlain(parts, match[0]);
    else {
      parts.push(isVariable
        ? { text: match[0], isMath: true, isVariable: true }
        : { text: match[0], isMath: true });
    }
    cursor = index + match[0].length;
  }

  if (cursor < text.length) appendPlain(parts, text.slice(cursor));
  return parts.length > 0 ? parts : [{ text, isMath: false }];
}

export function splitPromptSentences(text: string): string[] {
  return text
    .split(/(?<=[.!?])\s+(?=[А-ЯA-ZЁ«])/u)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
}

export function mathDisplayParts(text: string): MathDisplayPart[] {
  const parts: MathDisplayPart[] = [];
  const powers = /\^\(([^()]*)\)/gu;
  let cursor = 0;
  for (const match of text.matchAll(powers)) {
    const index = match.index ?? 0;
    if (index > cursor) {
      parts.push({ text: text.slice(cursor, index), isSuperscript: false });
    }
    parts.push({ text: match[1], isSuperscript: true });
    cursor = index + match[0].length;
  }
  if (cursor < text.length) {
    parts.push({ text: text.slice(cursor), isSuperscript: false });
  }
  return parts.length ? parts : [{ text, isSuperscript: false }];
}

export function isImportantPromptSentence(text: string): boolean {
  return IMPORTANT_SENTENCE.test(text);
}

export function answerInputConfig(prompt: string): AnswerInputConfig {
  if (/(?:двоичн|кодовое слово)/iu.test(prompt)) {
    return {
      inputMode: "numeric",
      hint: "Введите только цифры 0 и 1, без пробелов.",
    };
  }
  if (DIGIT_ANSWER.test(prompt)) {
    return {
      inputMode: "decimal",
      hint: /без пробелов/iu.test(prompt)
        ? "Введите ответ слитно, без пробелов и лишних знаков."
        : "Используйте цифры и знак минус, если он нужен.",
    };
  }
  return {
    inputMode: "text",
    hint: "Введите только ответ — без пояснений и лишних пробелов.",
  };
}
