import { useState, type ReactNode } from "react";

import { FormattedMathText } from "./math-display";
import { normalizeOffer, OfferSurface, type OfferTelemetryEvent } from "./offer-ux";
import { AnswerPreview } from "./matching-answer";
import { QuestionBody, questionBodyModel } from "./question-body";
import { focusPromptReference } from "./prompt-layout";
import { hasApprovedPrimaryScore, PrimaryScoreBadge } from "./question-metadata";
import { forecastUnitLabel } from "./score-estimate";
import { plural } from "./text-utils";
import type { PersonalRouteAction } from "./result-flow-model";
import type {
  ForecastKind,
  ForecastPoint,
  PublicDiagnostic,
  Question,
  ReviewAnswerPreview,
  ReviewItem,
  DeliveryStatus,
  PublicQuestionOutcome,
  SchoolLinks,
  ServerResult,
} from "./types";

export type RouteItem = PersonalRouteAction;

const CHECKED_FOLD = 8;

function statusWord(status: PublicQuestionOutcome["status"]): string {
  return status === "correct" ? "верно" : status === "skipped" ? "пропущено" : "неверно";
}

function statusSymbol(status: PublicQuestionOutcome["status"]): string {
  return status === "correct" ? "✓" : status === "skipped" ? "−" : "×";
}

/**
 * The condition of a reviewed question, so the review draws it with the shared
 * QuestionBody. Choices are not part of the review payload and the read-only body
 * never reads them.
 */
function reviewQuestion(item: ReviewItem): Question {
  const base = {
    id: item.question_id,
    topic: item.topic,
    title: item.title,
    prompt: item.prompt,
    asset: item.asset,
    assets: item.assets,
    asset_alt: item.asset_alt,
    max_primary_score: item.max_primary_score,
    source: item.source,
  };
  if (item.type === "single") return { ...base, type: "single", options: [] };
  if (item.type === "multiple") return { ...base, type: "multiple", options: [], selection_limit: 0 };
  if (item.type === "matching") return { ...base, type: "matching", items: [], options: [] };
  if (item.type === "text") return { ...base, type: "text" };
  return { ...base, type: "input" };
}

/** A wall of glued sentences is unreadable on a phone, so the explanation is listed. */
function guidancePoints(text: string): string[] {
  return text
    .split(/\n+/u)
    .flatMap((line) => line.split(/(?<=[.!?])\s+(?=[«"(]?[A-ZА-ЯЁ0-9])/u))
    .map((point) => point.trim())
    .filter(Boolean);
}

/** Positions of the blank, as the student writes them: one row of values per answer. */
function blankRows(preview: ReviewAnswerPreview): { markers: string[]; user: string[]; expected: string[] } {
  if (preview.kind !== "multiple") {
    return {
      markers: preview.markers,
      user: preview.markers.map((_, index) => preview.user[index] ?? ""),
      expected: preview.markers.map((_, index) => preview.expected[index] ?? ""),
    };
  }
  // A set answer is written on the blank in ascending order, so it compares in that order.
  const user = [...preview.user].sort();
  const expected = [...preview.expected].sort();
  const length = Math.max(user.length, expected.length);
  return {
    markers: Array.from({ length }, (_, index) => String(index + 1)),
    user: Array.from({ length }, (_, index) => user[index] ?? ""),
    expected: Array.from({ length }, (_, index) => expected[index] ?? ""),
  };
}

export function ResultScreen({
  result,
  diagnostic,
  onReview,
  onForecast,
  onReplayMistakes,
  onHome,
  pdfStatus,
  onRetryDelivery,
  onOpenChat,
}: {
  result: ServerResult;
  diagnostic: Pick<PublicDiagnostic, "exam" | "subject">;
  pdfStatus?: DeliveryStatus | null;
  onReview: (questionId?: string) => void;
  onForecast: () => void;
  onReplayMistakes?: () => void;
  onHome?: () => void;
  onRetryDelivery?: () => void;
  onOpenChat?: () => void;
}): ReactNode {
  const [checkedExpanded, setCheckedExpanded] = useState(false);
  const checked = result.per_question ?? [];
  const shownChecked = checkedExpanded ? checked : checked.slice(0, CHECKED_FOLD);
  const incorrectCount = Math.max(
    0, result.question_count - result.correct_count - (result.skipped_count ?? 0),
  );
  // Skipped questions were never answered, so counting them in the denominator
  // reads as "wrong" next to the breakdown line that says they were skipped.
  const answeredCount = Math.max(0, result.question_count - (result.skipped_count ?? 0));
  const accuracy = answeredCount > 0 ? Math.round(result.correct_count / answeredCount * 100) : 0;
  const disclaimer = /не предсказывает|не прогноз/u.test(result.unassessed_part ?? "")
    ? result.unassessed_part
    : `${result.unassessed_part ? `${result.unassessed_part}. ` : ""}Результат относится только к этим заданиям. Он не предсказывает балл на экзамене и не оценивает весь предмет.`;
  return (
    <section className="screen result-screen" aria-labelledby="result-title">
      <div className="result-hero">
        <p className="result-meta">{diagnostic.exam} · {diagnostic.subject}</p>
        <h1 id="result-title">Результат диагностики</h1>
        {result.question_count > 0 && (
          <div className="result-overview" aria-label="Итог тестовой части">
            {result.mode !== "quick" && answeredCount > 0 && <div className="result-score"><span>Точность ответов</span><strong>{accuracy}%</strong><small>{result.skipped_count > 0 ? `от ${answeredCount} отвеченных, пропуски не считаем` : "в этой диагностике"}</small></div>}
            <div className="result-correct">
              <span>Верные ответы</span>
              <strong>{result.correct_count} из {result.question_count} верно</strong>
            </div>
          </div>
        )}
        {result.skipped_count > 0 && (
          <p className="result-answer-breakdown">
            {result.correct_count} верно · {incorrectCount} неверно · {result.skipped_count} пропущено
          </p>
        )}
        <p className="result-disclaimer">{disclaimer}</p>
      </div>
      <div className="result-body">
      {checked.length > 0 && (
        <section className="result-checked" aria-labelledby="result-checked-title">
          <h2 id="result-checked-title">Проверенные задания</h2>
          <div className="result-checked-list">
            {shownChecked.map((question: PublicQuestionOutcome) => (
              <button
                key={question.question_id}
                type="button"
                className={`result-question-cell result-question-${question.status}`}
                aria-label={`Задание ${question.number}, ${question.topic}, ${statusWord(question.status)}`}
                onClick={() => onReview(question.question_id)}
              >
                <b aria-hidden="true">{statusSymbol(question.status)}</b>
                <strong>{question.number}</strong>
                <span>{question.topic}</span>
              </button>
            ))}
          </div>
          {checked.length > shownChecked.length && (
            <button className="text-back result-checked-more" type="button" onClick={() => setCheckedExpanded(true)}>
              Показаны первые {shownChecked.length} из {checked.length} · Показать все
            </button>
          )}
        </section>
      )}
      <div className="scope-note">
        <strong>Результат сохранён здесь</strong>
        <span>Он останется в разделе «Мои результаты». Telegram присылает только короткое уведомление со ссылкой на этот экран.</span>
      </div>
      <div className="result-actions">
        <button className="primary-button" onClick={() => onReview()} type="button">Посмотреть, где ошибся ({result.per_question?.filter((question) => question.status !== "correct").length ?? incorrectCount} {plural(result.per_question?.filter((question) => question.status !== "correct").length ?? incorrectCount, ["ошибка", "ошибки", "ошибок"])}) <span aria-hidden="true">→</span></button>
        {onReplayMistakes && <button className="secondary-button" onClick={onReplayMistakes} type="button">Прорешать ошибки заново · тренажёр</button>}
        {onHome && <button className="secondary-button" onClick={onHome} type="button">На главную</button>}
        <button className="secondary-button" onClick={onForecast} type="button">План</button>
      </div>
      {pdfStatus && pdfStatus !== "sent" && (
        <div className={`delivery-status delivery-${pdfStatus}`} role={pdfStatus === "failed" ? "alert" : undefined}>
          {pdfStatus === "pending" || pdfStatus === "sending" ? "Отправляем ссылку на результат в Telegram…" : null}
          {pdfStatus === "failed" && <><span>Не удалось отправить результат в Telegram.</span>{onRetryDelivery && <button type="button" onClick={onRetryDelivery}>Повторить</button>}</>}
          {pdfStatus === "abandoned" && "Отправка результата в Telegram прекращена после нескольких попыток."}
        </div>
      )}
      {pdfStatus === "sent" && onOpenChat && <button className="secondary-button" type="button" onClick={onOpenChat}>Открыть чат</button>}
      </div>
    </section>
  );
}

export function ReviewScreen({
  items,
  subject,
  index,
  loading = false,
  error = null,
  legacy = false,
  onRetry,
  onBack,
  onNext,
  onForecast,
  onHome,
  mode = "detail",
  selectedQuestionId,
  onSelectQuestion,
  onList,
}: {
  items: ReviewItem[];
  subject?: string;
  index: number;
  loading?: boolean;
  error?: string | null;
  legacy?: boolean;
  onRetry?: () => void;
  onBack: () => void;
  onNext: () => void;
  onForecast: () => void;
  onHome?: () => void;
  mode?: "list" | "detail";
  selectedQuestionId?: string | null;
  onSelectQuestion?: (questionId: string) => void;
  onList?: () => void;
}): ReactNode {
  const [showAll, setShowAll] = useState(false);
  const mistakes = items.filter((item) => !item.is_correct);
  const visible = showAll ? items : mistakes;
  const selectedIndex = selectedQuestionId
    ? visible.findIndex((candidate) => candidate.question_id === selectedQuestionId)
    : -1;
  const activeIndex = Math.min(
    Math.max(selectedIndex >= 0 ? selectedIndex : index, 0),
    Math.max(visible.length - 1, 0),
  );
  const item = selectedQuestionId
    ? items.find((candidate) => candidate.question_id === selectedQuestionId)
    : visible[activeIndex];

  if (loading) {
    return (
      <section className="screen review-screen centered-state" aria-busy="true" aria-live="polite">
        <span className="state-code">Разбор ошибок</span>
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
        <span className="state-code">Разбор ошибок</span>
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
        <span className="status-symbol" aria-hidden="true">i</span>
        <h1>Для этого результата нет полного разбора</h1>
        <p>Попытка была завершена до обновления. Мы не восстанавливаем правильные ответы из текущего каталога.</p>
        <button className="primary-button" onClick={onForecast} type="button">Мой план подготовки <span aria-hidden="true">→</span></button>
        <button className="secondary-button" onClick={onBack} type="button">Вернуться к результату</button>
      </section>
    );
  }

  if (mode === "list") {
    return (
      <section className="screen review-screen" aria-labelledby="review-list-title">
        <div className="review-topline"><button className="text-back" onClick={onBack} type="button">Назад</button><span>Разбор ошибок</span></div>
        <h1 id="review-list-title">{showAll
          ? `Проверенные задания (${items.length})`
          : `Где ошибся (${mistakes.length} ${plural(mistakes.length, ["ошибка", "ошибки", "ошибок"])})`}</h1>
        <div className="review-filter" role="group" aria-label="Что показывать в разборе">
          <button type="button" className={showAll ? "is-active" : undefined} aria-pressed={showAll} onClick={() => setShowAll(true)}>Все</button>
          <button type="button" className={showAll ? undefined : "is-active"} aria-pressed={!showAll} onClick={() => setShowAll(false)}>Только ошибки</button>
        </div>
        {visible.length === 0 ? <p>Ни одной ошибки. Так держать!</p> : (
          <div className="review-mistake-list-items">
            {visible.map((listed) => (
              <button
                key={listed.question_id}
                type="button"
                className={`review-mistake-${listed.status}`}
                onClick={() => onSelectQuestion?.(listed.question_id)}
                aria-label={`Открыть задание ${listed.number}: ${listed.topic}, ${statusWord(listed.status)}`}
              >
                <b aria-hidden="true">{statusSymbol(listed.status)}</b>
                <strong>{listed.number}</strong>
                <span>{listed.topic}</span>
              </button>
            ))}
          </div>
        )}
        <div className="review-direct-actions"><button className="text-back" type="button" onClick={onForecast}>К плану</button>{onHome && <button className="text-back" type="button" onClick={onHome}>На главную</button>}</div>
      </section>
    );
  }

  if (!item) {
    return (
      <section className="screen review-screen centered-state">
        <span className="status-symbol status-symbol-success" aria-hidden="true">🎉</span>
        <h1>Ни одной ошибки!</h1>
        <p>Ты решил всё верно — разбирать нечего. Так держать!</p>
        <button className="primary-button" onClick={onForecast} type="button">Мой план подготовки <span aria-hidden="true">→</span></button>
        <button className="secondary-button" onClick={onBack} type="button">Вернуться к результату</button>
      </section>
    );
  }

  const position = visible.findIndex((candidate) => candidate.question_id === item.question_id);
  const isLast = position < 0 || position === visible.length - 1;
  const nextItem = position >= 0 ? visible[position + 1] : undefined;
  const question = reviewQuestion(item);
  const body = questionBodyModel(question, false);
  const idPrefix = `review-${item.question_id}`;
  const structuredPreview = item.answer_preview;
  const blank = structuredPreview ? blankRows(structuredPreview) : null;
  const previewLabel = (value: string) => (structuredPreview?.option_labels?.[value] ?? value) || "—";
  const previewRows = structuredPreview?.kind === "multiple"
    ? Array.from(new Set([...structuredPreview.user, ...structuredPreview.expected])).map((marker) => ({ marker, user: structuredPreview.user.includes(marker) ? marker : "", expected: structuredPreview.expected.includes(marker) ? marker : "" }))
    : structuredPreview?.markers.map((marker, markerIndex) => ({ marker, user: structuredPreview.user[markerIndex] ?? "", expected: structuredPreview.expected[markerIndex] ?? "" })) ?? [];
  const points = guidancePoints(item.learning_material_text || item.guidance);

  return (
    <section className="screen review-screen" aria-labelledby={`${idPrefix}-title`}>
      <div className="review-topline">
        <button className="text-back" onClick={onList ?? onBack} type="button">К списку</button>
        <span>{position < 0
          ? "Выбранное задание"
          : `${showAll ? "Все задания" : "Разбор ошибок"} · ${position + 1} из ${visible.length}`}</span>
      </div>
      <QuestionBody
        question={question}
        subject={subject}
        model={body}
        idPrefix={idPrefix}
        illustrationAlt="Иллюстрация к заданию"
        meta={(
          <div className="review-heading">
            <span className="mistake-status">
              <b aria-hidden="true">{statusSymbol(item.status)}</b>
              {item.status === "skipped" ? "Пропущено" : item.status === "correct" ? "Верно" : "Неверно"}
            </span>
            <span className="review-topic">{item.topic}</span>
            {hasApprovedPrimaryScore(item.source) && <PrimaryScoreBadge maxPrimaryScore={item.max_primary_score} earnedPrimaryScore={item.earned_primary_score} />}
          </div>
        )}
      />
      {body.layout.isLongReference && <button className="text-back review-reference-jump" type="button" onClick={() => focusPromptReference(`${idPrefix}-reference`)}>К тексту ↑</button>}
      {blank ? (
        <div className="answer-review answer-review-blank">
          <div className="answer-review-user">
            <AnswerPreview markers={blank.markers} selected={blank.user} label="Твой ответ" compare={blank.expected} />
          </div>
          <div className="answer-review-expected">
            <AnswerPreview markers={blank.markers} selected={blank.expected} label="Правильный" />
          </div>
        </div>
      ) : (
        <dl className="answer-review">
          <div className="answer-review-user">
            <dt>Твой ответ</dt>
            <dd><FormattedMathText text={item.user_answer} subject={subject} /></dd>
          </div>
          <div className="answer-review-expected">
            <dt>Правильный</dt>
            <dd><FormattedMathText text={item.expected_answer} subject={subject} /></dd>
          </div>
        </dl>
      )}
      {structuredPreview && (
        <section className="review-answer-preview" aria-labelledby="review-answer-preview-title">
          <h2 id="review-answer-preview-title">Что стоит за цифрами</h2>
          <table className="review-answer-table">
            <caption className="sr-only">Сравнение ответа</caption>
            <thead><tr><th scope="col">Позиция</th><th scope="col">Твой</th><th scope="col">Верный</th></tr></thead>
            <tbody>{previewRows.map((row, rowIndex) => (
              <tr key={`${row.marker}-${rowIndex}`} className={row.user === row.expected ? undefined : "is-mismatch"}><th scope="row">{row.marker}</th><td><FormattedMathText text={previewLabel(row.user)} subject={subject} /></td><td><FormattedMathText text={previewLabel(row.expected)} subject={subject} /></td></tr>
            ))}</tbody>
          </table>
        </section>
      )}
      <section className="guidance" aria-labelledby="guidance-title">
        <span>Как решать</span>
        <h2 id="guidance-title">Разбери ход решения</h2>
        {points.length > 1
          ? <ul className="guidance-points">{points.map((point, pointIndex) => <li key={pointIndex}><FormattedMathText text={point} subject={subject} /></li>)}</ul>
          : <p><FormattedMathText text={points[0] ?? ""} subject={subject} /></p>}
      </section>
      <button className="primary-button" onClick={isLast ? onForecast : () => { if (showAll && nextItem && onSelectQuestion) onSelectQuestion(nextItem.question_id); else onNext(); }} type="button">
          {isLast ? "Мой план подготовки" : showAll ? "Следующее задание" : "Следующая ошибка"} <span aria-hidden="true">→</span>
      </button>
      <div className="review-direct-actions">
        <button className="text-back" type="button" onClick={onList ?? onBack}>К списку</button>
        <button className="text-back" type="button" onClick={onForecast}>К плану</button>
        {onHome && <button className="text-back" type="button" onClick={onHome}>На главную</button>}
      </div>
    </section>
  );
}

export function ForecastEmptyScreen({ completedCount, onBack, onStart, onPlan, minimumSampleSize = 2 }: {
  completedCount?: number | null;
  onBack: () => void;
  onStart: () => void;
  onPlan?: () => void;
  minimumSampleSize?: number;
}): ReactNode {
  const target = Math.max(1, Math.trunc(minimumSampleSize));
  const hasProgress = typeof completedCount === "number" && Number.isFinite(completedCount);
  const done = hasProgress ? Math.min(Math.max(Math.trunc(completedCount), 0), target) : null;
  return (
    <section className="screen centered-state forecast-empty-screen route-screen" aria-labelledby="forecast-empty-title">
      <button className="text-back" onClick={onBack} type="button">Назад</button>
      <span className="state-icon" aria-hidden="true">📈</span>
      <h1 id="forecast-empty-title">Пока мало данных</h1>
      <p>Пока недостаточно данных для числового ориентира.</p>
      {done !== null && <div className="forecast-empty-progress" aria-label={`Ответов учтено: ${done} из ${target}`}>
        {Array.from({ length: Math.min(target, 10) }, (_, index) => <span key={index} className={`forecast-empty-dot${done > index ? " is-done" : ""}`} aria-hidden="true" />)}
        <small>{done} из {target}</small>
      </div>}
      {onPlan && <button className="primary-button" onClick={onPlan} type="button">Открыть план <span aria-hidden="true">→</span></button>}
      <button className={onPlan ? "secondary-button route-repeat" : "primary-button route-repeat"} onClick={onStart} type="button">Пройти полную диагностику <span aria-hidden="true">→</span></button>
    </section>
  );
}

export function ForecastScreen({
  points,
  kind = "accuracy_percent",
  offers = [],
  offerDismissed = false,
  onOfferDismiss,
  onOfferEvent,
  onBack,
  onRoute,
}: {
  points: ForecastPoint[];
  kind?: ForecastKind;
  offers?: SchoolLinks["offers"];
  offerDismissed?: boolean;
  onOfferDismiss?: () => void;
  onOfferEvent?: (event: OfferTelemetryEvent) => void;
  onBack: () => void;
  onRoute: () => void;
}): ReactNode {
  const current = points.find((point) => point.id === "current");
  const next = points.find((point) => point.id !== "current");
  const ariaLabel = points.length > 0
    ? `Ориентир по результату: ${points.map((point) => `${point.label} — ${point.value}`).join(", ")}`
    : "Ориентир по результату пока без числовых точек";
  const offer = normalizeOffer(offers[0] ?? {});
  return (
    <section className="screen forecast-screen radar-screen" aria-labelledby="forecast-title">
      <button className="text-back" onClick={onBack} type="button">Назад</button>
      <h1 id="forecast-title">Рост — это <em>система</em></h1>
      <p className="lead">Занимайся регулярно, и вот куда можно прийти к экзамену.</p>
      <div className="forecast-path" role="img" aria-label={ariaLabel}>
        {current && (
          <div className="forecast-step forecast-step-current">
            <span className="forecast-step-marker" aria-hidden="true" />
            <div><small>{current.label}</small><strong>{current.value}</strong><span>{forecastUnitLabel(kind, current.value)}</span></div>
          </div>
        )}
        {next && (
          <>
            <div className="forecast-path-line" aria-hidden="true"><span>+{next.value - (current?.value ?? 0)}</span></div>
            <div className="forecast-step forecast-step-goal">
              <span className="forecast-step-marker" aria-hidden="true" />
              <div><small>{next.label}</small><strong>{next.value}</strong><span>{forecastUnitLabel(kind, next.value)}</span></div>
            </div>
          </>
        )}
      </div>
      {next && <p className="forecast-explainer">Это ориентир на основе среднего прироста, а не личная гарантия. Он достижим при системной подготовке.</p>}
      {points.length === 0 && <p className="forecast-empty">Пока нет числового ориентира. План уже собран по твоим темам.</p>}
      {offer && !offerDismissed && (
        <OfferSurface
          offer={offer}
          placement="forecast"
          onClose={() => onOfferDismiss?.()}
          onEvent={onOfferEvent}
        />
      )}
      <button className="primary-button" onClick={onRoute} type="button">Открыть план <span aria-hidden="true">→</span></button>
    </section>
  );
}

export function RouteScreen({
  items,
  offers,
  onSubjects,
  onRepeat,
  onAction,
  reminderMessage,
  onHome,
  xpReward,
}: {
  items: RouteItem[];
  offers: SchoolLinks["offers"];
  onSubjects: () => void;
  onRepeat?: () => void;
  onAction?: (action: PersonalRouteAction) => void;
  reminderMessage?: string | null;
  onHome?: () => void;
  xpReward?: number | null;
}): ReactNode {
  return (
    <section className="screen route-screen" aria-labelledby="route-title">
      <span className="state-code">План подготовки</span>
      <h1 id="route-title">Твой план</h1>
      <p className="lead">Начни с заданий, в которых были ошибки. Этот план относится к пройденной диагностике.</p>
      <ol className="route-list">
        {items.map((item, index) => (
          <li key={`${item.id}-${index}`}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <div><strong>{item.title}</strong><p>{item.description}</p>{onAction && item.kind !== "retest-reminder" && (
              <button className="text-back route-action" type="button" onClick={() => onAction(item)}>
                {item.kind === "review" ? "Открыть разбор" : "Тренировать тему"} <span aria-hidden="true">→</span>
              </button>
            )}{onAction && item.kind === "retest-reminder" && (
              <button className="text-back route-action" type="button" onClick={() => onAction(item)}>Запланировать повтор</button>
            )}</div>
          </li>
        ))}
      </ol>
      {reminderMessage && <p className="inline-success" role="status">{reminderMessage}</p>}
      <div className="scope-note">
        <strong>Где найти этот план</strong>
        <span>План и разбор ошибок открываются здесь в любой момент. Все пройденные диагностики лежат в разделе «Мои результаты».</span>
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
      {onHome && <button className="primary-button plan-home-action" onClick={onHome} type="button">На главную{typeof xpReward === "number" && Number.isFinite(xpReward) ? ` · +${Math.max(0, Math.trunc(xpReward))} XP` : ""}</button>}
      <button className="secondary-button" onClick={onSubjects} type="button">Выбрать другой предмет</button>
      {onRepeat && <button className="text-back route-repeat" onClick={onRepeat} type="button">Пройти диагностику ещё раз <span aria-hidden="true">→</span></button>}
    </section>
  );
}
