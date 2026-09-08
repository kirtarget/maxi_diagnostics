import { describe, expect, it } from "vitest";

import { forecastKind, forecastTrajectory, personalRoute, resultGameSummary, topicRecommendation } from "./result-flow-model";

describe("result flow model", () => {
  it("uses the current score plus at most two persisted forecast points", () => {
    expect(forecastTrajectory({
      score: 40,
      forecast: {
        points: [
          { id: "stage", label: "Первый этап", value: 57 },
          { id: "course", label: "Годовой курс", value: 74 },
          { id: "extra", label: "Лишняя точка", value: 88 },
        ],
      },
    } as never)).toEqual([
      { id: "current", label: "Сейчас", value: 40 },
      { id: "stage", label: "Первый этап", value: 57 },
      { id: "course", label: "Годовой курс", value: 74 },
    ]);
  });

  it("uses numeric legacy forecast records without creating additional points", () => {
    expect(forecastTrajectory({
      score: 40,
      forecast: { "Первый этап": 57, "Годовой курс": 74, invalid: Number.NaN },
    } as never)).toEqual([
      { id: "current", label: "Сейчас", value: 40 },
      { id: "Первый этап", label: "Первый этап", value: 57 },
      { id: "Годовой курс", label: "Годовой курс", value: 74 },
    ]);
  });

  it("never invents a forecast point when offers are absent", () => {
    expect(forecastTrajectory({ score: 40 } as never)).toEqual([
      { id: "current", label: "Сейчас", value: 40 },
    ]);
  });

  it("starts the trajectory at the estimate when the forecast speaks that unit", () => {
    expect(forecastTrajectory({
      score: 40,
      estimate: { kind: "test_score", value: 53, sample_size: 10 },
      forecast: { kind: "test_score", points: [{ id: "stage", label: "Первый этап", value: 71 }] },
    } as never)).toEqual([
      { id: "current", label: "Сейчас", value: 53 },
      { id: "stage", label: "Первый этап", value: 71 },
    ]);
  });

  it("keeps the percent as the starting point when the forecast has no scale", () => {
    expect(forecastTrajectory({
      score: 40,
      estimate: { kind: "test_score", value: 53, sample_size: 10 },
      forecast: { points: [{ id: "stage", label: "Первый этап", value: 60 }] },
    } as never)[0]).toEqual({ id: "current", label: "Сейчас", value: 40 });
  });

  it("reads the forecast unit from the persisted forecast", () => {
    expect(forecastKind({ score: 40 } as never)).toBe("accuracy_percent");
    expect(forecastKind({ score: 40, forecast: { kind: "grade", points: [] } } as never)).toBe("grade");
    expect(forecastKind({ score: 40, forecast: { kind: "nonsense", points: [] } } as never)).toBe("accuracy_percent");
  });

  it("builds a bounded route from persisted growth topics", () => {
    expect(personalRoute(["Алгоритмы", "Информация", "Лишняя тема"]).map((item) => item.title)).toEqual([
      "Разобрать «Алгоритмы»",
      "Повторить «Информация»",
      "Проверить рост",
    ]);
  });

  it("never turns an ordinal or question title into a route step", () => {
    expect(personalRoute(["Задание 1", { topic: "Неорганическая химия", question_count: 2 }, { topic: "Окислительно-восстановительные реакции", question_count: 2 }]).map((item) => item.title)).toEqual([
      "Разобрать «Неорганическая химия»",
      "Повторить «Окислительно-восстановительные реакции»",
      "Проверить рост",
    ]);
  });

  it("keeps the exact first non-correct question for review actions", () => {
    const actions = personalRoute({
      growth_topics: [{ topic: "Алгоритмы", question_count: 2 }],
      per_question: [
        { question_id: "q1", number: 1, topic: "Алгоритмы", status: "correct", is_correct: true },
        { question_id: "q2", number: 2, topic: "Алгоритмы", status: "incorrect", is_correct: false },
      ],
    });
    expect(actions[0]).toMatchObject({ kind: "review", topic: "Алгоритмы", questionId: "q2" });
  });

  it("does not offer a topic trainer for an all-skipped topic", () => {
    expect(personalRoute({
      growth_topics: [{ topic: "Алгоритмы", question_count: 2 }],
      per_question: [{ question_id: "q1", number: 1, topic: "Алгоритмы", status: "skipped", is_correct: false }],
    }).map((action) => action.kind)).toEqual(["retest-reminder"]);
  });

  it("calls one wrong answer a recommendation rather than a diagnosed gap", () => {
    expect(topicRecommendation([{ topic: "Орфоэпия", question_count: 1, correct_count: 0 }])).toEqual({
      heading: "Стоит повторить",
      topics: ["Орфоэпия"],
    });
  });


  it("builds bounded local game progress from a single result", () => {
    expect(resultGameSummary({
      score: 80,
      max_score: 100,
      correct_count: 4,
      question_count: 5,
      strong_topics: ["Алгоритмы"],
      growth_topics: [{ topic: "Информация" }],
    })).toMatchObject({
      points: 80,
      level: 4,
      levelProgress: 20,
      pointsToNextLevel: 20,
    });
    expect(resultGameSummary({
      score: 999,
      max_score: 0,
      correct_count: -2,
      question_count: -1,
      strong_topics: [],
      growth_topics: [],
    })).toMatchObject({ points: 0, level: 1, levelProgress: 0, pointsToNextLevel: 25 });
  });
});
