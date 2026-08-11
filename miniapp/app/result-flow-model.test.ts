import { describe, expect, it } from "vitest";

import { forecastTrajectory, personalRoute, pdfStatusCopy } from "./result-flow-model";

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

  it("distinguishes every PDF delivery state without claiming unsent delivery", () => {
    expect(pdfStatusCopy("pending").title).toBe("Готовим PDF для Telegram");
    expect(pdfStatusCopy("sending").title).toBe("Отправляем PDF в Telegram");
    expect(pdfStatusCopy("sent").title).toBe("PDF отправлен в Telegram");
    expect(pdfStatusCopy("failed").action).toBe("Проверить статус");
    expect(pdfStatusCopy("abandoned").title).toBe("PDF не удалось отправить");
  });
});
