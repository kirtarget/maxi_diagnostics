"use client";

import { useEffect, useRef, useState } from "react";

import { GameplayHomeScreen, GameplayProfileScreen, ModeScreen, NotTelegramScreen, SubjectsScreen, WelcomeScreen } from "./navigation-screens";
import { safeAssetPath } from "./question-assets";
import { QuestionView as TrainingQuestionView } from "./question-screen";
import {
  ResultScreen,
  ReviewScreen,
  RouteScreen,
} from "./result-flow";
import { personalRoute } from "./result-flow-model";
import { requestedAttemptId } from "./api";
import { gameplayProfileView } from "./gameplay-profile-model";
import { TrainerScreen } from "./trainer-screen";
import { trainerDiagnosticId, trainerHeaderView } from "./trainer-model";
import { LeagueScreen } from "./league-screen";
import { useBootstrap } from "./use-bootstrap";
import { useDiagnosticSession } from "./use-diagnostic-session";
import { useTrainer } from "./use-trainer";
import { isEmptyAnswer } from "./answer-values";
import { ConfirmSheet } from "./confirm-sheet";
import type { Brand, Screen } from "./types";

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
  const [diagnosticExitOpen, setDiagnosticExitOpen] = useState(false);
  const [diagnosticExitSaving, setDiagnosticExitSaving] = useState(false);
  const [diagnosticExitError, setDiagnosticExitError] = useState<string | null>(null);
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
    diagnostic, diagnosticLoad, questions, exam, mode, questionIndex,
    answers, inputDrafts, result, resultDiagnostic, review, reviewIndex, reviewError, syncWarning,
  } = session.state;

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
    void bootstrapSession.actions.refreshProgress();
    if (onboardingComplete) setScreen("home");
    else if (bootstrap?.onboarding?.status === "selection") session.actions.chooseMode("quick", exam);
    else setScreen("welcome");
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
      setDiagnosticExitError("Не удалось сохранить прогресс. Проверьте связь и повторите попытку.");
      return;
    }
    setDiagnosticExitOpen(false);
    goHome();
  };
  const routeItems = result ? personalRoute(result.growth_topics) : [];
  const replayAttemptId = session.actions.persistedAttemptId();
  const selectedTrainerSubject = diagnostic?.subject
    ?? resultDiagnostic?.subject
    ?? (bootstrap?.diagnostics.length === 1 ? bootstrap.diagnostics.at(0)?.subject : null);
  const trainerDiagnostic = trainerDiagnosticId(bootstrap, selectedTrainerSubject);
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
        <BrandHeader brand={displayBrand} disabled onHome={() => undefined} />
        <NotTelegramScreen botUrl={BUILD_BOT_URL} />
      </main>
    );
  }

  if (error && !bootstrap) {
    return (
      <main className="app-shell" style={style}>
        <BrandHeader brand={displayBrand} disabled onHome={() => undefined} />
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
      {!activeAssessment && <BrandHeader
        brand={displayBrand}
        disabled={!brand || screen === "submitting"}
        onHome={goHome}
      />}
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
              if (saved) session.actions.chooseMode("quick", bootstrap.diagnostics[0]?.exam ?? "");
            });
          }}
          links={bootstrap.school.links}
        />
      )}

      {screen === "home" && bootstrap && bootstrap.diagnostics.length > 0 && (
        <>
        <GameplayHomeScreen
          diagnostics={bootstrap.diagnostics}
          labels={bootstrap.school.brand.interface}
          profile={gameplayProfile}
          dailyPlan={dailyPlan}
          onStart={() => setScreen("mode")}
          onStartPlan={dailyPlan?.diagnostic_id
            ? () => void trainer.actions.start(dailyPlan.diagnostic_id!, "plan")
            : undefined}
          onStartTrainer={() => {
            if (trainerDiagnostic) void trainer.actions.start(trainerDiagnostic);
          }}
          onOpenProfile={() => setScreen("profile")}
          onOpenLeague={() => void openLeague()}
          offers={bootstrap.school.links.offers}
          onOfferEvent={handleOfferEvent}
          offerDismissed={Boolean(dismissedOfferPlacements.home)}
          onOfferDismiss={() => dismissOfferPlacement("home")}
        />
        {bootstrap.results.some((attempt) => attempt.result) && (
          <section className="screen" aria-label="Предыдущие результаты">
            <h2>Мои результаты</h2>
            <p className="lead">Каждый результат и разбор ошибок хранятся здесь. Открой любую пройденную диагностику.</p>
            {bootstrap.results.filter((attempt) => attempt.result).map((attempt) => (
              <button key={attempt.attempt_id} type="button" className="secondary-button" onClick={() => session.actions.openSavedResult(attempt)}>
                {attempt.exam} · {attempt.subject ?? "Диагностика"} · {attempt.result!.correct_count} из {attempt.result!.question_count}
              </button>
            ))}
          </section>
        )}
        </>
      )}

      {screen === "profile" && bootstrap && (
        <GameplayProfileScreen
          profile={gameplayProfile}
          onBack={() => setScreen("home")}
          onStart={() => setScreen("mode")}
        />
      )}

      {screen === "league" && (
        <LeagueScreen
          state={leagueState}
          onRetry={() => void openLeague()}
          onHome={() => setScreen(bootstrap?.diagnostics.length ? "home" : "welcome")}
        />
      )}

      {screen === "mode" && bootstrap && (
        <ModeScreen
          labels={bootstrap.school.brand.interface}
          onBack={() => setScreen("home")}
          onSelect={(selectedMode) => session.actions.chooseMode(
            selectedMode,
            bootstrap.diagnostics[0]?.exam ?? "",
          )}
        />
      )}

      {screen === "subjects" && bootstrap && (
        <SubjectsScreen
          diagnostics={bootstrap.diagnostics}
          exam={exam}
          labels={bootstrap.school.brand.interface}
          mode={mode}
          onBack={() => setScreen(onboardingComplete ? "mode" : "welcome")}
          onExam={session.actions.setExam}
          onSelect={session.actions.beginDiagnostic}
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
          <span className="submit-note">Не закрывай приложение</span>
        </section>
      )}

      {screen === "result" && result && bootstrap && (
        resultDiagnostic && (
          <ResultScreen
            diagnostic={resultDiagnostic}
            result={result}
            onReview={session.actions.openReview}
            onForecast={() => setScreen("route")}
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

      {screen === "review" && result && (
        <ReviewScreen
          error={reviewError}
          index={reviewIndex}
          items={review?.items ?? []}
          subject={resultDiagnostic?.subject}
          legacy={review?.available === false}
          loading={!review && !reviewError}
          onBack={session.actions.reviewBack}
          onForecast={() => setScreen("route")}
          onNext={session.actions.reviewNext}
          onRetry={() => {
            session.actions.clearReviewError();
            void session.actions.refreshReview();
          }}
        />
      )}

      {screen === "route" && result && bootstrap && (
        <RouteScreen
          items={routeItems}
          offers={bootstrap.school.links.offers}
          onSubjects={() => setScreen("subjects")}
        />
      )}
    </main>
  );
}
