import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import {
  answerTrainer,
  apiErrorDetail,
  finishTrainer,
  startTrainer,
} from "./api";
import { gameplayProfileView } from "./gameplay-profile-model";
import { GameplayHomeScreen } from "./navigation-screens";
import { ResultScreen } from "./result-flow";
import { TrainerScreen } from "./trainer-screen";
import { trainerInitialState, trainerReducer, type TrainerState } from "./trainer-model";
import type { Question } from "./types";

const question: Question = {
  id: "q1",
  type: "single",
  topic: "Алгебра",
  title: "Задание 1",
  prompt: "Сколько будет два плюс два?",
  options: [{ id: "a", label: "4" }, { id: "b", label: "5" }],
};

function fetcherWith(body: unknown, status = 200) {
  return vi.fn<typeof fetch>(async () => new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  }));
}

describe("trainer integration contracts", () => {
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
      pdfStatus="sent"
      result={{ score: 4, max_score: 10, score_unit: "баллов", correct_count: 2, question_count: 4, strong_topics: [], growth_topics: [], unassessed_part: null } as never}
      onReview={() => undefined}
      onForecast={() => undefined}
      onReplayMistakes={() => undefined}
    />);
    expect(html).toContain("Повторить ошибки");
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

  it("keeps the trainer CTA separate from the diagnostic CTA", () => {
    const html = renderToStaticMarkup(<GameplayHomeScreen
      diagnostics={[{ id: "math", content_version: "v1", exam: "ОГЭ", subject: "Математика", mark: "М", quick_count: 3, questions: [] }]}
      labels={{ start_diagnostic: "Начать диагностику" } as never}
      profile={gameplayProfileView({ completion_count: 0, achievement_keys: [] })}
      onStart={() => undefined}
      onStartTrainer={() => undefined}
      onOpenProfile={() => undefined}
    />);
    expect(html).toContain("Начать диагностику");
    expect(html).toContain("Тренировка");
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
        life_delta: -1, current_index: 1, revision: 2, status: "exhausted", lives_remaining: 4,
      },
    });
    const html = renderToStaticMarkup(<TrainerScreen state={state} dispatch={() => undefined} />);
    expect(html).toContain("Почти");
    expect(html).toContain("Проверь сложение.");
    expect(html).toContain("Завершить тренировку");
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
