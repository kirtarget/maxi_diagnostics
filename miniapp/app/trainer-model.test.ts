import { describe, expect, it } from "vitest";
import {
  isTrainerAnswerComplete,
  planProgress,
  planReasonLabel,
  trainerInitialState,
  trainerReducer,
  type TrainerStartResponse,
} from "./trainer-model";
import type { Question } from "./types";

const questions: Question[] = [
  { id: "single", type: "single", topic: "t", title: "1", prompt: "p", options: [{ id: "a", label: "A" }] },
  { id: "multiple", type: "multiple", topic: "t", title: "2", prompt: "p", selection_limit: 2, options: [{ id: "a", label: "A" }, { id: "b", label: "B" }] },
  { id: "matching", type: "matching", topic: "t", title: "3", prompt: "p", items: [{ id: "i", label: "I" }], options: [{ id: "a", label: "A" }] },
  { id: "input", type: "input", topic: "t", title: "4", prompt: "p" },
];
const start: TrainerStartResponse = { trainer_session_id: "s1", diagnostic_id: "d1", content_version: "v1", mode: "normal", question_ids: questions.map(({ id }) => id), current_index: 0, revision: 1, status: "in_progress", questions, lives_remaining: 3 };

describe("trainer model", () => {
  it("accepts complete answers for every public question kind", () => {
    expect(isTrainerAnswerComplete(questions[0], "a")).toBe(true);
    expect(isTrainerAnswerComplete(questions[1], ["a", "b"])).toBe(true);
    expect(isTrainerAnswerComplete(questions[2], { i: "a" })).toBe(true);
    expect(isTrainerAnswerComplete(questions[3], "42")).toBe(true);
  });

  it("keeps correctness out of the start payload", () => {
    expect(start).not.toHaveProperty("is_correct");
    expect(JSON.stringify(start)).not.toContain('"is_correct"');
  });

  it("waits for the server result and locks the answer", () => {
    let state = trainerReducer(trainerInitialState, { type: "start", response: start });
    state = trainerReducer(state, { type: "set_answer", answer: "a" });
    state = trainerReducer(state, { type: "submit_answer" });
    expect(state.phase).toBe("awaiting_result");
    const unchanged = trainerReducer(state, { type: "set_answer", answer: "other" });
    expect(unchanged.draftAnswer).toBe("a");
    state = trainerReducer(state, { type: "answer_result", response: { trainer_session_id: "s1", question_id: "single", is_correct: true, correct_answer: "a", explanation: "Good", xp_delta: 10, life_delta: 0, current_index: 1, revision: 2, status: "in_progress", lives_remaining: 3 } });
    expect(state.phase).toBe("feedback");
  });

  it("retries without losing the submitted answer", () => {
    let state = trainerReducer(trainerReducer(trainerInitialState, { type: "start", response: start }), { type: "set_answer", answer: "a" });
    state = trainerReducer(state, { type: "submit_answer" });
    state = trainerReducer(state, { type: "error", message: "offline" });
    state = trainerReducer(state, { type: "retry" });
    expect(state.phase).toBe("awaiting_result");
    expect(state.submittedAnswer).toBe("a");
  });

  it("does not allow a zero-life session to submit", () => {
    const zeroLives = { ...start, lives_remaining: 0 };
    let state = trainerReducer(trainerInitialState, { type: "start", response: zeroLives });
    state = trainerReducer(state, { type: "set_answer", answer: "a" });
    expect(trainerReducer(state, { type: "submit_answer" }).phase).toBe("answering");
  });

  it("carries next_life_at from the answer result into the session", () => {
    let state = trainerReducer(trainerInitialState, { type: "start", response: { ...start, lives_remaining: 1, next_life_at: null } });
    state = trainerReducer(state, { type: "set_answer", answer: "a" });
    state = trainerReducer(state, { type: "submit_answer" });
    state = trainerReducer(state, { type: "answer_result", response: { trainer_session_id: "s1", question_id: "single", is_correct: false, correct_answer: "a", explanation: null, xp_delta: 0, life_delta: -1, current_index: 1, revision: 2, status: "in_progress", lives_remaining: 0, next_life_at: "2026-08-28T12:00:00+00:00" } });
    expect(state.session?.lives_remaining).toBe(0);
    expect(state.session?.next_life_at).toBe("2026-08-28T12:00:00+00:00");
  });

  it("allows mistake replay to continue without spending lives", () => {
    const mistakes: TrainerStartResponse = { ...start, mode: "mistakes", source_attempt_id: "attempt-1", lives_remaining: 0 };
    let state = trainerReducer(trainerInitialState, { type: "start", response: mistakes });
    state = trainerReducer(state, { type: "set_answer", answer: "a" });
    state = trainerReducer(state, { type: "submit_answer" });
    expect(state.phase).toBe("awaiting_result");
  });
  it("reports no plan progress for a session that is not running the plan", () => {
    const state = trainerReducer(trainerInitialState, { type: "start", response: start });
    expect(planProgress(state)).toBeNull();
    expect(planReasonLabel(state, "single")).toBeNull();
  });

  it("counts answered plan questions and names the reason for each", () => {
    const plan: TrainerStartResponse = {
      ...start,
      mode: "plan",
      plan: {
        plan_date: "2026-09-02",
        total: 5,
        completed: 2,
        reasons: { single: "mistake_review", multiple: "growth_topic" },
      },
    };
    let state = trainerReducer(trainerInitialState, { type: "start", response: plan });
    expect(planProgress(state)).toEqual({ completed: 2, total: 5 });
    expect(planReasonLabel(state, "single")).toBe("повтор ошибки");
    expect(planReasonLabel(state, "multiple")).toBe("зона роста");
    expect(planReasonLabel(state, "matching")).toBeNull();

    state = trainerReducer(state, { type: "set_answer", answer: "a" });
    state = trainerReducer(state, { type: "submit_answer" });
    state = trainerReducer(state, { type: "answer_result", response: { trainer_session_id: "s1", question_id: "single", is_correct: true, correct_answer: "a", explanation: null, xp_delta: 10, life_delta: 0, current_index: 3, revision: 2, status: "in_progress", lives_remaining: 3 } });
    expect(planProgress(state)).toEqual({ completed: 3, total: 5 });
  });

  it("spends lives in plan mode just like a normal session", () => {
    const plan: TrainerStartResponse = { ...start, mode: "plan", lives_remaining: 0 };
    let state = trainerReducer(trainerInitialState, { type: "start", response: plan });
    state = trainerReducer(state, { type: "set_answer", answer: "a" });
    expect(trainerReducer(state, { type: "submit_answer" }).phase).toBe("answering");
  });
});
