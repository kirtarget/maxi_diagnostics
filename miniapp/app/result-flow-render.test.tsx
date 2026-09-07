import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ForecastEmptyScreen, ForecastScreen, ResultScreen, ReviewScreen } from "./result-flow";

describe("result flow screens", () => {
  it("separates skipped answers from incorrect answers", () => {
    const html = renderToStaticMarkup(
      <ResultScreen
        diagnostic={{ exam: "ЕГЭ", subject: "Математика" } as never}
        pdfStatus="pending"
        result={{
          diagnostic_id: "demo-math",
          mode: "full",
          score: 1,
          max_score: 18,
          score_unit: "балл",
          correct_count: 1,
          skipped_count: 3,
          question_count: 18,
          strong_topics: [],
          growth_topics: [],
        }}
        onReview={() => undefined}
        onForecast={() => undefined}
      />,
    );

    expect(html).toContain("1 верно · 14 неверно · 3 пропущено");
  });

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
          status: "incorrect",
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
          status: "skipped",
          user_answer: "Ты пропустил задание",
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
    expect(html).toContain("Пропущено");
    expect(html).not.toContain(">Неверно<");
  });

  it("uses the review subject for chemistry and language math rendering", () => {
    const chemistryHtml = renderToStaticMarkup(
      <ReviewScreen
        subject="Химия"
        items={[{
          question_id: "chemistry-q1",
          number: 1,
          type: "single",
          topic: "Вещества",
          title: "Задание 1",
          prompt: "Определите формулу Fe_(2)(SO_(4))_(3).",
          is_correct: false,
          status: "incorrect",
          user_answer: "Fe_(2)(SO_(4))_(3)",
          expected_answer: "Fe_(2)(SO_(4))_(3)",
          guidance: "Проверьте индексы.",
          guidance_kind: "fallback",
        }]}
        index={0}
        onBack={() => undefined}
        onNext={() => undefined}
        onForecast={() => undefined}
      />,
    );
    expect(chemistryHtml).toContain("<sub>2</sub>");
    expect(chemistryHtml).toContain("<sub>4</sub>");

    const languageHtml = renderToStaticMarkup(
      <ReviewScreen
        subject="Русский язык"
        items={[{
          question_id: "russian-q1",
          number: 1,
          type: "single",
          topic: "Язык",
          title: "Задание 1",
          prompt: "В 2022 году К и M: 3A₁₆.",
          is_correct: false,
          status: "incorrect",
          user_answer: "3A₁₆",
          expected_answer: "К",
          guidance: "Прочитайте условие.",
          guidance_kind: "fallback",
        }]}
        index={0}
        onBack={() => undefined}
        onNext={() => undefined}
        onForecast={() => undefined}
      />,
    );
    expect(languageHtml).not.toContain("math-expression");
    expect(languageHtml).toContain("3A₁₆");
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

    expect(html).toContain("Точность ответов");
    expect(html).toContain("<strong>0%</strong>");
    expect(html).toContain("0 из 4");
    expect(html).toContain("не предсказывает балл на экзамене");
    expect(html).not.toContain("Очки за этот результат");
  });

  it("ignores legacy exam estimates and shows factual answer accuracy", () => {
    const html = renderToStaticMarkup(
      <ResultScreen
        diagnostic={{ exam: "ЕГЭ", subject: "Физика" } as never}
        result={{
          score: 50,
          max_score: 100,
          score_unit: "баллов",
          correct_count: 5,
          question_count: 10,
          strong_topics: [],
          growth_topics: [],
          estimate: {
            kind: "test_score",
            value: 53,
            scaled_primary: 17,
            exam_max_primary: 45,
            sample_max_primary: 10,
            sample_size: 10,
            min_pass: 36,
          },
        } as never}
        onReview={() => undefined}
        onForecast={() => undefined}
      />,
    );

    expect(html).not.toContain("Ожидаемый результат");
    expect(html).not.toContain("53 балла ЕГЭ");
    expect(html).toContain("50%");
    expect(html).toContain("5 из 10");
  });

  it("shows the forecast in the unit the estimate uses", () => {
    const html = renderToStaticMarkup(
      <ForecastScreen
        points={[
          { id: "current", label: "Сейчас", value: 3 },
          { id: "course", label: "К экзамену", value: 4 },
        ]}
        kind="grade"
        onBack={() => undefined}
        onRoute={() => undefined}
      />,
    );

    expect(html).toContain("отметка");
    expect(html).not.toContain("баллов");
  });
});
