"use client";

import type { Dispatch, ReactNode } from "react";
import type { AnswerValue, InputQuestion, MatchingQuestion, MultipleQuestion, Question } from "./types";
import {
  isTrainerAnswerComplete,
  type TrainerAction,
  type TrainerState,
} from "./trainer-model";

export type TrainerScreenProps = {
  state: TrainerState;
  dispatch: Dispatch<TrainerAction>;
  onAnswer?: (questionId: string, answer: AnswerValue) => void;
  onFinish?: () => void;
  onHome?: () => void;
  onRetry?: () => void;
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

export function TrainerScreen({ state, dispatch, onAnswer, onFinish, onHome, onRetry }: TrainerScreenProps) {
  if (state.phase === "idle") return <section className="screen trainer-screen"><p>Тренажёр готовится.</p></section>;
  if (state.phase === "error") return <section className="screen trainer-screen" role="alert"><h1>Не удалось продолжить</h1><p>{state.error}</p><button className="primary-button" type="button" onClick={() => { dispatch({ type: "retry" }); onRetry?.(); }}>Повторить</button></section>;
  if (state.phase === "completed") {
    const result = state.finishResult;
    return <section className="screen trainer-screen trainer-complete" aria-labelledby="trainer-complete-title"><span className="state-code">Готово</span><h1 id="trainer-complete-title">Тренировка завершена</h1>{result && <p>{result.correct_count} из {result.question_count} верно · +{result.xp_earned} XP</p>}<p>Результат сохранён на сервере.</p><button className="primary-button" type="button" onClick={onHome}>На главную <span aria-hidden="true">→</span></button></section>;
  }
  const questionIndex = state.phase === "feedback" && state.answeredQuestionIndex !== null
    ? state.answeredQuestionIndex
    : state.currentIndex;
  const question = state.session?.questions[questionIndex];
  if (!question || !state.session) return null;
  const locked = state.phase !== "answering";
  const livesZero = state.session.lives_remaining <= 0;
  const canSubmit = isTrainerAnswerComplete(question, state.draftAnswer) && !livesZero;
  const isLast = state.currentIndex >= state.session.questions.length;
  const submit = () => {
    dispatch({ type: "submit_answer" });
    if (state.draftAnswer) onAnswer?.(question.id, state.draftAnswer);
  };
  return <section className="screen trainer-screen" aria-labelledby="trainer-title">
    <div className="question-topline"><span aria-label="Прогресс">{Math.min(questionIndex + 1, state.session.questions.length)} / {state.session.questions.length}</span><strong>⚡ {state.session.lives_remaining}</strong></div>
    <div className="question-progress-rail" role="progressbar" aria-valuemin={0} aria-valuemax={state.session.questions.length} aria-valuenow={Math.min(questionIndex + 1, state.session.questions.length)}><span className="question-progress-fill" style={{ width: `${(Math.min(questionIndex + 1, state.session.questions.length) / state.session.questions.length) * 100}%` }} /></div>
    <QuestionPrompt question={question} />
    <AnswerEditor question={question} value={state.draftAnswer} disabled={locked || livesZero} onChange={(answer) => dispatch({ type: "set_answer", answer })} />
    {livesZero && state.phase === "answering" && <p role="status">Жизни закончились. Вернись позже.</p>}
    {state.phase === "feedback" ? <><Feedback state={state} />{isLast ? <button className="primary-button question-next" type="button" onClick={() => { dispatch({ type: "finish_requested" }); onFinish?.(); }}>Завершить тренировку <span aria-hidden="true">→</span></button> : <button className="primary-button question-next" type="button" onClick={() => dispatch({ type: "next_question" })}>Следующий вопрос <span aria-hidden="true">→</span></button>}</> : <button className="primary-button question-next" type="button" disabled={!canSubmit || state.phase === "awaiting_result" || state.phase === "finishing"} onClick={submit}>{state.phase === "awaiting_result" ? "Проверяем…" : "Проверить ответ"}<span aria-hidden="true">→</span></button>}
  </section>;
}

export function trainerAnswerSummary(answer: AnswerValue | undefined): ReactNode {
  if (Array.isArray(answer)) return answer.join(", ");
  if (answer && typeof answer === "object") return Object.values(answer).join(", ");
  return answer ?? "";
}
