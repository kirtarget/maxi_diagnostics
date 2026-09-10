// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Home from "./page";
import type { Brand, BootstrapResponse, PublicDiagnostic, ServerAttempt, ServerResult } from "./types";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const SESSION_SCOPE = "account-scope-1";
const CONTENT_VERSION = "a".repeat(64);

const diagnostic: PublicDiagnostic = {
  id: "demo-math",
  content_version: CONTENT_VERSION,
  exam: "ЕГЭ",
  subject: "Математика",
  mark: "М",
  quick_count: 1,
  full_count: 1,
  question_count: 1,
  questions: [{
    id: "q1",
    type: "single",
    topic: "Тема 1",
    title: "Задание 1",
    prompt: "Выберите ответ",
    options: [{ id: "a", label: "A" }, { id: "b", label: "B" }],
  }],
};

const secondDiagnostic: PublicDiagnostic = {
  ...diagnostic,
  id: "demo-english",
  subject: "Английский язык",
};

const completedAttempt: ServerAttempt = {
  attempt_id: "attempt-done",
  diagnostic_id: "demo-math",
  content_version: CONTENT_VERSION,
  mode: "full",
  status: "completed",
  question_index: 1,
  question_count: 1,
  progress_revision: 2,
  answers: { q1: "a" },
};

const serverResult: ServerResult = {
  diagnostic_id: "demo-math",
  mode: "full",
  question_count: 1,
  correct_count: 0,
  skipped_count: 0,
  score: 0,
  max_score: 1,
  score_unit: "балл",
  strong_topics: [],
  growth_topics: ["Тема 1"],
};

const resultWithGrid: ServerResult = {
  ...serverResult,
  question_count: 18,
  correct_count: 17,
  max_score: 18,
  per_question: Array.from({ length: 18 }, (_, index) => ({
    question_id: `q${index + 1}`,
    number: index + 1,
    topic: "Механика",
    status: index === 9 ? "incorrect" as const : "correct" as const,
    is_correct: index !== 9,
  })),
};

const resultWithThreeMistakes: ServerResult = {
  ...resultWithGrid,
  correct_count: 15,
  per_question: resultWithGrid.per_question?.map((question) => {
    const isMistake = [10, 11, 18].includes(question.number);
    return { ...question, status: isMistake ? "incorrect" as const : "correct" as const, is_correct: !isMistake };
  }),
};

const reviewQ10 = {
  question_id: "q10", number: 10, type: "single" as const, topic: "Механика",
  title: "Задание 10", prompt: "Условие", is_correct: false, status: "incorrect" as const,
  user_answer: "1", expected_answer: "2", guidance: "Проверьте.", guidance_kind: "fallback" as const,
};

function bootstrapPayload(overrides: Partial<BootstrapResponse> = {}): BootstrapResponse {
  return {
    catalog_contract: 3,
    session_scope: SESSION_SCOPE,
    latest_attempt_id: null,
    school: {
      brand: {
        school_id: "north-school",
        name: "Северная школа",
        short_name: "Север",
        colors: {
          primary: "#5636D3",
          accent: "#C7F36B",
          background: "#F7F5EF",
          signal: "#D8FF42",
          ink: "#101517",
          paper: "#F5F5F0",
        },
        logo: "",
        interface: {} as Brand["interface"],
      },
      links: {
        website: "https://school.example",
        support: "https://school.example/support",
        privacy: "https://school.example/privacy",
        offers: [],
      },
    },
    diagnostics: [diagnostic],
    attempt: null,
    results: [],
    ...overrides,
  };
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

/** Per-path stubs for the JSON API. Unrouted paths answer with a bare `ok`. */
type Routes = Record<string, () => Promise<unknown | Response>>;

let routes: Routes;
let requestedPaths: string[];
let requestedBodies: Array<{ path: string; body: unknown }>;
let root: Root | null = null;
let container: HTMLElement;

function route(path: string, body: unknown): void {
  routes[path] = async () => body;
}

async function mountHome(): Promise<void> {
  container = document.createElement("div");
  document.body.appendChild(container);
  const mounted = createRoot(container);
  root = mounted;
  await act(async () => { mounted.render(<Home />); });
}

async function settle(): Promise<void> {
  await act(async () => { await Promise.resolve(); });
}

function click(selector: string): void {
  const element = container.querySelector<HTMLElement>(selector);
  if (!element) throw new Error(`missing element for ${selector}`);
  element.click();
}

/** The last question holds submission behind a summary sheet, so confirm it explicitly. */
async function confirmSubmission(): Promise<void> {
  await clickAndSettle(".confirm-sheet .primary-button");
}

async function clickAndSettle(selector: string): Promise<void> {
  await act(async () => { click(selector); });
}

function screenClasses(): string {
  return [...container.querySelectorAll("section")].map((node) => node.className).join(" | ");
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  window.localStorage.clear();
  window.scrollTo = () => undefined;
  window.Telegram = {
    WebApp: {
      initData: "signed-init-data",
      ready: () => undefined,
      expand: () => undefined,
      close: () => undefined,
      setHeaderColor: () => undefined,
      setBackgroundColor: () => undefined,
    },
  };
  routes = {};
  requestedPaths = [];
  requestedBodies = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    requestedPaths.push(path);
    if (typeof init?.body === "string") {
      requestedBodies.push({ path, body: JSON.parse(init.body) });
    }
    const handler = routes[path];
    const response = handler ? await handler() : { ok: true };
    return response instanceof Response ? response : jsonResponse(response);
  }));
});

afterEach(async () => {
  const mounted = root;
  root = null;
  if (mounted) await act(async () => { mounted.unmount(); });
  container?.remove();
  vi.unstubAllGlobals();
  delete window.Telegram;
});

describe("Home screen transitions", () => {
  it("keeps a real q10 result-grid selection through deferred review loading and scopes it by attempt", async () => {
    const firstAttempt = { ...completedAttempt, attempt_id: "attempt-done", result: resultWithGrid };
    const secondAttempt = { ...firstAttempt, attempt_id: "attempt-second", content_version: "b".repeat(64), result: { ...resultWithGrid, diagnostic_id: "demo-math" } };
    let reviewCalls = 0;
    const firstReview = deferred<unknown>();
    const secondReview = deferred<unknown>();
    routes["/api/diagnostics/bootstrap"] = async () => bootstrapPayload({ onboarding: { status: "completed" }, results: [firstAttempt, secondAttempt] });
    routes["/api/diagnostics/session/review"] = async () => {
      reviewCalls += 1;
      return reviewCalls === 1 ? firstReview.promise : secondReview.promise;
    };

    await mountHome();
    const resultButtons = [...container.querySelectorAll<HTMLButtonElement>("button.secondary-button")]
      .filter((button) => button.textContent?.includes("17 из 18"));
    expect(resultButtons).toHaveLength(2);
    await act(async () => resultButtons[0].click());
    const more = [...container.querySelectorAll<HTMLButtonElement>("button.result-checked-more")][0];
    expect(more?.textContent).toContain("Показаны первые 8 из 18");
    await act(async () => more?.click());
    const q10 = container.querySelector<HTMLButtonElement>('button[aria-label="Задание 10, Механика, неверно"]');
    expect(q10).not.toBeNull();
    await act(async () => q10?.click());
    expect(reviewCalls).toBe(1);
    firstReview.resolve({ ok: true, available: true, items: [reviewQ10], pdf_status: "sent" });
    await settle();
    expect(container.querySelector("#review-q10-title")?.textContent).toContain("Условие");
    await clickAndSettle(".review-topline .text-back");
    expect(container.querySelector("#review-list-title")?.textContent).toContain("Где ошибся");
    await clickAndSettle(".review-direct-actions .text-back:last-child");
    const secondResult = [...container.querySelectorAll<HTMLButtonElement>("button.secondary-button")]
      .find((button) => button.textContent?.includes("17 из 18"));
    expect(secondResult).not.toBeUndefined();
    await act(async () => secondResult?.click());
    await clickAndSettle(".result-actions .primary-button");
    expect(reviewCalls).toBe(2);
    secondReview.resolve({ ok: true, available: true, items: [{ ...reviewQ10, question_id: "q11", number: 11 }], pdf_status: "sent" });
    await settle();
    expect(container.querySelector("#review-list-title")?.textContent).toContain("Где ошибся");
    expect(window.sessionStorage.getItem("diagnostic-review:attempt-done:" + CONTENT_VERSION)).toBe("q10");
    expect(window.sessionStorage.getItem("diagnostic-review:attempt-second:" + "b".repeat(64))).toBeNull();
  });

  it("restores the last deferred mistake, advances to the route, and does not reopen review", async () => {
    vi.useFakeTimers();
    const attempt = { ...completedAttempt, result: resultWithThreeMistakes, pdf_status: "sent" as const };
    const reviewResponse = deferred<unknown>();
    const mistakes = [10, 11, 18].map((number) => ({
      ...reviewQ10,
      question_id: `q${number}`,
      number,
      title: `Задание ${number}`,
    }));
    routes["/api/diagnostics/bootstrap"] = async () => bootstrapPayload({ onboarding: { status: "completed" }, results: [attempt] });
    routes["/api/diagnostics/session/review"] = async () => reviewResponse.promise;
    window.sessionStorage.setItem("diagnostic-review:attempt-done:" + CONTENT_VERSION, "q18");

    try {
      await mountHome();
      const resultButton = [...container.querySelectorAll<HTMLButtonElement>("button.secondary-button")]
        .find((button) => button.textContent?.includes("15 из 18"));
      expect(resultButton).not.toBeUndefined();
      await act(async () => resultButton?.click());
      await clickAndSettle(".result-actions .primary-button");
      reviewResponse.resolve({ ok: true, available: true, items: mistakes, pdf_status: "sent" });
      await settle();

      expect(container.textContent).toContain("Разбор ошибок · 3 из 3");
      const routeButton = [...container.querySelectorAll<HTMLButtonElement>(".review-screen .primary-button")]
        .find((button) => button.textContent?.includes("Мой план подготовки"));
      expect(routeButton).not.toBeUndefined();
      await act(async () => routeButton?.click());
      expect(screenClasses()).toContain("route-screen");
      expect(requestedPaths.filter((path) => path.endsWith("/session/review"))).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("repeats the saved diagnostic from the route with its original mode", async () => {
    const attempt = { ...completedAttempt, result: { ...serverResult, xp_earned: 37 }, mode: "full" as const };
    route("/api/diagnostics/bootstrap", bootstrapPayload({
      onboarding: { status: "completed" },
      results: [attempt],
    }));
    route("/api/diagnostics/catalog", { diagnostic });

    await mountHome();
    const resultButton = [...container.querySelectorAll<HTMLButtonElement>("button.secondary-button")]
      .find((button) => button.textContent?.includes("0 из 1"));
    expect(resultButton).not.toBeUndefined();
    await act(async () => resultButton?.click());
    await clickAndSettle(".result-actions .secondary-button:last-child");
    expect(screenClasses()).toContain("forecast-empty-screen");
    await clickAndSettle(".forecast-empty-screen .primary-button");
    expect(screenClasses()).toContain("route-screen");
    expect(container.querySelector(".plan-home-action")?.textContent).toContain("+37 XP");

    await clickAndSettle(".route-repeat");
    await settle();
    expect(screenClasses()).toContain("question-screen");
    expect(requestedBodies.find(({ path }) => path === "/api/diagnostics/catalog")?.body).toMatchObject({ diagnostic_id: diagnostic.id });

    route("/api/diagnostics/session/complete", {
      ok: true,
      attempt: { ...attempt, attempt_id: "attempt-repeat", status: "completed" },
      result: { ...serverResult, mode: "full" },
    });
    await clickAndSettle(".question-skip");
    await confirmSubmission();
    await settle();
    expect(requestedBodies.find(({ path }) => path === "/api/diagnostics/session/complete")?.body).toMatchObject({ mode: "full" });
  });

  it("continues from an empty forecast to the plan when the current result has no estimate", async () => {
    const attempt = { ...completedAttempt, result: { ...serverResult, estimate: null } };
    route("/api/diagnostics/bootstrap", bootstrapPayload({
      onboarding: { status: "completed" },
      results: [attempt],
    }));

    await mountHome();
    const resultButton = [...container.querySelectorAll<HTMLButtonElement>("button.secondary-button")]
      .find((button) => button.textContent?.includes("0 из 1"));
    expect(resultButton).not.toBeUndefined();
    await act(async () => resultButton?.click());
    await clickAndSettle(".result-actions .secondary-button:last-child");

    expect(screenClasses()).toContain("forecast-empty-screen");
    expect(container.textContent).not.toContain("появится после 10");
    expect(container.textContent).not.toContain("0 ответов");
    await clickAndSettle(".forecast-empty-screen .primary-button");
    expect(screenClasses()).toContain("route-screen");
  });

  it("offers the full diagnostic from an empty quick forecast", async () => {
    const attempt = { ...completedAttempt, mode: "quick" as const, result: { ...serverResult, mode: "quick" as const, estimate: null } };
    route("/api/diagnostics/bootstrap", bootstrapPayload({
      onboarding: { status: "completed" },
      results: [attempt],
    }));
    route("/api/diagnostics/catalog", { diagnostic });

    await mountHome();
    const resultButton = [...container.querySelectorAll<HTMLButtonElement>("button.secondary-button")]
      .find((button) => button.textContent?.includes("0 из 1"));
    expect(resultButton).not.toBeUndefined();
    await act(async () => resultButton?.click());
    await clickAndSettle(".result-actions .secondary-button:last-child");
    await clickAndSettle(".forecast-empty-screen .secondary-button");
    await settle();

    expect(screenClasses()).toContain("question-screen");
    route("/api/diagnostics/session/complete", {
      ok: true,
      attempt: { ...attempt, attempt_id: "attempt-full", mode: "full", status: "completed" },
      result: { ...serverResult, mode: "full" },
    });
    vi.useFakeTimers();
    try {
      await clickAndSettle(".question-skip");
      await confirmSubmission();
      await act(async () => { vi.advanceTimersByTime(300); await Promise.resolve(); });
      await settle();
      expect(requestedBodies.find(({ path }) => path.endsWith("/api/diagnostics/session/complete"))?.body)
        .toMatchObject({ diagnostic_id: diagnostic.id, mode: "full" });
    } finally {
      vi.useRealTimers();
    }
  });

  it.each([
    ["success", { status: "scheduled", due_at: "2026-10-08T00:00:00+00:00" }, "Повтор запланирован"],
    ["error", new Error("network"), "Не удалось запланировать"],
  ])("ignores a deferred reminder %s from attempt A after switching to attempt B", async (_name, outcome, staleMessage) => {
    const attemptA = { ...completedAttempt, attempt_id: "attempt-a", result: { ...serverResult, xp_earned: 20 } };
    const attemptB = { ...completedAttempt, attempt_id: "attempt-b", result: { ...serverResult, xp_earned: 40 } };
    const reminder = deferred<unknown>();
    route("/api/diagnostics/bootstrap", bootstrapPayload({
      onboarding: { status: "completed" },
      results: [attemptA, attemptB],
    }));
    routes["/api/diagnostics/session/retest-reminder"] = async () => reminder.promise;

    await mountHome();
    const cards = container.querySelectorAll<HTMLButtonElement>(".gameplay-result-card");
    await act(async () => cards[0]?.click());
    await clickAndSettle(".result-actions .secondary-button:last-child");
    await clickAndSettle(".forecast-empty-screen .primary-button");
    await clickAndSettle(".route-action");
    expect(requestedPaths).toContain("/api/diagnostics/session/retest-reminder");

    await clickAndSettle(".plan-home-action");
    await settle();
    const refreshedCards = container.querySelectorAll<HTMLButtonElement>(".gameplay-result-card");
    await act(async () => refreshedCards[1]?.click());
    await clickAndSettle(".result-actions .secondary-button:last-child");
    await clickAndSettle(".forecast-empty-screen .primary-button");
    expect(screenClasses()).toContain("route-screen");
    expect(container.textContent).not.toContain("Повтор запланирован");

    if (outcome instanceof Error) reminder.reject(outcome);
    else reminder.resolve(outcome);
    await settle();
    expect(container.textContent).not.toContain(staleMessage);
  });

  it("shows an actionable trainer message when mistake replay has no source mistakes", async () => {
    const attempt = { ...completedAttempt, result: serverResult };
    route("/api/diagnostics/bootstrap", bootstrapPayload({
      onboarding: { status: "completed" },
      results: [attempt],
    }));
    routes["/api/diagnostics/trainer/start"] = async () => new Response(
      JSON.stringify({ detail: "trainer_no_mistakes" }),
      { status: 409, headers: { "Content-Type": "application/json" } },
    );

    await mountHome();
    const resultButton = [...container.querySelectorAll<HTMLButtonElement>("button.secondary-button")]
      .find((button) => button.textContent?.includes("0 из 1"));
    await act(async () => resultButton?.click());
    await clickAndSettle(".result-actions .secondary-button");
    await settle();
    expect(screenClasses()).toContain("trainer-screen");
    expect(container.textContent).toContain("нет ошибок для тренировки");
  });

  it("polls delivery immediately, retries pending work, and stops on terminal status", async () => {
    vi.useFakeTimers();
    const attempt = { ...completedAttempt, result: resultWithGrid, pdf_status: null };
    const pending = deferred<unknown>();
    const failed = deferred<unknown>();
    const retryPending = deferred<unknown>();
    const sent = deferred<unknown>();
    let deliveryCalls = 0;
    routes["/api/diagnostics/bootstrap"] = async () => bootstrapPayload({ onboarding: { status: "completed" }, results: [attempt] });
    routes["/api/diagnostics/session/delivery"] = async () => {
      deliveryCalls += 1;
      return [pending.promise, failed.promise, retryPending.promise, sent.promise][deliveryCalls - 1] ?? { ok: true, status: "sent" };
    };
    routes["/api/diagnostics/session/delivery/retry"] = async () => ({ ok: true, status: "pending" });

    try {
      await mountHome();
      const resultButton = [...container.querySelectorAll<HTMLButtonElement>("button.secondary-button")]
        .find((button) => button.textContent?.includes("17 из 18"));
      expect(resultButton).not.toBeUndefined();
      await act(async () => resultButton?.click());
      expect(deliveryCalls).toBe(1);
      pending.resolve({ ok: true, status: "pending" });
      await settle();
      await act(async () => { vi.advanceTimersByTime(5000); await Promise.resolve(); });
      expect(deliveryCalls).toBe(2);
      failed.resolve({ ok: true, status: "failed" });
      await settle();
      await clickAndSettle(".delivery-failed button");
      expect(requestedPaths).toContain("/api/diagnostics/session/delivery/retry");
      expect(deliveryCalls).toBe(3);
      retryPending.resolve({ ok: true, status: "pending" });
      await settle();
      await act(async () => { vi.advanceTimersByTime(5000); await Promise.resolve(); });
      expect(deliveryCalls).toBe(4);
      sent.resolve({ ok: true, status: "sent" });
      await settle();
      await act(async () => { vi.advanceTimersByTime(5000); await Promise.resolve(); });
      expect(deliveryCalls).toBe(4);
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps polling a retryable delivery failure until Telegram accepts the result", async () => {
    vi.useFakeTimers();
    const attempt = { ...completedAttempt, result: resultWithGrid, pdf_status: null };
    let deliveryCalls = 0;
    routes["/api/diagnostics/bootstrap"] = async () => bootstrapPayload({ onboarding: { status: "completed" }, results: [attempt] });
    routes["/api/diagnostics/session/delivery"] = async () => {
      deliveryCalls += 1;
      return { ok: true, status: deliveryCalls === 1 ? "failed" : "sent" };
    };

    try {
      await mountHome();
      const resultButton = [...container.querySelectorAll<HTMLButtonElement>("button.secondary-button")]
        .find((button) => button.textContent?.includes("17 из 18"));
      expect(resultButton).not.toBeUndefined();
      await act(async () => resultButton?.click());
      await settle();
      expect(deliveryCalls).toBe(1);
      expect(container.textContent).toContain("Не удалось отправить результат");

      await act(async () => {
        vi.advanceTimersByTime(5000);
        await Promise.resolve();
      });
      await settle();
      expect(deliveryCalls).toBe(2);
      expect(container.textContent).not.toContain("Не удалось отправить результат");
    } finally {
      vi.useRealTimers();
    }
  });

  it("ignores a late delivery response after leaving the result screen", async () => {
    vi.useFakeTimers();
    const attempt = { ...completedAttempt, result: resultWithGrid, pdf_status: null };
    const response = deferred<unknown>();
    routes["/api/diagnostics/bootstrap"] = async () => bootstrapPayload({ onboarding: { status: "completed" }, results: [attempt] });
    routes["/api/diagnostics/session/delivery"] = async () => response.promise;
    try {
      await mountHome();
      const resultButton = [...container.querySelectorAll<HTMLButtonElement>("button.secondary-button")]
        .find((button) => button.textContent?.includes("17 из 18"));
      await act(async () => resultButton?.click());
      expect(requestedPaths.filter((path) => path.endsWith("/session/delivery"))).toHaveLength(1);
      await act(async () => root?.unmount());
      root = null;
      response.resolve({ ok: true, status: "sent" });
      await act(async () => { await Promise.resolve(); vi.advanceTimersByTime(10_000); });
      expect(requestedPaths.filter((path) => path.endsWith("/session/delivery"))).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });
  it("persists first selection, runs quick diagnostic, then refreshes home and exposes the first route", async () => {
    route("/api/diagnostics/bootstrap", bootstrapPayload({ onboarding: { status: "welcome" } }));
    route("/api/diagnostics/onboarding", { status: "selection" });
    route("/api/diagnostics/catalog", { diagnostic });
    route("/api/diagnostics/session/complete", { ok: true, attempt: completedAttempt, result: serverResult });
    await mountHome();
    await clickAndSettle(".welcome-screen .primary-button");
    expect(requestedPaths).toContain("/api/diagnostics/onboarding");
    expect(container.querySelector("#subject-title")).not.toBeNull();
    expect(container.querySelector("#mode-title")).toBeNull();
    expect(screenClasses()).not.toContain("gameplay-home");
    expect(container.querySelector("#subject-title")).not.toBeNull();
    await clickAndSettle(".subject-card");
    expect(container.querySelector("#mode-title")).not.toBeNull();
    await clickAndSettle(".mode-card:not(.featured)");
    await clickAndSettle(".answer-option");
    route("/api/diagnostics/bootstrap", bootstrapPayload({
      onboarding: { status: "completed" },
      progress_profile: { completion_count: 1, achievement_keys: ["first_diagnostic_completed"] },
      daily_plan: { status: "ready", diagnostic_id: diagnostic.id, subject: diagnostic.subject, exam: diagnostic.exam, plan_date: "2026-09-06", total: 1, completed: 0 },
    }));
    await clickAndSettle(".question-next");
    vi.useFakeTimers();
    await confirmSubmission();
    expect(screenClasses()).toContain("submit-screen");
    expect(container.querySelector(".submit-note")).toBeNull();
    await act(async () => { vi.advanceTimersByTime(299); await Promise.resolve(); });
    expect(screenClasses()).toContain("submit-screen");
    await act(async () => { vi.advanceTimersByTime(1); await Promise.resolve(); });
    await settle();
    expect(screenClasses()).toContain("result-screen");
    expect(container.querySelector(".submit-note")).toBeNull();
    const completionCall = vi.mocked(fetch).mock.calls.find(([path]) => String(path).endsWith("/session/complete"));
    expect(JSON.parse(String(completionCall?.[1]?.body)).mode).toBe("quick");
    expect(container.textContent).not.toContain("Прогноз баллов");
    vi.useRealTimers();
    await clickAndSettle(".result-actions .secondary-button:last-child");
    expect(screenClasses()).toContain("route-screen");
    await clickAndSettle(".bottom-nav button:first-child");
    expect(screenClasses()).toContain("gameplay-home");
    expect(container.textContent).toContain("1 диагностика завершена");
    expect(container.textContent).toContain("Задания на сегодня");
  });

  it("resumes persisted selection without showing the dashboard", async () => {
    route("/api/diagnostics/bootstrap", bootstrapPayload({ onboarding: { status: "selection" } }));
    await mountHome();
    expect(container.querySelector("#subject-title")).not.toBeNull();
    expect(screenClasses()).not.toContain("gameplay-home");
    expect(container.querySelector("#subject-title")).not.toBeNull();
  });

  it("refreshes completed trainer progress before returning home", async () => {
    const initial = bootstrapPayload({
      onboarding: { status: "completed" },
      progress_profile: { completion_count: 1, achievement_keys: [] },
      gameplay_profile: { xp_total: 0, level: 1, level_progress: 0, streak_days: 0, lives_remaining: 5, daily_goal: { date: null, target: 3, progress: 0, complete: false }, quest: null },
    });
    route("/api/diagnostics/bootstrap", initial);
    route("/api/diagnostics/trainer/start", {
      trainer_session_id: "s".repeat(32), diagnostic_id: diagnostic.id, content_version: CONTENT_VERSION,
      mode: "normal", question_ids: ["q1"], current_index: 0, revision: 1, status: "active", questions: diagnostic.questions, lives_remaining: 5,
    });
    route("/api/diagnostics/trainer/answer", {
      trainer_session_id: "s".repeat(32), question_id: "q1", is_correct: true, correct_answer: "A", explanation: null,
      xp_delta: 10, life_delta: 0, current_index: 1, revision: 2, status: "active", lives_remaining: 5,
    });
    route("/api/diagnostics/trainer/finish", {
      trainer_session_id: "s".repeat(32), status: "completed", revision: 3, current_index: 1,
      question_count: 1, answered_count: 1, correct_count: 1, xp_earned: 10, lives_spent: 0, lives_remaining: 5,
    });
    await mountHome();
    await clickAndSettle(".bottom-nav button:nth-child(2)");
    await clickAndSettle(".answer-option");
    route("/api/diagnostics/bootstrap", { ...initial, gameplay_profile: { ...initial.gameplay_profile, xp_total: 10, streak_days: 1 } });
    await clickAndSettle(".question-next");
    await clickAndSettle(".question-next");
    expect(container.querySelector(".trainer-complete")).not.toBeNull();
    await clickAndSettle(".trainer-complete button");
    expect(container.querySelector(".gameplay-dashboard")?.textContent).toContain("10 XP");
  });

  it("opens a persisted result after its diagnostic has left the catalog", async () => {
    route("/api/diagnostics/bootstrap", bootstrapPayload({
      onboarding: { status: "completed" },
      results: [{ ...completedAttempt, diagnostic_id: "removed", exam: "ОГЭ", subject: "Архивный предмет", result: { ...serverResult, diagnostic_id: "removed" } }],
    }));
    await mountHome();
    await clickAndSettle('[aria-label="Предыдущие результаты"] button');
    expect(screenClasses()).toContain("result-screen");
    expect(container.textContent).toContain("Архивный предмет");
    expect(requestedPaths).not.toContain("/api/diagnostics/catalog");
    expect(container.textContent).not.toContain("Отработать ошибки");
  });

  it("moves from loading to welcome on a first visit", async () => {
    const gate = deferred<BootstrapResponse>();
    routes["/api/diagnostics/bootstrap"] = () => gate.promise;

    await mountHome();
    expect(screenClasses()).toContain("loading-screen");

    await act(async () => { gate.resolve(bootstrapPayload()); });
    expect(screenClasses()).toContain("welcome-screen");
    const brand = container.querySelector(".brand");
    expect(brand?.tagName).toBe("DIV");
    expect(brand?.closest("button, a")).toBeNull();
    expect(requestedPaths).toContain("/api/diagnostics/bootstrap");
  });

  it("moves from loading straight to home for a returning user with results", async () => {
    route("/api/diagnostics/bootstrap", bootstrapPayload({
      latest_attempt_id: completedAttempt.attempt_id,
      results: [completedAttempt],
      progress_profile: { completion_count: 1, achievement_keys: [] },
    }));

    await mountHome();
    expect(screenClasses()).toContain("gameplay-home");
    expect(screenClasses()).not.toContain("welcome-screen");
  });

  it("walks home to mode to subjects to the loading state and into the question", async () => {
    route("/api/diagnostics/bootstrap", bootstrapPayload({
      progress_profile: { completion_count: 1, achievement_keys: [] },
    }));
    const catalog = deferred<{ diagnostic: PublicDiagnostic }>();
    routes["/api/diagnostics/catalog"] = () => catalog.promise;

    await mountHome();
    expect(screenClasses()).toContain("gameplay-home");

    await clickAndSettle(".gameplay-home-cta");
    expect(container.querySelector("#subject-title")).not.toBeNull();

    await clickAndSettle(".subject-card");
    expect(container.querySelector("#mode-title")).not.toBeNull();
    await clickAndSettle(".mode-card.featured");

    // The catalog request is still open, so the interstitial has to be visible.
    expect(container.textContent).toContain("Загружаем задания…");

    await act(async () => { catalog.resolve({ diagnostic }); });
    expect(screenClasses()).toContain("question-screen");
    expect(container.textContent).toContain("Выберите ответ");
    expect(container.querySelector(".brand-bar")).toBeNull();
    expect(container.querySelector(".status-pill")).toBeNull();
    expect(container.querySelector(".assessment-header-title")?.textContent).toContain("Задание 1 из 1 · Тема 1");
  });

  it("confirms diagnostic exit and restores focus to the header trigger", async () => {
    route("/api/diagnostics/bootstrap", bootstrapPayload({
      progress_profile: { completion_count: 1, achievement_keys: [] },
    }));
    route("/api/diagnostics/catalog", { diagnostic });

    await mountHome();
    await clickAndSettle(".gameplay-home-cta");
    await clickAndSettle(".subject-card");
    await clickAndSettle(".mode-card.featured");
    await settle();

    const trigger = container.querySelector<HTMLButtonElement>(".assessment-header-exit");
    expect(trigger).not.toBeNull();
    trigger!.focus();
    await act(async () => { trigger!.click(); });
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain("Выйти из диагностики?");
    await clickAndSettle(".confirm-sheet .secondary-button");
    expect(document.activeElement).toBe(trigger);
  });

  it("flushes an immediate answer before confirming diagnostic exit", async () => {
    route("/api/diagnostics/bootstrap", bootstrapPayload({
      progress_profile: { completion_count: 1, achievement_keys: [] },
    }));
    route("/api/diagnostics/catalog", { diagnostic });
    routes["/api/diagnostics/session/progress"] = async () => {
      const payload = requestedBodies.filter(({ path }) => path.endsWith("/api/diagnostics/session/progress")).at(-1)?.body as { attempt_id: string; answers: Record<string, unknown> };
      return {
        ok: true,
        attempt: {
          attempt_id: payload.attempt_id,
          diagnostic_id: diagnostic.id,
          content_version: CONTENT_VERSION,
          mode: "quick",
          status: "in_progress",
          question_index: 0,
          question_count: 1,
          progress_revision: 1,
          answers: payload.answers,
        },
      };
    };

    await mountHome();
    await clickAndSettle(".gameplay-home-cta");
    await clickAndSettle(".subject-card");
    await clickAndSettle(".mode-card.featured");
    await settle();
    await clickAndSettle(".answer-option");
    await clickAndSettle(".assessment-header-exit");
    await clickAndSettle(".confirm-sheet .primary-button");

    expect(requestedPaths.filter((path) => path.endsWith("/api/diagnostics/session/progress")).length).toBeGreaterThan(0);
    expect(screenClasses()).toContain("gameplay-home");
  });

  it("keeps exit open after a progress conflict and retries with the recovered snapshot", async () => {
    let bootstrapCalls = 0;
    let progressCalls = 0;
    const recoveredAttempt: ServerAttempt = {
      ...completedAttempt,
      attempt_id: "attempt-recovered",
      status: "in_progress",
      question_index: 0,
      progress_revision: 4,
      answers: { q1: "a" },
    };
    routes["/api/diagnostics/bootstrap"] = async () => {
      bootstrapCalls += 1;
      return bootstrapPayload(bootstrapCalls > 1 ? {
        onboarding: { status: "completed" },
        progress_profile: { completion_count: 1, achievement_keys: [] },
        attempt: recoveredAttempt,
      } : {
        onboarding: { status: "completed" },
        progress_profile: { completion_count: 1, achievement_keys: [] },
      });
    };
    route("/api/diagnostics/catalog", { diagnostic });
    routes["/api/diagnostics/session/progress"] = async () => {
      progressCalls += 1;
      if (progressCalls === 1) return new Response(JSON.stringify({ detail: "progress_conflict" }), { status: 409 });
      const payload = requestedBodies.filter(({ path }) => path.endsWith("/api/diagnostics/session/progress")).at(-1)?.body as { attempt_id: string; answers: Record<string, unknown> };
      return {
        ok: true,
        attempt: { ...recoveredAttempt, attempt_id: payload.attempt_id, answers: payload.answers, progress_revision: 5 },
      };
    };

    await mountHome();
    await clickAndSettle(".gameplay-home-cta");
    await clickAndSettle(".subject-card");
    await clickAndSettle(".mode-card.featured");
    await settle();
    await clickAndSettle(".answer-option");
    await clickAndSettle(".assessment-header-exit");
    await clickAndSettle(".confirm-sheet .primary-button");

    expect(container.querySelector('[role="dialog"]')?.getAttribute("role")).toBe("dialog");
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("Не удалось сохранить прогресс");
    expect(screenClasses()).toContain("question-screen");
    expect(progressCalls).toBe(1);

    await clickAndSettle(".confirm-sheet .primary-button");
    expect(progressCalls).toBe(2);
    expect(screenClasses()).toContain("gameplay-home");
  });

  it("resumes autosave after a failed conflict recovery", async () => {
    let bootstrapCalls = 0;
    let progressCalls = 0;
    routes["/api/diagnostics/bootstrap"] = async () => {
      bootstrapCalls += 1;
      if (bootstrapCalls > 1) return new Response(JSON.stringify({ detail: "temporary_unavailable" }), { status: 503 });
      return bootstrapPayload({ onboarding: { status: "completed" }, progress_profile: { completion_count: 1, achievement_keys: [] } });
    };
    route("/api/diagnostics/catalog", { diagnostic });
    routes["/api/diagnostics/session/progress"] = async () => {
      progressCalls += 1;
      if (progressCalls === 1) return new Response(JSON.stringify({ detail: "progress_conflict" }), { status: 409 });
      const payload = requestedBodies.filter(({ path }) => path.endsWith("/api/diagnostics/session/progress")).at(-1)?.body as { attempt_id: string; answers: Record<string, unknown> };
      return { ok: true, attempt: { ...completedAttempt, attempt_id: payload.attempt_id, status: "in_progress", answers: payload.answers } };
    };

    await mountHome();
    await clickAndSettle(".gameplay-home-cta");
    await clickAndSettle(".subject-card");
    await clickAndSettle(".mode-card.featured");
    await settle();
    await clickAndSettle(".answer-option");
    await clickAndSettle(".assessment-header-exit");
    await clickAndSettle(".confirm-sheet .primary-button");
    expect(progressCalls).toBe(1);
    await clickAndSettle(".confirm-sheet .secondary-button");
    await clickAndSettle(".answer-option:nth-child(2)");
    await act(async () => { await new Promise((resolve) => window.setTimeout(resolve, 350)); });
    expect(progressCalls).toBe(2);
  });

  it("moves from the last question through submitting to the result, then to review", async () => {
    route("/api/diagnostics/bootstrap", bootstrapPayload({
      progress_profile: { completion_count: 1, achievement_keys: [] },
    }));
    route("/api/diagnostics/catalog", { diagnostic });
    const completion = deferred<unknown>();
    routes["/api/diagnostics/session/complete"] = () => completion.promise;
    route("/api/diagnostics/session/review", {
      ok: true,
      available: true,
      items: [{
        question_id: "q1",
        number: 1,
        type: "single",
        topic: "Тема 1",
        title: "Задание 1",
        prompt: "Выберите ответ",
        is_correct: false,
        status: "incorrect",
        user_answer: "A",
        expected_answer: "B",
        guidance: "Повтори тему.",
        guidance_kind: "individual",
      }],
    });

    await mountHome();
    await clickAndSettle(".gameplay-home-cta");
    await clickAndSettle(".subject-card");
    await clickAndSettle(".mode-card.featured");
    await settle();
    expect(screenClasses()).toContain("question-screen");

    await clickAndSettle(".answer-option");
    await clickAndSettle(".question-next");
    vi.useFakeTimers();
    await confirmSubmission();
    expect(screenClasses()).toContain("submit-screen");
    expect(container.querySelector(".submit-note")).toBeNull();

    await act(async () => { vi.advanceTimersByTime(299); await Promise.resolve(); });
    expect(screenClasses()).toContain("submit-screen");
    expect(container.querySelector(".submit-note")).toBeNull();
    await act(async () => { vi.advanceTimersByTime(1); await Promise.resolve(); });
    expect(container.querySelector(".submit-note")?.textContent).toBe("Не закрывай приложение");

    await act(async () => {
      completion.resolve({
        ok: true,
        attempt: { ...completedAttempt, attempt_id: "attempt-fresh" },
        result: serverResult,
      });
    });
    await settle();
    expect(screenClasses()).toContain("result-screen");
    vi.useRealTimers();
    expect(requestedPaths).toContain("/api/diagnostics/session/viewed");

    await clickAndSettle(".result-actions .primary-button");
    await settle();
    expect(screenClasses()).toContain("review-screen");
    expect(container.textContent).toContain("Тема 1");
  });

  it("submits the canonical empty marker when the last question is skipped", async () => {
    route("/api/diagnostics/bootstrap", bootstrapPayload({
      progress_profile: { completion_count: 1, achievement_keys: [] },
    }));
    route("/api/diagnostics/catalog", { diagnostic });
    const completion = deferred<unknown>();
    routes["/api/diagnostics/session/complete"] = () => completion.promise;

    await mountHome();
    await clickAndSettle(".gameplay-home-cta");
    await clickAndSettle(".subject-card");
    await clickAndSettle(".mode-card.featured");
    await settle();

    expect(container.textContent).toContain("Пропустить");
    await clickAndSettle(".question-skip");
    // N-09: the skip on the last question opens the summary instead of submitting.
    expect(screenClasses()).toContain("question-screen");
    expect(container.querySelector(".submit-review-list")?.textContent).toContain("Задание 1");
    await confirmSubmission();
    expect(screenClasses()).toContain("submit-screen");
    expect(requestedBodies.find(({ path }) => path === "/api/diagnostics/session/complete")?.body).toMatchObject({
      question_count: 1,
      answers: { q1: "" },
    });
  });

  it("cleans the submit warning timer after a completion error", async () => {
    route("/api/diagnostics/bootstrap", bootstrapPayload({ progress_profile: { completion_count: 1, achievement_keys: [] } }));
    route("/api/diagnostics/catalog", { diagnostic });
    routes["/api/diagnostics/session/complete"] = async () => new Response(
      JSON.stringify({ detail: "temporary_unavailable" }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    );

    await mountHome();
    await clickAndSettle(".gameplay-home-cta");
    await clickAndSettle(".subject-card");
    await clickAndSettle(".mode-card.featured");
    await settle();
    await clickAndSettle(".answer-option");

    vi.useFakeTimers();
    await clickAndSettle(".question-next");
    await settle();
    expect(screenClasses()).toContain("question-screen");
    expect(container.querySelector(".submit-note")).toBeNull();
    await act(async () => { vi.advanceTimersByTime(1_000); await Promise.resolve(); });
    expect(container.querySelector(".submit-note")).toBeNull();
    vi.useRealTimers();
  });

  it("lets the user replace a skipped answer after going back", async () => {
    const secondQuestion = { ...diagnostic.questions[0], id: "q2", title: "Задание 2" };
    const twoQuestionDiagnostic: PublicDiagnostic = {
      ...diagnostic,
      quick_count: 2,
      full_count: 2,
      question_count: 2,
      questions: [diagnostic.questions[0], secondQuestion],
    };
    route("/api/diagnostics/bootstrap", bootstrapPayload({
      diagnostics: [twoQuestionDiagnostic],
      progress_profile: { completion_count: 1, achievement_keys: [] },
    }));
    route("/api/diagnostics/catalog", { diagnostic: twoQuestionDiagnostic });
    const completion = deferred<unknown>();
    routes["/api/diagnostics/session/complete"] = () => completion.promise;

    await mountHome();
    await clickAndSettle(".gameplay-home-cta");
    await clickAndSettle(".subject-card");
    await clickAndSettle(".mode-card.featured");
    await settle();

    await clickAndSettle(".question-skip");
    await clickAndSettle(".back-button");
    expect(container.textContent).toContain("Задание пропущено");

    await clickAndSettle(".answer-option");
    expect(container.textContent).not.toContain("Задание пропущено");
    await clickAndSettle(".question-next");
    await clickAndSettle(".question-skip");
    await confirmSubmission();

    expect(requestedBodies.find(({ path }) => path === "/api/diagnostics/session/complete")?.body).toMatchObject({
      question_count: 2,
      answers: { q1: "a", q2: "" },
    });
  });

  it("moves from home into the trainer", async () => {
    route("/api/diagnostics/bootstrap", bootstrapPayload({
      progress_profile: { completion_count: 1, achievement_keys: [] },
    }));
    route("/api/diagnostics/trainer/start", {
      trainer_session_id: "s".repeat(32),
      diagnostic_id: "demo-math",
      content_version: CONTENT_VERSION,
      mode: "normal",
      question_ids: ["q1"],
      current_index: 0,
      revision: 1,
      status: "active",
      questions: diagnostic.questions,
      lives_remaining: 5,
    });

    await mountHome();
    await clickAndSettle(".bottom-nav button:nth-child(2)");
    await settle();

    expect(screenClasses()).toContain("trainer-screen");
    expect(requestedPaths).toContain("/api/diagnostics/trainer/start");
  });

  it("confirms the trainer exit before returning to the home screen", async () => {
    route("/api/diagnostics/bootstrap", bootstrapPayload({
      progress_profile: { completion_count: 1, achievement_keys: [] },
    }));
    route("/api/diagnostics/trainer/start", {
      trainer_session_id: "s".repeat(32),
      diagnostic_id: diagnostic.id,
      content_version: CONTENT_VERSION,
      mode: "normal",
      question_ids: ["q1"],
      current_index: 0,
      revision: 1,
      status: "active",
      questions: diagnostic.questions,
      lives_remaining: 5,
    });

    await mountHome();
    await clickAndSettle(".bottom-nav button:nth-child(2)");
    await settle();
    expect(screenClasses()).toContain("trainer-screen");

    await clickAndSettle(".trainer-exit");
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain("Выйти из тренировки?");
    await clickAndSettle(".confirm-sheet .secondary-button");
    expect(screenClasses()).toContain("trainer-screen");
    await clickAndSettle(".trainer-exit");
    await clickAndSettle(".confirm-sheet .primary-button");
    expect(screenClasses()).toContain("gameplay-home");
  });

  it("starts the trainer from the latest completed diagnostic instead of the first catalog item", async () => {
    const latestAttempt: ServerAttempt = {
      ...completedAttempt,
      attempt_id: "attempt-latest",
      diagnostic_id: secondDiagnostic.id,
      exam: secondDiagnostic.exam,
      subject: secondDiagnostic.subject,
      result: { ...serverResult, diagnostic_id: secondDiagnostic.id },
    };
    route("/api/diagnostics/bootstrap", bootstrapPayload({
      diagnostics: [diagnostic, secondDiagnostic],
      latest_attempt_id: latestAttempt.attempt_id,
      results: [latestAttempt],
      progress_profile: { completion_count: 1, achievement_keys: [] },
    }));
    route("/api/diagnostics/trainer/start", {
      trainer_session_id: "s".repeat(32),
      diagnostic_id: secondDiagnostic.id,
      content_version: CONTENT_VERSION,
      mode: "normal",
      question_ids: ["q1"],
      current_index: 0,
      revision: 1,
      status: "active",
      questions: secondDiagnostic.questions,
      lives_remaining: 5,
    });

    await mountHome();
    await clickAndSettle(".bottom-nav button:nth-child(2)");
    await settle();

    const startCall = vi.mocked(fetch).mock.calls.find(([path]) => String(path).endsWith("/api/diagnostics/trainer/start"));
    expect(JSON.parse(String(startCall?.[1]?.body))).toMatchObject({ diagnostic_id: secondDiagnostic.id });
  });

  it("moves from the home plan CTA into the plan trainer", async () => {
    route("/api/diagnostics/bootstrap", bootstrapPayload({
      diagnostics: [diagnostic, secondDiagnostic],
      progress_profile: { completion_count: 1, achievement_keys: [] },
      daily_plan: {
        plan_date: "2026-09-02",
        diagnostic_id: secondDiagnostic.id,
        subject: secondDiagnostic.subject,
        exam: secondDiagnostic.exam,
        total: 5,
        completed: 2,
        status: "ready",
      },
    }));
    let startPayload: unknown;
    routes["/api/diagnostics/trainer/start"] = async () => ({
      trainer_session_id: "s".repeat(32),
      diagnostic_id: secondDiagnostic.id,
      content_version: CONTENT_VERSION,
      mode: "plan",
      question_ids: ["q1"],
      current_index: 0,
      revision: 1,
      status: "active",
      questions: secondDiagnostic.questions,
      lives_remaining: 5,
      plan: { plan_date: "2026-09-02", total: 5, completed: 2, reasons: { q1: "mistake_review" } },
    });
    const originalFetch = globalThis.fetch;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith("/api/diagnostics/trainer/start")) {
        startPayload = JSON.parse(String(init?.body));
      }
      return originalFetch(input, init);
    }));

    await mountHome();
    expect(container.querySelector(".gameplay-plan-cta")?.textContent).toContain("Задания на сегодня: 2 из 5");

    await clickAndSettle(".gameplay-plan-cta");
    await settle();

    expect(screenClasses()).toContain("trainer-screen");
    expect(startPayload).toMatchObject({ mode: "plan", diagnostic_id: secondDiagnostic.id });
    expect(container.querySelector(".trainer-progress")?.textContent).toContain("Тема 1");
    expect(container.textContent).toContain("План: 2 из 5");
    expect(container.textContent).toContain("повтор ошибки");
  });

  it("loads the league through the bottom navigation on first visit", async () => {
    route("/api/diagnostics/bootstrap", bootstrapPayload({ onboarding: { status: "completed" } }));
    route("/api/diagnostics/league", {
      status: "active", week_start: "2026-09-07", week_end: "2026-09-13",
      rows: [{ rank: 1, display_label: "Аня", xp_week: 42, is_me: true }],
      me: { rank: 1, xp_week: 42 },
    });

    await mountHome();
    await clickAndSettle(".bottom-nav button:nth-child(3)");
    await settle();

    expect(screenClasses()).toContain("league-screen");
    expect(requestedPaths).toContain("/api/diagnostics/league");
    expect(container.textContent).toContain("7–13 сентября");
  });

  it("routes a missing trainer selection through subjects and starts directly", async () => {
    route("/api/diagnostics/bootstrap", bootstrapPayload({ onboarding: { status: "completed" }, diagnostics: [diagnostic, secondDiagnostic], results: [], progress_profile: { completion_count: 0, achievement_keys: [] } }));
    route("/api/diagnostics/trainer/start", {
      trainer_session_id: "s".repeat(32), diagnostic_id: diagnostic.id, content_version: CONTENT_VERSION,
      mode: "normal", question_ids: ["q1"], current_index: 0, revision: 1, status: "active", questions: diagnostic.questions, lives_remaining: 5,
    });

    await mountHome();
    await clickAndSettle(".bottom-nav button:nth-child(2)");
    expect(container.querySelector("#subject-title")).not.toBeNull();
    expect(container.querySelector("#mode-title")).toBeNull();
    await clickAndSettle(".subject-card");
    await settle();

    expect(container.querySelector("#mode-title")).toBeNull();
    expect(screenClasses()).toContain("trainer-screen");
    expect(requestedPaths).toContain("/api/diagnostics/trainer/start");
  });

  it("clears a cancelled trainer intent before a fresh onboarding selection", async () => {
    route("/api/diagnostics/bootstrap", bootstrapPayload({
      onboarding: { status: "welcome" },
      diagnostics: [diagnostic, secondDiagnostic],
      results: [],
      progress_profile: { completion_count: 0, achievement_keys: [] },
    }));
    route("/api/diagnostics/onboarding", { status: "selection" });

    await mountHome();
    await clickAndSettle(".bottom-nav button:nth-child(2)");
    expect(container.querySelector("#subject-title")).not.toBeNull();
    await clickAndSettle(".navigation-screen .text-back");
    expect(container.querySelector("#welcome-title")).not.toBeNull();

    await clickAndSettle(".welcome-screen .primary-button");
    expect(container.querySelector("#subject-title")).not.toBeNull();
    await clickAndSettle(".subject-card");

    expect(container.querySelector("#mode-title")).not.toBeNull();
    expect(container.querySelector(".trainer-screen")).toBeNull();
    expect(requestedPaths).not.toContain("/api/diagnostics/trainer/start");
  });

  it("uses the same subject-first start from profile as from home", async () => {
    route("/api/diagnostics/bootstrap", bootstrapPayload({ onboarding: { status: "completed" } }));
    await mountHome();
    await clickAndSettle(".bottom-nav button:nth-child(4)");
    expect(screenClasses()).toContain("gameplay-profile");
    await clickAndSettle(".gameplay-profile .primary-button");

    expect(container.querySelector("#subject-title")).not.toBeNull();
    expect(container.querySelector("#mode-title")).toBeNull();
  });

  it("marks the plan done on the home screen once every question is answered", async () => {
    route("/api/diagnostics/bootstrap", bootstrapPayload({
      progress_profile: { completion_count: 1, achievement_keys: [] },
      daily_plan: {
        plan_date: "2026-09-02",
        diagnostic_id: "demo-math",
        subject: "Математика",
        exam: "ЕГЭ",
        total: 5,
        completed: 5,
        status: "done",
      },
    }));

    await mountHome();

    expect(container.querySelector(".gameplay-plan-cta")).toBeNull();
    expect(container.querySelector(".gameplay-plan-done")?.textContent).toContain("План выполнен");
    expect(container.querySelector(".gameplay-home-cta")?.className).toContain("primary-button");
  });
});
