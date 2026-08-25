import type { ReactNode } from "react";

import { safeAssetPath } from "./question-assets";
import { shouldShowResultMetrics } from "./result-display";
import { pdfStatusCopy, resultGameSummary, topicRecommendation, type PdfStatusCopy, type PersonalRouteAction } from "./result-flow-model";
import type {
  ForecastPoint,
  PublicDiagnostic,
  ReviewItem,
  ReviewResponse,
  SchoolLinks,
  ServerResult,
  ServerTopic,
} from "./types";

export type RouteItem = PersonalRouteAction;

function topicName(topic: ServerTopic | string): string {
  return typeof topic === "string" ? topic : topic.topic;
}

function resultLevel(result: ServerResult): string {
  if (!result.max_score || !Number.isFinite(result.score)) return "Точка старта сохранена";
  const ratio = result.score / result.max_score;
  if (ratio >= 0.8) return "Сильная стартовая позиция";
  if (ratio >= 0.5) return "Уверенная база";
  return "Есть понятные точки роста";
}

export function ResultScreen({
  result,
  diagnostic,
  pdfStatus,
  onReview,
  onForecast,
  onReplayMistakes,
}: {
  result: ServerResult;
  diagnostic: PublicDiagnostic;
  pdfStatus: ReviewResponse["pdf_status"];
  onReview: () => void;
  onForecast: () => void;
  onReplayMistakes?: () => void;
}): ReactNode {
  const pdf = pdfStatusCopy(pdfStatus);
  const game = resultGameSummary(result);
  const recommendation = topicRecommendation(result.growth_topics);
  return (
    <section className="screen result-screen" aria-labelledby="result-title">
      <span className="state-code">03 / Точка старта</span>
      <div className="result-head">
        <p className="result-meta">{diagnostic.exam} · {diagnostic.subject}</p>
        <h1 id="result-title">Карта знаний готова</h1>
        <p>{resultLevel(result)}. Посмотрите, что уже получается и что даст следующий прирост.</p>
      </div>
      {shouldShowResultMetrics(result) && (
        <div className="result-overview" aria-label="Итог тестовой части">
          <div className="result-score">
            <span>Текущий балл</span>
            <strong>{result.score}</strong>
            <small>из {result.max_score} {result.score_unit}</small>
          </div>
          <div className="result-correct">
            <span>Верные ответы</span>
            <strong>{result.correct_count} из {result.question_count}</strong>
          </div>
        </div>
      )}
      <section className="result-game-card" aria-labelledby="result-game-title">
        <div className="result-game-heading">
          <div>
            <span className="result-game-kicker">MAXIMUM · эта диагностика</span>
            <h2 id="result-game-title">Очки за этот результат</h2>
          </div>
          <strong className="result-game-points">{game.points}</strong>
        </div>
        <div className="result-game-level">
          <div>
            <span>Уровень {game.level}</span>
            <strong>{game.levelTitle}</strong>
          </div>
          <span>{game.pointsToNextLevel > 0 ? `Ещё ${game.pointsToNextLevel} очков до следующего` : "Максимум для этой попытки"}</span>
        </div>
        <div className="result-game-progress" role="progressbar" aria-label={`Прогресс уровня: ${game.levelProgress}%`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={game.levelProgress}>
          <span style={{ width: `${game.levelProgress}%` }} />
        </div>
        <div className="result-achievements" aria-label="Локальные достижения этой диагностики">
          {game.achievements.map((achievement) => (
            <div className={`result-achievement${achievement.earned ? " is-earned" : ""}`} key={achievement.id}>
              <span aria-hidden="true">{achievement.earned ? "✓" : "·"}</span>
              <div><strong>{achievement.title}</strong><small>{achievement.description}</small></div>
            </div>
          ))}
        </div>
      </section>
      {(result.strong_topics.length > 0 || result.growth_topics.length > 0) && (
        <section className="topic-section" aria-labelledby="topic-heading">
          <h2 id="topic-heading">Карта тем</h2>
          <div className="topic-grid">
            {result.strong_topics.length > 0 && (
              <div className="topic-group topic-group-strong">
                <span><b aria-hidden="true">✓</b> Сильные темы</span>
                <ul>{result.strong_topics.map((topic) => <li key={topicName(topic)}>{topicName(topic)}</li>)}</ul>
              </div>
            )}
            {recommendation && (
              <div className="topic-group topic-group-growth">
                <span><b aria-hidden="true">↗</b> {recommendation.heading}</span>
                <ul>{recommendation.topics.map((topic) => <li key={topic}>{topic}</li>)}</ul>
              </div>
            )}
          </div>
        </section>
      )}
      {result.unassessed_part && (
        <div className="scope-note">
          <strong>Что вошло в диагностику</strong>
          <span>{result.unassessed_part}</span>
        </div>
      )}
      <div className={`delivery-note delivery-${pdfStatus}`} role="status" aria-live="polite">
        <strong>{pdf.title}</strong>
        <span>{pdf.description}</span>
      </div>
      <div className="result-actions">
        <button className="primary-button" onClick={onReview} type="button">Разобрать ошибки <span aria-hidden="true">→</span></button>
        {onReplayMistakes && <button className="secondary-button" onClick={onReplayMistakes} type="button">Повторить ошибки</button>}
        <button className="secondary-button" onClick={onForecast} type="button">Прогноз баллов</button>
      </div>
    </section>
  );
}

export function ReviewScreen({
  items,
  index,
  loading = false,
  error = null,
  legacy = false,
  onRetry,
  onBack,
  onNext,
  onForecast,
}: {
  items: ReviewItem[];
  index: number;
  loading?: boolean;
  error?: string | null;
  legacy?: boolean;
  onRetry?: () => void;
  onBack: () => void;
  onNext: () => void;
  onForecast: () => void;
}): ReactNode {
  const mistakes = items.filter((item) => !item.is_correct);
  const activeIndex = Math.min(Math.max(index, 0), Math.max(mistakes.length - 1, 0));
  const item = mistakes[activeIndex];

  if (loading) {
    return (
      <section className="screen review-screen centered-state" aria-busy="true" aria-live="polite">
        <span className="state-code">04 / Разбор</span>
        <h1>Загружаем разбор</h1>
        <p>Берём ответы из сохранённого результата.</p>
        <div className="skeleton skeleton-wide" />
        <div className="skeleton skeleton-card" />
      </section>
    );
  }

  if (error) {
    return (
      <section className="screen review-screen centered-state" role="alert">
        <span className="state-code">04 / Разбор</span>
        <h1>Разбор не загрузился</h1>
        <p>{error}</p>
        {onRetry && <button className="primary-button" onClick={onRetry} type="button">Повторить запрос</button>}
        <button className="secondary-button" onClick={onBack} type="button">Вернуться к результату</button>
      </section>
    );
  }

  if (legacy) {
    return (
      <section className="screen review-screen centered-state">
        <span className="state-code">04 / Разбор</span>
        <span className="status-symbol" aria-hidden="true">i</span>
        <h1>Для этого результата нет полного разбора</h1>
        <p>Попытка была завершена до обновления. Мы не восстанавливаем правильные ответы из текущего каталога.</p>
        <button className="primary-button" onClick={onForecast} type="button">Перейти к прогнозу <span aria-hidden="true">→</span></button>
        <button className="secondary-button" onClick={onBack} type="button">Вернуться к результату</button>
      </section>
    );
  }

  if (!item) {
    return (
      <section className="screen review-screen centered-state">
        <span className="state-code">04 / Разбор</span>
        <span className="status-symbol status-symbol-success" aria-hidden="true">✓</span>
        <h1>В проверенной части нет ошибок</h1>
        <p>Все автоматически проверяемые задания решены верно. Зафиксируем точку старта и посмотрим траекторию.</p>
        <button className="primary-button" onClick={onForecast} type="button">Перейти к прогнозу <span aria-hidden="true">→</span></button>
        <button className="secondary-button" onClick={onBack} type="button">Вернуться к результату</button>
      </section>
    );
  }

  const imagePaths = [item.asset, ...(item.assets ?? [])]
    .flatMap((asset) => asset ? [safeAssetPath(asset)] : [])
    .filter((asset): asset is string => Boolean(asset));
  const isLast = activeIndex === mistakes.length - 1;

  return (
    <section className="screen review-screen" aria-labelledby="review-title">
      <div className="review-topline">
        <button className="text-back" onClick={onBack} type="button">Назад</button>
        <span aria-live="polite">Ошибка {activeIndex + 1} из {mistakes.length}</span>
      </div>
      <span className="state-code">04 / Разбор ошибок</span>
      <div className="review-heading">
        <span className="mistake-status"><b aria-hidden="true">×</b> Неверно</span>
        <span>{item.topic}</span>
      </div>
      <h1 id="review-title">{item.title}</h1>
      <p className="review-prompt">{item.prompt}</p>
      {imagePaths.length > 0 && (
        <div className="review-media">
          {imagePaths.map((path, imageIndex) => (
            // Review paths come from the immutable, authenticated result snapshot.
            // eslint-disable-next-line @next/next/no-img-element
            <img alt={`Иллюстрация к заданию ${imageIndex + 1}`} key={path} src={path} />
          ))}
        </div>
      )}
      <dl className="answer-review">
        <div className="answer-review-user">
          <dt>Ваш ответ</dt>
          <dd>{item.user_answer}</dd>
        </div>
        <div className="answer-review-expected">
          <dt>Правильный ответ</dt>
          <dd>{item.expected_answer}</dd>
        </div>
      </dl>
      <section className="guidance" aria-labelledby="guidance-title">
        <span>Как решать</span>
        <h2 id="guidance-title">Разберите ход решения</h2>
        <p>{item.learning_material_text || item.guidance}</p>
      </section>
      <button className="primary-button" onClick={isLast ? onForecast : onNext} type="button">
        {isLast ? "Перейти к прогнозу" : "Следующая ошибка"} <span aria-hidden="true">→</span>
      </button>
    </section>
  );
}

export function ForecastScreen({ points, onBack, onRoute }: {
  points: ForecastPoint[];
  onBack: () => void;
  onRoute: () => void;
}): ReactNode {
  const current = points.find((point) => point.id === "current");
  const next = points.find((point) => point.id !== "current");
  const ariaLabel = points.length > 0
    ? `Ориентир по результату: ${points.map((point) => `${point.label} — ${point.value}`).join(", ")}`
    : "Ориентир по результату пока без числовых точек";
  return (
    <section className="screen forecast-screen radar-screen" aria-labelledby="forecast-title">
      <button className="text-back" onClick={onBack} type="button">Назад</button>
      <span className="state-code">05 / Ориентир роста</span>
      <h1 id="forecast-title">Рост — это <em>система.</em></h1>
      <p className="lead">Понятный маршрут, регулярная работа и проверка прогресса дают измеримый результат.</p>
      <div className="forecast-path" role="img" aria-label={ariaLabel}>
        {current && (
          <div className="forecast-step forecast-step-current">
            <span className="forecast-step-marker" aria-hidden="true" />
            <div><small>{current.label}</small><strong>{current.value}</strong><span>баллов</span></div>
          </div>
        )}
        {next && (
          <>
            <div className="forecast-path-line" aria-hidden="true"><span>+{next.value - (current?.value ?? 0)}</span></div>
            <div className="forecast-step forecast-step-goal">
              <span className="forecast-step-marker" aria-hidden="true" />
              <div><small>{next.label}</small><strong>{next.value}</strong><span>баллов</span></div>
            </div>
          </>
        )}
      </div>
      {next && <p className="forecast-explainer">Это ориентир на основе среднего прироста, а не личная гарантия. Он достижим при системной подготовке по вашему маршруту.</p>}
      {points.length === 0 && <p className="forecast-empty">Пока нет числового ориентира. Откройте маршрут: он уже собран по вашим темам.</p>}
      <button className="primary-button" onClick={onRoute} type="button">Открыть маршрут <span aria-hidden="true">→</span></button>
    </section>
  );
}

export function RouteScreen({
  items,
  pdf,
  offers,
  onRefreshPdf,
  onSubjects,
}: {
  items: RouteItem[];
  pdf: PdfStatusCopy;
  offers: SchoolLinks["offers"];
  onRefreshPdf: () => void;
  onSubjects: () => void;
}): ReactNode {
  return (
    <section className="screen route-screen" aria-labelledby="route-title">
      <span className="state-code">06 / Следующий шаг</span>
      <h1 id="route-title">Персональный маршрут</h1>
      <p className="lead">Сначала учебные действия, затем подходящий формат поддержки школы.</p>
      <ol className="route-list">
        {items.map((item, index) => (
          <li key={`${item.id}-${index}`}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <div><strong>{item.title}</strong><p>{item.description}</p></div>
          </li>
        ))}
      </ol>
      <div className="delivery-note" role="status" aria-live="polite">
        <strong>{pdf.title}</strong>
        <span>{pdf.description}</span>
        {pdf.action && <button className="inline-action" onClick={onRefreshPdf} type="button">{pdf.action}</button>}
      </div>
      {offers.length > 0 && (
        <section className="school-actions" aria-labelledby="school-actions-title">
          <span>Поддержка школы</span>
          <h2 id="school-actions-title">Продолжить подготовку</h2>
          <div>
            {offers.map((offer) => (
              <a href={offer.url} key={offer.id} target="_blank" rel="noreferrer">
                <span><strong>{offer.label}</strong><small>{offer.button}</small></span>
                <b aria-hidden="true">→</b>
              </a>
            ))}
          </div>
        </section>
      )}
      <button className="secondary-button" onClick={onSubjects} type="button">Выбрать другой предмет</button>
    </section>
  );
}
