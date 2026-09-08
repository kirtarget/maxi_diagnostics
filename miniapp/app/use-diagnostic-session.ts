"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";

import {
  apiErrorDetail,
  apiErrorQuestionId,
  bootstrapResumeSummary,
  buildCompletionPayload,
  clearLocalSession,
  completeDiagnostic,
  createAttemptId,
  createProgressSaveQueue,
  isConflictError,
  loadDiagnostic,
  loadReview,
  markResultViewed,
  restoreBootstrapSession,
  saveLocalSession,
  saveProgress,
  updateNumericInputAnswer,
  updateTextInputAnswer,
} from "./api";
import type { ProgressPayload, ProgressSaveQueue } from "./api";
import { emptyAnswerFor, updateAnswerFromEditor } from "./answer-values";
import {
  diagnosticLoadInitialState,
  diagnosticLoadReducer,
  diagnosticSummaryKey,
  type DiagnosticLoadState,
} from "./diagnostic-loader-model";
import { createReviewRequestGate } from "./review-request-gate";
import type { ProgressSaveState } from "./assessment-header";
export type { ProgressSaveState } from "./assessment-header";
import type { BootstrapSession } from "./use-bootstrap";
import type {
  AnswerMap,
  AnswerValue,
  DiagnosticMode,
  PublicDiagnostic,
  PublicDiagnosticSummary,
  Question,
  ReviewResponse,
  ServerResult,
  ServerAttempt,
  Screen,
} from "./types";
import { readExamPreference, SUBMIT_MINIMUM_MS, submitPresentation, writeExamPreference } from "./navigation-model";

export type DiagnosticSessionState = {
  /** Non-null only while the loaded diagnostic matches the selected one. */
  diagnostic: PublicDiagnostic | null;
  diagnosticLoad: DiagnosticLoadState;
  questions: Question[];
  exam: string;
  mode: DiagnosticMode;
  attemptId: string;
  questionIndex: number;
  answers: AnswerMap;
  inputDrafts: Record<string, string>;
  result: ServerResult | null;
  resultDiagnostic: Pick<PublicDiagnostic, "exam" | "subject"> | null;
  review: ReviewResponse | null;
  reviewIndex: number;
  reviewMode: "list" | "detail";
  reviewQuestionId: string | null;
  reviewError: string | null;
  syncWarning: string | null;
  progressSaveState: ProgressSaveState;
  progressToast: string | null;
  submitWarning: boolean;
};

export type DiagnosticSessionActions = {
  hydrate(preserveCurrentScreen?: boolean): Promise<boolean>;
  setExam(exam: string): void;
  chooseMode(mode: DiagnosticMode, exam: string): void;
  chooseFormat(mode: DiagnosticMode, diagnostic: PublicDiagnosticSummary): Promise<void>;
  beginDiagnostic(selected: PublicDiagnosticSummary, mode?: DiagnosticMode): Promise<void>;
  answerQuestion(value: AnswerValue): void;
  skipQuestion(): void;
  previousQuestion(): void;
  nextQuestion(): void;
  flushProgressForExit(): Promise<boolean>;
  openReview(questionId?: string): void;
  openSavedResult(attempt: ServerAttempt): void;
  refreshReview(): Promise<ReviewResponse | null>;
  reviewBack(): void;
  reviewNext(): void;
  reviewList(): void;
  clearReviewError(): void;
  /** Attempt id the server has stored, used to replay that attempt's mistakes. */
  persistedAttemptId(): string | null;
};

export type DiagnosticSession = {
  state: DiagnosticSessionState;
  actions: DiagnosticSessionActions;
};

function questionsFor(diagnostic: PublicDiagnostic, mode: DiagnosticMode): Question[] {
  return diagnostic.questions.slice(
    0, mode === "quick" ? diagnostic.quick_count : diagnostic.full_count,
  );
}

export function useDiagnosticSession({
  bootstrap,
  screen,
  setScreen,
}: {
  bootstrap: BootstrapSession;
  screen: Screen;
  setScreen: (screen: Screen) => void;
}): DiagnosticSession {
  const { initData, schoolId: schoolIdRef, sessionScopeRef, sessionScope } = bootstrap;
  const bootstrapData = bootstrap.state.bootstrap;
  const { load: loadBootstrapData, setError, refreshProgress } = bootstrap.actions;

  const [loadedDiagnostic, setLoadedDiagnostic] = useState<PublicDiagnostic | null>(null);
  const [diagnosticLoad, dispatchDiagnosticLoad] = useReducer(
    diagnosticLoadReducer,
    diagnosticLoadInitialState,
  );
  const [syncWarning, setSyncWarning] = useState<string | null>(null);
  const [mode, setMode] = useState<DiagnosticMode>("quick");
  const [exam, setExam] = useState("");
  const [diagnosticId, setDiagnosticId] = useState<string | null>(null);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [answers, setAnswers] = useState<AnswerMap>({});
  const [inputDrafts, setInputDrafts] = useState<Record<string, string>>({});
  const [attemptId, setAttemptId] = useState(createAttemptId);
  const [result, setResult] = useState<ServerResult | null>(null);
  const [savedResultDiagnostic, setSavedResultDiagnostic] = useState<Pick<PublicDiagnostic, "exam" | "subject"> | null>(null);
  const [review, setReview] = useState<ReviewResponse | null>(null);
  const [reviewIndex, setReviewIndex] = useState(0);
  const [reviewMode, setReviewMode] = useState<"list" | "detail">("list");
  const [reviewQuestionId, setReviewQuestionId] = useState<string | null>(null);
  const reviewSelectionIdentity = useRef<{ attemptId: string; contentVersion: string } | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [progressSaveState, setProgressSaveState] = useState<ProgressSaveState>("idle");
  const [progressToast, setProgressToast] = useState<string | null>(null);
  const [submitWarning, setSubmitWarning] = useState(false);

  const progressRevision = useRef(0);
  const syncedQuestionIndex = useRef(0);
  const syncedAnswers = useRef<AnswerMap>({});
  const latestQuestionIndex = useRef(0);
  const latestAnswers = useRef<AnswerMap>({});
  const activeAttemptId = useRef(attemptId);
  const persistedAttemptId = useRef<string | null>(null);
  const supersedesAttemptId = useRef<string | undefined>(undefined);
  const attemptGeneration = useRef(0);
  const reviewRequestGate = useRef<ReturnType<typeof createReviewRequestGate> | null>(null);
  if (!reviewRequestGate.current) {
    reviewRequestGate.current = createReviewRequestGate();
    reviewRequestGate.current.activate({ attemptId, generation: attemptGeneration.current });
  }
  const hydrateGeneration = useRef(0);
  const diagnosticLoadRequestId = useRef(0);
  const diagnosticCache = useRef(new Map<string, Promise<PublicDiagnostic>>());
  const recoveryPromise = useRef<Promise<void> | null>(null);
  const saveToastAttempt = useRef<string | null>(null);
  const pendingProgressTimer = useRef<number | null>(null);
  const pendingProgressPayload = useRef<ProgressPayload | null>(null);
  const skipAutoSaveAfterRecovery = useRef(false);
  const recoverConflict = useRef<() => Promise<void>>(async () => undefined);
  const progressQueue = useRef<ProgressSaveQueue<ProgressPayload> | null>(null);
  if (!progressQueue.current) {
    progressQueue.current = createProgressSaveQueue(
      async (payload) => {
        if (payload.attempt_id !== activeAttemptId.current) return;
        const sendGeneration = attemptGeneration.current;
        let response;
        try {
          response = await saveProgress(initData.current, {
            ...payload,
            progress_revision: progressRevision.current + 1,
          });
        } catch (saveError) {
          if (isConflictError(saveError) && payload.attempt_id === activeAttemptId.current) {
            progressQueue.current?.cancel(saveError);
            await recoverConflict.current();
          }
          throw saveError;
        }
        if (
          response.attempt.attempt_id !== activeAttemptId.current ||
          sendGeneration !== attemptGeneration.current
        ) return;
        progressRevision.current = response.attempt.progress_revision;
        syncedQuestionIndex.current = response.attempt.question_index;
        syncedAnswers.current = response.attempt.answers ?? {};
        persistedAttemptId.current = response.attempt.attempt_id;
        if (schoolIdRef.current && sessionScopeRef.current) {
          saveLocalSession(schoolIdRef.current, sessionScopeRef.current, {
            attemptId: response.attempt.attempt_id,
            ...(supersedesAttemptId.current
              ? { supersedesAttemptId: supersedesAttemptId.current }
              : {}),
            diagnosticId: response.attempt.diagnostic_id,
            contentVersion: response.attempt.content_version,
            mode: response.attempt.mode,
            questionIndex: latestQuestionIndex.current,
            revision: response.attempt.progress_revision,
            answers: latestAnswers.current,
            syncedQuestionIndex: response.attempt.question_index,
            syncedAnswers: response.attempt.answers,
          });
        }
      },
      (state) => {
        setProgressSaveState(state);
        if (state === "saved" && saveToastAttempt.current !== activeAttemptId.current) {
          saveToastAttempt.current = activeAttemptId.current;
          setProgressToast("Прогресс сохраняется");
        }
        setSyncWarning(state === "error"
          ? "Ответ сохранён на устройстве. Отправим его на сервер, когда связь восстановится."
          : null);
      },
    );
  }

  const diagnostic = loadedDiagnostic?.id === diagnosticId ? loadedDiagnostic : null;
  const questions = useMemo(
    () => diagnostic ? questionsFor(diagnostic, mode) : [],
    [diagnostic, mode],
  );
  const brand = bootstrapData?.school.brand;

  const loadCachedDiagnostic = useCallback((
    summary: PublicDiagnosticSummary,
    scope: string,
  ): Promise<PublicDiagnostic> => {
    const key = diagnosticSummaryKey(summary);
    const cached = diagnosticCache.current.get(key);
    if (cached) return cached;
    const request = loadDiagnostic(
      initData.current,
      scope,
      summary.id,
      summary.content_version,
    ).catch((loadError) => {
      diagnosticCache.current.delete(key);
      throw loadError;
    });
    diagnosticCache.current.set(key, request);
    return request;
  }, [initData]);

  const refreshReview = useCallback(async () => {
    if (!sessionScope || !initData.current) return null;
    const identity = { attemptId, generation: attemptGeneration.current };
    const outcome = await reviewRequestGate.current!.run(
      identity,
      () => loadReview(initData.current, attemptId, sessionScope),
    );
    if (outcome.status === "current") {
      setReview(outcome.value);
      const storedId = reviewSelectionIdentity.current && typeof window !== "undefined"
        ? window.sessionStorage.getItem(`diagnostic-review:${reviewSelectionIdentity.current.attemptId}:${reviewSelectionIdentity.current.contentVersion}`)
        : null;
      if (!reviewQuestionId && storedId && outcome.value.items.some((item) => item.question_id === storedId)) {
        setReviewQuestionId(storedId);
        setReviewMode("detail");
      } else if (reviewQuestionId && !outcome.value.items.some((item) => item.question_id === reviewQuestionId)) {
        setReviewQuestionId(null);
        setReviewMode("list");
      }
      setReviewError(null);
      return outcome.value;
    }
    if (outcome.status === "error") {
      setReviewError("Не удалось загрузить разбор. Повтори запрос.");
    }
    return null;
  }, [attemptId, initData, sessionScope, reviewQuestionId]);

  const hydrate = useCallback(async (preserveCurrentScreen = false, preserveProgressError = false) => {
    const generation = hydrateGeneration.current + 1;
    hydrateGeneration.current = generation;
    setError(null);
    if (!preserveCurrentScreen) setScreen("loading");
    let loaded;
    try {
      loaded = await loadBootstrapData();
      if (loaded.status === "outside") return false;
      const data = loaded.data;
      if (generation !== hydrateGeneration.current) return false;
      attemptGeneration.current += 1;
      if (!preserveProgressError) progressQueue.current?.cancel();
      loaded.apply();
      setLoadedDiagnostic(null);
      const preferredExam = readExamPreference(data.school.brand.school_id);
      setExam((current) => {
        const next = preferredExam && data.diagnostics.some((item) => item.exam === preferredExam)
          ? preferredExam
          : current && data.diagnostics.some((item) => item.exam === current)
            ? current
            : data.diagnostics[0]?.exam || "";
        if (next) writeExamPreference(data.school.brand.school_id, next);
        return next;
      });
      if (data.diagnostics.length === 0) {
        setScreen("welcome");
        return true;
      }

      const resumeSummary = bootstrapResumeSummary(data);
      let savedDiagnostic: PublicDiagnostic | null = null;
      let session = null;
      if (resumeSummary) {
        const requestId = diagnosticLoadRequestId.current + 1;
        diagnosticLoadRequestId.current = requestId;
        dispatchDiagnosticLoad({ type: "load", requestId, summary: resumeSummary, intent: "resume" });
        setScreen("diagnostic-loading");
        try {
          savedDiagnostic = await loadCachedDiagnostic(resumeSummary, data.session_scope);
          if (generation !== hydrateGeneration.current || requestId !== diagnosticLoadRequestId.current) return false;
          dispatchDiagnosticLoad({ type: "loaded", requestId, diagnostic: savedDiagnostic });
          session = restoreBootstrapSession(data, undefined, [savedDiagnostic]);
          if (
            !session && data.attempt?.status === "in_progress" &&
            data.attempt.diagnostic_id !== savedDiagnostic.id
          ) {
            const serverSummary = data.diagnostics.find(
              (item) => item.id === data.attempt?.diagnostic_id,
            );
            if (serverSummary) {
              dispatchDiagnosticLoad({ type: "load", requestId, summary: serverSummary, intent: "resume" });
              savedDiagnostic = await loadCachedDiagnostic(serverSummary, data.session_scope);
              if (generation !== hydrateGeneration.current || requestId !== diagnosticLoadRequestId.current) return false;
              dispatchDiagnosticLoad({ type: "loaded", requestId, diagnostic: savedDiagnostic });
              session = restoreBootstrapSession(data, undefined, [savedDiagnostic]);
            }
          }
        } catch {
          if (generation !== hydrateGeneration.current || requestId !== diagnosticLoadRequestId.current) return false;
          dispatchDiagnosticLoad({
            type: "failed",
            requestId,
            message: "Не удалось загрузить задания. Прогресс сохранён на устройстве.",
          });
          setScreen("diagnostic-loading");
          return false;
        }
      }
      if (session && savedDiagnostic) {
        reviewRequestGate.current!.activate({
          attemptId: session.attemptId,
          generation: attemptGeneration.current,
        });
        activeAttemptId.current = session.attemptId;
        persistedAttemptId.current = data.attempt?.attempt_id ?? (
          session.revision > 0 ? session.attemptId : null
        );
        supersedesAttemptId.current = session.supersedesAttemptId;
        setAttemptId(session.attemptId);
        setLoadedDiagnostic(savedDiagnostic);
        setDiagnosticId(session.diagnosticId);
        setMode(session.mode);
        setQuestionIndex(session.questionIndex);
        latestQuestionIndex.current = session.questionIndex;
        progressRevision.current = session.revision;
        syncedQuestionIndex.current = session.syncedQuestionIndex ?? session.questionIndex;
        syncedAnswers.current = session.syncedAnswers ?? session.answers;
        setAnswers(session.answers);
        latestAnswers.current = session.answers;
        setInputDrafts(Object.fromEntries(
          Object.entries(session.answers).filter(([, value]) => typeof value === "string"),
        ) as Record<string, string>);
        setReview(null);
        setReviewIndex(0);
        setReviewError(null);
        setScreen("question");
      } else {
        reviewRequestGate.current!.activate({
          attemptId: activeAttemptId.current,
          generation: attemptGeneration.current,
        });
        persistedAttemptId.current = data.attempt?.attempt_id ?? null;
        supersedesAttemptId.current = undefined;
        setReview(null);
        setReviewIndex(0);
        setReviewError(null);
        const onboarding = data.onboarding?.status ?? (data.progress_profile?.completion_count ? "completed" : "welcome");
        setScreen(onboarding === "completed" ? "home" : onboarding === "selection" ? "subjects" : "welcome");
      }
      return true;
    } catch {
      if (generation !== hydrateGeneration.current) return false;
      setError("Не удалось загрузить диагностику. Проверь соединение и повтори попытку.");
      return false;
    }
  }, [loadBootstrapData, loadCachedDiagnostic, setError, setScreen]);

  recoverConflict.current = () => {
    setSyncWarning("Прогресс изменился на другом устройстве. Загружаем актуальную версию.");
    skipAutoSaveAfterRecovery.current = true;
    if (!recoveryPromise.current) {
      recoveryPromise.current = hydrate(true, true)
        .then((recovered) => {
          if (!recovered) skipAutoSaveAfterRecovery.current = false;
        })
        .catch((error) => {
          skipAutoSaveAfterRecovery.current = false;
          throw error;
        })
        .finally(() => { recoveryPromise.current = null; });
    }
    return recoveryPromise.current;
  };

  useEffect(() => { void hydrate(); }, [hydrate]);

  useEffect(() => {
    if (!progressToast) return;
    const timer = window.setTimeout(() => setProgressToast(null), 3500);
    return () => window.clearTimeout(timer);
  }, [progressToast]);

  useEffect(() => {
    latestQuestionIndex.current = questionIndex;
    latestAnswers.current = answers;
    if (!brand || !sessionScope || screen !== "question" || !diagnostic || questions.length === 0) return;
    saveLocalSession(brand.school_id, sessionScope, {
      attemptId,
      ...(supersedesAttemptId.current
        ? { supersedesAttemptId: supersedesAttemptId.current }
        : {}),
      diagnosticId: diagnostic.id,
      contentVersion: diagnostic.content_version,
      mode,
      questionIndex,
      revision: progressRevision.current,
      answers,
      syncedQuestionIndex: syncedQuestionIndex.current,
      syncedAnswers: syncedAnswers.current,
    });
    if (skipAutoSaveAfterRecovery.current) {
      skipAutoSaveAfterRecovery.current = false;
      return;
    }
    if (!initData.current || Object.keys(answers).length === 0) return;
    const payload: ProgressPayload = {
      attempt_id: attemptId,
      session_scope: sessionScope,
      ...(supersedesAttemptId.current
        ? { supersedes_attempt_id: supersedesAttemptId.current }
        : {}),
      diagnostic_id: diagnostic.id,
      content_version: diagnostic.content_version,
      mode,
      question_index: questionIndex,
      question_count: questions.length,
      progress_revision: progressRevision.current + 1,
      answers,
    };
    pendingProgressPayload.current = payload;
    const timer = window.setTimeout(() => {
      pendingProgressTimer.current = null;
      pendingProgressPayload.current = null;
      progressQueue.current?.enqueue(payload);
    }, 300);
    pendingProgressTimer.current = timer;
    return () => {
      window.clearTimeout(timer);
      if (pendingProgressTimer.current === timer) {
        pendingProgressTimer.current = null;
        pendingProgressPayload.current = null;
      }
    };
  }, [answers, attemptId, brand, diagnostic, initData, mode, questionIndex, questions.length, screen, sessionScope]);

  useEffect(() => {
    if (screen !== "result" || !initData.current) return;
    if (!sessionScope) return;
    void markResultViewed(initData.current, attemptId, sessionScope).catch(() => undefined);
  }, [attemptId, initData, screen, sessionScope]);

  const beginLoadedDiagnostic = (selected: PublicDiagnostic, selectedMode: DiagnosticMode = mode) => {
    skipAutoSaveAfterRecovery.current = false;
    progressQueue.current?.cancel();
    attemptGeneration.current += 1;
    const nextAttemptId = createAttemptId();
    reviewRequestGate.current!.activate({
      attemptId: nextAttemptId,
      generation: attemptGeneration.current,
    });
    activeAttemptId.current = nextAttemptId;
    supersedesAttemptId.current = persistedAttemptId.current ?? undefined;
    setAttemptId(nextAttemptId);
    setLoadedDiagnostic(selected);
    setDiagnosticId(selected.id);
    setMode(selectedMode);
    setQuestionIndex(0);
    latestQuestionIndex.current = 0;
    progressRevision.current = 0;
    saveToastAttempt.current = null;
    setProgressSaveState("idle");
    setProgressToast(null);
    syncedQuestionIndex.current = 0;
    syncedAnswers.current = {};
    setAnswers({});
    latestAnswers.current = {};
    setInputDrafts({});
    setResult(null);
    setReview(null);
    setReviewIndex(0);
    setReviewError(null);
    setError(null);
    setScreen("question");
  };

  const beginDiagnostic = async (selected: PublicDiagnosticSummary, selectedMode: DiagnosticMode = mode) => {
    if (!sessionScope) return;
    const requestId = diagnosticLoadRequestId.current + 1;
    diagnosticLoadRequestId.current = requestId;
    dispatchDiagnosticLoad({ type: "load", requestId, summary: selected, intent: "new" });
    setScreen("diagnostic-loading");
    try {
      const loaded = await loadCachedDiagnostic(selected, sessionScope);
      if (requestId !== diagnosticLoadRequestId.current) return;
      dispatchDiagnosticLoad({ type: "loaded", requestId, diagnostic: loaded });
      beginLoadedDiagnostic(loaded, selectedMode);
    } catch {
      if (requestId !== diagnosticLoadRequestId.current) return;
      dispatchDiagnosticLoad({
        type: "failed",
        requestId,
        message: "Не удалось загрузить задания. Проверь соединение и повтори попытку.",
      });
    }
  };

  const answerQuestion = (value: AnswerValue) => {
    if (!diagnostic || !brand || !sessionScope) return;
    const question = questions[questionIndex];
    if ((question.type === "input" || question.type === "text") && typeof value === "string") {
      setInputDrafts((current) => ({ ...current, [question.id]: value }));
      const nextAnswers = question.type === "text"
        ? updateTextInputAnswer(answers, question.id, value, question.max_length)
        : updateNumericInputAnswer(answers, question.id, value);
      latestAnswers.current = nextAnswers;
      setAnswers(nextAnswers);
      return;
    }
    const nextAnswers = updateAnswerFromEditor(answers, question, value);
    latestAnswers.current = nextAnswers;
    setAnswers(nextAnswers);
  };

  const submit = async (answersForSubmission: AnswerMap = answers) => {
    if (!diagnostic || !brand || !sessionScope) return;
    const submitStartedAt = Date.now();
    const warningTimer = window.setTimeout(() => setSubmitWarning(true), SUBMIT_MINIMUM_MS);
    setSubmitWarning(false);
    setScreen("submitting");
    setError(null);
    const submittedAttemptId = attemptId;
    const submittedGeneration = attemptGeneration.current;
    try {
      try {
        await progressQueue.current?.flush();
      } catch (saveError) {
        if (isConflictError(saveError)) {
          setScreen("question");
          return;
        }
        throw saveError;
      }
      const response = await completeDiagnostic(
        initData.current,
        buildCompletionPayload(
          attemptId, sessionScope, diagnostic.id, diagnostic.content_version,
          progressRevision.current + 1, mode, answersForSubmission, supersedesAttemptId.current,
        ),
      );
      const remainingMs = submitPresentation(Date.now() - submitStartedAt).remainingMs;
      if (remainingMs > 0) await new Promise<void>((resolve) => window.setTimeout(resolve, remainingMs));
      if (
        submittedAttemptId !== activeAttemptId.current ||
        submittedGeneration !== attemptGeneration.current
      ) return;
      persistedAttemptId.current = response.attempt.attempt_id;
      activeAttemptId.current = response.attempt.attempt_id;
      reviewSelectionIdentity.current = {
        attemptId: response.attempt.attempt_id,
        contentVersion: response.attempt.content_version,
      };
      progressRevision.current = response.attempt.progress_revision;
      supersedesAttemptId.current = undefined;
      setResult(response.result);
      setSavedResultDiagnostic(null);
      setReview(null);
      setReviewIndex(0);
      setReviewMode("list");
      setReviewQuestionId(null);
      setReviewError(null);
      clearLocalSession(brand.school_id, sessionScope);
      setScreen("result");
      void refreshProgress();
    } catch (submitError) {
      if (isConflictError(submitError)) {
        progressQueue.current?.cancel();
        setScreen("question");
        await recoverConflict.current();
        return;
      }
      const refusedQuestionId = apiErrorDetail(submitError) === "invalid_answer_value"
        ? apiErrorQuestionId(submitError)
        : null;
      const refusedIndex = refusedQuestionId
        ? questions.findIndex((question) => question.id === refusedQuestionId)
        : -1;
      if (refusedIndex >= 0) {
        setQuestionIndex(refusedIndex);
        latestQuestionIndex.current = refusedIndex;
        setError(`Ответ на задание ${refusedIndex + 1} не принят. Проверь его и отправь результат снова.`);
      } else {
        setError("Не удалось получить результат. Ответы сохранены — повтори отправку.");
      }
      setScreen("question");
    } finally {
      window.clearTimeout(warningTimer);
      setSubmitWarning(false);
    }
  };

  const previousQuestion = () => {
    if (questionIndex === 0) {
      return;
    }
    setQuestionIndex((current) => {
      const next = current - 1;
      latestQuestionIndex.current = next;
      return next;
    });
  };

  const flushProgressForExit = async (): Promise<boolean> => {
    if (screen !== "question" || !diagnostic || !sessionScope || !initData.current) return true;
    if (pendingProgressTimer.current !== null) {
      window.clearTimeout(pendingProgressTimer.current);
      pendingProgressTimer.current = null;
    }
    pendingProgressPayload.current = null;
    if (Object.keys(latestAnswers.current).length > 0) {
      progressQueue.current?.enqueue({
        attempt_id: activeAttemptId.current,
        session_scope: sessionScope,
        ...(supersedesAttemptId.current
          ? { supersedes_attempt_id: supersedesAttemptId.current }
          : {}),
        diagnostic_id: diagnostic.id,
        content_version: diagnostic.content_version,
        mode,
        question_index: latestQuestionIndex.current,
        question_count: questions.length,
        progress_revision: progressRevision.current + 1,
        answers: latestAnswers.current,
      });
    }
    try {
      await progressQueue.current?.flush();
      return true;
    } catch {
      setProgressSaveState("error");
      setSyncWarning("Не удалось сохранить прогресс на сервере. Проверь связь и повтори выход.");
      return false;
    }
  };

  const nextQuestion = () => {
    if (questionIndex === questions.length - 1) {
      void submit();
      return;
    }
    setQuestionIndex((current) => {
      const next = current + 1;
      latestQuestionIndex.current = next;
      return next;
    });
  };

  const skipQuestion = () => {
    const question = questions[questionIndex];
    if (!question) return;
    const nextAnswers = { ...answers, [question.id]: emptyAnswerFor(question) };
    latestAnswers.current = nextAnswers;
    setAnswers(nextAnswers);
    if (questionIndex === questions.length - 1) {
      void submit(nextAnswers);
      return;
    }
    setQuestionIndex((current) => {
      const next = current + 1;
      latestQuestionIndex.current = next;
      return next;
    });
  };

  const openReview = (questionId?: string) => {
    setReviewQuestionId(questionId ?? null);
    setReviewMode(questionId ? "detail" : "list");
    const identity = reviewSelectionIdentity.current;
    if (questionId && identity && typeof window !== "undefined") {
      window.sessionStorage.setItem(`diagnostic-review:${identity.attemptId}:${identity.contentVersion}`, questionId);
    }
    if (questionId && review) {
      const mistakeIndex = review.items
        .filter((item) => !item.is_correct)
        .findIndex((item) => item.question_id === questionId);
      setReviewIndex(Math.max(0, mistakeIndex));
    }
    setReviewError(null);
    setScreen("review");
    if (!review) void refreshReview();
  };

  const mistakeCount = review?.items.filter((item) => !item.is_correct).length ?? 0;

  const reviewBack = () => {
    if (reviewMode === "list") {
      setScreen("result");
      return;
    }
    setReviewMode("list");
    setReviewQuestionId(null);
  };

  const reviewNext = () => {
    if (!review || mistakeCount === 0) return;
    const mistakes = review.items.filter((item) => !item.is_correct);
    const currentIndex = reviewQuestionId
      ? mistakes.findIndex((item) => item.question_id === reviewQuestionId)
      : reviewIndex;
    const nextIndex = Math.min(
      (currentIndex < 0 ? -1 : currentIndex) + 1,
      mistakes.length - 1,
    );
    const next = mistakes[nextIndex];
    if (!next) return;
    setReviewIndex(nextIndex);
    setReviewQuestionId(next.question_id);
    const identity = reviewSelectionIdentity.current;
    if (identity && typeof window !== "undefined") {
      window.sessionStorage.setItem(
        `diagnostic-review:${identity.attemptId}:${identity.contentVersion}`,
        next.question_id,
      );
    }
  };
  const reviewList = () => {
    setReviewMode("list");
    setReviewQuestionId(null);
  };

  return {
    state: {
      diagnostic,
      diagnosticLoad,
      questions,
      exam,
      mode,
      attemptId,
      questionIndex,
      answers,
      inputDrafts,
      result,
      resultDiagnostic: savedResultDiagnostic ?? diagnostic,
      review,
      reviewIndex,
      reviewMode,
      reviewQuestionId,
      reviewError,
      syncWarning,
      progressSaveState,
      progressToast,
      submitWarning,
    },
    actions: {
      hydrate,
      openSavedResult: (attempt) => {
        if (!attempt.result) return;
        setMode(attempt.mode);
        if (attempt.exam) setExam(attempt.exam);
        attemptGeneration.current += 1;
        progressQueue.current?.cancel();
        activeAttemptId.current = attempt.attempt_id;
        persistedAttemptId.current = attempt.attempt_id;
        reviewRequestGate.current!.activate({ attemptId: attempt.attempt_id, generation: attemptGeneration.current });
        setAttemptId(attempt.attempt_id);
        setResult(attempt.result);
        setSavedResultDiagnostic({ exam: attempt.exam ?? "", subject: attempt.subject ?? "Диагностика" });
        setReview(null);
        setReviewError(null);
        setReviewIndex(0);
        setReviewMode("list");
        setReviewQuestionId(null);
        reviewSelectionIdentity.current = { attemptId: attempt.attempt_id, contentVersion: attempt.content_version };
        setScreen("result");
      },
      setExam: (nextExam) => {
        setExam(nextExam);
        if (brand?.school_id) writeExamPreference(brand.school_id, nextExam);
      },
      chooseMode: (selectedMode, nextExam) => {
        setMode(selectedMode);
        setExam(nextExam);
        if (brand?.school_id) writeExamPreference(brand.school_id, nextExam);
        setScreen("subjects");
      },
      chooseFormat: (selectedMode, selectedDiagnostic) => {
        setMode(selectedMode);
        setExam(selectedDiagnostic.exam);
        if (brand?.school_id) writeExamPreference(brand.school_id, selectedDiagnostic.exam);
        return beginDiagnostic(selectedDiagnostic, selectedMode);
      },
      beginDiagnostic,
      answerQuestion,
      skipQuestion,
      previousQuestion,
      nextQuestion,
      flushProgressForExit,
      openReview,
      refreshReview,
      reviewBack,
      reviewNext,
      reviewList,
      clearReviewError: () => setReviewError(null),
      persistedAttemptId: () => persistedAttemptId.current,
    },
  };
}
