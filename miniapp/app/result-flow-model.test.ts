import { describe, expect, it } from "vitest";

import { forecastTrajectory, personalRoute, pdfStatusCopy, resultGameSummary, topicRecommendation } from "./result-flow-model";

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

  it("builds a bounded route from persisted growth topics", () => {
    expect(personalRoute(["Алгоритмы", "Информация", "Лишняя тема"]).map((item) => item.title)).toEqual([
      "Закрыть тему «Алгоритмы»",
      "Укрепить тему «Информация»",
      "Проверить рост",
    ]);
  });

  it("calls one wrong answer a recommendation rather than a diagnosed gap", () => {
    expect(topicRecommendation([{ topic: "Орфоэпия", question_count: 1, correct_count: 0 }])).toEqual({
      heading: "Стоит повторить",
      topics: ["Орфоэпия"],
    });
  });

  it("distinguishes every PDF delivery state without claiming unsent delivery", () => {
    expect(pdfStatusCopy("pending").title).toBe("Готовим PDF для Telegram");
    expect(pdfStatusCopy("sending").title).toBe("Отправляем PDF в Telegram");
    expect(pdfStatusCopy("sent").title).toBe("PDF отправлен в Telegram");
    expect(pdfStatusCopy("failed").action).toBe("Проверить статус");
    expect(pdfStatusCopy("abandoned").title).toBe("PDF не удалось отправить");
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
