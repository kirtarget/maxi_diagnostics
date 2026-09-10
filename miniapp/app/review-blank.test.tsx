// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ReviewScreen } from "./result-flow";
import type { ReviewItem } from "./types";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const physics = JSON.parse(
  readFileSync(join(process.cwd(), "..", "school", "diagnostics", "oge-physics-197.json"), "utf8"),
) as { questions: Array<{ id: string; type: string; topic: string; title: string; prompt: string }> };

/** ОГЭ physics q01 as the server hands it back after answering 1/1/1. */
function physicsQ1(): ReviewItem {
  const question = physics.questions[0];
  return {
    question_id: question.id,
    number: 1,
    type: "matching",
    topic: question.topic,
    title: question.title,
    prompt: question.prompt,
    is_correct: false,
    status: "incorrect",
    user_answer: "А) Теплопроводность: Процесс, проходящий при постоянном объеме и массе газа.",
    expected_answer: "А) Теплопроводность: Явление передачи тепла между телами при непосредственном контакте.",
    guidance: "Теплопроводность — явление передачи тепла (2). Изохорический процесс — процесс при постоянном объёме (1). Адиабатический процесс — процесс без теплопередачи (5).",
    guidance_kind: "individual",
    answer_preview: {
      kind: "matching",
      markers: ["А", "Б", "В"],
      user: ["1", "1", "1"],
      expected: ["2", "1", "5"],
      option_labels: { "1": "Процесс при постоянном объёме", "2": "Передача тепла при контакте", "5": "Процесс без теплопередачи" },
    },
  };
}

const correctQ2: ReviewItem = {
  question_id: "sp-physics-oge-2022-q2",
  number: 2,
  type: "single",
  topic: "Физические законы и формулы",
  title: "Задание 2",
  prompt: "Условие второго задания.",
  is_correct: true,
  status: "correct",
  user_answer: "2",
  expected_answer: "2",
  guidance: "Проверено.",
  guidance_kind: "fallback",
};

const noop = () => undefined;

describe("review answer blank", () => {
  it("prints the ОГЭ physics q01 answer and the key as blank rows and marks the differing positions", () => {
    const html = renderToStaticMarkup(<ReviewScreen
      items={[physicsQ1()]} index={0} subject="Физика"
      onBack={noop} onNext={noop} onForecast={noop}
    />);

    const blank = html.slice(html.indexOf("answer-review-blank"), html.indexOf("review-answer-preview"));
    const rows = blank.split("matching-answer-preview");
    // row 1 is the student's answer, row 2 the key
    expect(rows[1]).toContain("Твой ответ");
    expect(rows[1].match(/>(\d)<small>/gu)?.map((cell) => cell[1])).toEqual(["1", "1", "1"]);
    expect(rows[2]).toContain("Правильный");
    expect(rows[2].match(/>(\d)<small>/gu)?.map((cell) => cell[1])).toEqual(["2", "1", "5"]);

    // А and В differ, Б matches: only the two differing positions carry the mark
    expect((rows[1].match(/is-mismatch/gu) ?? []).length).toBe(2);
    expect(rows[1]).toContain('class="is-mismatch">1<small>А</small>');
    expect(rows[1]).toContain('class="is-mismatch">1<small>В</small>');
    expect(rows[1]).toContain("<span>1<small>Б</small>");
    expect(rows[2]).not.toContain("is-mismatch");
  });

  it("draws the condition with the shared question body instead of a review-only copy", () => {
    const html = renderToStaticMarkup(<ReviewScreen
      items={[physicsQ1()]} index={0} subject="Физика"
      onBack={noop} onNext={noop} onForecast={noop}
    />);

    expect(html).toContain('class="question-copy"');
    expect(html).toContain('id="review-sp-physics-oge-2022-q1-reference"');
    expect(html).not.toContain("review-prompt");
  });

  it("lists the explanation instead of gluing its sentences together", () => {
    const html = renderToStaticMarkup(<ReviewScreen
      items={[physicsQ1()]} index={0} subject="Физика"
      onBack={noop} onNext={noop} onForecast={noop}
    />);

    expect((html.match(/<li>/gu) ?? []).length).toBe(3);
    expect(html).toContain('class="guidance-points"');
  });
});

describe("review css", () => {
  const css = readFileSync(join(process.cwd(), "app", "globals.css"), "utf8");

  it("keeps a two-digit task number on one line in the mistake list", () => {
    expect(css).toMatch(/\.review-mistake-list-items strong,[^{]*\{[^}]*white-space:\s*nowrap;/u);
    expect(css).toMatch(/\.review-mistake-list-items strong,[^{]*\{[^}]*min-width:\s*2ch;/u);
  });

  it("gives a long answer the full width instead of two 150px columns", () => {
    expect(css).toMatch(/\.answer-review\s*\{[\s\S]*?flex-direction:\s*column;/u);
    expect(css).toMatch(/@media \(min-width:\s*480px\)\s*\{\s*\.answer-review\s*\{\s*flex-direction:\s*row;/u);
  });

  it("paints the topic chip neutrally, so it reads as a label and not as a score", () => {
    const chip = css.slice(css.indexOf(".review-heading > span:not("));
    const rule = chip.slice(0, chip.indexOf("}"));
    expect(rule).not.toContain("--accent-tint");
    expect(rule).not.toContain("--success");
    expect(rule).toMatch(/background:\s*color-mix\(in srgb, var\(--brand-ink\)/u);
  });
});

describe("review filter", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  function render(mode: "list" | "detail") {
    act(() => root.render(<ReviewScreen
      items={[physicsQ1(), correctQ2]} index={0} mode={mode} subject="Физика"
      onBack={noop} onNext={noop} onForecast={noop} onSelectQuestion={noop} onHome={noop}
    />));
  }

  it("lists mistakes only until the student asks for every task", () => {
    render("list");
    expect(container.querySelector("#review-list-title")?.textContent).toBe("Где ошибся (1 ошибка)");
    expect(container.querySelectorAll(".review-mistake-list-items button")).toHaveLength(1);

    const all = [...container.querySelectorAll<HTMLButtonElement>(".review-filter button")]
      .find((button) => button.textContent === "Все");
    expect(all).not.toBeUndefined();
    act(() => all?.click());

    expect(container.querySelector("#review-list-title")?.textContent).toBe("Проверенные задания (2)");
    const listed = [...container.querySelectorAll(".review-mistake-list-items button")];
    expect(listed).toHaveLength(2);
    expect(listed[1].getAttribute("aria-label")).toContain("верно");
  });

  it("counts the mistakes in the detail header and leads out of the review from any card", () => {
    render("detail");
    expect(container.querySelector(".review-topline span")?.textContent).toBe("Разбор ошибок · 1 из 1");
    const exits = [...container.querySelectorAll(".review-direct-actions .text-back")]
      .map((button) => button.textContent);
    expect(exits).toEqual(["К списку", "К плану", "На главную"]);
  });
});
