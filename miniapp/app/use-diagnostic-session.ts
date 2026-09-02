"use client";

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";

import {
  buildCompletionPayload,
  clearLocalSession,
  completeDiagnostic,
  createAttemptId,
  createProgressSaveQueue,
  bootstrapResumeSummary,
  isConflictError,
  loadDiagnostic,
  loadReview,
  markResultViewed,
  restoreBootstrapSession,
  saveLocalSession,
  saveProgress,
  updateNumericInputAnswer,
} from "./api";
import type { ProgressPayload, ProgressSaveQueue } from "./api";
import {
  diagnosticLoadInitialState,
  diagnosticLoadReducer,
  diagnosticSummaryKey,
  type DiagnosticLoadState,
} from "./diagnostic-loader-model";
import { createReviewRequestGate } from "./review-request-gate";
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
  Screen,
} from "./types";

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
  review: ReviewResponse | null;
  reviewIndex: number;
  reviewError: string | null;
  syncWarning: string | null;
};

export type DiagnosticSessionActions = {
  hydrate(preserveCurrentScreen?: boolean): Promise<boolean>;
  setExam(exam: string): void;
  chooseMode(mode: DiagnosticMode, exam: string): void;
  beginDiagnostic(selected: PublicDiagnosticSummary): Promise<void>;
  answerQuestion(value: AnswerValue): void;
  previousQuestion(): void;
  nextQuestion(): void;
  openReview(): void;
  refreshReview(): Promise<ReviewResponse | null>;
  reviewBack(): void;
  reviewNext(): void;
  clearReviewError(): void;
  /** Attempt id the server has stored, used to replay that attempt's mistakes. */
  persistedAttemptId(): string | null;
};

export type DiagnosticSession = {
  state: DiagnosticSessionState;
  actions: DiagnosticSessionActions;
};

function questionsFor(diagnostic: PublicDiagnostic, mode: DiagnosticMode): Question[] {
  return mode === "quick" ? diagnostic.questions.slice(0, diagnostic.quick_count) : diagnostic.questions;
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
  const { load: loadBootstrapData, setError, countCompletion } = bootstrap.actions;

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
  const [review, setReview] = useState<ReviewResponse | null>(null);
  const [reviewIndex, setReviewIndex] = useState(0);
  const [reviewError, setReviewError] = useState<string | null>(null);

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
        syncedAnswers.current = response.attempt.answers;
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
      setReviewError(null);
      return outcome.value;
    }
    if (outcome.status === "error") {
      setReviewError("Не удалось загрузить разбор. Повторите запрос.");
    }
    return null;
  }, [attemptId, initData, sessionScope]);

  const hydrate = useCallback(async (preserveCurrentScreen = false) => {
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
      progressQueue.current?.cancel();
      loaded.apply();
      setLoadedDiagnostic(null);
      setExam((current) => current || data.diagnostics[0]?.exam || "");
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
        setScreen(data.progress_profile?.completion_count ? "home" : "welcome");
      }
      return true;
    } catch {
      if (generation !== hydrateGeneration.current) return false;
      setError("Не удалось загрузить диагностику. Проверьте соединение и повторите попытку.");
      return false;
    }
  }, [loadBootstrapData, loadCachedDiagnostic, setError, setScreen]);

  recoverConflict.current = () => {
    setSyncWarning("Прогресс изменился на другом устройстве. Загружаем актуальную версию.");
    if (!recoveryPromise.current) {
      recoveryPromise.current = hydrate(true)
        .then(() => undefined)
        .finally(() => { recoveryPromise.current = null; });
    }
    return recoveryPromise.current;
  };

  useEffect(() => { void hydrate(); }, [hydrate]);

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
    if (!initData.current || Object.keys(answers).length === 0) return;
    const timer = window.setTimeout(() => {
      progressQueue.current?.enqueue({
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
      });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [answers, attemptId, brand, diagnostic, initData, mode, questionIndex, questions.length, screen, sessionScope]);

  useEffect(() => {
    if (screen !== "result" || !initData.current) return;
    if (!sessionScope) return;
    void markResultViewed(initData.current, attemptId, sessionScope).catch(() => undefined);
  }, [attemptId, initData, screen, sessionScope]);

  const beginLoadedDiagnostic = (selected: PublicDiagnostic) => {
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
    setQuestionIndex(0);
    latestQuestionIndex.current = 0;
    progressRevision.current = 0;
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

  const beginDiagnostic = async (selected: PublicDiagnosticSummary) => {
    if (!sessionScope) return;
    const requestId = diagnosticLoadRequestId.current + 1;
    diagnosticLoadRequestId.current = requestId;
    dispatchDiagnosticLoad({ type: "load", requestId, summary: selected, intent: "new" });
    setScreen("diagnostic-loading");
    try {
      const loaded = await loadCachedDiagnostic(selected, sessionScope);
      if (requestId !== diagnosticLoadRequestId.current) return;
      dispatchDiagnosticLoad({ type: "loaded", requestId, diagnostic: loaded });
      beginLoadedDiagnostic(loaded);
    } catch {
      if (requestId !== diagnosticLoadRequestId.current) return;
      dispatchDiagnosticLoad({
        type: "failed",
        requestId,
        message: "Не удалось загрузить задания. Проверьте соединение и повторите попытку.",
      });
    }
  };

  const answerQuestion = (value: AnswerValue) => {
    if (!diagnostic || !brand || !sessionScope) return;
    const question = questions[questionIndex];
    if (question.type === "input" && typeof value === "string") {
      setInputDrafts((current) => ({ ...current, [question.id]: value }));
      const nextAnswers = updateNumericInputAnswer(answers, question.id, value);
      latestAnswers.current = nextAnswers;
      setAnswers(nextAnswers);
      return;
    }
    const nextAnswers = { ...answers, [question.id]: value };
    latestAnswers.current = nextAnswers;
    setAnswers(nextAnswers);
  };

  const submit = async () => {
    if (!diagnostic || !brand || !sessionScope) return;
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
          progressRevision.current + 1, mode, answers, supersedesAttemptId.current,
        ),
      );
      if (
        submittedAttemptId !== activeAttemptId.current ||
        submittedGeneration !== attemptGeneration.current
      ) return;
      persistedAttemptId.current = response.attempt.attempt_id;
      activeAttemptId.current = response.attempt.attempt_id;
      progressRevision.current = response.attempt.progress_revision;
      supersedesAttemptId.current = undefined;
      setResult(response.result);
      countCompletion();
      setReview(null);
      setReviewIndex(0);
      setReviewError(null);
      clearLocalSession(brand.school_id, sessionScope);
      setScreen("result");
    } catch (submitError) {
      if (isConflictError(submitError)) {
        progressQueue.current?.cancel();
        setScreen("question");
        await recoverConflict.current();
        return;
      }
      setError("Не удалось получить результат. Ответы сохранены — повторите отправку.");
      setScreen("question");
    }
  };

  const previousQuestion = () => {
    if (questionIndex === 0) {
      setScreen("subjects");
      return;
    }
    setQuestionIndex((current) => {
      const next = current - 1;
      latestQuestionIndex.current = next;
      return next;
    });
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

  const openReview = () => {
    setReviewIndex(0);
    setReviewError(null);
    setScreen("review");
    if (!review) void refreshReview();
  };

  const mistakeCount = review?.items.filter((item) => !item.is_correct).length ?? 0;

  const reviewBack = () => {
    if (reviewIndex === 0) {
      setScreen("result");
      return;
    }
    setReviewIndex((current) => Math.max(0, current - 1));
  };

  const reviewNext = () => {
    setReviewIndex((current) => Math.min(current + 1, Math.max(0, mistakeCount - 1)));
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
      review,
      reviewIndex,
      reviewError,
      syncWarning,
    },
    actions: {
      hydrate,
      setExam,
      chooseMode: (selectedMode, nextExam) => {
        setMode(selectedMode);
        setExam(nextExam);
        setScreen("subjects");
      },
      beginDiagnostic,
      answerQuestion,
      previousQuestion,
      nextQuestion,
      openReview,
      refreshReview,
      reviewBack,
      reviewNext,
      clearReviewError: () => setReviewError(null),
      persistedAttemptId: () => persistedAttemptId.current,
    },
  };
}
