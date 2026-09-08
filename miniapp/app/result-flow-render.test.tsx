import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { ForecastEmptyScreen, ForecastScreen, ResultScreen, ReviewScreen, RouteScreen } from "./result-flow";
import type { ReviewItem } from "./types";

const physicsSchool = JSON.parse(
  readFileSync(new URL("../../school/diagnostics/oge-physics-197.json", import.meta.url), "utf8"),
) as { questions: Array<{ id: string; type: string; topic: string; title: string; prompt: string }> };

describe("result flow screens", () => {
  it("keeps quick results compact and renders the complete task grid", () => {
    const html = renderToStaticMarkup(<ResultScreen
      diagnostic={{ exam: "ОГЭ", subject: "Физика" } as never}
      result={{ diagnostic_id: "physics", mode: "quick", question_count: 18, correct_count: 10, skipped_count: 1, score: 10, max_score: 18, score_unit: "балл", strong_topics: [], growth_topics: [], per_question: Array.from({ length: 18 }, (_, index) => ({ question_id: `q${index + 1}`, number: index + 1, topic: "Механика", status: index === 9 ? "incorrect" : "correct", is_correct: index !== 9 })) }}
      onReview={() => undefined}
      onForecast={() => undefined}
    />);

    expect(html).toContain("10 из 18");
    expect(html).not.toContain("Точность ответов");
    expect(html).toContain("Задание 10, Механика, ошибка");
    expect(html).toContain("Посмотреть, где ошибся (1)");
    expect((html.match(/result-question-cell/g) ?? []).length).toBe(18);
  });

  it("uses the frozen school question ids for every full-result cell", () => {
    const questions = physicsSchool.questions.slice(0, 18);
    const html = renderToStaticMarkup(<ResultScreen
      diagnostic={{ exam: "ОГЭ", subject: "Физика" } as never}
      result={{
        diagnostic_id: "oge-physics-197", mode: "full", question_count: 18,
        correct_count: 17, skipped_count: 0, score: 17, max_score: 18, score_unit: "балл",
        strong_topics: [], growth_topics: [], per_question: questions.map((question, index) => ({
          question_id: question.id, number: index + 1, topic: question.topic,
          status: question.id.endsWith("q10") ? "incorrect" : "correct",
          is_correct: !question.id.endsWith("q10"),
        })),
      }}
      onReview={() => undefined}
      onForecast={() => undefined}
    />);

    expect((html.match(/result-question-cell/g) ?? []).length).toBe(18);
    expect(html).toContain("Задание 10");
    expect(html).toContain("17 из 18 верно");
  });

  it("collapses the real q4 and q18 references with question-scoped anchors", () => {
    const items: ReviewItem[] = [4, 18].map((number) => {
      const question = physicsSchool.questions[number - 1];
      return {
        question_id: question.id,
        number,
        type: question.type as ReviewItem["type"],
        topic: question.topic,
        title: question.title,
        prompt: question.prompt,
        is_correct: false,
        status: "incorrect" as const,
        user_answer: "Не отвечено",
        expected_answer: "Эталон",
        guidance: "Проверьте решение.",
        guidance_kind: "fallback" as const,
      };
    });
    const html = renderToStaticMarkup(<ReviewScreen
      items={[items[0]]}
      index={0}
      onBack={() => undefined}
      onNext={() => undefined}
      onForecast={() => undefined}
    />) + renderToStaticMarkup(<ReviewScreen
      items={[items[1]]}
      index={0}
      onBack={() => undefined}
      onNext={() => undefined}
      onForecast={() => undefined}
    />);

    expect(html).toContain("prompt-reference-toggle");
    expect(html).toContain("review-reference-sp-physics-oge-2022-q4");
    expect(html).toContain("review-reference-sp-physics-oge-2022-q18");
    expect(html.match(/К тексту ↑/g)?.length).toBe(2);
  });

  it("renders review list as a separate navigable mode", () => {
    const html = renderToStaticMarkup(<ReviewScreen mode="list" items={[{
      question_id: "q10", number: 10, type: "single", topic: "Механика", title: "Задание 10", prompt: "Условие", is_correct: false, status: "incorrect", user_answer: "1", expected_answer: "2", guidance: "Повтори тему.", guidance_kind: "fallback",
    }]} index={0} onBack={() => undefined} onNext={() => undefined} onForecast={() => undefined} onSelectQuestion={() => undefined} />);

    expect(html).toContain("Где ошибся (1)");
    expect(html).toContain("Открыть задание 10");
    expect(html).not.toContain("Ваш ответ");
  });

  it("opens a selected correct q10 directly in detail mode", () => {
    const html = renderToStaticMarkup(<ReviewScreen
      items={[
        { question_id: "q10", number: 10, type: "single", topic: "Механика", title: "Задание 10", prompt: "Условие", is_correct: true, status: "correct", user_answer: "2", expected_answer: "2", guidance: "Проверьте.", guidance_kind: "fallback" },
        { question_id: "q11", number: 11, type: "single", topic: "Электричество", title: "Задание 11", prompt: "Условие", is_correct: false, status: "incorrect", user_answer: "1", expected_answer: "2", guidance: "Проверьте.", guidance_kind: "fallback" },
      ]}
      selectedQuestionId="q10"
      mode="detail"
      index={0}
      onBack={() => undefined}
      onNext={() => undefined}
      onForecast={() => undefined}
    />);

    expect(html).toContain("<h1 id=\"review-title\" tabindex=\"-1\">Задание 10</h1>");
    expect(html).toContain("Верно");
  });

  it("keeps structured review output static and label-decoded", () => {
    const html = renderToStaticMarkup(<ReviewScreen items={[{
      question_id: "matching-q1", number: 1, type: "matching", topic: "Вещества", title: "Задание 1", prompt: "Установите соответствие.", is_correct: false, status: "incorrect", user_answer: "А: 2", expected_answer: "А: 1", answer_preview: { kind: "matching", markers: ["А"], user: ["2"], expected: ["1"], option_labels: { "1": "Вода", "2": "Кислота" } }, guidance: "Проверьте.", guidance_kind: "fallback",
    }]} index={0} onBack={() => undefined} onNext={() => undefined} onForecast={() => undefined} />);

    expect(html).toContain("Позиция");
    expect(html).toContain("Кислота");
    expect(html).not.toContain('aria-live="polite"');
  });

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

  it("does not offer a chat link without a valid bot callback", () => {
    const html = renderToStaticMarkup(
      <ResultScreen
        diagnostic={{ exam: "ОГЭ", subject: "Физика" } as never}
        pdfStatus="sent"
        result={{
          diagnostic_id: "demo-physics",
          mode: "full",
          score: 1,
          max_score: 1,
          score_unit: "балл",
          correct_count: 1,
          skipped_count: 0,
          question_count: 1,
          strong_topics: [],
          growth_topics: [],
        }}
        onReview={() => undefined}
        onForecast={() => undefined}
      />,
    );
    expect(html).not.toContain("Открыть чат");
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
    expect(html).not.toContain("Схема ответа");
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

  it("renders the structured answer preview from the immutable review item", () => {
    const html = renderToStaticMarkup(
      <ReviewScreen
        items={[{
          question_id: "matching-q1",
          number: 1,
          type: "matching",
          topic: "Вещества",
          title: "Задание 1",
          prompt: "Установите соответствие.",
          is_correct: false,
          status: "incorrect",
          user_answer: "А: 2; Б: 1",
          expected_answer: "А: 1; Б: 2",
          answer_preview: {
            kind: "matching",
            markers: ["А", "Б"],
            user: ["2", "1"],
            expected: ["1", "2"],
          },
          guidance: "Проверьте соответствие.",
          guidance_kind: "fallback",
        }]}
        index={0}
        onBack={() => undefined}
        onNext={() => undefined}
        onForecast={() => undefined}
      />,
    );
    expect(html).toContain("Схема ответа");
    expect(html).not.toContain("Ваш выбор");
    expect(html).not.toContain("Правильная схема");
    expect(html.match(/review-answer-table/g)?.length).toBe(1);
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
          answer_preview: {
            kind: "matching",
            markers: ["А"],
            user: ["1"],
            expected: ["2"],
            option_labels: { "1": "H_(2)SO_(4)", "2": "Br_(2)" },
          },
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
    expect(chemistryHtml).not.toContain("H_(2)SO_(4)");
    expect(chemistryHtml).not.toContain("Br_(2)");

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
    expect(html.indexOf("offer-surface-forecast")).toBeLessThan(html.indexOf("Открыть план"));
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
    expect(html).toContain("Пройти полную диагностику");
  });

  it("does not invent an answer count when the estimate has no sample size", () => {
    const html = renderToStaticMarkup(
      <ForecastEmptyScreen onBack={() => undefined} onStart={() => undefined} />,
    );

    expect(html).toContain("Пока недостаточно данных для числового ориентира.");
    expect(html).not.toContain("0 из");
    expect(html).not.toContain("forecast-empty-progress");
  });

  it("does not invent an XP suffix for a legacy plan without a reward", () => {
    const html = renderToStaticMarkup(
      <RouteScreen items={[]} offers={[]} onSubjects={() => undefined} onHome={() => undefined} />,
    );

    expect(html).toContain("На главную");
    expect(html).not.toContain("XP");
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
