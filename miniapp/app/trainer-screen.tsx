"use client";

import { useEffect, useRef, useState, type Dispatch, type ReactNode } from "react";
import type { AnswerValue, InputQuestion, MatchingQuestion, MultipleQuestion, Question } from "./types";
import {
  isTrainerAnswerComplete,
  type TrainerAction,
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
};

function QuestionPrompt({ question }: { question: Question }) {
  return <div className="trainer-prompt"><span>{question.title}</span><h1>{question.prompt}</h1><small>{question.topic}</small></div>;
}

function AnswerEditor({ question, value, disabled, onChange }: {
  question: Question;
  value: AnswerValue | undefined;
  disabled: boolean;
  onChange: (answer: AnswerValue) => void;
}) {
  if (question.type === "single") {
    return <div className="answer-list" role="radiogroup" aria-label="Выберите один вариант">
      {question.options.map((option, index) => <OptionButton key={option.id} label={option.label} marker={String.fromCharCode(65 + index)} selected={value === option.id} disabled={disabled} onClick={() => onChange(option.id)} />)}
    </div>;
  }
  if (question.type === "multiple") return <MultipleEditor question={question} value={Array.isArray(value) ? value : []} disabled={disabled} onChange={onChange} />;
  if (question.type === "matching") return <MatchingEditor question={question} value={value && !Array.isArray(value) && typeof value === "object" ? value : {}} disabled={disabled} onChange={onChange} />;
  return <InputEditor question={question} value={typeof value === "string" ? value : ""} disabled={disabled} onChange={onChange} />;
}

function OptionButton({ label, marker, selected, disabled, onClick }: { label: string; marker: string; selected: boolean; disabled: boolean; onClick: () => void }) {
  return <button type="button" role="radio" aria-checked={selected} disabled={disabled} className={`answer-option${selected ? " selected" : ""}`} onClick={onClick}>
    <span className="option-letter">{marker}</span><span>{label}</span><span className="selection-mark" aria-hidden="true" />
  </button>;
}

function MultipleEditor({ question, value, disabled, onChange }: { question: MultipleQuestion; value: string[]; disabled: boolean; onChange: (answer: AnswerValue) => void }) {
  return <div className="answer-list" role="group" aria-label={`Выберите ${question.selection_limit} варианта`}>
    {question.options.map((option, index) => {
      const selected = value.includes(option.id);
      return <OptionButton key={option.id} label={option.label} marker={String.fromCharCode(65 + index)} selected={selected} disabled={disabled || (!selected && value.length >= question.selection_limit)} onClick={() => onChange(selected ? value.filter((id) => id !== option.id) : [...value, option.id])} />;
    })}
  </div>;
}

function MatchingEditor({ question, value, disabled, onChange }: { question: MatchingQuestion; value: Record<string, string>; disabled: boolean; onChange: (answer: AnswerValue) => void }) {
  return <div className="matching-list">
    {question.items.map((item, index) => <label className="matching-row" key={item.id}>
      <span className="matching-index">{index + 1}</span><span>{item.label}</span>
      <select disabled={disabled} value={value[item.id] ?? ""} aria-label={`Соответствие для ${item.label}`} onChange={(event) => onChange({ ...value, [item.id]: event.target.value })}>
        <option value="">Выберите</option>{question.options.map((option) => <option value={option.id} key={option.id}>{option.label}</option>)}
      </select>
    </label>)}
  </div>;
}

function InputEditor({ question, value, disabled, onChange }: { question: InputQuestion; value: string; disabled: boolean; onChange: (answer: AnswerValue) => void }) {
  return <label className="short-answer"><span>Твой ответ</span><input disabled={disabled} value={value} maxLength={64} onChange={(event) => onChange(event.target.value)} placeholder="Введи ответ" /></label>;
}

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
      : <p>{minutesLeft !== null ? <>Одна жизнь восстановится через <b>{minutesLeft} мин</b>. </> : null}А диагностику можно проходить без жизней — там они не тратятся.</p>}
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

function Feedback({ state }: { state: TrainerState }) {
  const result = state.answerResult;
  if (!result) return null;
  return <aside className={`trainer-feedback ${result.is_correct ? "is-correct" : "is-wrong"}`} aria-live="polite">
    <strong>{result.is_correct ? "Верно" : "Почти"}</strong>
    {result.correct_answer && <p>Ответ: {result.correct_answer}</p>}
    {result.explanation && <p>{result.explanation}</p>}
    {result.xp_delta > 0 && <small>+{result.xp_delta} XP</small>}
  </aside>;
}

export function TrainerScreen({ state, dispatch, onAnswer, onFinish, onHome, onRetry, livesReminder, onRemindLives }: TrainerScreenProps) {
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
    return <section className="screen trainer-screen trainer-complete" aria-labelledby="trainer-complete-title"><span className="status-symbol status-symbol-success" aria-hidden="true">🎉</span><h1 id="trainer-complete-title">Тренировка завершена</h1>{result && <p>{result.correct_count} из {result.question_count} верно · +{result.xp_earned} XP</p>}<p>Результат сохранён на сервере.</p><button className="primary-button" type="button" onClick={onHome}>На главную <span aria-hidden="true">→</span></button></section>;
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
  const canSubmit = isTrainerAnswerComplete(question, state.draftAnswer);
  const isLast = state.currentIndex >= state.session.questions.length;
  const submit = () => {
    dispatch({ type: "submit_answer" });
    if (state.draftAnswer) onAnswer?.(question.id, state.draftAnswer);
  };
  return <section className="screen trainer-screen" aria-labelledby="trainer-title">
    <div className="question-topline"><span aria-label="Прогресс">Тренажёр · {Math.min(questionIndex + 1, state.session.questions.length)} из {state.session.questions.length}</span>{state.session.mode === "normal" && <strong className="trainer-lives" aria-label={`Жизни: ${state.session.lives_remaining}`}>{"♥".repeat(Math.min(5, Math.max(0, state.session.lives_remaining)))}<span className="trainer-lives-empty">{"♥".repeat(Math.max(0, 5 - state.session.lives_remaining))}</span></strong>}{state.session.mode === "mistakes" && <strong>Повтор ошибок</strong>}</div>
    <div className="question-progress-rail" role="progressbar" aria-valuemin={0} aria-valuemax={state.session.questions.length} aria-valuenow={Math.min(questionIndex + 1, state.session.questions.length)}><span className="question-progress-fill" style={{ width: `${(Math.min(questionIndex + 1, state.session.questions.length) / state.session.questions.length) * 100}%` }} /></div>
    <QuestionPrompt question={question} />
    <AnswerEditor question={question} value={state.draftAnswer} disabled={locked} onChange={(answer) => dispatch({ type: "set_answer", answer })} />
    {state.phase === "feedback" ? <><Feedback state={state} />{isLast ? <button className="primary-button question-next" type="button" onClick={() => { dispatch({ type: "finish_requested" }); onFinish?.(); }}>Завершить тренировку <span aria-hidden="true">→</span></button> : <button className="primary-button question-next" type="button" onClick={() => dispatch({ type: "next_question" })}>Следующий вопрос <span aria-hidden="true">→</span></button>}</> : <button className="primary-button question-next" type="button" disabled={!canSubmit || state.phase === "awaiting_result"} onClick={submit}>{state.phase === "awaiting_result" ? "Проверяем…" : "Проверить ответ"}<span aria-hidden="true">→</span></button>}
  </section>;
}

export function trainerAnswerSummary(answer: AnswerValue | undefined): ReactNode {
  if (Array.isArray(answer)) return answer.join(", ");
  if (answer && typeof answer === "object") return Object.values(answer).join(", ");
  return answer ?? "";
}
