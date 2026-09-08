"use client";

import { useEffect, useRef, useState } from "react";

import { BottomNav, GameplayHomeScreen, GameplayProfileScreen, ModeScreen, NotTelegramScreen, SubjectsScreen, WelcomeScreen } from "./navigation-screens";
import { safeAssetPath } from "./question-assets";
import { QuestionView as TrainingQuestionView } from "./question-screen";
import {
  ResultScreen,
  ReviewScreen,
  RouteScreen,
  ForecastEmptyScreen,
  ForecastScreen,
} from "./result-flow";
import { forecastKind, forecastTrajectory, personalRoute } from "./result-flow-model";
import { loadDeliveryStatus, requestedAttemptId, retryDelivery, scheduleRetestReminder } from "./api";
import { gameplayProfileView } from "./gameplay-profile-model";
import { TrainerScreen } from "./trainer-screen";
import { trainerDiagnosticId, trainerHeaderView } from "./trainer-model";
import { LeagueScreen } from "./league-screen";
import { useBootstrap } from "./use-bootstrap";
import { useDiagnosticSession } from "./use-diagnostic-session";
import { useTrainer } from "./use-trainer";
import { isEmptyAnswer } from "./answer-values";
import { ConfirmSheet } from "./confirm-sheet";
import type { Brand, DeliveryStatus, PublicDiagnosticSummary, Screen } from "./types";
import type { NavigationIntent, NavigationSelection } from "./navigation-model";
import { shouldShowBottomNav } from "./navigation-model";

type DisplayBrand = Pick<Brand, "name" | "short_name" | "logo"> & {
  resultStatus: string;
};

const BUILD_BOT_USERNAME = process.env.NEXT_PUBLIC_BUILD_BOT_USERNAME ?? "";
const BUILD_BOT_URL = /^[A-Za-z][A-Za-z0-9_]{1,28}[Bb][Oo][Tt]$/.test(BUILD_BOT_USERNAME)
  ? `https://t.me/${BUILD_BOT_USERNAME}`
  : null;

const BUILD_BRAND: DisplayBrand = {
  name: process.env.NEXT_PUBLIC_BUILD_SCHOOL_NAME ?? "School",
  short_name: process.env.NEXT_PUBLIC_BUILD_SCHOOL_SHORT_NAME ?? "School",
  logo: process.env.NEXT_PUBLIC_BUILD_SCHOOL_LOGO ?? "",
  resultStatus: process.env.NEXT_PUBLIC_BUILD_RESULT_STATUS ?? "Result in the app",
};

function BrandHeader({
  brand,
}: {
  brand: DisplayBrand;
}) {
  const logo = safeAssetPath(brand.logo);
  return (
    <header className="brand-bar">
      <div className="brand" aria-label={brand.name}>
        {logo ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img className="brand-mark brand-logo" src={logo} alt={brand.short_name} />
        ) : (
          <span className="brand-mark" aria-hidden="true">{brand.short_name.slice(0, 2)}</span>
        )}
        <span>{brand.name}</span>
      </div>
      <span className="status-pill">{brand.resultStatus}</span>
    </header>
  );
}

export default function Home() {
  const [screen, setScreen] = useState<Screen>("loading");
  const [diagnosticExitOpen, setDiagnosticExitOpen] = useState(false);
  const [diagnosticExitSaving, setDiagnosticExitSaving] = useState(false);
  const [diagnosticExitError, setDiagnosticExitError] = useState<string | null>(null);
  const [deliveryStatus, setDeliveryStatus] = useState<DeliveryStatus | null>(null);
  const [navigationSelection, setNavigationSelection] = useState<NavigationSelection>({ exam: "", diagnosticId: null, mode: null });
  const [navigationIntent, setNavigationIntent] = useState<NavigationIntent>(null);
  const [forecastOrigin, setForecastOrigin] = useState<"result" | "review">("result");
  const bootstrapSession = useBootstrap(setScreen);
  const session = useDiagnosticSession({ bootstrap: bootstrapSession, screen, setScreen });
  const trainer = useTrainer({
    bootstrap: bootstrapSession.state.bootstrap,
    initData: bootstrapSession.initData,
    sessionScope: bootstrapSession.sessionScope,
    setScreen,
    refreshProgress: bootstrapSession.actions.refreshProgress,
  });

  const { bootstrap, error, outsideTelegram, dismissedOfferPlacements, leagueState } = bootstrapSession.state;
  const { dismissOfferPlacement, handleOfferEvent, openLeague } = bootstrapSession.actions;
  const {
    diagnostic, diagnosticLoad, questions, exam, questionIndex,
    answers, inputDrafts, result, resultDiagnostic, review, reviewIndex, reviewError, syncWarning,
  } = session.state;

  useEffect(() => {
    if (!exam) return;
    setNavigationSelection((current) => current.exam === exam ? current : { ...current, exam });
  }, [exam]);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [screen, questionIndex]);

  const openedRequestedResult = useRef(false);
  useEffect(() => {
    if (openedRequestedResult.current) return;
    const requested = requestedAttemptId();
    if (!requested || !bootstrapSession.state.bootstrap) return;
    openedRequestedResult.current = true;
    const attempt = bootstrapSession.state.bootstrap.results.find(
      (item) => item.attempt_id === requested && item.result,
    );
    if (attempt) session.actions.openSavedResult(attempt);
  }, [bootstrapSession.state.bootstrap, session.actions]);

  const brand = bootstrap?.school.brand;
  const displayBrand: DisplayBrand = brand ? {
    name: brand.name,
    short_name: brand.short_name,
    logo: brand.logo,
    resultStatus: brand.interface.result_in_app,
  } : BUILD_BRAND;
  const gameplayProfile = gameplayProfileView({ ...bootstrap?.progress_profile, ...bootstrap?.gameplay_profile });
  const dailyPlan = bootstrap?.daily_plan ?? null;
  const onboardingComplete = bootstrap?.onboarding?.status === "completed"
    || (!bootstrap?.onboarding && Boolean(bootstrap?.progress_profile?.completion_count));
  const goHome = () => {
    setNavigationIntent(null);
    void bootstrapSession.actions.refreshProgress();
    if (onboardingComplete) setScreen("home");
    else if (bootstrap?.onboarding?.status === "selection") {
      setNavigationSelection((current) => ({ ...current, diagnosticId: null, mode: null }));
      setScreen("subjects");
    }
    else setScreen("welcome");
  };
  const openNewDiagnostic = () => {
    setNavigationSelection({ exam, diagnosticId: null, mode: null });
    setNavigationIntent(null);
    setScreen("subjects");
  };
  const openSubject = (summary: PublicDiagnosticSummary) => {
    setNavigationIntent(null);
    setNavigationSelection({ exam: summary.exam, diagnosticId: summary.id, mode: null });
    session.actions.setExam(summary.exam);
    setScreen("mode");
  };
  const requestDiagnosticExit = () => {
    setDiagnosticExitError(null);
    setDiagnosticExitOpen(true);
  };
  const confirmDiagnosticExit = async () => {
    if (diagnosticExitSaving) return;
    setDiagnosticExitSaving(true);
    setDiagnosticExitError(null);
    const saved = await session.actions.flushProgressForExit();
    setDiagnosticExitSaving(false);
    if (!saved) {
      setDiagnosticExitError("Не удалось сохранить прогресс. Проверь связь и повтори попытку.");
      return;
    }
    setDiagnosticExitOpen(false);
    goHome();
  };
  const routeItems = result ? personalRoute(result) : [];
  const [reminderMessage, setReminderMessage] = useState<string | null>(null);
  const reminderGeneration = useRef(0);
  const repeatDiagnostic = () => {
    if (!result || !bootstrap) return;
    const summary = bootstrap.diagnostics.find((item) => item.id === result.diagnostic_id);
    if (summary) void session.actions.beginDiagnostic(summary);
  };
  const startFullDiagnostic = () => {
    if (!result || !bootstrap) return;
    const summary = bootstrap.diagnostics.find((item) => item.id === result.diagnostic_id);
    if (summary) void session.actions.beginDiagnostic(summary, "full");
  };
  const handleRouteAction = (action: import("./result-flow-model").PersonalRouteAction) => {
    if (!result || !bootstrap) return;
    if (action.kind === "review") {
      if (action.questionId) session.actions.openReview(action.questionId);
      return;
    }
    if (action.kind === "mistakes") {
      const attemptId = session.actions.persistedAttemptId();
      if (attemptId) void trainer.actions.start(result.diagnostic_id, "mistakes", attemptId, action.topic);
      return;
    }
    const attemptId = session.actions.persistedAttemptId();
    if (!attemptId || !bootstrapSession.initData.current || !bootstrapSession.sessionScope) return;
    const generation = reminderGeneration.current + 1;
    reminderGeneration.current = generation;
    setReminderMessage(null);
    void scheduleRetestReminder(
      bootstrapSession.initData.current, attemptId, bootstrapSession.sessionScope,
    ).then((response) => {
      if (generation !== reminderGeneration.current || attemptId !== session.actions.persistedAttemptId()) return;
      if (response.status === "scheduled") setReminderMessage("Повтор запланирован на месяц после этой диагностики.");
      else if (response.status === "sent") setReminderMessage("Напоминание уже отправлено.");
      else setReminderMessage("Напоминание недоступно для этой попытки.");
    }).catch(() => {
      if (generation === reminderGeneration.current && attemptId === session.actions.persistedAttemptId()) {
        setReminderMessage("Не удалось запланировать напоминание.");
      }
    });
  };
  const replayAttemptId = session.actions.persistedAttemptId();
  const deliveryAttempt = bootstrap?.results.find((attempt) => attempt.attempt_id === replayAttemptId);
  const reminderAttemptId = useRef<string | null>(null);
  useEffect(() => {
    if (reminderAttemptId.current === replayAttemptId) return;
    reminderAttemptId.current = replayAttemptId;
    reminderGeneration.current += 1;
    setReminderMessage(null);
  }, [replayAttemptId]);
  const deliveryStateAttemptId = useRef<string | null>(null);
  const [deliveryPollNonce, restartDeliveryPolling] = useState(0);
  useEffect(() => {
    if (screen !== "result" || !replayAttemptId || !bootstrapSession.initData.current || !bootstrapSession.sessionScope) return;
    const attemptChanged = deliveryStateAttemptId.current !== replayAttemptId;
    if (attemptChanged) {
      deliveryStateAttemptId.current = replayAttemptId;
      setDeliveryStatus(deliveryAttempt?.pdf_status ?? null);
    }
    const currentStatus = attemptChanged ? deliveryAttempt?.pdf_status ?? null : deliveryStatus;
    if (["sent", "abandoned"].includes(currentStatus ?? "")) {
      return;
    }
    let active = true;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const response = await loadDeliveryStatus(
          bootstrapSession.initData.current,
          replayAttemptId,
          bootstrapSession.sessionScope!,
        );
        if (!active) return;
        setDeliveryStatus(response.status);
        if (response.status !== "pending" && response.status !== "sending" && response.status !== "failed") return;
        timer = window.setTimeout(() => { void poll(); }, 5000);
      } catch {
        return;
      }
    };
    void poll();
    return () => {
      active = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [screen, replayAttemptId, bootstrapSession.initData, bootstrapSession.sessionScope, deliveryAttempt?.pdf_status, deliveryPollNonce]);
  const selectedTrainerSubject = diagnostic?.subject
    ?? resultDiagnostic?.subject
    ?? (bootstrap?.diagnostics.length === 1 ? bootstrap.diagnostics.at(0)?.subject : null);
  const trainerDiagnostic = trainerDiagnosticId(bootstrap, selectedTrainerSubject);
  const selectedDiagnostic = bootstrap?.diagnostics.find((item) => item.id === navigationSelection.diagnosticId) ?? null;
  const openTrainer = () => {
    if (trainerDiagnostic) {
      void trainer.actions.start(trainerDiagnostic);
      return;
    }
    setNavigationIntent({ kind: "trainer" });
    setNavigationSelection((current) => ({ ...current, diagnosticId: null, mode: null }));
    setScreen("subjects");
  };
  const trainerHeader = trainerHeaderView(bootstrap, trainer.state.trainer.session);
  const activeAssessment = screen === "question" || screen === "trainer";

  const style = brand ? {
    "--brand-primary": brand.colors.primary,
    "--brand-accent": brand.colors.accent,
    "--brand-signal": brand.colors.signal,
    "--brand-ink": brand.colors.ink,
    "--brand-paper": brand.colors.paper,
    "--brand-background": brand.colors.background,
  } as React.CSSProperties : undefined;

  if (outsideTelegram && !bootstrap) {
    return (
      <main className="app-shell" style={style}>
        <BrandHeader brand={displayBrand} />
        <NotTelegramScreen botUrl={BUILD_BOT_URL} />
      </main>
    );
  }

  if (error && !bootstrap) {
    return (
      <main className="app-shell" style={style}>
        <BrandHeader brand={displayBrand} />
        <section className="screen centered-state" role="alert">
          <span className="state-icon" aria-hidden="true">✈️</span>
          <h1>Диагностика пока недоступна</h1>
          <p>{error}</p>
          <button className="primary-button" onClick={() => void session.actions.hydrate()} type="button">Повторить загрузку</button>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell" style={style}>
      {!activeAssessment && <BrandHeader brand={displayBrand} />}
      {error && bootstrap && !activeAssessment && (
        <div role="alert" className="inline-warning">{error}<button type="button" onClick={() => void bootstrapSession.actions.refreshProgress()}>Обновить прогресс</button></div>
      )}

      {screen === "loading" && (
        <section className="screen loading-screen" aria-busy="true" aria-live="polite">
          <div className="skeleton skeleton-wide" />
          <div className="skeleton skeleton-short" />
          <div className="skeleton skeleton-card" />
          <div className="loading-spinner" aria-hidden="true" />
          <p className="loading-note">Загружаем диагностику…</p>
        </section>
      )}

      {screen === "diagnostic-loading" && diagnosticLoad.phase === "loading" && (
        <section className="screen centered-state" aria-live="polite" aria-busy="true">
          <div className="loading-spinner" aria-hidden="true" />
          <h1>{diagnosticLoad.intent === "resume" ? "Восстанавливаем прогресс…" : "Загружаем задания…"}</h1>
          <p>{diagnosticLoad.summary.exam} · {diagnosticLoad.summary.subject}</p>
        </section>
      )}

      {screen === "diagnostic-loading" && diagnosticLoad.phase === "error" && (
        <section className="screen centered-state" role="alert">
          <span className="state-icon" aria-hidden="true">✈️</span>
          <h1>Задания пока недоступны</h1>
          <p>{diagnosticLoad.message}</p>
          <button className="primary-button" type="button" onClick={() => {
            if (diagnosticLoad.intent === "resume") void session.actions.hydrate();
            else void session.actions.beginDiagnostic(diagnosticLoad.summary);
          }}>Повторить</button>
          {diagnosticLoad.intent === "new" && (
            <button className="secondary-button" type="button" onClick={() => setScreen("subjects")}>Назад к предметам</button>
          )}
        </section>
      )}

      {screen === "welcome" && bootstrap && bootstrap.diagnostics.length === 0 && (
        <section className="screen centered-state">
          <span className="state-icon" aria-hidden="true">📚</span>
          <h1>Диагностики готовятся</h1>
          <p>Школа скоро добавит предметы. Пришлём уведомление в Telegram, как только всё будет готово.</p>
          <a className="secondary-button" href={bootstrap.school.links.support} target="_blank" rel="noreferrer">Связаться с поддержкой</a>
        </section>
      )}

      {screen === "welcome" && bootstrap && bootstrap.diagnostics.length > 0 && (
        <WelcomeScreen
          diagnostics={bootstrap.diagnostics}
          labels={bootstrap.school.brand.interface}
          onStart={() => {
            void bootstrapSession.actions.beginOnboarding().then((saved) => {
              if (saved) {
                setNavigationIntent(null);
                setNavigationSelection((current) => ({ ...current, diagnosticId: null, mode: null }));
                setScreen("subjects");
              }
            });
          }}
          links={bootstrap.school.links}
        />
      )}

      {screen === "home" && bootstrap && bootstrap.diagnostics.length > 0 && (
        <>
        <GameplayHomeScreen
          diagnostics={bootstrap.diagnostics}
          results={bootstrap.results}
          resumableAttempt={bootstrap.attempt}
          lastSubject={bootstrap.results.find((attempt) => attempt.result)?.subject ?? null}
          labels={bootstrap.school.brand.interface}
          profile={gameplayProfile}
          dailyPlan={dailyPlan}
          onStart={openNewDiagnostic}
          onResume={() => void session.actions.hydrate(true)}
          onOpenSubject={openSubject}
          onOpenResult={session.actions.openSavedResult}
          onStartPlan={dailyPlan?.diagnostic_id
            ? () => void trainer.actions.start(dailyPlan.diagnostic_id!, "plan")
            : undefined}
          onOpenProfile={() => setScreen("profile")}
          offers={bootstrap.school.links.offers}
          onOfferEvent={handleOfferEvent}
          offerDismissed={Boolean(dismissedOfferPlacements.home)}
          onOfferDismiss={() => dismissOfferPlacement("home")}
        />
        </>
      )}

      {screen === "profile" && bootstrap && (
        <GameplayProfileScreen
          profile={gameplayProfile}
          onBack={() => setScreen("home")}
          onStart={openNewDiagnostic}
        />
      )}

      {screen === "league" && (
        <LeagueScreen
          state={leagueState}
          onRetry={() => void openLeague()}
          onHome={() => setScreen(bootstrap?.diagnostics.length ? "home" : "welcome")}
          onTrain={openTrainer}
        />
      )}

      {screen === "mode" && bootstrap && (
        selectedDiagnostic && <ModeScreen
          diagnostic={selectedDiagnostic}
          labels={bootstrap.school.brand.interface}
          onBack={() => setScreen(navigationSelection.diagnosticId ? "subjects" : "home")}
          onSelect={(selectedMode) => {
            void session.actions.chooseFormat(selectedMode, selectedDiagnostic);
          }}
        />
      )}

      {screen === "subjects" && bootstrap && (
        <SubjectsScreen
          diagnostics={bootstrap.diagnostics}
          exam={exam}
          labels={bootstrap.school.brand.interface}
          mode={navigationSelection.mode ?? undefined}
          onBack={() => {
            setNavigationIntent(null);
            setScreen(onboardingComplete ? "home" : "welcome");
          }}
          onExam={session.actions.setExam}
          onSelect={(summary) => {
            setNavigationSelection((current) => ({ ...current, diagnosticId: summary.id }));
            if (navigationIntent?.kind === "trainer") {
              setNavigationIntent(null);
              void trainer.actions.start(summary.id);
            } else if (navigationSelection.mode) void session.actions.chooseFormat(navigationSelection.mode, summary);
            else setScreen("mode");
          }}
        />
      )}

      {screen === "question" && diagnostic && questions[questionIndex] && (
        <>
          {error && <p className="inline-error" role="alert">{error}</p>}
          <TrainingQuestionView
            question={questions[questionIndex]}
            subject={diagnostic?.subject}
            index={questionIndex}
            total={questions.length}
            answer={questions[questionIndex].type === "input" || questions[questionIndex].type === "text"
              ? inputDrafts[questions[questionIndex].id] ?? answers[questions[questionIndex].id]
              : answers[questions[questionIndex].id]}
            skipped={Object.hasOwn(answers, questions[questionIndex].id)
              && isEmptyAnswer(questions[questionIndex], answers[questions[questionIndex].id])}
            skippedIndexes={questions.flatMap((question, questionIndex) => (
              Object.hasOwn(answers, question.id) && isEmptyAnswer(question, answers[question.id])
                ? [questionIndex]
                : []
            ))}
            onAnswer={session.actions.answerQuestion}
            onBack={session.actions.previousQuestion}
            onExit={requestDiagnosticExit}
            progressSaveState={session.state.progressSaveState}
            progressAnnouncement={syncWarning ?? session.state.progressToast}
            progressAnnouncementRole={syncWarning ? "alert" : "status"}
            onNext={session.actions.nextQuestion}
            onSkip={session.actions.skipQuestion}
            labels={brand!.interface}
          />
        </>
      )}

      {screen === "submitting" && (
        <section className="screen submit-screen" aria-live="polite" aria-busy="true">
          <div className="submit-orbit" aria-hidden="true"><span>🧠</span></div>
          <h1>Считаем результат</h1>
          <p>Сервер проверяет ответы и собирает твою карту знаний. Обычно это меньше минуты.</p>
          {session.state.submitWarning && <span className="submit-note">Не закрывай приложение</span>}
        </section>
      )}

      {screen === "result" && result && bootstrap && (
        resultDiagnostic && (
          <ResultScreen
            diagnostic={resultDiagnostic}
            result={result}
            pdfStatus={deliveryStatus ?? deliveryAttempt?.pdf_status ?? null}
            onReview={session.actions.openReview}
            onForecast={() => { setForecastOrigin("result"); setScreen("forecast"); }}
            onHome={goHome}
            onRetryDelivery={() => {
              if (!replayAttemptId) return;
              void retryDelivery(bootstrapSession.initData.current, replayAttemptId, bootstrapSession.sessionScope!)
                .then((response) => setDeliveryStatus(response.status))
                .then(() => restartDeliveryPolling((value) => value + 1))
                .catch(() => setDeliveryStatus("failed"));
            }}
            onOpenChat={BUILD_BOT_URL ? () => {
              const webApp = window.Telegram?.WebApp;
              if (webApp?.openTelegramLink) webApp.openTelegramLink(BUILD_BOT_URL);
              else window.open(BUILD_BOT_URL, "_blank", "noopener,noreferrer");
            } : undefined}
            onReplayMistakes={replayAttemptId && bootstrap.diagnostics.some((item) => item.id === result.diagnostic_id)
              ? () => void trainer.actions.start(result.diagnostic_id, "mistakes", replayAttemptId)
              : undefined}
          />
        )
      )}

      {screen === "trainer" && (
        <TrainerScreen
          state={trainer.state.trainer}
          dispatch={trainer.actions.dispatch}
          onAnswer={(questionId, answer) => void trainer.actions.answer(questionId, answer)}
          onFinish={() => void trainer.actions.finish()}
          onHome={goHome}
          onRetry={trainer.actions.retry}
          livesReminder={trainer.state.livesReminder}
          onRemindLives={() => void trainer.actions.remindLives()}
          offers={bootstrap?.school.links.offers}
          header={trainerHeader}
          offerDismissed={dismissedOfferPlacements}
          onOfferDismiss={dismissOfferPlacement}
          onOfferEvent={handleOfferEvent}
          labels={brand?.interface}
        />
      )}

      <ConfirmSheet
        open={diagnosticExitOpen}
        title="Выйти из диагностики?"
        message={diagnosticExitError ?? "Прогресс сохранится, и диагностику можно будет продолжить позже."}
        messageRole={diagnosticExitError ? "alert" : undefined}
        confirmLabel={diagnosticExitSaving ? "Сохраняем…" : "Выйти"}
        confirmDisabled={diagnosticExitSaving}
        onCancel={() => { if (!diagnosticExitSaving) setDiagnosticExitOpen(false); }}
        onConfirm={confirmDiagnosticExit}
      />

      {screen === "forecast" && result && bootstrap && (
        result.estimate && result.estimate.sample_size >= 10
          ? <ForecastScreen
              points={forecastTrajectory(result)}
              kind={forecastKind(result)}
              offers={bootstrap.school.links.offers}
              onBack={() => setScreen(forecastOrigin)}
              onRoute={() => setScreen("plan")}
            />
          : <ForecastEmptyScreen
              completedCount={result.estimate?.sample_size}
              minimumSampleSize={10}
              onBack={() => setScreen(forecastOrigin)}
              onStart={startFullDiagnostic}
              onPlan={() => setScreen("plan")}
            />
      )}

      {screen === "review" && result && (
        <ReviewScreen
          error={reviewError}
          index={reviewIndex}
          mode={session.state.reviewMode}
          selectedQuestionId={session.state.reviewQuestionId}
          items={review?.items ?? []}
          subject={resultDiagnostic?.subject}
          legacy={review?.available === false}
          loading={!review && !reviewError}
          onHome={goHome}
          onBack={session.actions.reviewBack}
          onForecast={() => { setForecastOrigin("review"); setScreen("forecast"); }}
          onNext={session.actions.reviewNext}
          onSelectQuestion={(questionId) => session.actions.openReview(questionId)}
          onList={session.actions.reviewList}
          onRetry={() => {
            session.actions.clearReviewError();
            void session.actions.refreshReview();
          }}
        />
      )}

      {screen === "plan" && result && bootstrap && (
        <RouteScreen
          items={routeItems}
          offers={bootstrap.school.links.offers}
          onRepeat={bootstrap.diagnostics.some((item) => item.id === result.diagnostic_id) ? repeatDiagnostic : undefined}
          onSubjects={() => setScreen("subjects")}
          onAction={handleRouteAction}
          reminderMessage={reminderMessage}
          onHome={goHome}
          xpReward={result.xp_earned}
        />
      )}
      {shouldShowBottomNav(screen) && (
        <BottomNav
          screen={screen}
          onNavigate={(nextScreen) => {
            if (nextScreen === "home") goHome();
            else if (nextScreen === "league") void openLeague();
            else if (nextScreen === "trainer") openTrainer();
            else setScreen(nextScreen);
          }}
        />
      )}
    </main>
  );
}
