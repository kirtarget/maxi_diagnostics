import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ForecastEmptyScreen, ForecastScreen, ResultScreen, ReviewScreen } from "./result-flow";

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
          max_primary_score: 2,
          earned_primary_score: 0,
          source: {
            provider: "maximum",
            official_year: 2026,
            approval_status: "approved",
            source_kind: "original",
            source_url: "https://maximumtest.ru/",
            rights_status: "original",
            verified_at: "2026-09-01",
          },
        }]}
        index={0}
        onBack={() => undefined}
        onNext={() => undefined}
        onForecast={() => undefined}
      />,
    );
    expect(html).toContain("Ваш ответ");
    expect(html).toContain("Правильный ответ");
    expect(html).toContain("Как решать");
    expect(html).toContain("0 из 2 первичных баллов");
  });

  it("formats review question math like the worksheet", () => {
    const html = renderToStaticMarkup(
      <ReviewScreen
        items={[{
          question_id: "q8",
          number: 8,
          type: "single",
          topic: "Квадратные уравнения",
          title: "Задание 8",
          prompt: "Решите уравнение x^(2) + 4x − 5 = 0. Укажите больший корень.",
          is_correct: false,
          user_answer: "−5",
          expected_answer: "1",
          guidance: "По теореме Виета корни: 1 и −5.",
          guidance_kind: "fallback",
        }]}
        index={0}
        onBack={() => undefined}
        onNext={() => undefined}
        onForecast={() => undefined}
      />,
    );
    expect(html).toContain("math-expression");
    expect(html).toContain("<sup>2</sup>");
    expect(html).not.toContain("x^(2)");
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

  it("uses the persisted forecast labels and values without school-specific claims", () => {
    const html = renderToStaticMarkup(
      <ForecastScreen
        points={[
          { id: "current", label: "Текущий результат", value: 15 },
          { id: "custom-program", label: "Настраиваемая программа", value: 47 },
        ]}
        onBack={() => undefined}
        onRoute={() => undefined}
      />,
    );

    expect(html).toContain("<small>Текущий результат</small><strong>15</strong><span>баллов</span>");
    expect(html).toContain("<small>Настраиваемая программа</small><strong>47</strong><span>баллов</span>");
    expect(html).toContain("+32");
    expect(html).toContain("не личная гарантия");
    expect(html).not.toContain("MAXIMUM");
    expect(html).not.toContain("средний прирост");
    expect(html).not.toContain("+42");
  });

  it("renders a configured white-label offer between the forecast explanation and route action", () => {
    const html = renderToStaticMarkup(
      <ForecastScreen
        points={[
          { id: "current", label: "Сейчас", value: 74 },
          { id: "goal", label: "Цель", value: 85 },
        ]}
        offers={[{
          id: "school-course",
          label: "Подготовка к экзамену",
          button: "Узнать больше",
          url: "https://school.example/course",
        }]}
        offerDismissed={false}
        onOfferDismiss={() => undefined}
        onOfferEvent={() => undefined}
        onBack={() => undefined}
        onRoute={() => undefined}
      />,
    );

    expect(html).toContain("offer-surface-forecast");
    expect(html).toContain("Подготовка к экзамену");
    expect(html.indexOf("forecast-explainer")).toBeLessThan(html.indexOf("offer-surface-forecast"));
    expect(html.indexOf("offer-surface-forecast")).toBeLessThan(html.indexOf("Открыть маршрут"));
  });

  it("shows the not-enough-data state with progress toward two diagnostics", () => {
    const html = renderToStaticMarkup(
      <ForecastEmptyScreen
        completedCount={1}
        onBack={() => undefined}
        onStart={() => undefined}
      />,
    );
    expect(html).toContain("Пока мало данных");
    expect(html).toContain("1 из 2");
    expect(html).toContain("Пройти диагностику");
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
    expect(html).toContain("Очки за этот результат");
    expect(html).toContain("MAXIMUM · эта диагностика");
    expect(html).toContain("Первый шаг");
    expect(html).toContain("Уровень 1");
  });
});
