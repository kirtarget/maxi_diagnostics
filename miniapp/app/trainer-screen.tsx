"use client";

import { useEffect, useRef, useState, type Dispatch, type ReactNode } from "react";
import { ActionBar } from "./action-bar";
import { answerReadiness } from "./answer-readiness";
import { StructuredAnswerEditor } from "./question-screen";
import { AssessmentHeader } from "./assessment-header";
import { ConfirmSheet } from "./confirm-sheet";
import { FormattedMathText } from "./math-display";
import { normalizeOffer, OfferSurface, type OfferPlacement, type OfferTelemetryEvent } from "./offer-ux";
import { hasApprovedPrimaryScore, PrimaryScoreBadge } from "./question-metadata";
import { QuestionBody, questionBodyModel } from "./question-body";
import { correctOptionIds, lifeNote } from "./trainer-feedback";
import { focusPromptReference } from "./prompt-layout";
import { plural } from "./text-utils";
import type { AnswerValue, Brand, Question, SchoolLinks } from "./types";
import {
  planProgress,
  planReasonLabel,
  trainerFeedbackKind,
  trainerModeLabel,
  type TrainerAction,
  type TrainerMode,
  type TrainerHeaderView,
  type TrainerState,
} from "./trainer-model";

export type LivesReminderState = {
  status: "idle" | "pending" | "scheduled" | "error";
};

export type TrainerScreenProps = {
  state: TrainerState;
  dispatch: Dispatch<TrainerAction>;
  onAnswer?: (questionId: string, answer: AnswerValue) => void;
  onFinish?: () => void;
  onHome?: () => void;
  onRetry?: () => void;
  livesReminder?: LivesReminderState;
  onRemindLives?: () => void;
  offers?: SchoolLinks["offers"];
  header?: TrainerHeaderView | null;
  offerDismissed?: Partial<Record<"trainer", boolean>>;
  onOfferDismiss?: (placement: Extract<OfferPlacement, "trainer">) => void;
  onOfferEvent?: (event: OfferTelemetryEvent) => void;
  labels?: Brand["interface"];
};

const LIFE_REFILL_INTERVAL_MS = 4 * 60 * 60 * 1000;

function formatCountdown(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  return now;
}

function TrainerNoLivesScreen({ nextLifeAt, livesReminder, onRemindLives, onHome, onRetry }: {
  nextLifeAt: string | null;
  livesReminder?: LivesReminderState;
  onRemindLives?: () => void;
  onHome?: () => void;
  onRetry?: () => void;
}) {
  const now = useNow();
  const dueAt = nextLifeAt ? Date.parse(nextLifeAt) : Number.NaN;
  const remainingMs = Number.isFinite(dueAt) ? dueAt - now : null;
  const ready = remainingMs !== null && remainingMs <= 0;
  const fraction = remainingMs === null ? 0 : Math.min(1, Math.max(0, 1 - remainingMs / LIFE_REFILL_INTERVAL_MS));
  const minutesLeft = remainingMs === null ? null : Math.max(1, Math.ceil(remainingMs / 60_000));
  const reminderStatus = livesReminder?.status ?? "idle";
  return <section className="screen trainer-screen centered-state no-lives-screen" aria-labelledby="no-lives-title">
    <div className="lives-row" aria-hidden="true"><span className="lives-row-lost">♥</span>♥♥♥♥</div>
    <h1 id="no-lives-title">Жизни закончились</h1>
    {ready
      ? <p>Жизнь уже должна вернуться — обнови тренировку и продолжай.</p>
      : <p>{minutesLeft !== null ? <>Одна жизнь восстановится через <b>{minutesLeft} {plural(minutesLeft, ["минуту", "минуты", "минут"])}</b>. </> : null}А диагностику можно проходить без жизней — там они не тратятся.</p>}
    {remainingMs !== null && !ready && (
      <div className="lives-recovery">
        <span className="lives-recovery-icon" aria-hidden="true">⏳</span>
        <div className="lives-recovery-track">
          <strong>Восстановление</strong>
          <div className="lives-recovery-rail" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(fraction * 100)}>
            <span className="lives-recovery-fill" style={{ width: `${fraction * 100}%` }} />
          </div>
        </div>
        <span className="lives-recovery-timer">{formatCountdown(remainingMs)}</span>
      </div>
    )}
    {ready
      ? <button className="primary-button" type="button" onClick={onRetry}>Обновить жизни <span aria-hidden="true">→</span></button>
      : <button className="primary-button" type="button" onClick={onHome}>Пройти диагностику <span aria-hidden="true">→</span></button>}
    {!ready && (reminderStatus === "scheduled"
      ? <p className="lives-reminder-note" role="status">Напомним в Telegram, когда жизни вернутся.</p>
      : <button className="link-button" type="button" disabled={reminderStatus === "pending"} onClick={onRemindLives}>
        {reminderStatus === "pending" ? "Настраиваем напоминание…" : "Напомнить в Telegram, когда жизни вернутся"}
      </button>)}
    {reminderStatus === "error" && <p className="lives-reminder-note" role="alert">Не получилось настроить напоминание. Попробуй ещё раз.</p>}
  </section>;
}

function Feedback({ state, subject, showPrimaryScore, mode }: { state: TrainerState; subject?: string; showPrimaryScore: boolean; mode: TrainerMode }) {
  const result = state.answerResult;
  if (!result) return null;
  const kind = trainerFeedbackKind(result);
  const label = kind === "correct" ? "Верно" : kind === "partial" ? "Почти" : "Неверно";
  const life = lifeNote(result, mode);
  return <aside className={`trainer-feedback is-${kind}`} aria-live="polite">
    <strong>{label}</strong>
    {showPrimaryScore && <PrimaryScoreBadge maxPrimaryScore={result.max_primary_score} earnedPrimaryScore={result.earned_primary_score} />}
    {result.correct_answer && (
      <p className="trainer-correct-answer">
        <span>Правильный ответ</span>
        <b><FormattedMathText text={result.correct_answer} subject={subject} /></b>
      </p>
    )}
    {result.explanation && <p><FormattedMathText text={result.explanation} subject={subject} /></p>}
    <div className="trainer-feedback-tally">
      {result.xp_delta > 0 && <small>+{result.xp_delta} XP</small>}
      {life && <small className={`trainer-life-note${life.isWarning ? " is-warning" : ""}`} role={life.isWarning ? "alert" : undefined}>{life.text}</small>}
    </div>
    {life?.isWarning && result.lives_remaining === 1 && <p className="trainer-last-life">Осталась одна жизнь. Следующий неверный ответ закончит тренировку.</p>}
  </aside>;
}

export function TrainerScreen({ state, dispatch, onAnswer, onFinish, onHome, onRetry, livesReminder, onRemindLives, offers = [], header, offerDismissed = {}, onOfferDismiss, onOfferEvent, labels }: TrainerScreenProps) {
  const offer = normalizeOffer(offers[0] ?? {});
  const [confirmOpen, setConfirmOpen] = useState(false);
  const autoFinishKey = `${state.session?.trainer_session_id ?? ""}:${state.session?.revision ?? ""}`;
  const autoFinishedKey = useRef<string | null>(null);
  useEffect(() => {
    if (state.phase !== "finishing" || !state.session || autoFinishedKey.current === autoFinishKey) return;
    autoFinishedKey.current = autoFinishKey;
    onFinish?.();
  }, [autoFinishKey, onFinish, state.phase, state.session]);
  if (state.phase === "idle") return <section className="screen trainer-screen"><p>Тренажёр готовится.</p></section>;
  if (state.phase === "error") return <section className="screen trainer-screen" role="alert"><h1>Не удалось продолжить</h1><p>{state.error}</p><button className="primary-button" type="button" onClick={() => { dispatch({ type: "retry" }); onRetry?.(); }}>Повторить</button></section>;
  if (state.phase === "finishing") return <section className="screen trainer-screen" aria-live="polite"><p>Завершаем тренировку…</p></section>;
  if (state.phase === "completed") {
    const result = state.finishResult;
    return <section className="screen trainer-screen trainer-complete" aria-labelledby="trainer-complete-title"><span className="status-symbol status-symbol-success" aria-hidden="true">🎉</span><h1 id="trainer-complete-title">Тренировка завершена</h1>{result && <p>{result.correct_count} из {result.question_count} верно · +{result.xp_earned} XP</p>}<p>Результат сохранён на сервере.</p>{offer && !offerDismissed.trainer && <OfferSurface offer={offer} placement="trainer" onClose={() => onOfferDismiss?.("trainer")} onEvent={onOfferEvent} />}<button className="primary-button" type="button" onClick={onHome}>На главную <span aria-hidden="true">→</span></button></section>;
  }
  if (state.phase === "answering" && state.session && state.session.mode === "normal" && state.session.lives_remaining <= 0) {
    return <TrainerNoLivesScreen
      nextLifeAt={state.session.next_life_at ?? null}
      livesReminder={livesReminder}
      onRemindLives={onRemindLives}
      onHome={onHome}
      onRetry={onRetry}
    />;
  }
  const questionIndex = state.phase === "feedback" && state.answeredQuestionIndex !== null
    ? state.answeredQuestionIndex
    : state.currentIndex;
  const question = state.session?.questions[questionIndex];
  if (!question || !state.session) return null;
  const locked = state.phase !== "answering";
  const plan = planProgress(state);
  const subject = header?.subject ?? state.session.diagnostic_id;
  const readiness = answerReadiness(question, state.draftAnswer, subject);
  const isLast = state.currentIndex >= state.session.questions.length;
  const submit = () => {
    dispatch({ type: "submit_answer" });
    if (state.draftAnswer) onAnswer?.(question.id, state.draftAnswer);
  };
  const modeLabel = header?.modeLabel ?? trainerModeLabel(state.session.mode);
  const body = questionBodyModel(question);
  const scored = state.session.mode !== "mistakes";
  const livesLeft = state.session.lives_remaining;
  const barMessage = state.phase === "feedback"
    ? (isLast ? "Тренировка почти закончена" : "Разбор ниже, дальше следующий вопрос")
    : state.phase === "awaiting_result"
      ? "Проверяем ответ"
      : readiness.isAnswered
        ? (scored && livesLeft === 1 ? "Это последняя жизнь. Неверный ответ закончит тренировку." : "Готово, можно проверить")
        : readiness.reason;
  return <section className="screen trainer-screen" aria-labelledby="trainer-title">
    <AssessmentHeader model={{
      topic: `Задание ${Math.min(questionIndex + 1, state.session.questions.length)} из ${state.session.questions.length} · ${question.topic || subject || "Тренажёр"}`,
      current: Math.min(questionIndex + 1, state.session.questions.length),
      total: state.session.questions.length,
      backDisabled: true,
      progressVariant: state.session.questions.length <= 12 ? "dots" : "bar",
      percent: (Math.min(questionIndex + 1, state.session.questions.length) / state.session.questions.length) * 100,
      titleClassName: "trainer-progress",
      showCount: false,
      exitClassName: "trainer-exit",
      onReference: body.layout.isLongReference ? () => focusPromptReference("trainer-reference") : undefined,
      backLabel: labels?.back,
      onBack: () => undefined,
      onExit: () => setConfirmOpen(true),
    }} />
    <div className="trainer-body">
    <div className="trainer-header-meta">
      <span className="trainer-mode">{modeLabel}</span>
      {state.session.mode === "normal" && <strong className="trainer-lives" aria-label={`Жизни: ${state.session.lives_remaining}`}>{"♥".repeat(Math.min(5, Math.max(0, state.session.lives_remaining)))}<span className="trainer-lives-empty">{"♥".repeat(Math.max(0, 5 - state.session.lives_remaining))}</span></strong>}
      {plan && <strong className="trainer-plan-progress">План: {plan.completed} из {plan.total}</strong>}
    </div>
    <QuestionBody
      question={question}
      subject={subject}
      model={body}
      idPrefix="trainer"
      illustrationAlt="Иллюстрация к заданию"
      meta={(
        <div className="trainer-prompt-meta">
          {planReasonLabel(state, question.id) && <span className="trainer-plan-reason">{planReasonLabel(state, question.id)}</span>}
          {hasApprovedPrimaryScore(question.source) && <PrimaryScoreBadge maxPrimaryScore={question.max_primary_score} />}
        </div>
      )}
    />
    <StructuredAnswerEditor
      question={question}
      subject={subject}
      value={state.phase === "feedback" ? state.submittedAnswer : state.draftAnswer}
      disabled={locked}
      suppressAutoHint={body.instructions.length > 0}
      labels={labels && { answer: labels.answer_label, placeholder: labels.enter_answer, choose: labels.choose_option }}
      correctOptions={state.phase === "feedback" ? correctOptionIds(question, state.answerResult?.correct_answer) : undefined}
      onChange={(answer) => dispatch({ type: "set_answer", answer })}
    />
    {state.phase === "feedback" && <Feedback state={state} subject={subject} showPrimaryScore={hasApprovedPrimaryScore(question.source)} mode={state.session.mode} />}
    </div>
    <ActionBar
      primaryLabel={state.phase === "feedback"
        ? (isLast ? "Завершить тренировку" : "Следующий вопрос")
        : state.phase === "awaiting_result" ? "Проверяем…" : "Проверить ответ"}
      primaryDisabled={state.phase !== "feedback" && (!readiness.isAnswered || state.phase === "awaiting_result")}
      onPrimary={() => {
        if (state.phase !== "feedback") { submit(); return; }
        if (isLast) { dispatch({ type: "finish_requested" }); onFinish?.(); return; }
        dispatch({ type: "next_question" });
      }}
      message={barMessage}
    />
    <ConfirmSheet open={confirmOpen} onCancel={() => setConfirmOpen(false)} onConfirm={() => { setConfirmOpen(false); onHome?.(); }} />
  </section>;
}

export function trainerAnswerSummary(answer: AnswerValue | undefined): ReactNode {
  if (Array.isArray(answer)) return answer.join(", ");
  if (answer && typeof answer === "object") return Object.values(answer).join(", ");
  return answer ?? "";
}
