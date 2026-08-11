import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ForecastScreen, ReviewScreen } from "./result-flow";

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
});
