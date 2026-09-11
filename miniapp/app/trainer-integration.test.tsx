import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import {
  answerTrainer,
  apiErrorDetail,
  finishTrainer,
  startTrainer,
} from "./api";
import { ResultScreen } from "./result-flow";
import { ConfirmSheet } from "./confirm-sheet";
import { TrainerScreen } from "./trainer-screen";
import { trainerErrorMessage } from "./use-trainer";
import { trainerInitialState, trainerReducer, type TrainerState } from "./trainer-model";
import type { Question } from "./types";

const question: Question = {
  id: "q1",
  type: "single",
  topic: "Алгебра",
  title: "Задание 1",
  prompt: "Сколько будет два плюс два?",
  max_primary_score: 1,
  source: {
    provider: "maximum",
    official_year: 2026,
    approval_status: "approved",
    source_kind: "original",
    source_url: "https://maximumtest.ru/",
    rights_status: "original",
    verified_at: "2026-09-01",
  },
  options: [{ id: "a", label: "4" }, { id: "b", label: "5" }],
};

function fetcherWith(body: unknown, status = 200) {
  return vi.fn<typeof fetch>(async () => new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  }));
}

describe("trainer integration contracts", () => {
  it.each([
    ["trainer_no_mistakes", "В этой диагностике нет ошибок для тренировки."],
    ["trainer_mistakes_source_not_found", "Результат диагностики больше недоступен для тренировки."],
    ["trainer_mistakes_source_conflict", "Результат уже используется в другой тренировке. Открой его снова и повтори попытку."],
  ])("maps %s from the real mistakes replay endpoint to an actionable message", (detail, message) => {
    const error = Object.assign(new Error("diagnostic_api_409"), { detail });
    expect(trainerErrorMessage(error)).toBe(message);
  });

  it("sends init data, bootstrap scope, bounded count, and normal mode on start", async () => {
    const fetcher = fetcherWith({
      trainer_session_id: "s".repeat(32), diagnostic_id: "math", content_version: "v1",
      mode: "normal", question_ids: ["q1"], current_index: 0, revision: 1,
      status: "active", questions: [question], lives_remaining: 5,
    });
    await startTrainer("signed-init-data", {
      session_scope: "a".repeat(24), diagnostic_id: "math", count: 5, mode: "normal",
    }, fetcher);
    const init = fetcher.mock.calls[0]?.[1];
    expect(JSON.parse(String(init?.body))).toEqual({
      init_data: "signed-init-data",
      session_scope: "a".repeat(24),
      diagnostic_id: "math",
      count: 5,
      mode: "normal",
    });
  });

  it("submits the current revision and keeps feedback server-owned", async () => {
    const fetcher = fetcherWith({
      trainer_session_id: "s".repeat(32), question_id: "q1", is_correct: false,
      correct_answer: "4", explanation: "Проверь сложение.", xp_delta: 0,
      life_delta: -1, current_index: 1, revision: 2, status: "exhausted", lives_remaining: 4,
    });
    const response = await answerTrainer("signed", {
      session_scope: "b".repeat(24), trainer_session_id: "s".repeat(32),
      question_id: "q1", answer: "b", revision: 1, idempotency_key: "trainer-answer-1",
    }, fetcher);
    expect(response.is_correct).toBe(false);
    expect(response.correct_answer).toBe("4");
    expect(JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body))).toMatchObject({
      init_data: "signed", question_id: "q1", answer: "b", revision: 1,
    });
  });

  it("starts mistake replay with the owned attempt id", async () => {
    const fetcher = fetcherWith({
      trainer_session_id: "s".repeat(32), diagnostic_id: "math", content_version: "v1",
      mode: "mistakes", source_attempt_id: "attempt-1", question_ids: ["q1"], current_index: 0,
      revision: 1, status: "active", questions: [question], lives_remaining: 0,
    });
    await startTrainer("signed-init-data", {
      session_scope: "a".repeat(24), diagnostic_id: "math", count: 5,
      mode: "mistakes", source_attempt_id: "attempt-1",
    }, fetcher);
    expect(JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body))).toMatchObject({
      mode: "mistakes", source_attempt_id: "attempt-1",
    });
  });

  it("finishes an exhausted resume and exposes the completed summary", async () => {
    const fetcher = vi.fn<typeof fetch>();
    fetcher.mockResolvedValueOnce(new Response(JSON.stringify({
      trainer_session_id: "s".repeat(32), diagnostic_id: "math", content_version: "v1",
      mode: "normal", question_ids: [], current_index: 0, revision: 7,
      status: "exhausted", questions: [], lives_remaining: 3,
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    fetcher.mockResolvedValueOnce(new Response(JSON.stringify({
      trainer_session_id: "s".repeat(32), status: "completed", revision: 8, current_index: 0,
      question_count: 0, answered_count: 0, correct_count: 0, xp_earned: 0, lives_spent: 0, lives_remaining: 3,
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    const started = await startTrainer("signed", {
      session_scope: "r".repeat(24), diagnostic_id: "math", count: 5, mode: "normal",
    }, fetcher);
    let state = trainerReducer(trainerInitialState, { type: "start", response: started });
    expect(state.phase).toBe("finishing");
    expect(renderToStaticMarkup(<TrainerScreen state={state} dispatch={() => undefined} />)).toContain("Завершаем тренировку");
    const finished = await finishTrainer("signed", {
      session_scope: "r".repeat(24), trainer_session_id: started.trainer_session_id, revision: started.revision,
    }, fetcher);
    state = trainerReducer(state, { type: "finish_result", response: finished });

    expect(state.phase).toBe("completed");
    expect(state.finishResult).toMatchObject({ question_count: 0, answered_count: 0, correct_count: 0 });
    expect(JSON.parse(String(fetcher.mock.calls[1]?.[1]?.body))).toMatchObject({
      trainer_session_id: started.trainer_session_id, revision: 7,
    });
  });

  it("shows replay errors only when a completed attempt is available", () => {
    const html = renderToStaticMarkup(<ResultScreen
      diagnostic={{ exam: "ОГЭ", subject: "Математика" } as never}
      result={{ score: 4, max_score: 10, score_unit: "баллов", correct_count: 2, question_count: 4, strong_topics: [], growth_topics: [], unassessed_part: null } as never}
      onReview={() => undefined}
      onForecast={() => undefined}
      onReplayMistakes={() => undefined}
    />);
    expect(html).toContain("Прорешать ошибки заново · тренажёр");
  });

  it("exposes safe server conflict details for visible recovery", async () => {
    const fetcher = fetcherWith({ detail: "trainer_content_changed" }, 409);
    await expect(finishTrainer("signed", {
      session_scope: "c".repeat(24), trainer_session_id: "s".repeat(32), revision: 2,
    }, fetcher)).rejects.toMatchObject({ message: "diagnostic_api_409", detail: "trainer_content_changed" });
    try {
      await finishTrainer("signed", {
        session_scope: "c".repeat(24), trainer_session_id: "s".repeat(32), revision: 2,
      }, fetcher);
    } catch (error) {
      expect(apiErrorDetail(error)).toBe("trainer_content_changed");
    }
  });

  it("renders server feedback for the answered question, including the last question", () => {
    let state: TrainerState = trainerReducer(trainerInitialState, {
      type: "start",
      response: {
        trainer_session_id: "s".repeat(32), diagnostic_id: "math", content_version: "v1",
        mode: "normal", question_ids: ["q1"], current_index: 0, revision: 1,
        status: "active", questions: [question], lives_remaining: 5,
      },
    });
    state = trainerReducer(state, { type: "set_answer", answer: "b" });
    state = trainerReducer(state, { type: "submit_answer" });
    state = trainerReducer(state, {
      type: "answer_result",
      response: {
        trainer_session_id: "s".repeat(32), question_id: "q1", is_correct: false,
        correct_answer: "4", explanation: "Проверь сложение.", xp_delta: 0,
        max_primary_score: 1, earned_primary_score: 0,
        life_delta: -1, current_index: 1, revision: 2, status: "exhausted", lives_remaining: 4,
      },
    });
    const html = renderToStaticMarkup(<TrainerScreen
      state={state}
      dispatch={() => undefined}
      offers={[{ id: "school-course", label: "Разобрать тему с преподавателем", button: "Открыть", url: "https://school.example/course" }]}
      onOfferDismiss={() => undefined}
      onOfferEvent={() => undefined}
    />);
    expect(html).toContain("Неверно");
    expect(html).toContain("Проверь сложение.");
    expect(html).toContain("Завершить тренировку");
    expect(html).toContain("до 1 первичного балла");
    expect(html).toContain("0 из 1 первичного балла");
    expect(html).not.toContain("offer-surface");
  });

  it("marks the correct option green, the wrong pick red, and announces the spent life", () => {
    let state: TrainerState = trainerReducer(trainerInitialState, {
      type: "start",
      response: {
        trainer_session_id: "s".repeat(32), diagnostic_id: "math", content_version: "v1",
        mode: "normal", question_ids: ["q1"], current_index: 0, revision: 1,
        status: "active", questions: [question], lives_remaining: 3,
      },
    });
    state = trainerReducer(state, { type: "set_answer", answer: "b" });
    state = trainerReducer(state, { type: "submit_answer" });
    state = trainerReducer(state, {
      type: "answer_result",
      response: {
        trainer_session_id: "s".repeat(32), question_id: "q1", is_correct: false,
        correct_answer: "4", explanation: "Проверь сложение.", xp_delta: 0,
        life_delta: -1, current_index: 1, revision: 2, status: "exhausted", lives_remaining: 2,
      },
    });
    const html = renderToStaticMarkup(<TrainerScreen state={state} dispatch={() => undefined} />);
    // option a carries the correct label "4"; option b is what the student picked
    expect(html).toContain("answer-option is-right");
    expect(html).toContain("answer-option selected is-wrong");
    expect(html).toContain("Правильный ответ");
    expect(html).toContain("−1 жизнь · осталось 2 жизни");
    expect(html).toContain("trainer-feedback is-incorrect");
  });

  it("warns before the last life is gone", () => {
    let state: TrainerState = trainerReducer(trainerInitialState, {
      type: "start",
      response: {
        trainer_session_id: "s".repeat(32), diagnostic_id: "math", content_version: "v1",
        mode: "normal", question_ids: ["q1"], current_index: 0, revision: 1,
        status: "active", questions: [question], lives_remaining: 2,
      },
    });
    state = trainerReducer(state, { type: "set_answer", answer: "b" });
    state = trainerReducer(state, { type: "submit_answer" });
    state = trainerReducer(state, {
      type: "answer_result",
      response: {
        trainer_session_id: "s".repeat(32), question_id: "q1", is_correct: false,
        correct_answer: "4", explanation: null, xp_delta: 0,
        life_delta: -1, current_index: 1, revision: 2, status: "exhausted", lives_remaining: 1,
      },
    });
    const html = renderToStaticMarkup(<TrainerScreen state={state} dispatch={() => undefined} />);
    expect(html).toContain("Осталась одна жизнь");
  });

  it("keeps the primary action in the shared bar and explains why it is blocked", () => {
    const state: TrainerState = trainerReducer(trainerInitialState, {
      type: "start",
      response: {
        trainer_session_id: "s".repeat(32), diagnostic_id: "math", content_version: "v1",
        mode: "normal", question_ids: ["q1"], current_index: 0, revision: 1,
        status: "active", questions: [question], lives_remaining: 5,
      },
    });
    const html = renderToStaticMarkup(<TrainerScreen state={state} dispatch={() => undefined} />);
    expect(html).toContain("question-action-bar");
    expect(html).toContain("question-announcement");
    expect(html).toContain("Выбери вариант");
  });

  it("offers a reveal and a skip that both name the cost", () => {
    const state: TrainerState = trainerReducer(trainerInitialState, {
      type: "start",
      response: {
        trainer_session_id: "s".repeat(32), diagnostic_id: "math", content_version: "v1",
        mode: "normal", question_ids: ["q1"], current_index: 0, revision: 1,
        status: "active", questions: [question], lives_remaining: 4,
      },
    });
    const html = renderToStaticMarkup(<TrainerScreen state={state} dispatch={() => undefined} />);
    expect(html).toContain("Показать ответ");
    expect(html).toContain("Пропустить вопрос");
    expect(html).toContain("Спишется одна жизнь, останется 3");
  });

  it("gives up without a complete answer and reveals the correct one", () => {
    let state: TrainerState = trainerReducer(trainerInitialState, {
      type: "start",
      response: {
        trainer_session_id: "s".repeat(32), diagnostic_id: "math", content_version: "v1",
        mode: "normal", question_ids: ["q1"], current_index: 0, revision: 1,
        status: "active", questions: [question], lives_remaining: 4,
      },
    });
    // no draft answer at all: submit_answer must refuse, give_up must not
    expect(trainerReducer(state, { type: "submit_answer" }).phase).toBe("answering");
    state = trainerReducer(state, { type: "give_up", intent: "reveal" });
    expect(state.phase).toBe("awaiting_result");
    state = trainerReducer(state, {
      type: "answer_result",
      response: {
        trainer_session_id: "s".repeat(32), question_id: "q1", is_correct: false,
        correct_answer: "4", explanation: null, xp_delta: 0,
        life_delta: -1, current_index: 1, revision: 2, status: "exhausted", lives_remaining: 3,
      },
    });
    expect(state.phase).toBe("feedback");
    const html = renderToStaticMarkup(<TrainerScreen state={state} dispatch={() => undefined} />);
    expect(html).toContain("Правильный ответ");
  });

  it("carries a skip straight to the next question and still reports the life", () => {
    const twoQuestions = { ...question, id: "q2" };
    let state: TrainerState = trainerReducer(trainerInitialState, {
      type: "start",
      response: {
        trainer_session_id: "s".repeat(32), diagnostic_id: "math", content_version: "v1",
        mode: "normal", question_ids: ["q1", "q2"], current_index: 0, revision: 1,
        status: "active", questions: [question, twoQuestions], lives_remaining: 4,
      },
    });
    state = trainerReducer(state, { type: "give_up", intent: "skip" });
    state = trainerReducer(state, {
      type: "answer_result",
      response: {
        trainer_session_id: "s".repeat(32), question_id: "q1", is_correct: false,
        correct_answer: "4", explanation: null, xp_delta: 0,
        life_delta: -1, current_index: 1, revision: 2, status: "active", lives_remaining: 3,
      },
    });
    expect(state.phase).toBe("answering");
    expect(state.currentIndex).toBe(1);
    expect(state.answerResult).toBeNull();
    const html = renderToStaticMarkup(<TrainerScreen state={state} dispatch={() => undefined} />);
    expect(html).toContain("Вопрос пропущен. −1 жизнь · осталось 3 жизни");
  });

  it("sends give_up to the real answer endpoint", async () => {
    const fetcher = fetcherWith({
      trainer_session_id: "s".repeat(32), question_id: "q1", is_correct: false,
      correct_answer: "4", explanation: null, xp_delta: 0,
      life_delta: -1, current_index: 1, revision: 2, status: "exhausted", lives_remaining: 3,
    });
    await answerTrainer("signed", {
      session_scope: "a".repeat(24), trainer_session_id: "s".repeat(32),
      question_id: "q1", answer: null as never, revision: 1,
      idempotency_key: "trainer-answer-1", give_up: true,
    }, fetcher);
    const body = JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body));
    expect(body.give_up).toBe(true);
    expect(body.answer).toBeNull();
  });

  it("shows partial credit as Почти and formats explanation math", () => {
    let state: TrainerState = trainerReducer(trainerInitialState, {
      type: "start",
      response: {
        trainer_session_id: "s".repeat(32), diagnostic_id: "physics", content_version: "v1",
        mode: "normal", question_ids: ["q1"], current_index: 0, revision: 1,
        status: "active", questions: [question], lives_remaining: 5,
      },
    });
    state = trainerReducer(state, { type: "set_answer", answer: "b" });
    state = trainerReducer(state, { type: "submit_answer" });
    state = trainerReducer(state, {
      type: "answer_result",
      response: {
        trainer_session_id: "s".repeat(32), question_id: "q1", is_correct: false,
        correct_answer: "x = 2", explanation: "Подставь x^(2) в формулу.", xp_delta: 1,
        max_primary_score: 2, earned_primary_score: 1,
        life_delta: 0, current_index: 1, revision: 2, status: "exhausted", lives_remaining: 5,
      },
    });
    const html = renderToStaticMarkup(<TrainerScreen state={state} dispatch={() => undefined} />);
    expect(html).toContain("Почти");
    expect(html).toContain("math-expression");
    expect(html).not.toContain("x^(2)");
  });

  it("uses the subject in the trainer header and keeps the mode visible", () => {
    const state = trainerReducer(trainerInitialState, {
      type: "start",
      response: {
        trainer_session_id: "s".repeat(32), diagnostic_id: "physics", content_version: "v1",
        mode: "normal", question_ids: ["q1"], current_index: 0, revision: 1,
        status: "active", questions: [question], lives_remaining: 5,
      },
    });
    const html = renderToStaticMarkup(<TrainerScreen
      state={state}
      dispatch={() => undefined}
      header={{ diagnosticId: "physics", exam: "ЕГЭ", subject: "Физика", mode: "normal", modeLabel: "Тренировка" }}
    />);
    expect(html).toContain("Задание 1 из 1 · Алгебра");
    expect(html).toContain("Тренировка");
  });

  it("collapses a long trainer reference without duplicating the question heading", () => {
    const longQuestion = { ...question, id: "q-long", prompt: [
      "Какие высказывания соответствуют содержанию текста?",
      ...Array.from({ length: 9 }, (_, index) => `(${index + 1}) Фрагмент текста для тренировки чтения и анализа.`),
    ].join("\n") };
    const state = trainerReducer(trainerInitialState, {
      type: "start",
      response: {
        trainer_session_id: "s".repeat(32), diagnostic_id: "physics", content_version: "v1",
        mode: "normal", question_ids: ["q-long"], current_index: 0, revision: 1,
        status: "active", questions: [longQuestion], lives_remaining: 5,
      },
    });
    const html = renderToStaticMarkup(<TrainerScreen state={state} dispatch={() => undefined} />);
    expect(html.match(/<h1\b/g)).toHaveLength(1);
    expect(html).toContain('id="trainer-title"');
    expect(html).toContain('tabindex="-1"');
    expect(html).toContain("К тексту ↑");
    expect(html).toContain('aria-controls="trainer-reference"');
    expect(html).toContain("prompt-reference-long");
    expect(html).toContain("Развернуть текст");
    expect(html).toContain("prompt-sentence-1");
  });

  it("uses the shared image viewer for trainer questions", () => {
    const state = trainerReducer(trainerInitialState, {
      type: "start",
      response: {
        trainer_session_id: "s".repeat(32), diagnostic_id: "biology", content_version: "v1",
        mode: "normal", question_ids: ["q1"], current_index: 0, revision: 1,
        status: "active", questions: [{ ...question, asset: "assets/questions/q9.png", asset_alt: "Схема растения" }], lives_remaining: 5,
      },
    });
    const html = renderToStaticMarkup(<TrainerScreen state={state} dispatch={() => undefined} />);
    expect(html).toContain('class="image-viewer question-media"');
    expect(html).toContain('alt="Схема растения"');
    expect(html).toContain("Нажми, чтобы увеличить");
  });

  it("renders the school offer only on the completed trainer screen", () => {
    const state: TrainerState = {
      ...trainerInitialState,
      phase: "completed",
      session: {
        trainer_session_id: "s".repeat(32), diagnostic_id: "physics", content_version: "v1",
        mode: "normal", question_ids: [], current_index: 0, revision: 2,
        status: "completed", questions: [], lives_remaining: 5,
      },
      finishResult: {
        trainer_session_id: "s".repeat(32), status: "completed", revision: 2, current_index: 0,
        question_count: 0, answered_count: 0, correct_count: 0, xp_earned: 0, lives_spent: 0, lives_remaining: 5,
      },
    };
    const html = renderToStaticMarkup(<TrainerScreen
      state={state}
      dispatch={() => undefined}
      offers={[{ id: "school-course", label: "Продолжить подготовку", button: "Открыть", url: "https://school.example/course" }]}
      offerDismissed={{ trainer: false }}
      onOfferDismiss={() => undefined}
      onOfferEvent={() => undefined}
    />);
    expect(html).toContain("offer-surface-trainer");
  });

  it("defines the shared exit confirmation copy", () => {
    const html = renderToStaticMarkup(<ConfirmSheet open onCancel={() => undefined} onConfirm={() => undefined} />);
    expect(html).toContain("Выйти из тренировки?");
  });

  it("formats trainer question math the same way as the diagnostic sheet", () => {
    const mathQuestion = {
      ...question,
      prompt: "Решите уравнение x^(2) − 5x + 6 = 0. Укажите меньший корень.",
      options: [{ id: "a", label: "А) 2" }, { id: "b", label: "Б) 3" }],
    };
    const state = trainerReducer(trainerInitialState, {
      type: "start",
      response: {
        trainer_session_id: "s".repeat(32), diagnostic_id: "math", content_version: "v1",
        mode: "normal", question_ids: ["q1"], current_index: 0, revision: 1,
        status: "active", questions: [mathQuestion], lives_remaining: 5,
      },
    });
    const html = renderToStaticMarkup(<TrainerScreen state={state} dispatch={() => undefined} />);
    expect(html).toContain("math-expression");
    expect(html).toContain("<sup>2</sup>");
    expect(html).not.toContain("x^(2)");
    expect(html).not.toContain("А) 2");
  });

  it("uses the trainer subject for chemistry and language math rendering", () => {
    const chemistryQuestion = {
      ...question,
      prompt: "Определите формулу Fe_(2)(SO_(4))_(3).",
    };
    const chemistryState = trainerReducer(trainerInitialState, {
      type: "start",
      response: {
        trainer_session_id: "s".repeat(32), diagnostic_id: "chemistry", content_version: "v1",
        mode: "normal", question_ids: ["q1"], current_index: 0, revision: 1,
        status: "active", questions: [chemistryQuestion], lives_remaining: 5,
      },
    });
    const chemistryHtml = renderToStaticMarkup(<TrainerScreen
      state={chemistryState}
      dispatch={() => undefined}
      header={{ diagnosticId: "chemistry", exam: "ЕГЭ", subject: "Химия", mode: "normal", modeLabel: "Тренировка" }}
    />);
    expect(chemistryHtml).toContain("<sub>2</sub>");
    expect(chemistryHtml).toContain("<sub>4</sub>");

    const languageState = trainerReducer(trainerInitialState, {
      type: "start",
      response: {
        trainer_session_id: "s".repeat(32), diagnostic_id: "russian-language", content_version: "v1",
        mode: "normal", question_ids: ["q1"], current_index: 0, revision: 1,
        status: "active", questions: [{ ...question, prompt: "В 2022 году К и M: 3A₁₆." }], lives_remaining: 5,
      },
    });
    const languageHtml = renderToStaticMarkup(<TrainerScreen
      state={languageState}
      dispatch={() => undefined}
      header={{ diagnosticId: "russian-language", exam: "ЕГЭ", subject: "Русский язык", mode: "normal", modeLabel: "Тренировка" }}
    />);
    expect(languageHtml).not.toContain("math-expression");
    expect(languageHtml).toContain("3A₁₆");
  });

  it("shows the dedicated no-lives screen with a countdown and a Telegram reminder", () => {
    const state = trainerReducer(trainerInitialState, {
      type: "start",
      response: {
        trainer_session_id: "s".repeat(32), diagnostic_id: "math", content_version: "v1",
        mode: "normal", question_ids: ["q1"], current_index: 0, revision: 1,
        status: "active", questions: [question], lives_remaining: 0,
        next_life_at: new Date(Date.now() + 42 * 60_000).toISOString(),
      },
    });
    const html = renderToStaticMarkup(
      <TrainerScreen
        state={state}
        dispatch={() => undefined}
        livesReminder={{ status: "idle" }}
        onRemindLives={() => undefined}
        offers={[{ id: "school-course", label: "Продолжить подготовку", button: "Открыть", url: "https://school.example/course" }]}
        onOfferDismiss={() => undefined}
        onOfferEvent={() => undefined}
      />,
    );
    expect(html).toContain("Жизни закончились");
    expect(html).toContain("Восстановление");
    expect(html).toContain("Напомнить в Telegram");
    expect(html).toContain("Пройти диагностику");
    expect(html).not.toContain("offer-surface");
    expect(html).not.toContain("Проверить ответ");
  });

  it("confirms a scheduled Telegram reminder instead of the button", () => {
    const state = trainerReducer(trainerInitialState, {
      type: "start",
      response: {
        trainer_session_id: "s".repeat(32), diagnostic_id: "math", content_version: "v1",
        mode: "normal", question_ids: ["q1"], current_index: 0, revision: 1,
        status: "active", questions: [question], lives_remaining: 0,
        next_life_at: new Date(Date.now() + 42 * 60_000).toISOString(),
      },
    });
    const html = renderToStaticMarkup(
      <TrainerScreen state={state} dispatch={() => undefined} livesReminder={{ status: "scheduled" }} onRemindLives={() => undefined} />,
    );
    expect(html).toContain("Напомним в Telegram");
  });

  it("keeps mistake replay available when the normal life pool is empty", () => {
    const state = trainerReducer(trainerInitialState, {
      type: "start",
      response: {
        trainer_session_id: "s".repeat(32), diagnostic_id: "math", content_version: "v1",
        mode: "mistakes", source_attempt_id: "attempt-1", question_ids: ["q1"], current_index: 0, revision: 1,
        status: "active", questions: [question], lives_remaining: 0,
      },
    });
    const html = renderToStaticMarkup(<TrainerScreen state={state} dispatch={() => undefined} />);
    expect(html).toContain("Повтор ошибок");
    expect(html).not.toContain("Жизни закончились");
    expect(html).not.toContain("⚡");
    expect(html).not.toContain('class="answer-option" disabled');
  });
});
