import type { ServerAttempt } from "./types";
import { formatCompletedDate, resultFact } from "./navigation-model";

export type ResultsScreenProps = {
  results: ServerAttempt[];
  onOpenResult: (attempt: ServerAttempt) => void;
  onStartDiagnostic: () => void;
};

export function ResultsScreen({ results, onOpenResult, onStartDiagnostic }: ResultsScreenProps) {
  const completed = results.filter((attempt) => attempt.result);
  return (
    <section className="screen results-screen" aria-labelledby="results-title">
      <span className="today-eyebrow">Результаты</span>
      <h1 id="results-title">Твои диагностики</h1>
      <p className="results-lead">Здесь точность по каждой диагностике — для тебя, родителя и школы. Дневные сессии остаются в пути по темам.</p>
      {completed.length === 0 ? (
        <div className="results-empty">
          <span className="state-icon" aria-hidden="true">📋</span>
          <p>Пока нет завершённых диагностик. Пройди диагностику, чтобы увидеть точность и разбор.</p>
          <button className="primary-button" onClick={onStartDiagnostic} type="button">Пройти диагностику <span aria-hidden="true">→</span></button>
        </div>
      ) : (
        <div className="results-list">
          {completed.map((attempt) => (
            <button className="results-card" key={attempt.attempt_id} onClick={() => onOpenResult(attempt)} type="button">
              <span className="results-card-main">
                <strong>{attempt.subject ?? "Диагностика"}</strong>
                <small>{formatCompletedDate(attempt.completed_at)}</small>
              </span>
              <span className="results-card-fact">
                <strong>{resultFact(attempt)}</strong>
                <small>{attempt.exam ?? ""}</small>
              </span>
              <span className="results-card-arrow" aria-hidden="true">→</span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
