import { describe, expect, it, vi } from "vitest";

import {
  buildCompletionPayload,
  bootstrapResumeSummary,
  createProgressSaveQueue,
  loadReview,
  loadLocalSession,
  postDiagnostic,
  recordOfferEvent,
  reconcileRestoredSession,
  restoreBootstrapSession,
  saveLocalSession,
  storageKey,
  updateMatchingAnswer,
  isConflictError,
  isValidNumericInput,
  loadDiagnostic,
  updateNumericInputAnswer,
} from "./api";
import type {
  BootstrapResponse,
  Brand,
  PublicDiagnostic,
  SavedSession,
  ServerAttempt,
} from "./types";

function memoryStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() { return values.size; },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => { values.delete(key); },
    setItem: (key, value) => { values.set(key, value); },
  };
}

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

const diagnostics: PublicDiagnostic[] = [{
  id: "demo-math",
  content_version: "a".repeat(64),
  exam: "demo",
  subject: "Математика",
  mark: "М",
  quick_count: 4,
  questions: [
    {
      id: "q1",
      type: "single",
      topic: "Тема 1",
      title: "Задание 1",
      prompt: "Выберите ответ",
      options: [{ id: "a", label: "A" }, { id: "b", label: "B" }],
    },
    {
      id: "q2",
      type: "multiple",
      topic: "Тема 2",
      title: "Задание 2",
      prompt: "Выберите ответы",
      selection_limit: 2,
      options: [
        { id: "x", label: "X" },
        { id: "y", label: "Y" },
        { id: "z", label: "Z" },
      ],
    },
    {
      id: "q3",
      type: "matching",
      topic: "Тема 3",
      title: "Задание 3",
      prompt: "Установите соответствие",
      items: [{ id: "left-1", label: "Первое" }, { id: "left-2", label: "Второе" }],
      options: [{ id: "right-1", label: "Один" }, { id: "right-2", label: "Два" }],
    },
    {
      id: "q4",
      type: "input",
      topic: "Тема 4",
      title: "Задание 4",
      prompt: "Введите ответ",
    },
  ],
  question_count: 4,
}];
const SESSION_SCOPE = "account-scope-1";

const validSession: SavedSession = {
  attemptId: "attempt-1",
  diagnosticId: "demo-math",
  contentVersion: "a".repeat(64),
  mode: "full",
  questionIndex: 3,
  revision: 4,
  answers: {
    q1: "a",
    q2: ["x"],
    q3: { "left-1": "right-1" },
    q4: "42",
  },
};

const serverAttempt: ServerAttempt = {
  attempt_id: "attempt-1",
  diagnostic_id: "demo-math",
  content_version: "a".repeat(64),
  mode: "full",
  status: "in_progress",
  question_index: 0,
  question_count: 4,
  progress_revision: 1,
  answers: { q1: "a" },
};

function bootstrapPayload({
  attempt = null,
  results = [],
  latestAttemptId = attempt?.attempt_id ?? results[0]?.attempt_id ?? null,
}: {
  attempt?: ServerAttempt | null;
  results?: ServerAttempt[];
  latestAttemptId?: string | null;
} = {}): BootstrapResponse {
  return {
    catalog_contract: 2,
    session_scope: SESSION_SCOPE,
    latest_attempt_id: latestAttemptId,
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
        logo: "assets/logo.svg",
        interface: {} as Brand["interface"],
      },
      links: {
        website: "https://school.example",
        support: "https://school.example/support",
        privacy: "https://school.example/privacy",
        offers: [],
      },
    },
    diagnostics,
    attempt,
    results,
  };
}

describe("diagnostic API payloads", () => {
  it("selects resumable content from metadata without semantically validating offline answers", () => {
    const storage = memoryStorage();
    saveLocalSession("north-school", SESSION_SCOPE, {
      ...validSession,
      revision: 0,
      answers: { unknown_question: "kept-until-content-loads" },
    }, storage);

    expect(bootstrapResumeSummary(bootstrapPayload(), storage)).toMatchObject({ id: "demo-math" });
    expect(storage.getItem(storageKey("north-school", SESSION_SCOPE))).not.toBeNull();
  });

  it("loads exactly one versioned diagnostic within the bootstrap session", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ diagnostic: diagnostics[0] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));

    await expect(loadDiagnostic(
      "signed-init-data", SESSION_SCOPE, "demo-math", "a".repeat(64), fetcher,
    )).resolves.toEqual(diagnostics[0]);
    expect(fetcher).toHaveBeenCalledWith("/api/diagnostics/catalog", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        init_data: "signed-init-data",
        session_scope: SESSION_SCOPE,
        diagnostic_id: "demo-math",
        content_version: "a".repeat(64),
      }),
    }));
  });

  it("rejects diagnostic content that does not match the requested version", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({
      diagnostic: { ...diagnostics[0], content_version: "b".repeat(64) },
    }), { status: 200, headers: { "Content-Type": "application/json" } }));

    await expect(loadDiagnostic(
      "signed-init-data", SESSION_SCOPE, "demo-math", "a".repeat(64), fetcher,
    )).rejects.toThrow("diagnostic_catalog_mismatch");
  });
  it("recognizes a server conflict that requires a fresh bootstrap", () => {
    expect(isConflictError(new Error("diagnostic_api_409"))).toBe(true);
    expect(isConflictError(new Error("diagnostic_api_422"))).toBe(false);
  });
  it("removes a cleared matching entry so partial progress remains restorable", () => {
    expect(updateMatchingAnswer({ "left-1": "right-1" }, "left-1", "")).toEqual({});
  });
  it("completion sends answers but no score", () => {
    const payload = buildCompletionPayload(
      "attempt-1", "b".repeat(24), "demo-math", "a".repeat(64), 7, "full", { q1: "2" },
    );

    expect(payload).toEqual({
      attempt_id: "attempt-1",
      session_scope: "b".repeat(24),
      diagnostic_id: "demo-math",
      content_version: "a".repeat(64),
      progress_revision: 7,
      mode: "full",
      question_count: 1,
      answers: { q1: "2" },
    });
  });

  it("uses a school-specific storage key", () => {
    expect(storageKey("north-school", SESSION_SCOPE)).toBe(
      "diagnostic-session-v3:north-school:account-scope-1",
    );
  });

  it("caches only resumable session fields", () => {
    const storage = memoryStorage();
    saveLocalSession("north-school", SESSION_SCOPE, {
      attemptId: "attempt-1",
      diagnosticId: "demo-math",
      contentVersion: "a".repeat(64),
      mode: "quick",
      questionIndex: 1,
      revision: 2,
      answers: { q1: "a" },
      score: 100,
      result: { correct_count: 1 },
    } as never, storage);

    expect(JSON.parse(storage.getItem(storageKey("north-school", SESSION_SCOPE)) ?? "null")).toEqual({
      attemptId: "attempt-1",
      diagnosticId: "demo-math",
      contentVersion: "a".repeat(64),
      mode: "quick",
      questionIndex: 1,
      revision: 2,
      answers: { q1: "a" },
    });
    expect(loadLocalSession("north-school", SESSION_SCOPE, diagnostics, storage)).toEqual({
      attemptId: "attempt-1",
      diagnosticId: "demo-math",
      contentVersion: "a".repeat(64),
      mode: "quick",
      questionIndex: 1,
      revision: 2,
      answers: { q1: "a" },
    });
  });

  it("posts Telegram authentication and retries a transient failure up to three attempts", async () => {
    const fetcher = vi.fn()
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValue(new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }));

    await expect(postDiagnostic<{ ok: boolean }>(
      "/api/diagnostics/bootstrap",
      "signed-init-data",
      {},
      fetcher,
    )).resolves.toEqual({ ok: true });

    expect(fetcher).toHaveBeenCalledTimes(3);
    expect(JSON.parse(String(fetcher.mock.calls[0][1]?.body))).toEqual({
      init_data: "signed-init-data",
    });
  });

  it("requests a lives reminder with only authentication and session scope", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ok: true, due_at: "2026-08-28T12:00:00+00:00",
    }), { status: 200, headers: { "Content-Type": "application/json" } }));

    const { requestLivesReminder } = await import("./api");
    await expect(requestLivesReminder("signed-init-data", "a".repeat(24), fetcher))
      .resolves.toEqual({ ok: true, due_at: "2026-08-28T12:00:00+00:00" });

    expect(String(fetcher.mock.calls[0][0])).toContain("/api/diagnostics/trainer/lives-reminder");
    expect(JSON.parse(String(fetcher.mock.calls[0][1]?.body))).toEqual({
      init_data: "signed-init-data",
      session_scope: "a".repeat(24),
    });
  });

  it("posts only review authentication and session identifiers", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ok: true, available: true, items: [], pdf_status: "pending",
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetcher);
    try {
      await loadReview("init", "attempt_123", "scope");
      expect(fetcher).toHaveBeenCalledWith("/api/diagnostics/session/review", expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          init_data: "init",
          attempt_id: "attempt_123",
          session_scope: "scope",
        }),
      }));
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("records only the allowlisted offer event fields", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));

    await recordOfferEvent("signed-init-data", {
      session_scope: "scope",
      event_id: "event-1",
      placement: "home",
      offer_id: "exam-preparation",
      event_type: "impression",
    }, fetcher);

    expect(fetcher).toHaveBeenCalledWith("/api/diagnostics/offer-events", expect.objectContaining({
      body: JSON.stringify({
        init_data: "signed-init-data",
        session_scope: "scope",
        event_id: "event-1",
        placement: "home",
        offer_id: "exam-preparation",
        event_type: "impression",
      }),
    }));
    const body = JSON.parse(String(fetcher.mock.calls[0][1]?.body));
    expect(body).not.toHaveProperty("url");
    expect(body).not.toHaveProperty("answers");
    expect(body).not.toHaveProperty("results");
  });

  it("honors Retry-After before retrying a shared-NAT rate limit", async () => {
    vi.useFakeTimers();
    try {
      const fetcher = vi.fn()
        .mockResolvedValueOnce(new Response("", {
          status: 429,
          headers: { "Retry-After": "1" },
        }))
        .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }));

      const request = postDiagnostic<{ ok: boolean }>(
        "/api/diagnostics/bootstrap", "signed-init-data", {}, fetcher,
      );
      await vi.advanceTimersByTimeAsync(999);
      expect(fetcher).toHaveBeenCalledTimes(1);
      await vi.advanceTimersByTimeAsync(1);
      await expect(request).resolves.toEqual({ ok: true });
      expect(fetcher).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("serializes progress writes and coalesces queued snapshots to the latest", async () => {
    const first = deferred<void>();
    const latest = deferred<void>();
    const sent: number[] = [];
    const states: string[] = [];
    const queue = createProgressSaveQueue<{ question_index: number }>(
      (payload) => {
        sent.push(payload.question_index);
        return sent.length === 1 ? first.promise : latest.promise;
      },
      (state) => states.push(state),
    );

    queue.enqueue({ question_index: 0 });
    queue.enqueue({ question_index: 1 });
    queue.enqueue({ question_index: 2 });
    expect(sent).toEqual([0]);

    first.resolve();
    await first.promise;
    await Promise.resolve();
    expect(sent).toEqual([0, 2]);

    latest.resolve();
    await queue.flush();
    expect(states.at(-1)).toBe("saved");
    expect(states).not.toContain("error");
  });

  it("does not let an older failed save overwrite the latest save state", async () => {
    const older = deferred<void>();
    const latest = deferred<void>();
    const sent: number[] = [];
    const states: string[] = [];
    const queue = createProgressSaveQueue<{ question_index: number }>(
      (payload) => {
        sent.push(payload.question_index);
        return sent.length === 1 ? older.promise : latest.promise;
      },
      (state) => states.push(state),
    );

    queue.enqueue({ question_index: 0 });
    queue.enqueue({ question_index: 1 });
    older.reject(new Error("offline"));
    await older.promise.catch(() => undefined);
    await Promise.resolve();
    expect(states).not.toContain("error");
    expect(sent).toEqual([0, 1]);

    latest.resolve();
    await queue.flush();
    expect(states.at(-1)).toBe("saved");
  });

  it("does not let an older successful save clear the latest save error", async () => {
    const older = deferred<void>();
    const latest = deferred<void>();
    const sent: number[] = [];
    const states: string[] = [];
    const queue = createProgressSaveQueue<{ question_index: number }>(
      (payload) => {
        sent.push(payload.question_index);
        return sent.length === 1 ? older.promise : latest.promise;
      },
      (state) => states.push(state),
    );

    queue.enqueue({ question_index: 0 });
    queue.enqueue({ question_index: 1 });
    older.resolve();
    await older.promise;
    await Promise.resolve();
    expect(states).not.toContain("saved");

    latest.reject(new Error("offline"));
    await expect(queue.flush()).rejects.toThrow("offline");
    expect(states.at(-1)).toBe("error");
  });

  it("reports an error when the latest progress save fails", async () => {
    const queue = createProgressSaveQueue(
      async () => { throw new Error("offline"); },
      (state) => states.push(state),
    );
    const states: string[] = [];

    queue.enqueue({ question_index: 1 });
    await expect(queue.flush()).rejects.toThrow("offline");
    expect(states.at(-1)).toBe("error");
  });

  it("completion carries the expected active attempt when replacing it", () => {
    const payload = buildCompletionPayload(
      "attempt-2", "b".repeat(24), "demo-math", "a".repeat(64), 1, "quick", { q1: "2" },
      "attempt-1",
    );

    expect(payload.supersedes_attempt_id).toBe("attempt-1");
  });

  it("cancels queued snapshots after a conflict before they can overwrite server state", async () => {
    const active = deferred<void>();
    const sent: number[] = [];
    const states: string[] = [];
    const queue = createProgressSaveQueue<{ question_index: number }>(
      async (payload) => {
        sent.push(payload.question_index);
        await active.promise;
      },
      (state) => states.push(state),
    );

    queue.enqueue({ question_index: 0 });
    queue.enqueue({ question_index: 1 });
    queue.cancel();
    active.resolve();
    await queue.flush();

    expect(sent).toEqual([0]);
    expect(states.at(-1)).toBe("saving");
  });

  it("surfaces a conflict cancellation to a submit waiter", async () => {
    const active = deferred<void>();
    const queue = createProgressSaveQueue(
      async () => active.promise,
      () => undefined,
    );
    const conflict = new Error("diagnostic_api_409");

    queue.enqueue({ question_index: 0 });
    queue.cancel(conflict);
    active.resolve();

    await expect(queue.flush()).rejects.toBe(conflict);
  });

  it("rebases a browser-ahead snapshot onto the restored server revision", () => {
    const local = {
      ...validSession,
      questionIndex: 1,
      answers: { q1: "a", q2: ["x"] },
    };

    expect(reconcileRestoredSession(serverAttempt, local, diagnostics)).toEqual({
      ...local,
      revision: 1,
      syncedQuestionIndex: 0,
      syncedAnswers: { q1: "a" },
    });
  });

  it("prefers the valid device snapshot on a same-progress tie to preserve offline edits", () => {
    const local = {
      ...validSession,
      questionIndex: 0,
      revision: 1,
      answers: { q1: "b" },
    };

    expect(reconcileRestoredSession(serverAttempt, local, diagnostics)).toEqual(local);
  });

  it("rebases unsent local answers after the server committed a lost response", () => {
    const local = {
      ...validSession,
      revision: 0,
      questionIndex: 1,
      answers: { q1: "a", q2: ["x"] },
      syncedQuestionIndex: 0,
      syncedAnswers: {},
    };

    expect(reconcileRestoredSession(serverAttempt, local, diagnostics)).toEqual({
      attemptId: "attempt-1",
      diagnosticId: "demo-math",
      contentVersion: "a".repeat(64),
      mode: "full",
      questionIndex: 1,
      revision: 1,
      answers: { q1: "a", q2: ["x"] },
      syncedQuestionIndex: 0,
      syncedAnswers: { q1: "a" },
    });
  });

  it("continues when browser storage is unavailable", () => {
    const throwing = {
      getItem: () => { throw new DOMException("blocked", "SecurityError"); },
      setItem: () => { throw new DOMException("blocked", "SecurityError"); },
      removeItem: () => { throw new DOMException("blocked", "SecurityError"); },
    } as unknown as Storage;

    expect(() => saveLocalSession("north-school", SESSION_SCOPE, validSession, throwing)).not.toThrow();
    expect(loadLocalSession("north-school", SESSION_SCOPE, diagnostics, throwing)).toBeNull();
  });

  it("keeps a newer offline device attempt that explicitly supersedes the server attempt", () => {
    const local = {
      ...validSession,
      attemptId: "attempt-2",
      revision: 0,
      supersedesAttemptId: serverAttempt.attempt_id,
    };

    expect(reconcileRestoredSession(serverAttempt, local, diagnostics)).toEqual(local);
  });

  it("does not resurrect an unrelated local attempt after another device superseded it", () => {
    const staleLocal = { ...validSession, attemptId: "attempt-old", revision: 7 };

    expect(reconcileRestoredSession(serverAttempt, staleLocal, diagnostics)).toEqual({
      attemptId: "attempt-1",
      diagnosticId: "demo-math",
      contentVersion: "a".repeat(64),
      mode: "full",
      questionIndex: 0,
      revision: 1,
      answers: { q1: "a" },
    });
  });

  it("keeps unsent local progress at acknowledged revision zero", () => {
    const storage = memoryStorage();
    const unsent = { ...validSession, revision: 0, answers: { q1: "b" } };

    saveLocalSession("north-school", SESSION_SCOPE, unsent, storage);

    expect(loadLocalSession(
      "north-school", SESSION_SCOPE, diagnostics, storage,
    )).toEqual(unsent);
  });

  it("clears a local attempt already completed in the real bootstrap results shape", () => {
    const storage = memoryStorage();
    saveLocalSession("north-school", SESSION_SCOPE, validSession, storage);
    const completedAttempt: ServerAttempt = {
      ...serverAttempt,
      status: "completed",
      question_index: 4,
      answers: validSession.answers,
    };

    expect(restoreBootstrapSession(bootstrapPayload({
      attempt: null,
      results: [completedAttempt],
    }), storage)).toBeNull();
    expect(storage.getItem(storageKey("north-school", SESSION_SCOPE))).toBeNull();
  });

  it("clears acknowledged local progress after another device superseded and completed", () => {
    const storage = memoryStorage();
    saveLocalSession("north-school", SESSION_SCOPE, validSession, storage);
    const unrelatedCompletedAttempt: ServerAttempt = {
      ...serverAttempt,
      attempt_id: "attempt-2",
      status: "completed",
      question_index: 4,
      answers: validSession.answers,
    };

    expect(restoreBootstrapSession(bootstrapPayload({
      attempt: null,
      results: [unrelatedCompletedAttempt],
    }), storage)).toBeNull();
    expect(storage.getItem(storageKey("north-school", SESSION_SCOPE))).toBeNull();
  });

  it("keeps a genuinely unsent local attempt when another result exists", () => {
    const storage = memoryStorage();
    const unsent = { ...validSession, attemptId: "attempt-new", revision: 0 };
    saveLocalSession("north-school", SESSION_SCOPE, unsent, storage);
    const completedAttempt = {
      ...serverAttempt, attempt_id: "attempt-2", status: "completed",
    } as ServerAttempt;

    expect(restoreBootstrapSession(bootstrapPayload({
      attempt: null, results: [completedAttempt],
    }), storage)).toEqual({ ...unsent, supersedesAttemptId: "attempt-2" });
  });

  it("rebases a revision-zero offline attempt onto the latest cross-device result", () => {
    const storage = memoryStorage();
    const offline = {
      ...validSession,
      attemptId: "attempt-offline",
      supersedesAttemptId: "attempt-old",
      revision: 0,
    };
    saveLocalSession("north-school", SESSION_SCOPE, offline, storage);
    const latest = {
      ...serverAttempt, attempt_id: "attempt-latest", status: "completed",
    } as ServerAttempt;

    expect(restoreBootstrapSession(bootstrapPayload({
      attempt: null,
      results: [latest],
      latestAttemptId: latest.attempt_id,
    }), storage)).toEqual({
      ...offline,
      supersedesAttemptId: latest.attempt_id,
    });
  });

  it("keeps numeric input drafts out of persisted answers until valid", () => {
    expect(updateNumericInputAnswer({ q1: "a", q4: "12" }, "q4", "-")).toEqual({ q1: "a" });
    expect(updateNumericInputAnswer({ q1: "a" }, "q4", "-1.5")).toEqual({
      q1: "a", q4: "-1.5",
    });
    expect(updateNumericInputAnswer({ q1: "a", q4: "12" }, "q4", "")).toEqual({ q1: "a" });
  });

  it("uses the same bounded numeric grammar as the server", () => {
    expect(isValidNumericInput("1e999")).toBe(true);
    expect(isValidNumericInput("1e1000")).toBe(false);
    expect(isValidNumericInput("1".repeat(65))).toBe(false);
    expect(isValidNumericInput(" 42")).toBe(false);
  });

  it("does not expose one Telegram account's local answers to another account", () => {
    const storage = memoryStorage();
    saveLocalSession("north-school", SESSION_SCOPE, validSession, storage);
    const otherAccount = { ...bootstrapPayload(), session_scope: "account-scope-2" };

    expect(restoreBootstrapSession(otherAccount, storage)).toBeNull();
    expect(storage.getItem(storageKey("north-school", SESSION_SCOPE))).not.toBeNull();
  });

  it("uses valid server progress after clearing an invalid local snapshot", () => {
    const storage = memoryStorage();
    storage.setItem(storageKey("north-school", SESSION_SCOPE), JSON.stringify({
      ...validSession,
      questionIndex: -1,
    }));

    const local = loadLocalSession("north-school", SESSION_SCOPE, diagnostics, storage);
    expect(local).toBeNull();
    expect(reconcileRestoredSession(serverAttempt, local, diagnostics)).toEqual({
      attemptId: "attempt-1",
      diagnosticId: "demo-math",
      contentVersion: "a".repeat(64),
      mode: "full",
      questionIndex: 0,
      revision: 1,
      answers: { q1: "a" },
    });
  });

  it("clears answers for questions outside the selected quick mode", () => {
    const storage = memoryStorage();
    const quickDiagnostics = [{ ...diagnostics[0], quick_count: 2 }];
    storage.setItem(storageKey("north-school", SESSION_SCOPE), JSON.stringify({
      ...validSession,
      mode: "quick",
      questionIndex: 1,
      answers: { q1: "a", q3: { "left-1": "right-1" } },
    }));

    expect(loadLocalSession("north-school", SESSION_SCOPE, quickDiagnostics, storage)).toBeNull();
    expect(storage.getItem(storageKey("north-school", SESSION_SCOPE))).toBeNull();
  });

  it.each([
    ["short attempt id", { attemptId: "bad" }],
    ["unknown diagnostic id", { diagnosticId: "missing-diagnostic" }],
    ["stale content version", { contentVersion: "b".repeat(64) }],
    ["invalid mode", { mode: "medium" }],
    ["negative question index", { questionIndex: -1 }],
    ["fractional question index", { questionIndex: 1.5 }],
    ["missing revision", { revision: undefined }],
    ["negative revision", { revision: -1 }],
    ["fractional revision", { revision: 1.5 }],
    ["unbounded revision", { revision: 1001 }],
    ["out-of-range question index", { questionIndex: 4 }],
    ["stale question key", { answers: { ...validSession.answers, stale: "x" } }],
    ["unknown single option", { answers: { ...validSession.answers, q1: "missing" } }],
    ["numeric multiple value", { answers: { ...validSession.answers, q2: ["x", 2] } }],
    ["unknown multiple option", { answers: { ...validSession.answers, q2: ["x", "missing"] } }],
    ["duplicate multiple option", { answers: { ...validSession.answers, q2: ["x", "x"] } }],
    ["numeric matching value", { answers: { ...validSession.answers, q3: { "left-1": 2 } } }],
    ["unknown matching item", { answers: { ...validSession.answers, q3: { stale: "right-1" } } }],
    ["unknown matching option", { answers: { ...validSession.answers, q3: { "left-1": "missing" } } }],
    ["numeric input value", { answers: { ...validSession.answers, q4: 42 } }],
    ["nonnumeric input text", { answers: { ...validSession.answers, q4: "forty-two" } }],
    ["control character input", { answers: { ...validSession.answers, q4: "42\u0000" } }],
  ])("clears an invalid cached session with %s", (_name, patch) => {
    const storage = memoryStorage();
    storage.setItem(storageKey("north-school", SESSION_SCOPE), JSON.stringify({ ...validSession, ...patch }));

    expect(loadLocalSession("north-school", SESSION_SCOPE, diagnostics, storage)).toBeNull();
    expect(storage.getItem(storageKey("north-school", SESSION_SCOPE))).toBeNull();
  });
});
