import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AnswerEditor } from "./answer-editor";
import type { Question } from "./types";

const base = { topic: "Алгебра", title: "Задание 1", prompt: "Реши задание." };

const single: Question = {
  ...base,
  id: "q-single",
  type: "single",
  options: [{ id: "a", label: "12" }, { id: "b", label: "18" }],
};

const multiple: Question = {
  ...base,
  id: "q-multiple",
  type: "multiple",
  selection_limit: 2,
  options: [{ id: "a", label: "12" }, { id: "b", label: "18" }, { id: "c", label: "20" }],
};

const matching: Question = {
  ...base,
  id: "q-matching",
  type: "matching",
  items: [{ id: "i1", label: "Первый" }, { id: "i2", label: "Второй" }],
  options: [{ id: "o1", label: "Один" }, { id: "o2", label: "Два" }],
};

const input: Question = {
  ...base,
  id: "q-input",
  type: "input",
  prompt: "Найди значение выражения. Ответ дайте в виде десятичной дроби.",
};

const shortText: Question = {
  ...base,
  id: "q-text",
  type: "text",
  max_length: 40,
  prompt: "Выпишите союз из предложения.",
};

const noop = () => undefined;

describe("AnswerEditor", () => {
  it("renders single choice as a radiogroup with the selected option marked", () => {
    const html = renderToStaticMarkup(<AnswerEditor question={single} value="b" onChange={noop} />);
    expect(html).toContain('role="radiogroup"');
    expect(html).toContain('role="radio"');
    expect(html).toContain('class="answer-option selected"');
    expect(html).toContain('aria-checked="true"');
    expect(html).not.toContain("selection-mark square");
  });

  it("renders multiple choice as a toggle group with square selection marks", () => {
    const html = renderToStaticMarkup(<AnswerEditor question={multiple} value={["a"]} onChange={noop} />);
    expect(html).toContain('role="group"');
    expect(html).toContain('aria-label="Выберите 2 варианта"');
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain("selection-mark square");
    expect(html).not.toContain('role="radio"');
  });

  it("renders matching rows with a select per item and the supplied choose label", () => {
    const html = renderToStaticMarkup(
      <AnswerEditor question={matching} value={{ i1: "o2" }} onChange={noop} labels={{ choose: "Выберите вариант" }} />,
    );
    expect(html).toContain('class="matching-list"');
    expect(html.match(/<select/g)).toHaveLength(2);
    expect(html).toContain("Выберите вариант");
    expect(html).toContain('aria-label="Соответствие для Первый"');
  });

  it("renders the short answer field with the brand labels and the prompt-derived hint", () => {
    const html = renderToStaticMarkup(
      <AnswerEditor question={input} value="8,4" onChange={noop} labels={{ answer: "Ваш ответ", placeholder: "Введите ответ" }} />,
    );
    expect(html).toContain('class="short-answer"');
    expect(html).toContain("Ваш ответ");
    expect(html).toContain('placeholder="Введите ответ"');
    expect(html).toContain('inputMode="decimal"');
    expect(html).toContain('class="answer-numeric"');
    expect(html).toContain("Очистить");
  });

  it("renders free text as a plain field bounded by max_length", () => {
    const html = renderToStaticMarkup(
      <AnswerEditor question={shortText} value="однако" onChange={noop} />,
    );
    expect(html).toContain('class="short-answer"');
    expect(html).toContain('inputMode="text"');
    expect(html).toContain('maxLength="40"');
    expect(html).not.toContain("answer-numeric");
    expect(html).not.toContain("цифры");
  });

  it("falls back to the default free-text length when the catalog omits it", () => {
    const html = renderToStaticMarkup(
      <AnswerEditor question={{ ...shortText, max_length: undefined }} value="" onChange={noop} />,
    );
    expect(html).toContain('maxLength="80"');
  });

  it("disables every control when the answer is locked", () => {
    for (const question of [single, multiple, matching, input, shortText]) {
      const html = renderToStaticMarkup(
        <AnswerEditor question={question} value={undefined} onChange={noop} disabled />,
      );
      expect(html).toContain("disabled");
    }
  });
});
