"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  buildCompletionPayload,
  clearLocalSession,
  completeDiagnostic,
  createAttemptId,
  createProgressSaveQueue,
  isConflictError,
  loadBootstrap,
  loadReview,
  markResultViewed,
  restoreBootstrapSession,
  saveLocalSession,
updateNumericInputAnswer,
saveProgress,
} from "./api";
import type { ProgressPayload, ProgressSaveQueue } from "./api";
import { GameplayHomeScreen, GameplayProfileScreen, ModeScreen, SubjectsScreen, WelcomeScreen } from "./navigation-screens";
import { safeAssetPath } from "./question-assets";
import { QuestionView as TrainingQuestionView } from "./question-screen";
import {
  ForecastScreen,
  ResultScreen,
  ReviewScreen,
  RouteScreen,
} from "./result-flow";
import { forecastTrajectory, pdfStatusCopy, personalRoute } from "./result-flow-model";
import { createReviewRequestGate } from "./review-request-gate";
import { initializeTelegram } from "./telegram-webapp";
import { gameplayProfileView } from "./gameplay-profile-model";
import type {
  AnswerMap,
  AnswerValue,
  Brand,
  BootstrapResponse,
  DiagnosticMode,
  PublicDiagnostic,
  Question,
  ReviewResponse,
  ServerResult,
} from "./types";

type Screen = "loading" | "welcome" | "home" | "profile" | "mode" | "subjects" | "question" | "submitting" | "result" | "review" | "forecast" | "route";

type DisplayBrand = Pick<Brand, "name" | "short_name" | "logo"> & {
  resultStatus: string;
};

const BUILD_BRAND: DisplayBrand = {
  name: process.env.NEXT_PUBLIC_BUILD_SCHOOL_NAME ?? "School",
  short_name: process.env.NEXT_PUBLIC_BUILD_SCHOOL_SHORT_NAME ?? "School",
  logo: process.env.NEXT_PUBLIC_BUILD_SCHOOL_LOGO ?? "",
  resultStatus: process.env.NEXT_PUBLIC_BUILD_RESULT_STATUS ?? "Result in Telegram",
};

function questionsFor(diagnostic: PublicDiagnostic, mode: DiagnosticMode): Question[] {
  return mode === "quick" ? diagnostic.questions.slice(0, diagnostic.quick_count) : diagnostic.questions;
}

function BrandHeader({
  brand,
  disabled,
  onHome,
}: {
  brand: DisplayBrand;
  disabled: boolean;
  onHome: () => void;
}) {
  const logo = safeAssetPath(brand.logo);
  return (
    <header className="brand-bar">
      <button className="brand" type="button" onClick={onHome} disabled={disabled}>
        {logo ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img className="brand-mark brand-logo" src={logo} alt={brand.short_name} />
        ) : (
          <span className="brand-mark" aria-hidden="true">{brand.short_name.slice(0, 2)}</span>
        )}
        <span>{brand.name}</span>
      </button>
      <span className="status-pill">{brand.resultStatus}</span>
    </header>
  );
}

export default function Home() {
  const [screen, setScreen] = useState<Screen>("loading");
  const [bootstrap, setBootstrap] = useState<BootstrapResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
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
  const initData = useRef("");
  const progressRevision = useRef(0);
  const syncedQuestionIndex = useRef(0);
  const syncedAnswers = useRef<AnswerMap>({});
  const latestQuestionIndex = useRef(0);
  const latestAnswers = useRef<AnswerMap>({});
  const activeAttemptId = useRef(attemptId);
  const persistedAttemptId = useRef<string | null>(null);
  const supersedesAttemptId = useRef<string | undefined>(undefined);
  const schoolIdRef = useRef<string | null>(null);
  const sessionScopeRef = useRef<string | null>(null);
  const attemptGeneration = useRef(0);
  const reviewRequestGate = useRef<ReturnType<typeof createReviewRequestGate> | null>(null);
  if (!reviewRequestGate.current) {
    reviewRequestGate.current = createReviewRequestGate();
    reviewRequestGate.current.activate({ attemptId, generation: attemptGeneration.current });
  }
  const hydrateGeneration = useRef(0);
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

  const diagnostic = useMemo(
    () => bootstrap?.diagnostics.find((item) => item.id === diagnosticId) ?? null,
    [bootstrap, diagnosticId],
  );
  const questions = useMemo(
    () => diagnostic ? questionsFor(diagnostic, mode) : [],
    [diagnostic, mode],
  );
  const brand = bootstrap?.school.brand;
  const sessionScope = bootstrap?.session_scope;

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
  }, [attemptId, sessionScope]);

  const hydrate = useCallback(async (preserveCurrentScreen = false) => {
    const generation = hydrateGeneration.current + 1;
    hydrateGeneration.current = generation;
    setError(null);
    if (!preserveCurrentScreen) setScreen("loading");
    const webApp = initializeTelegram();
    initData.current = webApp?.initData ?? "";
    if (!initData.current) {
      setError("Откройте диагностику из Telegram-бота школы, чтобы подтвердить вход.");
      return false;
    }
    try {
      const data = await loadBootstrap(initData.current);
      if (generation !== hydrateGeneration.current) return false;
      attemptGeneration.current += 1;
      progressQueue.current?.cancel();
      setBootstrap(data);
      setExam((current) => current || data.diagnostics[0]?.exam || "");
      schoolIdRef.current = data.school.brand.school_id;
      sessionScopeRef.current = data.session_scope;
      webApp?.setHeaderColor(data.school.brand.colors.background);
      webApp?.setBackgroundColor(data.school.brand.colors.background);
      if (data.diagnostics.length === 0) {
        setScreen("welcome");
        return true;
      }

      const session = restoreBootstrapSession(data);
      const savedDiagnostic = session && data.diagnostics.find((item) => item.id === session.diagnosticId);
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
  }, []);
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
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [screen, questionIndex]);

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
  }, [answers, attemptId, brand, diagnostic, mode, questionIndex, questions.length, screen, sessionScope]);

  useEffect(() => {
    if (screen !== "result" || !initData.current) return;
    if (!sessionScope) return;
    void markResultViewed(initData.current, attemptId, sessionScope).catch(() => undefined);
  }, [attemptId, screen, sessionScope]);

  const beginDiagnostic = (selected: PublicDiagnostic) => {
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

  const displayBrand: DisplayBrand = brand ? {
    name: brand.name,
    short_name: brand.short_name,
    logo: brand.logo,
    resultStatus: brand.interface.result_in_telegram,
  } : BUILD_BRAND;
  const gameplayProfile = gameplayProfileView({ ...bootstrap?.progress_profile, ...bootstrap?.gameplay_profile });
  const mistakeCount = review?.items.filter((item) => !item.is_correct).length ?? 0;
  const forecastPoints = result ? forecastTrajectory(result) : [];
  const routeItems = result ? personalRoute(result.growth_topics) : [];
  const currentPdfStatus = review?.pdf_status ?? "pending";

  const openReview = () => {
    setReviewIndex(0);
    setReviewError(null);
    setScreen("review");
    if (!review) void refreshReview();
  };

  const style = brand ? {
    "--brand-primary": brand.colors.primary,
    "--brand-accent": brand.colors.accent,
    "--brand-signal": brand.colors.signal,
    "--brand-ink": brand.colors.ink,
    "--brand-paper": brand.colors.paper,
    "--brand-background": brand.colors.background,
  } as React.CSSProperties : undefined;

  if (error && !bootstrap) {
    return (
      <main className="app-shell" style={style}>
        <div className="ambient-grid" aria-hidden="true" />
        <BrandHeader brand={displayBrand} disabled onHome={() => undefined} />
        <section className="screen centered-state" role="alert">
          <span className="state-code">Ошибка загрузки</span>
          <h1>Диагностика пока недоступна</h1>
          <p>{error}</p>
          <button className="primary-button" onClick={() => void hydrate()} type="button">Повторить загрузку</button>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell" style={style}>
      <div className="ambient-grid" aria-hidden="true" />
      <BrandHeader
        brand={displayBrand}
        disabled={!brand || screen === "submitting"}
        onHome={() => setScreen(bootstrap?.diagnostics.length ? "home" : "welcome")}
      />

      {screen === "loading" && (
        <section className="screen loading-screen" aria-busy="true" aria-live="polite">
          <span className="state-code">Подготовка</span>
          <h1>Загружаем диагностику</h1>
          <div className="skeleton skeleton-wide" />
          <div className="skeleton skeleton-short" />
          <div className="skeleton skeleton-card" />
        </section>
      )}

      {screen === "welcome" && bootstrap && bootstrap.diagnostics.length === 0 && (
        <section className="screen centered-state">
          <span className="state-code">Нет материалов</span>
          <h1>Диагностики ещё готовятся</h1>
          <p>Вернитесь позже или уточните дату запуска у школы.</p>
          <a className="secondary-button" href={bootstrap.school.links.support} target="_blank" rel="noreferrer">Связаться с поддержкой</a>
        </section>
      )}

      {screen === "welcome" && bootstrap && bootstrap.diagnostics.length > 0 && (
        <WelcomeScreen
          diagnostics={bootstrap.diagnostics}
          labels={bootstrap.school.brand.interface}
          onStart={() => setScreen("home")}
          links={bootstrap.school.links}
        />
      )}

      {screen === "home" && bootstrap && bootstrap.diagnostics.length > 0 && (
        <GameplayHomeScreen
          diagnostics={bootstrap.diagnostics}
          labels={bootstrap.school.brand.interface}
          profile={gameplayProfile}
          onStart={() => setScreen("mode")}
          onOpenProfile={() => setScreen("profile")}
        />
      )}

      {screen === "profile" && bootstrap && (
        <GameplayProfileScreen
          profile={gameplayProfile}
          onBack={() => setScreen("home")}
          onStart={() => setScreen("mode")}
        />
      )}

      {screen === "mode" && bootstrap && (
        <ModeScreen
          labels={bootstrap.school.brand.interface}
          onBack={() => setScreen("home")}
          onSelect={(selectedMode) => {
            setMode(selectedMode);
            setExam(bootstrap.diagnostics[0]?.exam ?? "");
            setScreen("subjects");
          }}
        />
      )}

      {screen === "subjects" && bootstrap && (
        <SubjectsScreen
          diagnostics={bootstrap.diagnostics}
          exam={exam}
          labels={bootstrap.school.brand.interface}
          mode={mode}
          onBack={() => setScreen("mode")}
          onExam={setExam}
          onSelect={beginDiagnostic}
        />
      )}

      {screen === "question" && diagnostic && questions[questionIndex] && (
        <>
          {syncWarning && <p className="inline-warning" role="status">{syncWarning}</p>}
          {error && <p className="inline-error" role="alert">{error}</p>}
          <TrainingQuestionView
            question={questions[questionIndex]}
            index={questionIndex}
            total={questions.length}
            answer={questions[questionIndex].type === "input"
              ? inputDrafts[questions[questionIndex].id] ?? answers[questions[questionIndex].id]
              : answers[questions[questionIndex].id]}
            onAnswer={answerQuestion}
            onBack={() => questionIndex === 0 ? setScreen("subjects") : setQuestionIndex((current) => {
              const next = current - 1;
              latestQuestionIndex.current = next;
              return next;
            })}
            onNext={() => questionIndex === questions.length - 1 ? void submit() : setQuestionIndex((current) => {
              const next = current + 1;
              latestQuestionIndex.current = next;
              return next;
            })}
            labels={brand!.interface}
          />
        </>
      )}

      {screen === "submitting" && (
        <section className="screen centered-state" aria-live="polite" aria-busy="true">
          <div className="calculating-orbit" aria-hidden="true"><span>Σ</span></div>
          <span className="state-code">Ответы отправлены</span>
          <h1>Сервер считает результат</h1>
          <p>Проверяем ответы и собираем карту тем.</p>
          <div className="loading-line"><span /></div>
        </section>
      )}

      {screen === "result" && result && bootstrap && (
        diagnostic && (
          <ResultScreen
            diagnostic={diagnostic}
            pdfStatus={currentPdfStatus}
            result={result}
            onReview={openReview}
            onForecast={() => setScreen("forecast")}
          />
        )
      )}

      {screen === "review" && result && (
        <ReviewScreen
          error={reviewError}
          index={reviewIndex}
          items={review?.items ?? []}
          legacy={review?.available === false}
          loading={!review && !reviewError}
          onBack={() => reviewIndex === 0
            ? setScreen("result")
            : setReviewIndex((current) => Math.max(0, current - 1))}
          onForecast={() => setScreen("forecast")}
          onNext={() => setReviewIndex((current) => Math.min(current + 1, Math.max(0, mistakeCount - 1)))}
          onRetry={() => {
            setReviewError(null);
            void refreshReview();
          }}
        />
      )}

      {screen === "forecast" && result && (
        <ForecastScreen
          points={forecastPoints}
          onBack={() => setScreen(review ? "review" : "result")}
          onRoute={() => setScreen("route")}
        />
      )}

      {screen === "route" && result && bootstrap && (
        <RouteScreen
          items={routeItems}
          offers={bootstrap.school.links.offers}
          pdf={pdfStatusCopy(currentPdfStatus)}
          onRefreshPdf={() => void refreshReview()}
          onSubjects={() => setScreen("subjects")}
        />
      )}
    </main>
  );
}
