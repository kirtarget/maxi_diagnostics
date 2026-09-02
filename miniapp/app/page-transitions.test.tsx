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
    catalog_contract: 2,
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
});

describe("Home screen transitions", () => {
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
});
