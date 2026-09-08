// @vitest-environment jsdom
import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
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

const diagnosticsDir = resolve(dirname(fileURLToPath(import.meta.url)), "../../school/diagnostics");
function catalogQuestion(id: string): InputQuestion {
  for (const file of ["oge-chemistry-192.json", "oge-physics-197.json"]) {
    const diagnostic = JSON.parse(readFileSync(resolve(diagnosticsDir, file), "utf8")) as {
      questions: Array<Record<string, unknown>>;
    };
    const question = diagnostic.questions.find((candidate) => candidate.id === id);
    if (question) return question as unknown as InputQuestion;
  }
  throw new Error(`Missing catalog question ${id}`);
}

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

    const cells = [...container.querySelectorAll<HTMLButtonElement>(".sequence-answer-cell")];
    expect(cells).toHaveLength(3);
    expect(container.querySelectorAll(".sequence-answer-cell select")).toHaveLength(0);
    const choose = async (index: number, marker: string) => {
      await act(async () => cells[index].click());
      const dialog = container.querySelector<HTMLElement>("[role=dialog]")!;
      const option = dialog.querySelector<HTMLButtonElement>(`button[data-option-key="${marker}"]`)!;
      await act(async () => option.click());
    };
    expect(cells[1].disabled).toBe(true);
    await choose(0, "2");
    await choose(1, "7");
    await choose(2, "7");

    expect(onAnswer).toHaveBeenLastCalledWith("277");
    expect(container.querySelector<HTMLButtonElement>(".question-next")?.disabled).toBe(false);
  });

  it("blocks reused chips when reuse is disabled", async () => {
    const matching = { ...parseSequenceMatchingPrompt(chemistryQuestion.prompt, { ...chemistryQuestion, allow_reuse: false })!, allowReuse: false };
    const onChange = vi.fn();
    await act(async () => {
      root.render(<MatchingAnswer model={matchingModelFromSequence(matching)} value="2" onChange={onChange} />);
    });

    const cells = container.querySelectorAll<HTMLButtonElement>(".sequence-answer-cell");
    await act(async () => cells[0].click());
    await act(async () => container.querySelector<HTMLButtonElement>('button[data-option-key="2"]')?.click());
    await act(async () => cells[1].click());
    expect(container.querySelector<HTMLButtonElement>('[role=dialog] button[data-option-key="2"]')?.disabled).toBe(true);
    expect(container.querySelector<HTMLButtonElement>('[role=dialog] button[data-option-key="7"]')?.disabled).toBe(false);
  });

  it("keeps every chip disabled in feedback mode and exposes the 44px target", async () => {
    const matching = parseSequenceMatchingPrompt(chemistryQuestion.prompt, chemistryQuestion)!;
    const onChange = vi.fn();
    await act(async () => {
      root.render(<MatchingAnswer model={matchingModelFromSequence(matching)} value="" onChange={onChange} disabled />);
    });

    const cells = [...container.querySelectorAll<HTMLButtonElement>(".sequence-answer-cell")];
    expect(cells).toHaveLength(3);
    expect(cells.every((button) => button.disabled)).toBe(true);
    expect(container.querySelector<HTMLButtonElement>(".sequence-answer-sheet-trigger")?.disabled).toBe(true);
    expect(onChange).not.toHaveBeenCalled();
    const css = readFileSync("app/globals.css", "utf8");
    expect(css).toMatch(/\.matching-answer-option\s*\{[\s\S]*min-width:\s*44px;[\s\S]*min-height:\s*44px;/u);
  });

  it("renders and fills real chemistry q03 ordering cells", async () => {
    const onAnswer = vi.fn();
    await act(async () => {
      root.render(<QuestionView question={catalogQuestion("sp-chemistry-oge-2022-q3")} index={0} total={1} answer="" labels={labels} onAnswer={onAnswer} onBack={() => undefined} onNext={() => undefined} />);
    });

    const cells = [...container.querySelectorAll<HTMLButtonElement>(".sequence-answer-cell")];
    expect(cells).toHaveLength(3);
    expect(container.querySelectorAll(".sequence-answer-palette [role=radio]")).toHaveLength(3);
    expect(cells.map((cell) => cell.dataset.sequenceCell)).toEqual(["1", "2", "3"]);
    await act(async () => container.querySelector<HTMLButtonElement>('button[data-option-key="1"]')?.click());
    expect(onAnswer).toHaveBeenLastCalledWith("1");
    expect(container.textContent).toContain("Заполнено 1 из 3");
  });

  it("renders real physics q04 lettered cells and all seven choices", async () => {
    const onAnswer = vi.fn();
    await act(async () => {
      root.render(<QuestionView question={catalogQuestion("sp-physics-oge-2022-q4")} subject="Физика" index={0} total={1} answer="" labels={labels} onAnswer={onAnswer} onBack={() => undefined} onNext={() => undefined} />);
    });

    const cells = [...container.querySelectorAll<HTMLButtonElement>(".sequence-answer-cell")];
    expect(cells).toHaveLength(4);
    expect(cells.map((cell) => cell.dataset.sequenceCell)).toEqual(["А", "Б", "В", "Г"]);
    expect(container.querySelectorAll(".sequence-answer-palette [role=radio]")).toHaveLength(7);
    await act(async () => cells[0].click());
    await act(async () => container.querySelector<HTMLButtonElement>('.sequence-answer-palette [data-option-key="6"]')?.click());
    expect(onAnswer).toHaveBeenLastCalledWith("6");
    expect(cells[0].textContent).toContain("А");
  });
});
