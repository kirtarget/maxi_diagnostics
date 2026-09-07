import { describe, expect, it } from "vitest";
import {
  trainerDiagnosticId,
  trainerFeedbackKind,
  trainerHeaderView,
  trainerModeLabel,
  isTrainerAnswerComplete,
  planProgress,
  planReasonLabel,
  trainerInitialState,
  trainerReducer,
  type TrainerAnswerResponse,
  type TrainerStartResponse,
} from "./trainer-model";
import type { BootstrapResponse, Brand, Question, SchoolLinks } from "./types";

const questions: Question[] = [
  { id: "single", type: "single", topic: "t", title: "1", prompt: "p", options: [{ id: "a", label: "A" }] },
  { id: "multiple", type: "multiple", topic: "t", title: "2", prompt: "p", selection_limit: 2, options: [{ id: "a", label: "A" }, { id: "b", label: "B" }] },
  { id: "matching", type: "matching", topic: "t", title: "3", prompt: "p", items: [{ id: "i", label: "I" }], options: [{ id: "a", label: "A" }] },
  { id: "input", type: "input", topic: "t", title: "4", prompt: "p" },
  { id: "text", type: "text", topic: "t", title: "5", prompt: "p", max_length: 40 },
];
const start: TrainerStartResponse = { trainer_session_id: "s1", diagnostic_id: "d1", content_version: "v1", mode: "normal", question_ids: questions.map(({ id }) => id), current_index: 0, revision: 1, status: "in_progress", questions, lives_remaining: 3 };

const fixtureBrand: Brand = {
  school_id: "fixture-school",
  name: "Fixture School",
  short_name: "Fixture",
  colors: {
    primary: "#000000",
    accent: "#111111",
    background: "#222222",
    signal: "#333333",
    ink: "#444444",
    paper: "#555555",
  },
  logo: "",
  interface: {
    command_start: "start",
    command_diagnostics: "diagnostics",
    command_results: "results",
    command_plan: "plan",
    start_diagnostic: "start diagnostic",
    open_diagnostic: "open diagnostic",
    results: "results",
    plan: "plan",
    home: "home",
    take_full_diagnostic: "take full diagnostic",
    check_another_subject: "check another subject",
    take_another_diagnostic: "take another diagnostic",
    quick_result: "quick result",
    full_result: "full result",
    ready_result: "ready result",
    unassessed_full: "unassessed full",
    results_heading: "results heading",
    diagnostic_fallback: "diagnostic fallback",
    plan_for: "plan for",
    keep_strong: "keep strong",
    focus_next: "focus next",
    open_result_hint: "open result hint",
    result_not_found: "result not found",
    back: "back",
    task_label: "task",
    of_label: "of",
    answer_label: "answer",
    enter_answer: "enter answer",
    choose_option: "choose option",
    next_question: "next question",
    get_result: "get result",
    result_in_app: "result in app",
    privacy_label: "privacy",
    support_label: "support",
    choose_label: "choose",
    close_diagnostic: "close diagnostic",
    illustration_alt: "illustration",
    result_score: "score",
    result_correct: "correct",
    delivery_note: "delivery note",
  },
};

const fixtureLinks: SchoolLinks = {
  website: "https://school.example",
  support: "https://school.example/support",
  privacy: "https://school.example/privacy",
  offers: [],
};

function bootstrapWith(overrides: Partial<BootstrapResponse> = {}): BootstrapResponse {
  return {
    catalog_contract: 3,
    session_scope: "scope",
    latest_attempt_id: null,
    school: { brand: fixtureBrand, links: fixtureLinks },
    diagnostics: [
      { id: "math", content_version: "v1", exam: "ОГЭ", subject: "Математика", mark: "", quick_count: 1, full_count: 1, question_count: 1 },
      { id: "english", content_version: "v1", exam: "ОГЭ", subject: "Английский язык", mark: "", quick_count: 1, full_count: 1, question_count: 1 },
    ],
    attempt: null,
    results: [],
    ...overrides,
  };
}

function completedAttempt(attemptId: string, diagnosticId: string): BootstrapResponse["results"][number] {
  return {
    attempt_id: attemptId,
    diagnostic_id: diagnosticId,
    content_version: "v1",
    mode: "full",
    status: "completed",
    question_index: 1,
    question_count: 1,
    progress_revision: 1,
    answers: {},
  };
}

describe("trainer model", () => {
  it("selects the trainer diagnostic from the resumable attempt before plan and results", () => {
    const bootstrap = bootstrapWith({
      attempt: { ...completedAttempt("active", "math"), status: "in_progress" },
      daily_plan: { plan_date: "2026-09-07", diagnostic_id: "english", subject: "Английский язык", exam: "ОГЭ", total: 1, completed: 0, status: "ready" },
      latest_attempt_id: "completed",
      results: [
        completedAttempt("completed", "english"),
      ],
    });

    expect(trainerDiagnosticId(bootstrap, "Английский язык")).toBe("math");
  });

  it("falls back through plan, latest completed result, first completed result, then subject", () => {
    const plan = bootstrapWith({
      daily_plan: { plan_date: "2026-09-07", diagnostic_id: "english", subject: "Английский язык", exam: "ОГЭ", total: 1, completed: 0, status: "ready" },
      latest_attempt_id: "latest",
      results: [
        completedAttempt("older", "math"),
        completedAttempt("latest", "english"),
      ],
    });
    expect(trainerDiagnosticId(plan)).toBe("english");

    const latest = bootstrapWith({ latest_attempt_id: "latest", results: [
      completedAttempt("older", "math"),
      completedAttempt("latest", "english"),
    ] });
    expect(trainerDiagnosticId(latest)).toBe("english");

    const first = bootstrapWith({ results: [
      completedAttempt("older", "math"),
      completedAttempt("newer", "english"),
    ] });
    expect(trainerDiagnosticId(first)).toBe("math");

    const subject = bootstrapWith({ diagnostics: [
      { id: "math", content_version: "v1", exam: "ОГЭ", subject: "Математика", mark: "", quick_count: 1, full_count: 1, question_count: 1 },
    ] });
    expect(trainerDiagnosticId(subject, "Математика")).toBe("math");
  });

  it("does not select an arbitrary diagnostic when no fallback is eligible", () => {
    const bootstrap = bootstrapWith({
      diagnostics: [
        { id: "math", content_version: "v1", exam: "ОГЭ", subject: "Математика", mark: "", quick_count: 1, full_count: 1, question_count: 1 },
      ],
      attempt: completedAttempt("finished", "math"),
      results: [{ ...completedAttempt("unfinished", "math"), status: "in_progress" }],
    });
    expect(trainerDiagnosticId(bootstrap)).toBeNull();
    expect(trainerDiagnosticId(bootstrapWith())).toBeNull();
  });

  it("returns a typed header view and labels each trainer mode", () => {
    const bootstrap = bootstrapWith();
    const planSession: TrainerStartResponse = { ...start, diagnostic_id: "english", mode: "plan" };
    expect(trainerHeaderView(bootstrap, planSession)).toEqual({ diagnosticId: "english", exam: "ОГЭ", subject: "Английский язык", mode: "plan", modeLabel: "План на сегодня" });
    expect(trainerModeLabel("normal")).toBe("Тренировка");
    expect(trainerModeLabel("mistakes")).toBe("Повтор ошибок");
    expect(trainerModeLabel("plan")).toBe("План на сегодня");
  });

  it("uses the running session diagnostic for plan and mistakes headers", () => {
    const bootstrap = bootstrapWith({
      attempt: { ...completedAttempt("active", "math"), status: "in_progress" },
      daily_plan: { plan_date: "2026-09-07", diagnostic_id: "english", subject: "Английский язык", exam: "ОГЭ", total: 1, completed: 0, status: "ready" },
      diagnostics: [
        ...bootstrapWith().diagnostics,
        { id: "physics", content_version: "v1", exam: "ЕГЭ", subject: "Физика", mark: "Ф", quick_count: 1, full_count: 1, question_count: 1 },
      ],
    });
    expect(trainerDiagnosticId(bootstrap)).toBe("math");

    expect(trainerHeaderView(bootstrap, { ...start, diagnostic_id: "english", mode: "plan" })).toMatchObject({
      diagnosticId: "english",
      exam: "ОГЭ",
      subject: "Английский язык",
      mode: "plan",
    });
    expect(trainerHeaderView(bootstrap, { ...start, diagnostic_id: "physics", mode: "mistakes" })).toMatchObject({
      diagnosticId: "physics",
      exam: "ЕГЭ",
      subject: "Физика",
      mode: "mistakes",
    });
  });

  it("classifies partial primary credit separately from incorrect answers", () => {
    const result = (overrides: Partial<TrainerAnswerResponse>): TrainerAnswerResponse => ({
      trainer_session_id: "s1",
      question_id: "single",
      is_correct: false,
      correct_answer: null,
      explanation: null,
      xp_delta: 0,
      life_delta: 0,
      current_index: 0,
      revision: 1,
      status: "active",
      lives_remaining: 3,
      ...overrides,
    });
    expect(trainerFeedbackKind(result({ is_correct: true }))).toBe("correct");
    expect(trainerFeedbackKind(result({ earned_primary_score: 1, max_primary_score: 2 }))).toBe("partial");
    expect(trainerFeedbackKind(result({ earned_primary_score: 0, max_primary_score: 2 }))).toBe("incorrect");
    expect(trainerFeedbackKind(result({ earned_primary_score: 2, max_primary_score: 2 }))).toBe("incorrect");
  });
  it("accepts complete answers for every public question kind", () => {
    expect(isTrainerAnswerComplete(questions[0], "a")).toBe(true);
    expect(isTrainerAnswerComplete(questions[1], ["a", "b"])).toBe(true);
    expect(isTrainerAnswerComplete(questions[2], { i: "a" })).toBe(true);
    expect(isTrainerAnswerComplete(questions[3], "42")).toBe(true);
    expect(isTrainerAnswerComplete(questions[4], " Однако ")).toBe(true);
  });

  it("uses structured completion rules for sequence and table-gap trainer inputs", () => {
    const sequence = {
      ...questions[3],
      prompt: "Установите соответствие.\nА) Первый\nБ) Второй\n1) Один\n2) Два",
      answer_format: "sequence",
      answer_length: 2,
      allow_reuse: false,
    } as Question;
    expect(isTrainerAnswerComplete(sequence, "12")).toBe(true);
    expect(isTrainerAnswerComplete(sequence, "1")).toBe(false);

    const tableGap = {
      ...questions[3],
      prompt: "Заполните таблицу.\nПоле 1 | Поле 2\n(А) | (Б)\nПропущенные элементы:\n1) один\n2) два",
      answer_format: "sequence",
      answer_length: 2,
      allow_reuse: false,
    } as Question;
    expect(isTrainerAnswerComplete(tableGap, "12")).toBe(true);
    expect(isTrainerAnswerComplete(tableGap, "1")).toBe(false);
  });

  it("treats a blank or oversized free-text draft as incomplete", () => {
    expect(isTrainerAnswerComplete(questions[4], "   ")).toBe(false);
    expect(isTrainerAnswerComplete(questions[4], undefined)).toBe(false);
    expect(isTrainerAnswerComplete(questions[4], "с".repeat(41))).toBe(false);
    expect(isTrainerAnswerComplete(questions[4], ["но"])).toBe(false);
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
