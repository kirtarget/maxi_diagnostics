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
  isValidNumericInput,
  markResultViewed,
  restoreBootstrapSession,
  saveLocalSession,
updateMatchingAnswer,
updateNumericInputAnswer,
saveProgress,
} from "./api";
import type { ProgressPayload, ProgressSaveQueue } from "./api";
import { initializeTelegram } from "./telegram-webapp";
import type {
  AnswerMap,
  AnswerValue,
  Brand,
  BootstrapResponse,
  DiagnosticMode,
  MatchingQuestion,
  MultipleQuestion,
  PublicDiagnostic,
  Question,
  ServerResult,
} from "./types";

type Screen = "loading" | "welcome" | "mode" | "subjects" | "question" | "submitting" | "result";

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

function isAnswered(question: Question, answer: AnswerValue | undefined): boolean {
  if (question.type === "single") {
    return typeof answer === "string" && answer.trim().length > 0;
  }
  if (question.type === "input") return isValidNumericInput(answer);
  if (question.type === "multiple") {
    return Array.isArray(answer) && answer.length === question.selection_limit;
  }
  return Boolean(
    answer &&
    typeof answer === "object" &&
    !Array.isArray(answer) &&
    question.items.every((item) => Boolean(answer[item.id])),
  );
}

function safeAssetPath(asset: string): string | undefined {
  if (!/^[A-Za-z0-9_./-]+$/.test(asset) || asset.includes("..")) return undefined;
  return `/${asset.replace(/^\/+/, "")}`;
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

function QuestionView({
  question,
  index,
  total,
  answer,
  onAnswer,
  onBack,
  onNext,
  labels,
}: {
  question: Question;
  index: number;
  total: number;
  answer: AnswerValue | undefined;
  onAnswer: (value: AnswerValue) => void;
  onBack: () => void;
  onNext: () => void;
  labels: Brand["interface"];
}) {
  const progress = Math.round(((index + 1) / total) * 100);
  const imagePath = question.asset ? safeAssetPath(question.asset) : undefined;

  return (
    <section className="screen question-screen" aria-labelledby="question-title">
      <div className="question-topline">
        <button className="back-button" onClick={onBack} type="button" aria-label={labels.back}>{labels.back}</button>
        <div className="question-progress-copy">
          <span>{labels.task_label} {index + 1} {labels.of_label} {total}</span>
          <strong>{progress}%</strong>
        </div>
      </div>
      <div className="progress-track" aria-hidden="true"><span style={{ width: `${progress}%` }} /></div>
      <div className="question-meta"><span>{question.title}</span><span>{question.topic}</span></div>
      <h1 id="question-title" className="question-title">{question.prompt}</h1>
      {imagePath && (
        <div className="question-media">
          {/* School assets are mounted by the deployment image, never copied from a source school. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={imagePath} alt={labels.illustration_alt} />
        </div>
      )}

      {question.type === "single" && (
        <div className="answer-list" role="radiogroup" aria-label="Выберите один вариант">
          {question.options.map((option, optionIndex) => {
            const selected = answer === option.id;
            return (
              <button
                type="button"
                role="radio"
                aria-checked={selected}
                className={`answer-option${selected ? " selected" : ""}`}
                key={option.id}
                onClick={() => onAnswer(option.id)}
              >
                <span className="option-letter">{String.fromCharCode(65 + optionIndex)}</span>
                <span>{option.label}</span>
                <span className="selection-mark" aria-hidden="true" />
              </button>
            );
          })}
        </div>
      )}

      {question.type === "multiple" && (
        <MultipleAnswers
          question={question}
          value={Array.isArray(answer) ? answer : []}
          onChange={onAnswer}
        />
      )}

      {question.type === "matching" && (
        <MatchingAnswers
          question={question}
          value={answer && typeof answer === "object" && !Array.isArray(answer) ? answer : {}}
          onChange={onAnswer}
          chooseLabel={labels.choose_option}
        />
      )}

      {question.type === "input" && (
        <label className="short-answer">
          <span>{labels.answer_label}</span>
          <input
            autoComplete="off"
            inputMode="decimal"
            maxLength={64}
            value={typeof answer === "string" ? answer : ""}
            onChange={(event) => onAnswer(event.target.value)}
            placeholder={labels.enter_answer}
          />
        </label>
      )}

      <button className="primary-button question-next" disabled={!isAnswered(question, answer)} onClick={onNext} type="button">
        {index === total - 1 ? labels.get_result : labels.next_question}
        <span aria-hidden="true">→</span>
      </button>
    </section>
  );
}

function MultipleAnswers({
  question,
  value,
  onChange,
}: {
  question: MultipleQuestion;
  value: string[];
  onChange: (value: string[]) => void;
}) {
  const toggle = (id: string) => {
    if (value.includes(id)) onChange(value.filter((item) => item !== id));
    else if (value.length < question.selection_limit) onChange([...value, id]);
  };

  return (
    <div className="answer-list" role="group" aria-label={`Выберите ${question.selection_limit} варианта`}>
      {question.options.map((option, index) => {
        const selected = value.includes(option.id);
        return (
          <button
            type="button"
            aria-pressed={selected}
            className={`answer-option${selected ? " selected" : ""}`}
            key={option.id}
            onClick={() => toggle(option.id)}
          >
            <span className="option-letter">{String.fromCharCode(65 + index)}</span>
            <span>{option.label}</span>
            <span className="selection-mark square" aria-hidden="true" />
          </button>
        );
      })}
    </div>
  );
}

function MatchingAnswers({
  question,
  value,
  onChange,
  chooseLabel,
}: {
  question: MatchingQuestion;
  value: Record<string, string>;
  onChange: (value: Record<string, string>) => void;
  chooseLabel: string;
}) {
  return (
    <div className="matching-list">
      {question.items.map((item, index) => (
        <label className="matching-row" key={item.id}>
          <span className="matching-index">{index + 1}</span>
          <span>{item.label}</span>
          <select
            aria-label={`Соответствие для ${item.label}`}
            value={value[item.id] ?? ""}
            onChange={(event) => onChange(updateMatchingAnswer(value, item.id, event.target.value))}
          >
            <option value="">{chooseLabel}</option>
            {question.options.map((option) => <option value={option.id} key={option.id}>{option.label}</option>)}
          </select>
        </label>
      ))}
    </div>
  );
}

function topicName(topic: string | { topic: string }): string {
  return typeof topic === "string" ? topic : topic.topic;
}

export default function Home() {
  const [screen, setScreen] = useState<Screen>("loading");
  const [bootstrap, setBootstrap] = useState<BootstrapResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [syncWarning, setSyncWarning] = useState<string | null>(null);
  const [mode, setMode] = useState<DiagnosticMode>("quick");
  const [diagnosticId, setDiagnosticId] = useState<string | null>(null);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [answers, setAnswers] = useState<AnswerMap>({});
  const [inputDrafts, setInputDrafts] = useState<Record<string, string>>({});
  const [attemptId, setAttemptId] = useState(createAttemptId);
  const [result, setResult] = useState<ServerResult | null>(null);
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
        setScreen("question");
      } else {
        persistedAttemptId.current = data.attempt?.attempt_id ?? null;
        supersedesAttemptId.current = undefined;
        setScreen("welcome");
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
  const style = brand ? {
    "--brand-primary": brand.colors.primary,
    "--brand-accent": brand.colors.accent,
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
        onHome={() => setScreen("welcome")}
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
        <section className="screen welcome-screen">
          <span className="state-code">Персональная карта знаний</span>
          <div className="poster-motif" aria-hidden="true"><span>01</span><span>{bootstrap.diagnostics.length.toString().padStart(2, "0")}</span></div>
          <h1>Узнайте свою точку старта</h1>
          <p className="hero-copy">Ответьте на задания, получите оценку сильных тем и точек роста. Прогресс сохраняется после каждого ответа.</p>
          <div className="welcome-facts">
            <div><strong>{Math.min(...bootstrap.diagnostics.map((item) => item.quick_count))}</strong><span>от заданий</span></div>
            <div><strong>{bootstrap.diagnostics.length}</strong><span>предметов</span></div>
            <div><strong>2</strong><span>формата</span></div>
          </div>
          <button className="primary-button" onClick={() => setScreen("mode")} type="button">{brand?.interface.start_diagnostic} <span aria-hidden="true">→</span></button>
          <div className="utility-links">
            <a href={bootstrap.school.links.privacy} target="_blank" rel="noreferrer">{brand?.interface.privacy_label}</a>
            <a href={bootstrap.school.links.support} target="_blank" rel="noreferrer">{brand?.interface.support_label}</a>
          </div>
        </section>
      )}

      {screen === "mode" && bootstrap && (
        <section className="screen" aria-labelledby="mode-title">
          <button className="text-back" onClick={() => setScreen("welcome")} type="button">{brand?.interface.back}</button>
          <span className="state-code">01 / Формат</span>
          <h1 id="mode-title">Насколько подробно?</h1>
          <p className="lead">Выберите короткую оценку уровня или полный набор заданий.</p>
          <div className="mode-list">
            {(["quick", "full"] as const).map((item) => (
              <button
                className={`mode-card ${item === "full" ? "featured" : ""}`}
                key={item}
                onClick={() => { setMode(item); setScreen("subjects"); }}
                type="button"
              >
                <span className="mode-badge">{item === "quick" ? "Короткий формат" : "Подробный формат"}</span>
                <strong>{item === "quick" ? brand?.interface.quick_result : brand?.interface.full_result}</strong>
                <span>{item === "quick" ? "Основные темы и ориентир уровня" : "Все доступные задания и полный результат"}</span>
                <em>{brand?.interface.choose_label} →</em>
              </button>
            ))}
          </div>
        </section>
      )}

      {screen === "subjects" && bootstrap && (
        <section className="screen" aria-labelledby="subject-title">
          <button className="text-back" onClick={() => setScreen("mode")} type="button">{brand?.interface.back}</button>
          <span className="state-code">02 / Предмет</span>
          <h1 id="subject-title">Что будем проверять?</h1>
          <p className="lead">Все предметы и задания загружены из каталога вашей школы.</p>
          <div className="subject-list">
            {bootstrap.diagnostics.map((item) => {
              const count = questionsFor(item, mode).length;
              return (
                <button className="subject-card" key={item.id} onClick={() => beginDiagnostic(item)} type="button">
                  <span className="subject-mark">{item.mark}</span>
                  <span><strong>{item.subject}</strong><small>{item.exam} · {count} заданий</small></span>
                  <em>{brand?.interface.start_diagnostic}</em>
                </button>
              );
            })}
          </div>
        </section>
      )}

      {screen === "question" && diagnostic && questions[questionIndex] && (
        <>
          {syncWarning && <p className="inline-warning" role="status">{syncWarning}</p>}
          {error && <p className="inline-error" role="alert">{error}</p>}
          <QuestionView
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
        <section className="screen result-screen" aria-labelledby="result-title">
          <span className="state-code">03 / Результат</span>
          <div className="result-head">
            <h1 id="result-title">{brand?.interface.results_heading}</h1>
            <div className="score-block"><strong>{result.score}</strong><span>{brand?.interface.of_label} {result.max_score}</span></div>
          </div>
          <p className="result-summary">{brand?.interface.result_correct}: <strong>{result.correct_count} {brand?.interface.of_label} {result.question_count}</strong>.</p>
          {result.unassessed_part && <p className="scope-note">Не оценивалась часть: {result.unassessed_part}</p>}
          <div className="topic-grid">
            <div><span>{brand?.interface.keep_strong}</span>{result.strong_topics.map((topic) => <strong key={topicName(topic)}>{topicName(topic)}</strong>)}</div>
            <div><span>{brand?.interface.focus_next}</span>{result.growth_topics.map((topic) => <strong key={topicName(topic)}>{topicName(topic)}</strong>)}</div>
          </div>
          {"points" in (result.forecast ?? {}) && Array.isArray(result.forecast?.points) && result.forecast.points.length > 0 && (
            <div className="forecast-list" aria-label="Прогноз результата">
              {result.forecast.points.map((point) => <div key={point.id}><span>{point.label}</span><strong>{point.value}</strong></div>)}
            </div>
          )}
          <p className="delivery-note">{brand?.interface.delivery_note}</p>
          {bootstrap.school.links.offers.map((offer) => (
            <a className="primary-button" href={offer.url} target="_blank" rel="noreferrer" key={offer.id}>{offer.button}<span aria-hidden="true">→</span></a>
          ))}
          <button className="secondary-button" type="button" onClick={() => setScreen("subjects")}>{brand?.interface.check_another_subject}</button>
          <button className="text-action" type="button" onClick={() => window.Telegram?.WebApp.close()}>{brand?.interface.close_diagnostic}</button>
        </section>
      )}
    </main>
  );
}
