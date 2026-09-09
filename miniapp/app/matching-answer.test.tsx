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
  matchingReadiness,
  type MatchingModel,
} from "./matching-answer";
import { parseSequenceMatchingPrompt } from "./sequence-matching";
import type { MatchingQuestion } from "./types";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const drawnQuestion = {
  id: "q-drawn",
  type: "matching",
  prompt: "Установите соответствие.",
  items: [
    { id: "i1", label: "", asset: "assets/questions/drawn-1.png" },
    { id: "i2", label: "Б) Написанный пункт" },
  ],
  options: [
    { id: "o1", label: "1) Первый" },
    { id: "o2", label: "", asset: "assets/questions/drawn-2.png" },
  ],
} as unknown as MatchingQuestion;


describe("a drawn matching cell", () => {
  it("names a position by its letter when the letter is inside the figure", () => {
    const model = matchingModelFromQuestion(drawnQuestion);

    expect(model.rows.map((row) => row.marker)).toEqual(["А", "Б"]);
    expect(model.options.map((option) => option.marker)).toEqual(["1", "2"]);
  });

  it("carries the figure into the model instead of an empty label", () => {
    const model = matchingModelFromQuestion(drawnQuestion);

    expect(model.rows[0]).toMatchObject({ label: "", asset: "assets/questions/drawn-1.png" });
    expect(model.rows[1].asset).toBeUndefined();
    expect(model.options[1]).toMatchObject({ label: "", asset: "assets/questions/drawn-2.png" });
  });

  it("shows the figure in the position and in the option list", () => {
    const model = matchingModelFromQuestion(drawnQuestion);

    const html = renderToStaticMarkup(
      <MatchingAnswer model={model} value={{}} onChange={() => undefined} />,
    );

    expect(html).toContain('src="/assets/questions/drawn-1.png"');
    expect(html).toContain('src="/assets/questions/drawn-2.png"');
    expect(html).toContain('class="matching-answer-cell-figure"');
  });

  it("refuses a figure path that escapes the asset tree", () => {
    const escaping = {
      ...drawnQuestion,
      items: [
        { id: "i1", label: "", asset: "../../secret.png" },
        { id: "i2", label: "Б) Написанный пункт" },
      ],
    } as unknown as MatchingQuestion;

    const html = renderToStaticMarkup(
      <MatchingAnswer model={matchingModelFromQuestion(escaping)} value={{}} onChange={() => undefined} />,
    );

    expect(html).not.toContain("secret.png");
  });
});


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

  it("uses the accessible option sheet for the real chemistry q9 density", async () => {
    const chemistryQuestion = catalogQuestion("sp-chemistry-oge-2022-q9");
    const model = matchingModelFromQuestion(chemistryQuestion as unknown as MatchingQuestion);
    const onChange = vi.fn();
    await act(async () => {
      root.render(<MatchingAnswer model={model} value={{}} subject="Химия" onChange={onChange} />);
    });

    expect(model.options).toHaveLength(5);
    expect(container.querySelectorAll(".matching-answer-options")).toHaveLength(0);
    const triggers = [...container.querySelectorAll<HTMLButtonElement>(".matching-answer-trigger")];
    expect(triggers).toHaveLength(model.rows.length);
    await act(async () => triggers[0].click());
    const sheetOptions = [...container.querySelectorAll<HTMLButtonElement>('[role="dialog"] [role="radio"]')];
    expect(sheetOptions).toHaveLength(model.options.length);
    expect(sheetOptions.every((option) => option.textContent?.trim())).toBe(true);
    await act(async () => sheetOptions[4].click());
    expect(onChange).toHaveBeenLastCalledWith({ i1: "o5" });

    await act(async () => {
      root.render(<MatchingAnswer model={model} value={{ i1: "o5" }} subject="Химия" onChange={onChange} />);
    });
    const selectedTrigger = container.querySelector<HTMLButtonElement>('[data-state="filled"] .matching-answer-trigger');
    expect(selectedTrigger?.textContent).toContain("5");
    // The trigger prints the formula the way the list above does, not the raw
    // «FeCl_(2)» the catalog stores.
    expect(selectedTrigger?.textContent).toContain("FeCl");
    expect(selectedTrigger?.textContent).not.toContain("_(");
    expect(selectedTrigger?.querySelectorAll("sub").length).toBeGreaterThan(0);
  });

  it("keeps sequence activation sequential and clears the whole sequence", async () => {
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
    const cells = [...container.querySelectorAll<HTMLButtonElement>(".sequence-answer-cell")];
    const option = (key: string) => container.querySelector<HTMLButtonElement>(`button[data-option-key="${key}"]`)!;
    expect(cells[0].getAttribute("aria-label")).toContain("Первый пункт");
    expect(cells[1].disabled).toBe(true);
    expect(cells[2].disabled).toBe(true);
    await act(async () => cells[0].click());
    await act(async () => option("1").click());
    expect(onChange).toHaveBeenLastCalledWith("1");
    const updatedCells = [...container.querySelectorAll<HTMLButtonElement>(".sequence-answer-cell")];
    expect(updatedCells[2].disabled).toBe(true);
    await act(async () => updatedCells[1].click());
    await act(async () => option("2").click());
    expect(onChange).toHaveBeenLastCalledWith("12");
    expect(updatedCells[1].textContent).toContain("2");
    await act(async () => container.querySelector<HTMLButtonElement>(".sequence-answer-clear")?.click());
    expect(onChange).toHaveBeenLastCalledWith("");
    expect(cells[1].textContent).toContain("—");
    expect(cells[0].textContent).toContain("—");
  });

  it("keeps Arrow selection on the active row after a controlled rerender", async () => {
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
      allowReuse: false,
      options: mapModel.options.slice(0, 3).map((option) => ({ ...option, key: option.marker })),
    };
    let value = "";
    const onChange = vi.fn((next: unknown) => { value = String(next); });
    await act(async () => root.render(<MatchingAnswer model={model} value={value} onChange={onChange} />));
    let options = [...container.querySelectorAll<HTMLButtonElement>('.sequence-answer-palette [role="radio"]')];
    options[0].focus();
    await act(async () => options[0].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true })));
    expect(onChange).toHaveBeenLastCalledWith("2");
    await act(async () => root.render(<MatchingAnswer model={model} value={value} onChange={onChange} />));
    options = [...container.querySelectorAll<HTMLButtonElement>('.sequence-answer-palette [role="radio"]')];
    expect(options[1].disabled).toBe(false);
    expect(options[1].getAttribute("aria-checked")).toBe("true");
    options[1].focus();
    await act(async () => options[1].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true })));
    expect(onChange).toHaveBeenLastCalledWith("3");
    expect(document.activeElement).toBe(options[2]);
  });

  it("keeps a long-option sheet open while Arrow selects the next radio", async () => {
    const onChange = vi.fn();
    await act(async () => root.render(<MatchingAnswer model={longSequenceModel} value="" onChange={onChange} />));
    const trigger = container.querySelector<HTMLButtonElement>(".sequence-answer-sheet-trigger")!;
    await act(async () => trigger.click());
    const options = [...container.querySelectorAll<HTMLButtonElement>('[role="dialog"] [role="radio"]')];
    options[0].focus();
    await act(async () => options[0].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true })));
    expect(onChange).toHaveBeenLastCalledWith("2");
    expect(container.querySelector('[role="dialog"]')).not.toBeNull();
    expect(document.activeElement).toBe(options[1]);
  });

  it("wraps Shift+Tab from the controlled Arrow-selected radio in a 9-option sheet", async () => {
    const model: MatchingModel = {
      ...longSequenceModel,
      options: Array.from({ length: 9 }, (_, index) => ({
        key: String(index + 1),
        marker: String(index + 1),
        label: `Вариант ${index + 1}`,
      })),
    };
    let value = "";
    const onChange = vi.fn((next: unknown) => { value = String(next); });
    await act(async () => root.render(<MatchingAnswer model={model} value={value} onChange={onChange} />));
    const trigger = container.querySelector<HTMLButtonElement>(".sequence-answer-sheet-trigger")!;
    await act(async () => trigger.click());
    let options = [...container.querySelectorAll<HTMLButtonElement>('[role="dialog"] [role="radio"]')];
    options[0].focus();
    await act(async () => options[0].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true })));
    expect(onChange).toHaveBeenLastCalledWith("2");
    await act(async () => root.render(<MatchingAnswer model={model} value={value} onChange={onChange} />));
    options = [...container.querySelectorAll<HTMLButtonElement>('[role="dialog"] [role="radio"]')];
    expect(options[0].tabIndex).toBe(-1);
    expect(options[1].tabIndex).toBe(0);
    options[1].focus();
    const event = new KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true, cancelable: true });
    await act(async () => options[1].dispatchEvent(event));
    expect(event.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(container.querySelector<HTMLButtonElement>('[role="dialog"] .secondary-button'));
  });

  it("uses the same actual radio tab stop when wrapping a matching sheet", async () => {
    const model: MatchingModel = {
      ...mapModel,
      options: Array.from({ length: 8 }, (_, index) => ({
        key: `o${index + 1}`,
        marker: String(index + 1),
        label: `Вариант ${index + 1}`,
      })),
    };
    await act(async () => root.render(<MatchingAnswer model={model} value={{}} onChange={vi.fn()} />));
    await act(async () => container.querySelector<HTMLButtonElement>(".matching-answer-trigger")?.click());
    const options = [...container.querySelectorAll<HTMLButtonElement>('[role="dialog"] [role="radio"]')];
    options[0].focus();
    const event = new KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true, cancelable: true });
    await act(async () => document.dispatchEvent(event));
    expect(event.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(container.querySelector<HTMLButtonElement>('[role="dialog"] .secondary-button'));
  });

  it("closes the sheet with Escape and restores focus to its trigger", async () => {
    const onChange = vi.fn();
    await act(async () => root.render(<MatchingAnswer model={longSequenceModel} value="" onChange={onChange} />));
    const trigger = container.querySelector<HTMLButtonElement>(".sequence-answer-sheet-trigger")!;
    trigger.focus();
    expect(trigger.getAttribute("aria-haspopup")).toBe("dialog");
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    await act(async () => trigger.click());
    expect(container.querySelector('[role="dialog"]')).not.toBeNull();
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    const dialog = container.querySelector<HTMLElement>('[role="dialog"]')!;
    const dialogControls = [...dialog.querySelectorAll<HTMLButtonElement>("button")];
    dialogControls.at(-1)?.focus();
    await act(async () => dialogControls.at(-1)?.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true })));
    expect(document.activeElement).toBe(dialogControls[0]);
    dialogControls[0].focus();
    await act(async () => dialogControls[0].dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true })));
    expect(document.activeElement).toBe(dialogControls.at(-1));
    await act(async () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("switches between sequence and map renderers without changing hook order", async () => {
    const sequenceModel: MatchingModel = {
      ...mapModel,
      source: "sequence",
      options: mapModel.options.map((option) => ({ ...option, key: option.marker })),
    };
    await act(async () => root.render(<MatchingAnswer model={sequenceModel} value="" onChange={vi.fn()} />));
    expect(container.querySelector(".matching-answer-sequence")).not.toBeNull();
    await act(async () => root.render(<MatchingAnswer model={mapModel} value={{}} onChange={vi.fn()} />));
    expect(container.querySelector(".matching-answer-matching")).not.toBeNull();
    await act(async () => root.render(<MatchingAnswer model={sequenceModel} value="" onChange={vi.fn()} />));
    expect(container.querySelector(".matching-answer-sequence")).not.toBeNull();
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
    expect(preview).not.toContain('aria-live');
  });

  it("keeps real sequence option labels visible and tappable", async () => {
    const chemistry = catalogQuestion("sp-chemistry-oge-2022-q3");
    const sequence = parseSequenceMatchingPrompt(chemistry.prompt as string, chemistry as never)!;
    const onChange = vi.fn();
    await act(async () => root.render(
      <MatchingAnswer model={matchingModelFromSequence(sequence)} value="" onChange={onChange} />,
    ));
    expect(container.textContent).toContain("Калий");
    const potassium = container.querySelector<HTMLButtonElement>('button[data-option-key="1"]');
    expect(potassium?.textContent).toContain("Калий");
    expect(container.querySelector<HTMLButtonElement>('[data-sequence-cell="1"]')?.getAttribute("aria-label")).toContain("Позиция 1");
    await act(async () => potassium?.click());
    expect(onChange).toHaveBeenLastCalledWith("1");

    const physics = catalogQuestion("sp-physics-oge-2022-q4");
    const physicsSequence = parseSequenceMatchingPrompt(physics.prompt as string, physics as never)!;
    await act(async () => root.render(
      <MatchingAnswer model={matchingModelFromSequence(physicsSequence)} value="" onChange={vi.fn()} />,
    ));
    const electric = container.querySelector<HTMLButtonElement>('button[data-option-key="6"]');
    expect(electric?.textContent).toContain("Электрический");
    expect(electric?.getAttribute("aria-label")).toContain("Электрический");
  });

  it("keeps Cyrillic markers for Russian matching content", () => {
    const russian = catalogQuestion("sp-russian-language-ege-2022-q8");
    const model = matchingModelFromQuestion(russian as unknown as MatchingQuestion);
    expect(model.rows.length).toBeGreaterThan(1);
    expect(model.rows.every((row) => !/[A-Z]/u.test(row.marker))).toBe(true);
  });

  it("labels the answer summary by position when a cell is named by a heading", () => {
    const html = renderToStaticMarkup(
      <AnswerPreview
        markers={["Скорость бруска", "Полная механическая энергия пружины"]}
        selected={["2", ""]}
      />,
    );

    // The chip is 31px wide, so a heading would overrun its neighbour.
    expect(html).not.toContain("Полная механическая энергия пружины");
    expect(html).toContain("<small>1</small>");
    expect(html).toContain("<small>2</small>");
  });

  it("keeps a short marker in the answer summary", () => {
    const html = renderToStaticMarkup(
      <AnswerPreview markers={["А", "Б"]} selected={["1", "2"]} />,
    );

    expect(html).toContain("<small>А</small>");
    expect(html).toContain("<small>Б</small>");
  });

  it("reads a Latin B as the Cyrillic В it looks like", () => {
    // Б has no Latin lookalike. Reading B as Б gave the chemistry mapping two
    // positions called Б and left В missing.
    const question = {
      id: "q-lookalike",
      type: "matching",
      prompt: "Установите соответствие.",
      items: [
        { id: "i1", label: "А) Первый" },
        { id: "i2", label: "Б) Второй" },
        { id: "i3", label: "B) Третий" },
      ],
      options: [{ id: "o1", label: "1) Один" }, { id: "o2", label: "2) Два" }],
    } as unknown as MatchingQuestion;

    const model = matchingModelFromQuestion(question, "Химия");

    expect(model.rows.map((row) => row.marker)).toEqual(["А", "Б", "В"]);
  });

  it("gives the real chemistry mapping four separate positions", () => {
    const file = readFileSync(resolve(diagnosticsDir, "ege-chemistry-1208.json"), "utf8");
    const question = (JSON.parse(file) as { questions: Array<{ id: string }> }).questions
      .find((candidate) => candidate.id === "sp-chemistry-ege-2022-q8");

    const model = matchingModelFromQuestion(question as unknown as MatchingQuestion, "Химия");

    expect(model.rows.map((row) => row.marker)).toEqual(["А", "Б", "В", "Г"]);
  });

  it("keeps every non-English catalog matching marker Cyrillic", () => {
    const violations: string[] = [];
    // A marker that is one letter must be the Cyrillic letter of the КИМ, not
    // its Latin lookalike. A marker named by a table heading is free text and
    // may hold Latin inside a formula or a unit, such as NaCl.
    const isLatinLetterMarker = (marker: string) => /^[A-Z][).]?$/u.test(marker.trim());
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
            if (isLatinLetterMarker(row.marker)) violations.push(id + ":" + row.marker);
          }
        }
        if (question.type === "input") {
          const sequence = parseSequenceMatchingPrompt(String(question.prompt ?? ""), question as never);
          if (sequence) {
            const model = matchingModelFromSequence(sequence);
            for (const row of model.rows) {
              if (isLatinLetterMarker(row.marker)) violations.push(id + ":" + row.marker);
            }
          }
        }
      }
    }
    expect(englishQuestions).toBeGreaterThan(0);
    expect(violations).toEqual([]);
  });
});

describe("one marker source for the row and the hint", () => {
  // N-07: the hint under the button used to derive its own markers, so a row
  // drawn «А» was asked for as «1», and a row drawn «В» as the Latin «B».
  const rowMarkerFromOwnRegex = (label: string, index: number) =>
    /^\s*([А-ЯЁA-Z0-9]+)(?:[).]|\s|$)/u.exec(label)?.[1] ?? String(index + 1);

  it("names an unanswered row exactly as the editor drew it", () => {
    const question = catalogQuestion("sp-chemistry-ege-2022-q14") as unknown as MatchingQuestion;
    const model = matchingModelFromQuestion(question);
    const readiness = matchingReadiness(model, {});

    expect(readiness.isAnswered).toBe(false);
    expect(readiness.reason).toBe("Осталось заполнить: " + model.rows.map((row) => row.marker).join(", "));
    expect(readiness.reason).toContain("А");
    expect(readiness.reason).not.toMatch(/[A-Z]/u);
  });

  it("agrees with the drawn marker on every catalog matching row", () => {
    const divergences: string[] = [];
    for (const file of readdirSync(diagnosticsDir).filter((name) => name.endsWith(".json"))) {
      const diagnostic = JSON.parse(readFileSync(resolve(diagnosticsDir, file), "utf8")) as {
        subject?: string;
        questions?: Array<Record<string, unknown>>;
      };
      for (const question of diagnostic.questions ?? []) {
        if (question.type !== "matching") continue;
        const model = matchingModelFromQuestion(question as unknown as MatchingQuestion, diagnostic.subject);
        const asked = matchingReadiness(model, {}).reason.replace("Осталось заполнить: ", "").split(", ");
        model.rows.forEach((row, index) => {
          if (asked[index] !== row.marker) divergences.push(`${String(question.id)}: drawn ${row.marker}, asked ${asked[index]}`);
        });
      }
    }
    expect(divergences).toEqual([]);
  });

  it("reproduces the old divergence, so the sweep above is not vacuous", () => {
    const question = catalogQuestion("sp-chemistry-ege-2022-q8") as unknown as MatchingQuestion;
    const model = matchingModelFromQuestion(question);
    const own = question.items.map((item, index) => rowMarkerFromOwnRegex(item.label, index));

    expect(model.rows.map((row) => row.marker)).not.toEqual(own);
    expect(own).toContain("B");
  });
});

describe("a repeated option", () => {
  const fourRows = {
    id: "q-repeat",
    type: "matching",
    prompt: "Установите соответствие.",
    items: [
      { id: "i1", label: "А) Первый" },
      { id: "i2", label: "Б) Второй" },
      { id: "i3", label: "В) Третий" },
    ],
    options: [
      { id: "o1", label: "1) Один" },
      { id: "o2", label: "2) Два" },
      { id: "o3", label: "3) Три" },
    ],
  } as unknown as MatchingQuestion;

  it("blocks the hand-off instead of sending three identical positions", () => {
    // F-22: the repeat was marked under the row, and the answer went anyway.
    const model = matchingModelFromQuestion(fourRows);
    const readiness = matchingReadiness(model, { i1: "o1", i2: "o1", i3: "o3" });

    expect(readiness.isAnswered).toBe(false);
    expect(readiness.reason).toBe("Вариант 1 выбран дважды");
  });

  it("stays silent when the КИМ has fewer options than positions", () => {
    const twoOptions = {
      ...fourRows,
      options: [{ id: "o1", label: "1) Один" }, { id: "o2", label: "2) Два" }],
    } as unknown as MatchingQuestion;
    const model = matchingModelFromQuestion(twoOptions);

    expect(matchingReadiness(model, { i1: "o1", i2: "o1", i3: "o2" })).toEqual({ isAnswered: true, reason: "" });
  });

  it("does not warn on a row when a repeat is the only way to answer", async () => {
    const twoOptions = {
      ...fourRows,
      options: [{ id: "o1", label: "1) Один" }, { id: "o2", label: "2) Два" }],
    } as unknown as MatchingQuestion;
    await act(async () => {
      root.render(
        <MatchingAnswer
          model={matchingModelFromQuestion(twoOptions)}
          value={{ i1: "o1", i2: "o1", i3: "o2" }}
          onChange={() => undefined}
        />,
      );
    });

    expect(container.querySelectorAll(".matching-answer-duplicate")).toHaveLength(0);
  });
});

describe("a long option", () => {
  const withOptions = (labels: string[]) => ({
    id: "q-long",
    type: "matching",
    prompt: "Установите соответствие.",
    items: [{ id: "i1", label: "А) Первый" }, { id: "i2", label: "Б) Второй" }, { id: "i3", label: "В) Третий" }],
    options: labels.map((label, index) => ({ id: "o" + (index + 1), label: index + 1 + ") " + label })),
  } as unknown as MatchingQuestion);

  const render = async (question: MatchingQuestion) => {
    await act(async () => {
      root.render(<MatchingAnswer model={matchingModelFromQuestion(question)} value={{}} onChange={() => undefined} />);
    });
  };

  it("keeps short options as readable chips in the row", async () => {
    await render(withOptions(["Соль", "Оксид", "Кислота"]));

    const chips = [...container.querySelectorAll(".matching-answer-row .matching-answer-option")];
    expect(chips).toHaveLength(9);
    expect(chips.every((chip) => chip.classList.contains("compact"))).toBe(false);
    expect(chips[0].textContent).toContain("Соль");
    expect(container.querySelectorAll(".matching-answer-trigger")).toHaveLength(0);
  });

  it("puts the number in the chip when a formula cannot fit, and keeps the formula above", async () => {
    // N-36: «Sr(OH)₂, H₂SO₄, (CH₃COO)₂Pb» wrapped into a tower inside a 100px chip.
    const formula = "Sr(OH)2, H2SO4, (CH3COO)2Pb";
    await render(withOptions([formula, "Соль", "Оксид", "Кислота"]));

    const chips = [...container.querySelectorAll(".matching-answer-row .matching-answer-option")];
    expect(chips).toHaveLength(12);
    expect(chips.every((chip) => chip.classList.contains("compact"))).toBe(true);
    expect(chips[0].textContent).toBe("1");
    expect(chips[0].getAttribute("aria-label")).toContain(formula);

    const reference = [...container.querySelectorAll(".matching-answer-option-reference")];
    expect(reference).toHaveLength(4);
    expect(reference[0].textContent).toContain(formula);
  });

  it("keeps the crowded six-option row out of the tower shape", async () => {
    await render(withOptions(["Кислотный оксид", "Основный оксид", "Соль", "Кислота", "Основание", "Амфотерный"]));

    const chips = [...container.querySelectorAll(".matching-answer-row .matching-answer-option")];
    const triggers = container.querySelectorAll(".matching-answer-trigger");
    expect(chips.every((chip) => chip.classList.contains("compact")) || triggers.length > 0).toBe(true);
    for (const chip of chips) expect(chip.textContent!.length).toBeLessThanOrEqual(2);
  });

  it("still opens a sheet for an option no chip could ever hold", async () => {
    const essay = "Автор противопоставляет героя обществу и показывает его одиночество среди людей";
    await render(withOptions([essay, "Соль", "Оксид", "Кислота"]));

    const triggers = [...container.querySelectorAll<HTMLButtonElement>(".matching-answer-trigger")];
    expect(triggers).toHaveLength(3);
    await act(async () => { triggers[0].click(); });
    const sheetOptions = [...container.querySelectorAll('[role="dialog"] [role="radio"]')];
    expect(sheetOptions).toHaveLength(4);
    expect(sheetOptions[0].textContent).toContain(essay);
  });
});
