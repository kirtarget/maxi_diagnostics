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
});
