import type { ReactNode } from "react";

export type ProgressSaveState = "idle" | "saving" | "saved" | "error";

export type AssessmentHeaderModel = {
  topic: string;
  current: number;
  total: number;
  backDisabled: boolean;
  progressVariant: "dots" | "bar";
  percent: number;
  saveState?: ProgressSaveState;
  announcement?: string | null;
  announcementRole?: "status" | "alert";
  progressMessage?: string;
  skippedIndexes?: readonly number[];
  /** When given, the rail nodes become buttons that jump back to a question. */
  onJumpToQuestion?: (index: number) => void;
  backClassName?: string;
  exitClassName?: string;
  progressClassName?: string;
  saveClassName?: string;
  titleClassName?: string;
  showCount?: boolean;
  backLabel?: string;
  onBack: () => void;
  onExit: () => void;
  onReference?: () => void;
};

function saveStateLabel(state: ProgressSaveState | undefined): string | null {
  if (state === "saving") return "Сохраняем прогресс…";
  if (state === "saved") return "Прогресс сохранён";
  if (state === "error") return "Офлайн: ответ сохранён на устройстве";
  return null;
}

export function AssessmentHeader({ model, children }: { model: AssessmentHeaderModel; children?: ReactNode }) {
  const stateLabel = saveStateLabel(model.saveState);
  const progressLabel = `${model.current} из ${model.total}`;
  return (
    <header className="assessment-header">
      <button
        className={`assessment-header-back back-button${model.backClassName ? ` ${model.backClassName}` : ""}`}
        type="button"
        aria-label={model.backLabel ?? "Назад"}
        disabled={model.backDisabled}
        onClick={model.onBack}
      >←</button>
      <div className="assessment-header-main">
        <div className="assessment-header-title-row">
          <span className={`assessment-header-title${model.titleClassName ? ` ${model.titleClassName}` : ""}`}>{model.topic}</span>
          {model.showCount !== false && <span className="assessment-header-count">{progressLabel}</span>}
        </div>
        <div
          className={`question-progress-rail assessment-progress assessment-progress-${model.progressVariant}${model.progressClassName ? ` ${model.progressClassName}` : ""}`}
          role="progressbar"
          aria-label="Прогресс диагностики"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={model.percent}
          aria-valuetext={model.progressMessage ?? `${model.topic}. ${progressLabel}`}
        >
          {model.progressVariant === "dots"
              ? <span className="assessment-progress-dots" aria-hidden={model.onJumpToQuestion ? undefined : true}>{Array.from({ length: model.total }, (_, index) => {
                const classes = ["question-progress-node"];
                if (index < model.current - 1) classes.push("is-complete");
                if (index === model.current - 1) classes.push("is-current");
                const skipped = model.skippedIndexes?.includes(index);
                if (skipped) classes.push("is-skipped");
                if (!model.onJumpToQuestion) return <i className={classes.join(" ")} key={index} />;
                const visited = index <= model.current - 1;
                return (
                  <button
                    type="button"
                    className={`${classes.join(" ")} question-progress-jump`}
                    key={index}
                    disabled={!visited}
                    aria-current={index === model.current - 1 ? "step" : undefined}
                    aria-label={`Задание ${index + 1}${skipped ? ", пропущено" : ""}`}
                    onClick={() => model.onJumpToQuestion?.(index)}
                  />
                );
              })}</span>
            : <span className="assessment-progress-fill" aria-hidden="true" style={{ width: `${model.percent}%` }} />}
        </div>
        {stateLabel && <span className={`question-save-state${model.saveClassName ? ` ${model.saveClassName}` : ""}`}>{stateLabel}</span>}
        {model.announcement && <span className="assessment-announcement" role={model.announcementRole ?? "status"} aria-live={model.announcementRole === "alert" ? "assertive" : "polite"}>{model.announcement}</span>}
      </div>
      {model.onReference && <button className="assessment-reference-button" type="button" onClick={model.onReference}>К тексту ↑</button>}
      {children}
      <button className={`assessment-header-exit${model.exitClassName ? ` ${model.exitClassName}` : ""}`} type="button" aria-label="Выйти" onClick={model.onExit}>×</button>
    </header>
  );
}
