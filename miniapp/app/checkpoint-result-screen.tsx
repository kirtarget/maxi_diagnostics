import type { CheckpointRecordResponse } from "./types";
import { plural } from "./text-utils";

export type CheckpointResultScreenProps = {
  result: CheckpointRecordResponse;
  onViewPath: () => void;
  onHome: () => void;
};

/** Weekly-checkpoint outcome. Shows the срез tally as a count, never an accuracy percent. */
export function CheckpointResultScreen({ result, onViewPath, onHome }: CheckpointResultScreenProps) {
  const passed = result.passed;
  const total = result.question_total;
  const mastered = result.mastered_count;
  return (
    <section className={`screen checkpoint-result is-${passed ? "passed" : "retry"}`} aria-labelledby="checkpoint-result-title">
      <span className="checkpoint-result-eyebrow" aria-hidden="true">◆ Чекпоинт недели ◆</span>
      <span className="status-symbol" aria-hidden="true">{passed ? "🎉" : "🔁"}</span>
      <h1 id="checkpoint-result-title">{passed ? "Чекпоинт пройден" : "Чекпоинт не пройден"}</h1>
      <p className="checkpoint-result-sub">
        {mastered} из {total} {plural(total, ["задание", "задания", "заданий"])} закрыто
      </p>

      {passed ? (
        <div className="checkpoint-result-note is-up">
          <span className="checkpoint-result-icon" aria-hidden="true">↑</span>
          <span className="checkpoint-result-copy">
            <strong>Блок закреплён</strong>
            <small>Следующие темы пути открылись. Загляни в путь и продолжай.</small>
          </span>
        </div>
      ) : (
        <div className="checkpoint-result-note is-repeat">
          <span className="checkpoint-result-icon" aria-hidden="true">!</span>
          <span className="checkpoint-result-copy">
            <strong>Ещё раз</strong>
            <small>Повтори темы блока в ежедневных сессиях и вернись к чекпоинту.</small>
          </span>
        </div>
      )}

      {passed
        ? <button className="primary-button checkpoint-result-path" onClick={onViewPath} type="button">Смотреть путь <span aria-hidden="true">→</span></button>
        : <button className="primary-button checkpoint-result-path" onClick={onHome} type="button">Вернуться к занятиям <span aria-hidden="true">→</span></button>}
      <button className="secondary-button checkpoint-result-home" onClick={onHome} type="button">На главную</button>
    </section>
  );
}
