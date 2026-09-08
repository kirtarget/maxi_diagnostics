// @vitest-environment jsdom
import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QuestionView } from "./question-screen";
import { MatchingAnswer, matchingModelFromSequence } from "./matching-answer";
import { parseSequenceMatchingPrompt } from "./sequence-matching";
import type { Brand, InputQuestion } from "./types";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const labels = {
  back: "Назад",
  task_label: "Задание",
  of_label: "из",
  illustration_alt: "Иллюстрация",
  next_question: "Следующее задание",
  get_result: "Получить результат",
  answer_label: "Ваш ответ",
  enter_answer: "Введите ответ",
  choose_option: "Выберите вариант",
} as unknown as Brand["interface"];

const chemistryQuestion: InputQuestion = {
  id: "q-chemistry-05",
  type: "input",
  topic: "Химия",
  title: "Задание 5",
  prompt: [
    "Установите соответствие между веществами и продуктами реакции.",
    "А) первое вещество",
    "Б) второе вещество",
    "В) третье вещество",
    "1) продукт один | 2) продукт два | 3) продукт три",
    "4) продукт четыре | 5) продукт пять | ___",
    "7) продукт семь | 8) продукт восемь | 9) продукт девять",
  ].join("\n"),
  answer_format: "sequence",
  answer_length: 3,
  allow_reuse: true,
  markers: ["А", "Б", "В"],
};

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("contract-4 sequence question", () => {
  it("selects chips in sequence and emits the compact answer 277", async () => {
    const onAnswer = vi.fn();
    function Harness() {
      const [answer, setAnswer] = useState("");
      return (
        <QuestionView
          question={chemistryQuestion}
          index={0}
          total={1}
          answer={answer}
          labels={labels}
          onAnswer={(value) => { onAnswer(value); setAnswer(typeof value === "string" ? value : ""); }}
          onBack={() => undefined}
          onNext={() => undefined}
        />
      );
    }
    await act(async () => {
      root.render(<Harness />);
    });

    const rows = [...container.querySelectorAll<HTMLElement>(".matching-answer-row")];
    expect(rows).toHaveLength(3);
    expect(container.querySelectorAll(".matching-answer-row select")).toHaveLength(0);
    const choose = async (row: HTMLElement, marker: string) => {
      await act(async () => {
        row.querySelector<HTMLButtonElement>(".matching-answer-trigger")?.click();
      });
      const dialog = row.querySelector<HTMLElement>("[role=dialog]")!;
      const option = dialog.querySelector<HTMLButtonElement>(`button[data-option-key="${marker}"]`)!;
      await act(async () => option.click());
    };
    expect(rows[1].querySelector<HTMLButtonElement>(".matching-answer-trigger")?.disabled).toBe(false);
    await choose(rows[0], "2");
    await choose(rows[1], "7");
    await choose(rows[2], "7");

    expect(onAnswer).toHaveBeenLastCalledWith("277");
    expect(container.querySelector<HTMLButtonElement>(".question-next")?.disabled).toBe(false);
  });

  it("blocks reused chips when reuse is disabled", async () => {
    const matching = { ...parseSequenceMatchingPrompt(chemistryQuestion.prompt, { ...chemistryQuestion, allow_reuse: false })!, allowReuse: false };
    const onChange = vi.fn();
    await act(async () => {
      root.render(<MatchingAnswer model={matchingModelFromSequence(matching)} value="2" onChange={onChange} />);
    });

    const row = container.querySelectorAll<HTMLElement>(".matching-answer-row")[1];
    await act(async () => row.querySelector<HTMLButtonElement>(".matching-answer-trigger")?.click());
    expect(row.querySelector<HTMLButtonElement>('button[data-option-key="2"]')?.disabled).toBe(true);
    expect(row.querySelector<HTMLButtonElement>('button[data-option-key="7"]')?.disabled).toBe(false);
  });

  it("keeps every chip disabled in feedback mode and exposes the 44px target", async () => {
    const matching = parseSequenceMatchingPrompt(chemistryQuestion.prompt, chemistryQuestion)!;
    const onChange = vi.fn();
    await act(async () => {
      root.render(<MatchingAnswer model={matchingModelFromSequence(matching)} value="" onChange={onChange} disabled />);
    });

    const triggers = [...container.querySelectorAll<HTMLButtonElement>(".matching-answer-trigger")];
    expect(triggers).toHaveLength(3);
    expect(triggers.every((button) => button.disabled)).toBe(true);
    expect(onChange).not.toHaveBeenCalled();
    const css = readFileSync("app/globals.css", "utf8");
    expect(css).toMatch(/\.matching-answer-option\s*\{[\s\S]*min-width:\s*44px;[\s\S]*min-height:\s*44px;/u);
  });
});
