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
  isSubscript: boolean;
  isAnnotation?: boolean;
};

// Aggregate-state and concentration marks are reading conditions, not part of
// the formula, so they keep body type instead of bold or index sizing.
// Some source files spell the solution mark with Latin lookalikes, so both
// alphabets are accepted rather than left to render as part of the formula.
const STATE_ANNOTATION = /\((?:[рp]-[рp][аa]?|ж|г|т|тв|изб|конц|разб|крист|aq)\.?\)/giu;

function splitAnnotations(text: string): MathDisplayPart[] {
  const parts: MathDisplayPart[] = [];
  let cursor = 0;
  for (const match of text.matchAll(STATE_ANNOTATION)) {
    if (match.index > cursor) {
      parts.push({ text: text.slice(cursor, match.index), isSuperscript: false, isSubscript: false });
    }
    parts.push({ text: match[0], isSuperscript: false, isSubscript: false, isAnnotation: true });
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor), isSuperscript: false, isSubscript: false });
  return parts;
}

const IMPORTANT_SENTENCE = /(?:^|[,;:]\s)(?:выберите|вычислите|запишите|найдите|назовите|определите|решите|сопоставьте|укажите|установите)(?:\s|$)|^(?:какой|какая|какие|каково|сколько|чему равен|чему равна)(?:\s|$)/iu;
const DIGIT_ANSWER = /(?:без пробелов|двоичн|кодовое слово|последовательност[ьи]\s+цифр|числов|цифр|решите\s+уравнение|ответ\s+дайте\s+в)/iu;
const VARIABLE_CONTEXT = /(?:букв|переменн|обознач|код|точк|отрез|прям|вектор|угол)/iu;
const LANGUAGE_SUBJECT = /(?:русск|russian|англ|english|литератур|literature|истор|history|обществозн|обществ|social[-_ ]?studies)/iu;
const VARIABLE_STOP_WORDS = new Set(["а", "в", "и", "к", "о", "с", "у", "я", "б"]);

type MathSpan = { start: number; end: number };

function balancedEnd(text: string, opening: number): number | null {
  const stack: string[] = [];
  for (let index = opening; index < text.length; index += 1) {
    const character = text[index];
    if (character === "(" || character === "[") {
      stack.push(character === "(" ? ")" : "]");
    } else if (character === ")" || character === "]") {
      if (stack.at(-1) !== character) return null;
      stack.pop();
      if (stack.length === 0) return index + 1;
    }
  }
  return null;
}

function consumeAtom(text: string, start: number): number {
  let index = start;
  if (text[index] === "√") {
    index += 1;
    while (/\s/u.test(text[index] ?? "")) index += 1;
  }
  while (index < text.length && /[A-Za-zА-ЯЁа-яё0-9₀-₉⁰-⁹]/u.test(text[index])) index += 1;
  while ((text[index] === "." || text[index] === ",") && /[0-9]/u.test(text[index + 1] ?? "")) {
    index += 1;
    while (index < text.length && /[0-9]/u.test(text[index])) index += 1;
  }
  while (index < text.length) {
    const marker = text[index];
    if ((marker === "_" || marker === "^") && text[index + 1] === "(") {
      const end = balancedEnd(text, index + 1);
      if (end === null) break;
      index = end;
      continue;
    }
    if (text[index] === "(" || text[index] === "[") {
      const end = balancedEnd(text, index);
      if (end === null) break;
      index = end;
      continue;
    }
    if (text[index] === "-" && /[0-9]/u.test(text[index + 1] ?? "")) {
      index += 1;
      while (index < text.length && /[0-9₀-₉⁰-⁹]/u.test(text[index])) index += 1;
      continue;
    }
    // A formula continues after an index or a state annotation: H_(2)O is one
    // token, not "H_(2)" plus a stray "O".
    if (/[A-Za-zА-ЯЁа-яё0-9₀-₉⁰-⁹]/u.test(text[index])) {
      while (index < text.length && /[A-Za-zА-ЯЁа-яё0-9₀-₉⁰-⁹]/u.test(text[index])) index += 1;
      continue;
    }
    break;
  }
  return index;
}

function isMathSpan(text: string, span: MathSpan): boolean {
  const token = text.slice(span.start, span.end);
  if (/^\d+(?:[.,]\d+)?°$/u.test(token)) return true;
  if (/[_^]\(/u.test(token) || /[+\-−×÷*/=≤≥<>⇄→√·∙]/u.test(token)) return true;
  if (/[≠:]/u.test(token) && (/^[A-Za-z](?:[0-9₀-₉⁰-⁹])?\s*[≠:]\s*[A-Za-z](?:[0-9₀-₉⁰-⁹])?$/u.test(token)
    || /[0-9₀-₉⁰-⁹]/u.test(token))) return true;
  if (/[A-Za-zА-ЯЁа-яё]/u.test(token) && /[0-9₀-₉⁰-⁹]/u.test(token)) return true;
  if (/^[A-Za-z]$/u.test(token)) {
    return !VARIABLE_STOP_WORDS.has(token.toLocaleLowerCase("ru-RU")) && VARIABLE_CONTEXT.test(text);
  }
  return false;
}

function nextMathSpan(text: string, from: number): MathSpan | null {
  for (let start = from; start < text.length; start += 1) {
    const isFormulaMarker = (text[start] === "_" || text[start] === "^") && text[start + 1] === "(";
    if (!/[A-Za-zА-ЯЁа-яё0-9√()[\]]/u.test(text[start]) && !isFormulaMarker) continue;
    const end = consumeAtom(text, start);
    if (end <= start) continue;

    let expressionEnd = end;
    let cursor = end;
    while (cursor < text.length) {
      const whitespace = /^\s*/u.exec(text.slice(cursor))?.[0].length ?? 0;
      const operator = text[cursor + whitespace];
      if (!operator || !/[+\-−×÷*/=≤≥<>⇄→√≠:·∙]/u.test(operator)) break;
      const operandStart = cursor + whitespace + 1;
      const operandWhitespace = /^\s*/u.exec(text.slice(operandStart))?.[0].length ?? 0;
      const atomStart = operandStart + operandWhitespace;
      if (operator === "-" && !/[0-9]/u.test(text[atomStart] ?? "")) break;
      const atomEnd = consumeAtom(text, atomStart);
      if (atomEnd <= atomStart) break;
      expressionEnd = atomEnd;
      cursor = atomEnd;
    }

    if (/^\d/u.test(text.slice(start, expressionEnd))) {
      const unit = /^\s*(?:кг|г|мг|м|см|мм|км|л|мл|с|мин|ч|°C|кДж|Н|Па|Вт|В|А|Ом|моль)(?![\p{L}])(?:\s*\/\s*(?:кг|г|мг|м|см|мм|км|л|мл|с|мин|ч|моль)(?![\p{L}]))?/iu.exec(text.slice(expressionEnd));
    if (unit) {
      expressionEnd += unit[0].length;
      const marker = text[expressionEnd];
      if ((marker === "_" || marker === "^") && text[expressionEnd + 1] === "(") {
        const exponentEnd = balancedEnd(text, expressionEnd + 1);
        if (exponentEnd !== null) expressionEnd = exponentEnd;
      }
    }
    }

    const span = { start, end: expressionEnd };
    if (isMathSpan(text, span)) return span;
  }
  return null;
}

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

export function tokenizeMathText(text: string, subject?: string): MathTextPart[] {
  if (subject && LANGUAGE_SUBJECT.test(subject)) return [{ text, isMath: false }];
  const parts: MathTextPart[] = [];
  let cursor = 0;

  while (cursor < text.length) {
    const span = nextMathSpan(text, cursor);
    if (!span) break;
    if (span.start > cursor) appendPlain(parts, text.slice(cursor, span.start));
    const token = text.slice(span.start, span.end);
    const isVariable = /^[A-Za-zА-ЯЁ]$/u.test(token);
    const shouldKeepPlain = isHistoricalDateToken(text, span.start, token);
    if (shouldKeepPlain) appendPlain(parts, token);
    else parts.push(isVariable
      ? { text: token, isMath: true, isVariable: true }
      : { text: token, isMath: true });
    cursor = span.end;
  }

  if (cursor < text.length) appendPlain(parts, text.slice(cursor));
  return parts.length > 0 ? parts : [{ text, isMath: false }];
}

export function splitPromptSentences(text: string): string[] {
  const sentences: string[] = [];
  let start = 0;
  for (let index = 0; index < text.length; index += 1) {
    if (!/[.!?]/u.test(text[index])) continue;
    let next = index + 1;
    while (/\s/u.test(text[next] ?? "")) next += 1;
    if (!/[A-ZА-ЯЁ]/u.test(text[next] ?? "")) continue;
    const prefix = text.slice(start, index + 1);
    if (/(?:^|[\s(])[A-ZА-ЯЁ]\.$/u.test(prefix) || /(?:^|\s)(?:т\. д\.|н\.у\.)$/iu.test(prefix)) continue;
    sentences.push(text.slice(start, index + 1).trim());
    start = next;
    index = next - 1;
  }
  if (start < text.length) sentences.push(text.slice(start).trim());
  return sentences.filter(Boolean);
}

export function mathDisplayParts(text: string): MathDisplayPart[] {
  const parts: MathDisplayPart[] = [];
  let cursor = 0;
  while (cursor < text.length) {
    const marker = text[cursor];
    if ((marker !== "^" && marker !== "_") || text[cursor + 1] !== "(") {
      cursor += 1;
      continue;
    }
    const end = balancedEnd(text, cursor + 1);
    if (end === null) {
      cursor += 1;
      continue;
    }
    if (cursor > 0) {
      parts.push(...splitAnnotations(text.slice(0, cursor)));
    }
    const content = text.slice(cursor + 2, end - 1).trim();
    const state = marker === "_" ? /^(\d[0-9₀-₉⁰-⁹]*)?\s*(\([^()]*\))$/u.exec(content) : null;
    if (state) {
      if (state[1]) parts.push({ text: state[1], isSuperscript: false, isSubscript: true });
      parts.push({ text: state[2], isSuperscript: false, isSubscript: false, isAnnotation: true });
    } else {
      parts.push({
        text: content,
        isSuperscript: marker === "^",
        isSubscript: marker === "_",
      });
    }
    text = text.slice(end);
    cursor = 0;
  }
  if (text.length > 0) {
    parts.push(...splitAnnotations(text));
  }
  return parts.length ? parts : [{ text, isSuperscript: false, isSubscript: false }];
}

const SUBSCRIPT_CHARACTERS: Record<string, string> = {
  "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
  "+": "₊", "-": "₋", "=": "₌", "(": "₍", ")": "₎",
};
const SUPERSCRIPT_CHARACTERS: Record<string, string> = {
  "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
  "+": "⁺", "-": "⁻", "=": "⁼", "(": "⁽", ")": "⁾",
};

export function plainMathText(text: string, subject?: string): string {
  if (subject && LANGUAGE_SUBJECT.test(subject)) return text;
  return mathDisplayParts(text).map((part) => {
    if (!part.isSubscript && !part.isSuperscript) return part.text;
    const map = part.isSubscript ? SUBSCRIPT_CHARACTERS : SUPERSCRIPT_CHARACTERS;
    return [...part.text].map((character) => map[character] ?? character).join("");
  }).join("");
}

export function isImportantPromptSentence(text: string): boolean {
  return IMPORTANT_SENTENCE.test(text);
}

export function answerInputConfig(prompt: string): AnswerInputConfig {
  if (/(?:двоичн|кодовое слово)/iu.test(prompt)) {
    return {
      inputMode: "numeric",
      hint: "Введи только цифры 0 и 1, без пробелов.",
    };
  }
  if (DIGIT_ANSWER.test(prompt)) {
    return {
      inputMode: "decimal",
      hint: /без пробелов/iu.test(prompt)
        ? "Введи ответ слитно, без пробелов и лишних знаков."
        : "Используй цифры и знак минус, если он нужен.",
    };
  }
  return {
    inputMode: "text",
    hint: "Введи только ответ — без пояснений и лишних пробелов.",
  };
}
