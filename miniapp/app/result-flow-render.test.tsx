import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ForecastScreen, ResultScreen, ReviewScreen } from "./result-flow";

describe("result flow screens", () => {
  it("renders the persisted answers and honest fallback label", () => {
    const html = renderToStaticMarkup(
      <ReviewScreen
        items={[{
          question_id: "q1",
          number: 1,
          type: "single",
          topic: "Алгоритмы",
          title: "Задание 1",
          prompt: "Условие",
          is_correct: false,
          user_answer: "12",
          expected_answer: "16",
          guidance: "Решайте по шагам.",
          guidance_kind: "fallback",
        }]}
        index={0}
        onBack={() => undefined}
        onNext={() => undefined}
        onForecast={() => undefined}
      />,
    );
    expect(html).toContain("Ваш ответ");
    expect(html).toContain("Правильный ответ");
    expect(html).toContain("Общий алгоритм");
  });

  it("renders only the provided forecast points", () => {
    const html = renderToStaticMarkup(
      <ForecastScreen
        points={[{ id: "current", label: "Сейчас", value: 40 }]}
        onBack={() => undefined}
        onRoute={() => undefined}
      />,
    );
    expect(html).toContain("40");
    expect(html).not.toContain("Годовой курс");
  });

  it("renders zero metrics so a truthy score gate cannot hide a valid server result", () => {
    const html = renderToStaticMarkup(
      <ResultScreen
        diagnostic={{ exam: "ОГЭ", subject: "Математика" } as never}
        pdfStatus="pending"
        result={{
          score: 0,
          max_score: 100,
          score_unit: "баллов",
          correct_count: 0,
          question_count: 4,
          strong_topics: [],
          growth_topics: [],
          unassessed_part: "Письменная часть не проверялась",
        } as never}
        onReview={() => undefined}
        onForecast={() => undefined}
      />,
    );

    expect(html).toContain("Текущий балл");
    expect(html).toContain("<strong>0</strong>");
    expect(html).toContain("0 из 4");
    expect(html).toContain("из 100 баллов");
  });
});
