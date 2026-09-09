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
  score: 0,
  max_score: 1,
  score_unit: "балл",
  strong_topics: [],
  growth_topics: ["Тема 1"],
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
  const promise = new Promise<T>((resolvePromise) => { resolve = resolvePromise; });
  return { promise, resolve };
}

/** Per-path stubs for the JSON API. Unrouted paths answer with a bare `ok`. */
type Routes = Record<string, () => Promise<unknown>>;

let routes: Routes;
let requestedPaths: string[];
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
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input);
    requestedPaths.push(path);
    const handler = routes[path];
    return jsonResponse(handler ? await handler() : { ok: true });
  }));
});

afterEach(async () => {
  const mounted = root;
  root = null;
  if (mounted) await act(async () => { mounted.unmount(); });
  container?.remove();
  vi.unstubAllGlobals();
  delete window.Telegram;
  window.history.replaceState({}, "", "/");
});

describe("Home screen transitions", () => {
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
    await clickAndSettle(".brand");
    expect(container.querySelector("#subject-title")).not.toBeNull();
    await clickAndSettle(".subject-card");
    await clickAndSettle(".answer-option");
    route("/api/diagnostics/bootstrap", bootstrapPayload({
      onboarding: { status: "completed" },
      progress_profile: { completion_count: 1, achievement_keys: ["first_diagnostic_completed"] },
      daily_plan: { status: "ready", diagnostic_id: diagnostic.id, subject: diagnostic.subject, exam: diagnostic.exam, plan_date: "2026-09-06", total: 1, completed: 0 },
    }));
    await clickAndSettle(".question-next");
    expect(screenClasses()).toContain("result-screen");
    const completionCall = vi.mocked(fetch).mock.calls.find(([path]) => String(path).endsWith("/session/complete"));
    expect(JSON.parse(String(completionCall?.[1]?.body)).mode).toBe("quick");
    expect(container.textContent).not.toContain("Прогноз баллов");
    await clickAndSettle(".result-actions .secondary-button:last-child");
    expect(screenClasses()).toContain("route-screen");
    await clickAndSettle(".brand");
    expect(screenClasses()).toContain("gameplay-home");
    expect(container.textContent).toContain("1 диагностика завершена");
    expect(container.textContent).toContain("План на сегодня");
  });

  it("resumes persisted selection without showing the dashboard", async () => {
    route("/api/diagnostics/bootstrap", bootstrapPayload({ onboarding: { status: "selection" } }));
    await mountHome();
    expect(container.querySelector("#subject-title")).not.toBeNull();
    expect(screenClasses()).not.toContain("gameplay-home");
    await clickAndSettle(".brand");
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
    await clickAndSettle(".gameplay-trainer-cta");
    await clickAndSettle(".answer-option");
    route("/api/diagnostics/bootstrap", { ...initial, gameplay_profile: { ...initial.gameplay_profile, xp_total: 10, streak_days: 1 } });
    await clickAndSettle(".question-next");
    await clickAndSettle(".question-next");
    expect(container.querySelector(".trainer-complete")).not.toBeNull();
    await clickAndSettle(".trainer-complete button");
    expect(container.querySelector(".gameplay-home-status")?.textContent).toContain("1день подряд");
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
    expect(container.textContent).not.toContain("Повторить ошибки");
  });

  it("moves from loading to welcome on a first visit", async () => {
    const gate = deferred<BootstrapResponse>();
    routes["/api/diagnostics/bootstrap"] = () => gate.promise;

    await mountHome();
    expect(screenClasses()).toContain("loading-screen");

    await act(async () => { gate.resolve(bootstrapPayload()); });
    expect(screenClasses()).toContain("welcome-screen");
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
    expect(container.querySelector("#mode-title")).not.toBeNull();

    await clickAndSettle(".mode-card.featured");
    expect(container.querySelector("#subject-title")).not.toBeNull();

    // The catalog request is still open, so the interstitial has to be visible.
    await clickAndSettle(".subject-card");
    expect(container.textContent).toContain("Загружаем задания…");

    await act(async () => { catalog.resolve({ diagnostic }); });
    expect(screenClasses()).toContain("question-screen");
    expect(container.textContent).toContain("Выберите ответ");
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
      pdf_status: "sent",
      items: [{
        question_id: "q1",
        number: 1,
        type: "single",
        topic: "Тема 1",
        title: "Задание 1",
        prompt: "Выберите ответ",
        is_correct: false,
        user_answer: "A",
        expected_answer: "B",
        guidance: "Повтори тему.",
        guidance_kind: "individual",
      }],
    });

    await mountHome();
    await clickAndSettle(".gameplay-home-cta");
    await clickAndSettle(".mode-card.featured");
    await clickAndSettle(".subject-card");
    await settle();
    expect(screenClasses()).toContain("question-screen");

    await clickAndSettle(".answer-option");
    await clickAndSettle(".question-next");
    expect(screenClasses()).toContain("submit-screen");

    await act(async () => {
      completion.resolve({
        ok: true,
        attempt: { ...completedAttempt, attempt_id: "attempt-fresh" },
        result: serverResult,
      });
    });
    await settle();
    expect(screenClasses()).toContain("result-screen");
    expect(requestedPaths).toContain("/api/diagnostics/session/viewed");

    await clickAndSettle(".result-actions .primary-button");
    await settle();
    expect(screenClasses()).toContain("review-screen");
    expect(container.textContent).toContain("Повтори тему.");
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
    await clickAndSettle(".gameplay-trainer-cta");
    await settle();

    expect(screenClasses()).toContain("trainer-screen");
    expect(requestedPaths).toContain("/api/diagnostics/trainer/start");
  });

  it("opens the plan screen from the home CTA and starts the plan from there", async () => {
    route("/api/diagnostics/bootstrap", bootstrapPayload({
      progress_profile: { completion_count: 1, achievement_keys: [] },
      daily_plan: {
        plan_date: "2026-09-02",
        diagnostic_id: "demo-math",
        subject: "Математика",
        exam: "ЕГЭ",
        total: 5,
        completed: 2,
        status: "ready",
      },
    }));
    let startPayload: unknown;
    routes["/api/diagnostics/trainer/start"] = async () => ({
      trainer_session_id: "s".repeat(32),
      diagnostic_id: "demo-math",
      content_version: CONTENT_VERSION,
      mode: "plan",
      question_ids: ["q1"],
      current_index: 0,
      revision: 1,
      status: "active",
      questions: diagnostic.questions,
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

    route("/api/diagnostics/daily-plan", {
      plan_date: "2026-09-02",
      diagnostic_id: "demo-math",
      subject: "Математика",
      exam: "ЕГЭ",
      total: 5,
      completed: 2,
      status: "ready",
      questions: [
        { question_id: "q1", topic: "Дроби", reason: "mistake_review", completed: true },
        { question_id: "q2", topic: "Проценты", reason: "mistake_review", completed: true },
        { question_id: "q3", topic: "Уравнения", reason: "growth_topic", completed: false },
        { question_id: "q4", topic: "Функции", reason: "growth_topic", completed: false },
        { question_id: "q5", topic: "Графики", reason: "growth_topic", completed: false },
      ],
    });

    await mountHome();
    expect(container.querySelector(".gameplay-plan-cta")?.textContent).toContain("План на сегодня · 2 из 5");

    await clickAndSettle(".gameplay-plan-cta");
    await settle();

    expect(screenClasses()).toContain("plan-screen");
    expect(container.querySelectorAll(".plan-task")).toHaveLength(5);
    expect(container.querySelectorAll(".plan-task-done")).toHaveLength(2);
    expect(container.textContent).toContain("Уравнения");
    expect(container.textContent).toContain("Повтор ошибки");
    expect(container.textContent).toContain("осталось 3 задания");

    await clickAndSettle(".primary-button");
    await settle();

    expect(screenClasses()).toContain("trainer-screen");
    expect(startPayload).toMatchObject({ mode: "plan", diagnostic_id: "demo-math" });
    expect(container.textContent).toContain("План: 2 из 5");
    expect(container.textContent).toContain("повтор ошибки");
  });

  it("opens the plan screen straight from the bot's ?screen=plan deeplink", async () => {
    route("/api/diagnostics/bootstrap", bootstrapPayload({
      progress_profile: { completion_count: 1, achievement_keys: [] },
      daily_plan: {
        plan_date: "2026-09-02",
        diagnostic_id: "demo-math",
        subject: "Математика",
        exam: "ЕГЭ",
        total: 5,
        completed: 0,
        status: "ready",
      },
    }));
    route("/api/diagnostics/daily-plan", {
      plan_date: "2026-09-02",
      diagnostic_id: "demo-math",
      subject: "Математика",
      exam: "ЕГЭ",
      total: 1,
      completed: 0,
      status: "ready",
      questions: [{ question_id: "q1", topic: "Дроби", reason: "growth_topic", completed: false }],
    });
    window.history.replaceState({}, "", "/?screen=plan");

    await mountHome();
    await settle();

    expect(screenClasses()).toContain("plan-screen");
    expect(container.textContent).toContain("План на сегодня");
    expect(container.textContent).toContain("Дроби");
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
    expect(container.querySelector(".gameplay-plan-done")?.textContent).toContain("План на сегодня выполнен");
    expect(container.querySelector(".gameplay-home-cta")?.className).toContain("primary-button");
  });
});
