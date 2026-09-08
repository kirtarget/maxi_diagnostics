// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  AnswerPreview,
  MatchingAnswer,
  matchingModelFromQuestion,
  matchingModelFromSequence,
  type MatchingModel,
} from "./matching-answer";
import { parseSequenceMatchingPrompt } from "./sequence-matching";
import type { MatchingQuestion } from "./types";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const mapModel: MatchingModel = {
  source: "matching",
  rows: [
    { key: "i1", marker: "А", label: "Первый пункт" },
    { key: "i2", marker: "Б", label: "Второй пункт" },
  ],
  options: [
    { key: "o1", marker: "1", label: "Первый вариант" },
    { key: "o2", marker: "2", label: "Второй вариант" },
    { key: "o3", marker: "3", label: "Третий вариант" },
    { key: "o4", marker: "4", label: "Четвёртый вариант" },
    { key: "o5", marker: "5", label: "Пятый вариант" },
  ],
  markers: ["А", "Б"],
  answerLength: 2,
  allowReuse: false,
};

const longSequenceModel: MatchingModel = {
  ...mapModel,
  source: "sequence",
  rows: [
    { key: "А", marker: "А", label: "Первый пункт" },
    { key: "Б", marker: "Б", label: "Второй пункт" },
  ],
  options: Array.from({ length: 7 }, (_, index) => ({
    key: String(index + 1),
    marker: String(index + 1),
    label: `Вариант ${index + 1} с полным текстом`,
  })),
  markers: ["А", "Б"],
  answerLength: 2,
  allowReuse: true,
};

const diagnosticsDir = resolve(dirname(fileURLToPath(import.meta.url)), "../../school/diagnostics");
function catalogQuestion(id: string): Record<string, unknown> {
  for (const file of readdirSync(diagnosticsDir).filter((name) => name.endsWith(".json"))) {
    const diagnostic = JSON.parse(readFileSync(resolve(diagnosticsDir, file), "utf8")) as {
      questions?: Array<Record<string, unknown>>;
    };
    const question = diagnostic.questions?.find((candidate) => candidate.id === id);
    if (question) return question;
  }
  throw new Error("Missing catalog question " + id);
}

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

describe("MatchingAnswer", () => {
  it("renders every short option as a radio chip and serializes a map selection", async () => {
    const onChange = vi.fn();
    await act(async () => {
      root.render(<MatchingAnswer model={mapModel} value={{}} onChange={onChange} />);
    });

    const rows = [...container.querySelectorAll<HTMLElement>(".matching-answer-row")];
    expect(rows).toHaveLength(2);
    expect(container.querySelectorAll('[role="radiogroup"]')).toHaveLength(2);
    expect(rows.every((row) => row.querySelector('[role="radiogroup"]') !== null)).toBe(true);
    expect(container.querySelectorAll('[role="radio"]')).toHaveLength(10);
    expect(rows.every((row) => !row.classList.contains("locked"))).toBe(true);

    await act(async () => {
      rows[0].querySelector<HTMLButtonElement>('button[data-option-key="o2"]')?.click();
    });
    expect(onChange).toHaveBeenLastCalledWith({ i1: "o2" });
  });

  it("shows where a used option is selected and clears only the map row", async () => {
    const onChange = vi.fn();
    await act(async () => {
      root.render(<MatchingAnswer model={mapModel} value={{ i1: "o2" }} onChange={onChange} />);
    });

    const secondRow = container.querySelectorAll<HTMLElement>(".matching-answer-row")[1];
    const reused = secondRow.querySelector<HTMLButtonElement>('button[data-option-key="o2"]');
    expect(reused?.disabled).toBe(true);
    expect(secondRow.textContent).toContain("в строке А");

    await act(async () => {
      container.querySelector<HTMLButtonElement>(".matching-answer-clear")?.click();
    });
    expect(onChange).toHaveBeenLastCalledWith({});
  });

  it("opens a full-text option sheet for long lists and keeps it keyboard-addressable", async () => {
    const onChange = vi.fn();
    await act(async () => {
      root.render(<MatchingAnswer model={longSequenceModel} value="" onChange={onChange} />);
    });

    expect(container.querySelectorAll('[role="radio"]')).toHaveLength(0);
    const trigger = container.querySelector<HTMLButtonElement>(".matching-answer-trigger");
    expect(trigger?.disabled).toBe(false);
    expect(container.querySelectorAll('[role="radiogroup"]')).toHaveLength(0);
    await act(async () => trigger?.click());
    expect(container.querySelector('[role="dialog"]')).not.toBeNull();
    expect(container.querySelectorAll('[role="dialog"] [role="radio"]')).toHaveLength(7);
    expect(container.querySelectorAll('[role="dialog"] [role="radiogroup"]')).toHaveLength(1);
    expect(container.querySelectorAll('[role="radiogroup"]')).toHaveLength(1);

    await act(async () => {
      container.querySelector<HTMLButtonElement>('[role="dialog"] button[data-option-key="7"]')?.click();
    });
    expect(onChange).toHaveBeenLastCalledWith("7");
  });

  it("keeps local holes until the prefix is valid and clear preserves later choices visually", async () => {
    const model: MatchingModel = {
      ...mapModel,
      source: "sequence",
      rows: [
        { key: "А", marker: "А", label: "Первый пункт" },
        { key: "Б", marker: "Б", label: "Второй пункт" },
        { key: "В", marker: "В", label: "Третий пункт" },
      ],
      markers: ["А", "Б", "В"],
      answerLength: 3,
      allowReuse: true,
      options: mapModel.options.map((option) => ({ ...option, key: option.marker })),
    };
    const onChange = vi.fn();
    await act(async () => root.render(<MatchingAnswer model={model} value="" onChange={onChange} />));
    const rows = [...container.querySelectorAll<HTMLElement>(".matching-answer-row")];
    const option = (row: HTMLElement, key: string) => row.querySelector<HTMLButtonElement>(`button[data-option-key="${key}"]`)!;
    await act(async () => option(rows[1], "2").click());
    expect(onChange).toHaveBeenLastCalledWith("");
    await act(async () => option(rows[0], "1").click());
    expect(onChange).toHaveBeenLastCalledWith("12");
    await act(async () => rows[0].querySelector<HTMLButtonElement>(".matching-answer-clear")?.click());
    expect(onChange).toHaveBeenLastCalledWith("");
    expect(option(rows[1], "2").classList.contains("selected")).toBe(true);
    expect(option(rows[0], "1").classList.contains("selected")).toBe(false);
  });

  it("closes the sheet with Escape and restores focus to its trigger", async () => {
    const onChange = vi.fn();
    await act(async () => root.render(<MatchingAnswer model={longSequenceModel} value="" onChange={onChange} />));
    const trigger = container.querySelector<HTMLButtonElement>(".matching-answer-trigger")!;
    trigger.focus();
    await act(async () => trigger.click());
    expect(container.querySelector('[role="dialog"]')).not.toBeNull();
    await act(async () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("disables chips and sheet triggers in feedback mode", async () => {
    const onChange = vi.fn();
    await act(async () => {
      root.render(<MatchingAnswer model={mapModel} value={{}} onChange={onChange} disabled />);
    });
    expect([...container.querySelectorAll<HTMLButtonElement>("button")].every((button) => button.disabled)).toBe(true);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("adapts the real chemistry and physics matching catalog shapes", () => {
    const chemistrySequence = catalogQuestion("sp-chemistry-ege-2022-q5");
    const sequence = parseSequenceMatchingPrompt(
      chemistrySequence.prompt as string,
      chemistrySequence as never,
    );
    expect(sequence).not.toBeNull();
    expect(sequence && matchingModelFromSequence(sequence)).toMatchObject({
      source: "sequence",
      answerLength: 3,
      allowReuse: true,
    });
    expect(sequence?.options).toHaveLength(9);
    expect(sequence && matchingModelFromSequence(sequence).rows).toHaveLength(3);

    const chemistryMatching = matchingModelFromQuestion(
      catalogQuestion("sp-chemistry-ege-2022-q7") as unknown as MatchingQuestion,
    );
    expect(chemistryMatching).toMatchObject({
      source: "matching",
      answerLength: 4,
      allowReuse: true,
    });
    expect(chemistryMatching.options).toHaveLength(5);
    expect(chemistryMatching.rows.map((row) => row.marker)).toEqual(["А", "Б", "В", "Г"]);

    const physicsMatching = matchingModelFromQuestion(
      catalogQuestion("sp-physics-oge-2022-q1") as unknown as MatchingQuestion,
    );
    expect(physicsMatching.options).toHaveLength(5);
    expect(physicsMatching.rows).toHaveLength(3);
    const preview = renderToStaticMarkup(
      <AnswerPreview markers={physicsMatching.markers} selected={["2", "1", "5"]} />,
    );
    expect(preview).toContain(">2<");
    expect(preview).toContain(">1<");
    expect(preview).toContain(">5<");
  });

  it("keeps Cyrillic markers for Russian matching content", () => {
    const russian = catalogQuestion("sp-russian-language-ege-2022-q8");
    const model = matchingModelFromQuestion(russian as unknown as MatchingQuestion);
    expect(model.rows.length).toBeGreaterThan(1);
    expect(model.rows.every((row) => !/[A-Z]/u.test(row.marker))).toBe(true);
  });

  it("keeps every non-English catalog matching marker Cyrillic", () => {
    const violations: string[] = [];
    let englishQuestions = 0;
    for (const file of readdirSync(diagnosticsDir).filter((name) => name.endsWith(".json"))) {
      const diagnostic = JSON.parse(readFileSync(resolve(diagnosticsDir, file), "utf8")) as {
        subject?: string;
        questions?: Array<Record<string, unknown>>;
      };
      for (const question of diagnostic.questions ?? []) {
        const id = String(question.id ?? "");
        const locale = [diagnostic.subject ?? "", id].join(" ").toLocaleLowerCase();
        const isEnglish = locale.includes("english") || locale.includes("англий");
        if (isEnglish) {
          englishQuestions += 1;
          continue;
        }
        if (question.type === "matching") {
          const model = matchingModelFromQuestion(question as unknown as MatchingQuestion);
          for (const row of model.rows) {
            if (/[A-Z]/u.test(row.marker)) violations.push(id + ":" + row.marker);
          }
        }
        if (question.type === "input") {
          const sequence = parseSequenceMatchingPrompt(String(question.prompt ?? ""), question as never);
          if (sequence) {
            const model = matchingModelFromSequence(sequence);
            for (const row of model.rows) {
              if (/[A-Z]/u.test(row.marker)) violations.push(id + ":" + row.marker);
            }
          }
        }
      }
    }
    expect(englishQuestions).toBeGreaterThan(0);
    expect(violations).toEqual([]);
  });
});
