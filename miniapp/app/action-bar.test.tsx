import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ActionBar } from "./action-bar";
import { answerReadiness } from "./answer-readiness";
import { AssessmentHeader } from "./assessment-header";
import { ResultScreen } from "./result-flow";
import { viewport } from "./layout";
import type { Question } from "./types";

const numeric: Question = {
  id: "q1",
  type: "input",
  topic: "Механика",
  title: "Задание",
  prompt: "Найди скорость.",
} as unknown as Question;

const skipModel = (available: boolean) => ({
  label: "Пропустить",
  caption: "Отметим как пропущенное, вернуться можно в любой момент",
  available,
  onSkip: () => undefined,
});

function bar(ready: boolean): string {
  return renderToStaticMarkup(
    <ActionBar
      primaryLabel="Следующее задание"
      primaryDisabled={!ready}
      onPrimary={() => undefined}
      message={ready ? "Готово, можно дальше" : "Введи число"}
      skip={skipModel(!ready)}
    />,
  );
}

describe("action bar", () => {
  it("keeps every row mounted when the answer becomes complete (N-10)", () => {
    const blocked = bar(false);
    const ready = bar(true);
    const rows = (html: string) => [
      (html.match(/question-next/g) ?? []).length,
      (html.match(/question-announcement/g) ?? []).length,
      (html.match(/question-skip"|question-skip is-reserved"/g) ?? []).length,
    ];

    expect(rows(blocked)).toEqual(rows(ready));
    expect(blocked).toContain('class="question-skip"');
    expect(ready).toContain('class="question-skip is-reserved"');
    expect(ready).toContain('disabled=""');
  });

  it("orders the bar as button, then reason, then skip (N-29)", () => {
    const html = bar(false);
    expect(html.indexOf("question-next")).toBeLessThan(html.indexOf("question-announcement"));
    expect(html.indexOf("question-announcement")).toBeLessThan(html.indexOf("question-skip"));
    expect(html).toContain("Отметим как пропущенное, вернуться можно в любой момент");
  });

  it("keeps one live region that also announces readiness (N-30)", () => {
    const blocked = bar(false);
    const ready = bar(true);
    expect((blocked.match(/role="status"/g) ?? []).length).toBe(1);
    expect((ready.match(/role="status"/g) ?? []).length).toBe(1);
    expect(blocked).toContain("Введи число");
    expect(ready).toContain("Готово, можно дальше");
  });

  it("shows a submit error next to the action as an assertive message (N-32)", () => {
    const html = renderToStaticMarkup(
      <ActionBar
        primaryLabel="Получить результат"
        primaryDisabled={false}
        onPrimary={() => undefined}
        message="Ответ на задание 3 не принят. Проверь его и отправь результат снова."
        messageRole="alert"
        skip={skipModel(true)}
      />,
    );
    expect(html).toContain('role="alert"');
    expect(html).toContain("Ответ на задание 3 не принят");
  });
});

describe("answer readiness module", () => {
  it("reports the blocking reason so the trainer can reuse the same rule", () => {
    expect(answerReadiness(numeric, undefined)).toEqual({ isAnswered: false, reason: "Введи число" });
    expect(answerReadiness(numeric, "0,25")).toEqual({ isAnswered: true, reason: "" });
  });

  it("treats a half-filled answer as incomplete, which is what keeps a skip sticky (N-29)", () => {
    const multiple = {
      id: "q2", type: "multiple", topic: "Механика", title: "Задание",
      prompt: "Выбери два", selection_limit: 2,
      options: [{ id: "a", label: "А" }, { id: "b", label: "Б" }, { id: "c", label: "В" }],
    } as unknown as Question;

    expect(answerReadiness(multiple, ["a"]).isAnswered).toBe(false);
    expect(answerReadiness(multiple, ["a", "b"]).isAnswered).toBe(true);
  });
});

describe("progress rail", () => {
  it("turns visited nodes into jump buttons and labels the skipped one (N-09)", () => {
    const html = renderToStaticMarkup(
      <AssessmentHeader model={{
        topic: "Задание 3 из 4",
        current: 3,
        total: 4,
        backDisabled: false,
        progressVariant: "dots",
        percent: 75,
        skippedIndexes: [1],
        onJumpToQuestion: () => undefined,
        onBack: () => undefined,
        onExit: () => undefined,
      }} />,
    );
    expect(html).toContain('aria-label="Задание 2, пропущено"');
    expect(html).toContain("question-progress-jump");
    // The unvisited node stays out of the tab order.
    expect(html).toMatch(/aria-label="Задание 4"[^>]*disabled=""|disabled=""[^>]*aria-label="Задание 4"/);
  });
});

describe("result accuracy", () => {
  it("divides by answered questions and says so when there are skips (N-09)", () => {
    const html = renderToStaticMarkup(<ResultScreen
      diagnostic={{ exam: "ОГЭ", subject: "Физика" } as never}
      result={{
        diagnostic_id: "physics", mode: "full", question_count: 8, correct_count: 1,
        skipped_count: 7, score: 1, max_score: 8, score_unit: "балл",
        strong_topics: [], growth_topics: [], per_question: [],
      }}
      onReview={() => undefined}
      onForecast={() => undefined}
    />);

    expect(html).toContain("100%");
    expect(html).not.toContain("13%");
    expect(html).toContain("от 1 отвеченных, пропуски не считаем");
    expect(html).toContain("1 верно · 0 неверно · 7 пропущено");
  });
});

describe("document viewport", () => {
  it("requests viewport-fit cover so safe-area insets resolve (N-31)", () => {
    expect(viewport.viewportFit).toBe("cover");
  });
});
