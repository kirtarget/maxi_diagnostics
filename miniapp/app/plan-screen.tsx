"use client";

import type { PlanScreenState } from "./plan-model";
import type { DailyPlanDetail, DailyPlanTask, PlanReason } from "./types";

const REASON_LABEL: Record<PlanReason, string> = {
  mistake_review: "Повтор ошибки",
  growth_topic: "Слабая тема",
};

function taskCountWord(count: number): string {
  const tail = count % 100;
  if (tail >= 11 && tail <= 14) return "заданий";
  const last = count % 10;
  if (last === 1) return "задание";
  if (last >= 2 && last <= 4) return "задания";
  return "заданий";
}

function PlanTaskRow({ task, index, current }: { task: DailyPlanTask; index: number; current: boolean }) {
  return (
    <li className={`plan-task${task.completed ? " plan-task-done" : ""}${current ? " plan-task-current" : ""}`}>
      <span className="plan-task-marker" aria-hidden="true">{task.completed ? "✓" : index + 1}</span>
      <span className="plan-task-body">
        <strong>{task.topic || "Задание"}</strong>
        <small>{REASON_LABEL[task.reason]}</small>
      </span>
      {current && <span className="plan-task-next">Следующее</span>}
    </li>
  );
}

function PlanReady({ data, onStart, onBack }: { data: DailyPlanDetail; onStart?: () => void; onBack?: () => void }) {
  const remaining = Math.max(data.total - data.completed, 0);
  const nextIndex = data.questions.findIndex((task) => !task.completed);
  const percent = data.total > 0 ? Math.round((data.completed / data.total) * 100) : 0;

  if (data.status === "no_diagnostic" || data.questions.length === 0) {
    return (
      <section className="screen plan-screen" aria-labelledby="plan-title">
        {onBack && <button className="text-back" onClick={onBack} type="button">На главную</button>}
        <h1 id="plan-title">План на сегодня</h1>
        <p className="plan-empty">
          План собирается по результатам диагностики. Пройди её, и завтра здесь появятся задания
          по твоим слабым темам.
        </p>
      </section>
    );
  }

  return (
    <section className="screen plan-screen" aria-labelledby="plan-title">
      {onBack && <button className="text-back" onClick={onBack} type="button">На главную</button>}
      <h1 id="plan-title">План на сегодня</h1>
      <p className="plan-subject">{[data.subject, data.exam].filter(Boolean).join(" · ") || "Диагностика"}</p>

      <div className="plan-progress-card">
        <div className="plan-progress-row">
          <strong>{data.completed} из {data.total}</strong>
          <span>{remaining > 0 ? `осталось ${remaining} ${taskCountWord(remaining)}` : "всё выполнено"}</span>
        </div>
        <div
          className="gameplay-progress"
          role="progressbar"
          aria-label="Прогресс плана"
          aria-valuenow={percent}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <span style={{ width: `${percent}%` }} />
        </div>
      </div>

      <ol className="plan-tasks">
        {data.questions.map((task, index) => (
          <PlanTaskRow key={task.question_id} task={task} index={index} current={index === nextIndex} />
        ))}
      </ol>

      {data.status === "done" ? (
        <p className="gameplay-plan-done" role="status"><span aria-hidden="true">✓</span> План на сегодня выполнен</p>
      ) : (
        onStart && (
          <button className="primary-button" onClick={onStart} type="button">
            {data.completed > 0 ? "Продолжить план" : "Начать план"} <span aria-hidden="true">→</span>
          </button>
        )
      )}
      <p className="plan-note">Задания идут по порядку: сначала повтор ошибок, затем слабые темы.</p>
    </section>
  );
}

export function PlanScreen({
  state,
  onStart,
  onRetry,
  onBack,
}: {
  state: PlanScreenState;
  onStart?: () => void;
  onRetry?: () => void;
  onBack?: () => void;
}) {
  if (state.kind === "loading") {
    return <section className="screen plan-screen" aria-busy="true"><p>Загружаем план…</p></section>;
  }
  if (state.kind === "error") {
    return (
      <section className="screen plan-screen" role="alert">
        <p>{state.message}</p>
        {onRetry && <button className="primary-button" onClick={onRetry} type="button">Повторить</button>}
        {onBack && <button className="text-back" onClick={onBack} type="button">На главную</button>}
      </section>
    );
  }
  return <PlanReady data={state.data} onStart={onStart} onBack={onBack} />;
}
