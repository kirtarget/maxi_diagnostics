// @vitest-environment jsdom
import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QuestionView } from "./question-screen";
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
  it("selects 2, 7, 7 and emits the compact answer 277", async () => {
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

    const selects = [...container.querySelectorAll<HTMLSelectElement>(".sequence-matching-row select")];
    expect(selects).toHaveLength(3);
    for (const [select, value] of selects.map((select, index) => [select, ["2", "7", "7"][index]] as const)) {
      await act(async () => {
        select.value = value;
        select.dispatchEvent(new Event("change", { bubbles: true }));
      });
    }

    expect(onAnswer).toHaveBeenLastCalledWith("277");
    expect(container.querySelector<HTMLButtonElement>(".question-next")?.disabled).toBe(false);
  });
});
