import type {
  AnswerMap,
  AnswerValue,
  BootstrapResponse,
  CompletionResponse,
  DiagnosticMode,
  PublicDiagnostic,
  ReviewResponse,
  SavedSession,
  ServerAttempt,
} from "./types";
import type {
  TrainerAnswerResponse,
  TrainerFinishResponse,
  TrainerStartResponse,
} from "./trainer-model";
import { parseLeagueResponse, type LeagueResponse } from "./league-model";
import {
  isValidNumericInput,
  updateMatchingAnswer,
  updateNumericInputAnswer,
} from "./answer-values";

export {
  isValidNumericInput,
  updateMatchingAnswer,
  updateNumericInputAnswer,
};

const API_BASE_URL = (process.env.NEXT_PUBLIC_DIAGNOSTIC_API_URL ?? "").replace(/\/$/, "");
const REQUEST_TIMEOUT_MS = 12_000;
const REQUEST_ATTEMPTS = 3;

type FetchLike = typeof fetch;
type ProgressSaveState = "saving" | "saved" | "error";

export function isConflictError(error: unknown): boolean {
  return error instanceof Error && error.message === "diagnostic_api_409";
}

export function apiErrorDetail(error: unknown): string | null {
  if (!(error instanceof Error)) return null;
  const detail = (error as Error & { detail?: unknown }).detail;
  return typeof detail === "string" ? detail : null;
}

export type ProgressPayload = {
  attempt_id: string;
  session_scope: string;
  supersedes_attempt_id?: string;
  diagnostic_id: string;
  content_version: string;
  mode: DiagnosticMode;
  question_index: number;
  question_count: number;
  progress_revision: number;
  answers: AnswerMap;
};

export type ProgressSaveQueue<T> = {
  enqueue: (payload: T) => void;
  flush: () => Promise<void>;
  cancel: (reason?: unknown) => void;
};

const ATTEMPT_ID_PATTERN = /^[A-Za-z0-9_-]{8,48}$/;
const SAVED_SESSION_KEYS = new Set([
  "attemptId",
  "supersedesAttemptId",
  "diagnosticId",
  "contentVersion",
  "mode",
  "questionIndex",
  "revision",
  "answers",
  "syncedQuestionIndex",
  "syncedAnswers",
]);

export function storageKey(schoolId: string, sessionScope: string): string {
  return `diagnostic-session-v3:${schoolId}:${sessionScope}`;
}

export function createAttemptId(): string {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `attempt-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`.slice(0, 48);
}

export function buildCompletionPayload(
  attemptId: string,
  sessionScope: string,
  diagnosticId: string,
  contentVersion: string,
  progressRevision: number,
  mode: DiagnosticMode,
  answers: AnswerMap,
  supersedesAttemptId?: string,
) {
  return {
    attempt_id: attemptId,
    session_scope: sessionScope,
    ...(supersedesAttemptId ? { supersedes_attempt_id: supersedesAttemptId } : {}),
    diagnostic_id: diagnosticId,
    content_version: contentVersion,
    progress_revision: progressRevision,
    mode,
    question_count: Object.keys(answers).length,
    answers,
  };
}

export function saveLocalSession(
  schoolId: string,
  sessionScope: string,
  session: SavedSession,
  storage: Storage | undefined = typeof window === "undefined" ? undefined : window.localStorage,
): void {
  if (!storage) return;
  const {
    attemptId, supersedesAttemptId, diagnosticId, contentVersion,
    mode, questionIndex, revision, answers, syncedQuestionIndex, syncedAnswers,
  } = session;
  try {
    storage.setItem(storageKey(schoolId, sessionScope), JSON.stringify({
      attemptId,
      ...(supersedesAttemptId ? { supersedesAttemptId } : {}),
      diagnosticId,
      contentVersion,
      mode,
      questionIndex,
      revision,
      answers,
      ...(syncedQuestionIndex !== undefined ? { syncedQuestionIndex } : {}),
      ...(syncedAnswers !== undefined ? { syncedAnswers } : {}),
    } satisfies SavedSession));
  } catch {
    return;
  }
}

export function loadLocalSession(
  schoolId: string,
  sessionScope: string,
  diagnostics: PublicDiagnostic[],
  storage: Storage | undefined = typeof window === "undefined" ? undefined : window.localStorage,
): SavedSession | null {
  if (!storage) return null;
  const key = storageKey(schoolId, sessionScope);
  try {
    const raw = storage.getItem(key);
    if (!raw) return null;
    const value = validateSavedSession(JSON.parse(raw), diagnostics);
    if (!value) {
      clearLocalSession(schoolId, sessionScope, storage);
      return null;
    }
    return value;
  } catch {
    clearLocalSession(schoolId, sessionScope, storage);
    return null;
  }
}

export function validateSavedSession(
  candidate: unknown,
  diagnostics: PublicDiagnostic[],
): SavedSession | null {
  if (!isRecord(candidate) || Object.keys(candidate).some((key) => !SAVED_SESSION_KEYS.has(key))) {
    return null;
  }
  const {
    attemptId, supersedesAttemptId, diagnosticId, contentVersion,
    mode, questionIndex, revision, answers, syncedQuestionIndex, syncedAnswers,
  } = candidate;
  if (
    typeof attemptId !== "string" ||
    !ATTEMPT_ID_PATTERN.test(attemptId) ||
    (supersedesAttemptId !== undefined && (
      typeof supersedesAttemptId !== "string" ||
      !ATTEMPT_ID_PATTERN.test(supersedesAttemptId) ||
      supersedesAttemptId === attemptId
    )) ||
    typeof diagnosticId !== "string" ||
    diagnosticId.length < 3 ||
    diagnosticId.length > 64 ||
    typeof contentVersion !== "string" ||
    !/^[0-9a-f]{64}$/.test(contentVersion) ||
    (mode !== "quick" && mode !== "full") ||
    typeof questionIndex !== "number" ||
    !Number.isInteger(questionIndex) ||
    typeof revision !== "number" ||
    !Number.isSafeInteger(revision) ||
    revision < 0 ||
    revision > 1000 ||
    !isRecord(answers) ||
    (syncedQuestionIndex !== undefined && (
      typeof syncedQuestionIndex !== "number" || !Number.isInteger(syncedQuestionIndex)
    )) ||
    (syncedAnswers !== undefined && !isRecord(syncedAnswers))
  ) {
    return null;
  }

  const diagnostic = diagnostics.find((item) => item.id === diagnosticId);
  if (!diagnostic) return null;
  if (diagnostic.content_version !== contentVersion) return null;
  const questions = mode === "quick"
    ? diagnostic.questions.slice(0, diagnostic.quick_count)
    : diagnostic.questions;
  if (questionIndex < 0 || questionIndex >= questions.length) return null;
  if (syncedQuestionIndex !== undefined && (
    syncedQuestionIndex < 0 || syncedQuestionIndex >= questions.length
  )) return null;
  const questionsById = new Map(questions.map((question) => [question.id, question]));
  for (const answerMap of [answers, ...(syncedAnswers ? [syncedAnswers] : [])]) {
    for (const [questionId, answer] of Object.entries(answerMap)) {
      const question = questionsById.get(questionId);
      if (!question || !isValidAnswer(question, answer)) return null;
    }
  }

  try {
    if (new TextEncoder().encode(JSON.stringify(answers)).length > 64_000) return null;
  } catch {
    return null;
  }
  return {
    attemptId,
    ...(typeof supersedesAttemptId === "string" ? { supersedesAttemptId } : {}),
    diagnosticId,
    contentVersion,
    mode,
    questionIndex,
    revision,
    answers,
    ...(typeof syncedQuestionIndex === "number" ? { syncedQuestionIndex } : {}),
    ...(isRecord(syncedAnswers) ? { syncedAnswers: syncedAnswers as AnswerMap } : {}),
  } as SavedSession;
}

function sameAnswer(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function rebasePendingLocalChanges(server: SavedSession, local: SavedSession): SavedSession {
  if (!local.syncedAnswers || local.syncedQuestionIndex === undefined) {
    return {
      ...local,
      revision: server.revision,
      syncedQuestionIndex: server.questionIndex,
      syncedAnswers: server.answers,
    };
  }
  const answers: AnswerMap = { ...server.answers };
  const keys = new Set([
    ...Object.keys(local.syncedAnswers),
    ...Object.keys(local.answers),
  ]);
  for (const key of keys) {
    if (sameAnswer(local.syncedAnswers[key], local.answers[key])) continue;
    if (Object.hasOwn(local.answers, key)) answers[key] = local.answers[key];
    else delete answers[key];
  }
  return {
    ...server,
    questionIndex: local.questionIndex !== local.syncedQuestionIndex
      ? local.questionIndex
      : server.questionIndex,
    answers,
    syncedQuestionIndex: server.questionIndex,
    syncedAnswers: server.answers,
  };
}

export function reconcileRestoredSession(
  serverAttempt: ServerAttempt | null,
  localSession: SavedSession | null,
  diagnostics: PublicDiagnostic[],
): SavedSession | null {
  const local = localSession ? validateSavedSession(localSession, diagnostics) : null;
  const server = savedServerSession(serverAttempt, diagnostics);
  if (!server) return local;
  if (!local) return server;
  if (local.attemptId !== server.attemptId) {
    return local.supersedesAttemptId === server.attemptId ? local : server;
  }
  if (local.diagnosticId !== server.diagnosticId || local.mode !== server.mode) return server;

  if (local.revision < server.revision) return rebasePendingLocalChanges(server, local);
  if (local.revision > server.revision) return rebasePendingLocalChanges(server, local);
  return local;
}

export function restoreBootstrapSession(
  bootstrap: BootstrapResponse,
  storage: Storage | undefined = typeof window === "undefined" ? undefined : window.localStorage,
): SavedSession | null {
  const schoolId = bootstrap.school.brand.school_id;
  let local = loadLocalSession(
    schoolId, bootstrap.session_scope, bootstrap.diagnostics, storage,
  );
  const completedAttemptIds = new Set(
    bootstrap.results
      .filter((attempt) => attempt.status === "completed")
      .map((attempt) => attempt.attempt_id),
  );
  if (local && completedAttemptIds.has(local.attemptId)) {
    clearLocalSession(schoolId, bootstrap.session_scope, storage);
    local = null;
  }
  if (local && !bootstrap.attempt && bootstrap.latest_attempt_id) {
    if (local.attemptId === bootstrap.latest_attempt_id || local.revision > 0) {
      clearLocalSession(schoolId, bootstrap.session_scope, storage);
      local = null;
    } else {
      local = { ...local, supersedesAttemptId: bootstrap.latest_attempt_id };
    }
  }
  if (
    local && local.revision > 0 &&
    bootstrap.attempt?.attempt_id !== local.attemptId &&
    !completedAttemptIds.has(local.attemptId)
  ) {
    clearLocalSession(schoolId, bootstrap.session_scope, storage);
    local = null;
  }

  const restored = reconcileRestoredSession(bootstrap.attempt, local, bootstrap.diagnostics);
  if (restored && completedAttemptIds.has(restored.attemptId)) {
    clearLocalSession(schoolId, bootstrap.session_scope, storage);
    return null;
  }
  return restored;
}

export function createProgressSaveQueue<T>(
  send: (payload: T) => Promise<unknown>,
  onState: (state: ProgressSaveState) => void,
): ProgressSaveQueue<T> {
  let active = false;
  let latestRevision = 0;
  let generation = 0;
  let pending: { payload: T; revision: number; generation: number } | null = null;
  let terminalError: unknown = null;
  let flushWaiters: Array<{
    resolve: () => void;
    reject: (reason?: unknown) => void;
  }> = [];

  const finishFlushes = () => {
    const waiters = flushWaiters;
    flushWaiters = [];
    waiters.forEach(({ resolve, reject }) => {
      if (terminalError) reject(terminalError);
      else resolve();
    });
  };

  const drain = async () => {
    active = true;
    while (pending) {
      const current = pending;
      pending = null;
      let failed: unknown = null;
      try {
        await send(current.payload);
      } catch (error) {
        failed = error;
      }
      if (current.generation === generation) {
        terminalError = failed;
      }
      if (current.revision === latestRevision && pending === null) {
        onState(failed ? "error" : "saved");
      }
    }
    active = false;
    finishFlushes();
  };

  return {
    enqueue(payload: T): void {
      if (!active && pending === null) terminalError = null;
      latestRevision += 1;
      pending = { payload, revision: latestRevision, generation };
      onState("saving");
      if (!active) void drain();
    },
    flush(): Promise<void> {
      if (!active && pending === null) {
        return terminalError ? Promise.reject(terminalError) : Promise.resolve();
      }
      return new Promise((resolve, reject) => flushWaiters.push({ resolve, reject }));
    },
    cancel(reason?: unknown): void {
      generation += 1;
      latestRevision += 1;
      pending = null;
      terminalError = reason ?? null;
      if (!active) finishFlushes();
    },
  };
}

function savedServerSession(
  attempt: ServerAttempt | null,
  diagnostics: PublicDiagnostic[],
): SavedSession | null {
  if (!attempt || attempt.status !== "in_progress") return null;
  const diagnostic = diagnostics.find((item) => item.id === attempt.diagnostic_id);
  if (!diagnostic) return null;
  const questionCount = attempt.mode === "quick" ? diagnostic.quick_count : diagnostic.questions.length;
  if (attempt.question_count !== questionCount) return null;
  return validateSavedSession({
    attemptId: attempt.attempt_id,
    diagnosticId: attempt.diagnostic_id,
    contentVersion: attempt.content_version,
    mode: attempt.mode,
    questionIndex: attempt.question_index,
    revision: attempt.progress_revision,
    answers: attempt.answers,
  }, diagnostics);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isValidAnswer(
  question: PublicDiagnostic["questions"][number],
  answer: unknown,
): boolean {
  if (question.type === "single") {
    return typeof answer === "string" && question.options.some((option) => option.id === answer);
  }
  if (question.type === "input") {
    return isValidNumericInput(answer);
  }
  if (question.type === "multiple") {
    if (!Array.isArray(answer) || answer.length > question.selection_limit) return false;
    if (!answer.every((value): value is string => typeof value === "string")) return false;
    const allowed = new Set(question.options.map((option) => option.id));
    return new Set(answer).size === answer.length && answer.every((value) => allowed.has(value));
  }
  if (!isRecord(answer)) return false;
  const itemIds = new Set(question.items.map((item) => item.id));
  const optionIds = new Set(question.options.map((option) => option.id));
  return Object.entries(answer).every(
    ([itemId, value]) => itemIds.has(itemId) && typeof value === "string" && optionIds.has(value),
  );
}

export function clearLocalSession(
  schoolId: string,
  sessionScope: string,
  storage: Storage | undefined = typeof window === "undefined" ? undefined : window.localStorage,
): void {
  try {
    storage?.removeItem(storageKey(schoolId, sessionScope));
  } catch {
    return;
  }
}

export async function postDiagnostic<T>(
  path: string,
  initData: string,
  payload: Record<string, unknown> = {},
  fetcher: FetchLike = fetch,
): Promise<T> {
  if (!initData) throw new Error("telegram_init_data_missing");
  let lastError: unknown;

  for (let attempt = 0; attempt < REQUEST_ATTEMPTS; attempt += 1) {
    const controller = new AbortController();
    const timeout = globalThis.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const response = await fetcher(`${API_BASE_URL}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ init_data: initData, ...payload }),
        signal: controller.signal,
      });
      if (!response.ok) {
        const error = new Error(`diagnostic_api_${response.status}`);
        try {
          const body = await response.clone().json() as { detail?: unknown };
          if (typeof body.detail === "string") {
            (error as Error & { detail?: string }).detail = body.detail;
          }
        } catch {
          // Keep the stable status error when the response has no JSON body.
        }
        if (response.status < 500 && response.status !== 429) throw error;
        lastError = error;
        if (response.status === 429) {
          const retryAfter = Number(response.headers.get("Retry-After"));
          const delayMs = Number.isFinite(retryAfter) && retryAfter >= 0
            ? Math.min(5_000, Math.max(250, retryAfter * 1_000))
            : Math.min(4_000, 500 * (2 ** attempt));
          await new Promise((resolve) => globalThis.setTimeout(resolve, delayMs));
        }
        continue;
      }
      return await response.json() as T;
    } catch (error) {
      lastError = error;
      if (error instanceof Error && /^diagnostic_api_4(?!29)/.test(error.message)) throw error;
    } finally {
      globalThis.clearTimeout(timeout);
    }
  }

  throw lastError instanceof Error ? lastError : new Error("diagnostic_api_failed");
}

export const loadBootstrap = (initData: string) =>
  postDiagnostic<BootstrapResponse>("/api/diagnostics/bootstrap", initData);

export const saveProgress = (
  initData: string,
  payload: ProgressPayload,
) => postDiagnostic<{ ok: true; attempt: ServerAttempt }>(
  "/api/diagnostics/session/progress", initData, payload,
);

export const completeDiagnostic = (
  initData: string,
  payload: ReturnType<typeof buildCompletionPayload>,
) => postDiagnostic<CompletionResponse>("/api/diagnostics/session/complete", initData, payload);

export const markResultViewed = (
  initData: string, attemptId: string, sessionScope: string,
) =>
  postDiagnostic<{ ok: true }>("/api/diagnostics/session/viewed", initData, {
    attempt_id: attemptId,
    session_scope: sessionScope,
  });

export const loadReview = (initData: string, attemptId: string, sessionScope: string) =>
  postDiagnostic<ReviewResponse>("/api/diagnostics/session/review", initData, {
    attempt_id: attemptId,
    session_scope: sessionScope,
  });

export async function loadWeeklyLeague(
  initData: string,
  sessionScope: string,
  fetcher: FetchLike = fetch,
): Promise<LeagueResponse> {
  const payload = await postDiagnostic<unknown>("/api/diagnostics/league", initData, { session_scope: sessionScope }, fetcher);
  const league = parseLeagueResponse(payload);
  if (!league) throw new Error("diagnostic_league_invalid_response");
  return league;
}

export type TrainerStartPayload =
  | { session_scope: string; diagnostic_id: string; count: number; mode: "normal" }
  | { session_scope: string; diagnostic_id: string; count: number; mode: "mistakes"; source_attempt_id: string };

export const startTrainer = (
  initData: string,
  payload: TrainerStartPayload,
  fetcher: FetchLike = fetch,
) => postDiagnostic<TrainerStartResponse>("/api/diagnostics/trainer/start", initData, payload, fetcher);

export const answerTrainer = (
  initData: string,
  payload: {
    session_scope: string;
    trainer_session_id: string;
    question_id: string;
    answer: AnswerValue;
    revision: number;
    idempotency_key: string;
  },
  fetcher: FetchLike = fetch,
) => postDiagnostic<TrainerAnswerResponse>("/api/diagnostics/trainer/answer", initData, payload, fetcher);

export const requestLivesReminder = (
  initData: string,
  sessionScope: string,
  fetcher: FetchLike = fetch,
) => postDiagnostic<{ ok: true; due_at: string | null }>(
  "/api/diagnostics/trainer/lives-reminder", initData, { session_scope: sessionScope }, fetcher,
);

export const finishTrainer = (
  initData: string,
  payload: { session_scope: string; trainer_session_id: string; revision: number },
  fetcher: FetchLike = fetch,
) => postDiagnostic<TrainerFinishResponse>("/api/diagnostics/trainer/finish", initData, payload, fetcher);

export type OfferEventPayload = {
  session_scope: string;
  event_id: string;
  placement: "home" | "diagnostic_result" | "trainer";
  offer_id: string;
  event_type: "impression" | "click" | "dismiss";
};

export const recordOfferEvent = (
  initData: string,
  payload: OfferEventPayload,
  fetcher: FetchLike = fetch,
) => postDiagnostic<{ ok: true }>("/api/diagnostics/offer-events", initData, payload, fetcher);
