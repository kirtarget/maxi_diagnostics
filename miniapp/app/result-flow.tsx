import { useEffect, useRef, useState, type ReactNode } from "react";

import { FormattedMathText, FormattedStem } from "./math-display";
import { normalizeOffer, OfferSurface, type OfferTelemetryEvent } from "./offer-ux";
import { PromptTable } from "./prompt-table";
import { parseQuestionPrompt } from "./question-prompt";
import { createPromptAnchorAllocator, focusPromptReference, promptLayout } from "./prompt-layout";
import { hasApprovedPrimaryScore, PrimaryScoreBadge } from "./question-metadata";
import { ImageViewer } from "./image-viewer";
import { forecastUnitLabel } from "./score-estimate";
import { topicRecommendation, type PersonalRouteAction } from "./result-flow-model";
import type {
  ForecastKind,
  ForecastPoint,
  PublicDiagnostic,
  ReviewItem,
  DeliveryStatus,
  PublicQuestionOutcome,
  SchoolLinks,
  ServerResult,
  ServerTopic,
} from "./types";

export type RouteItem = PersonalRouteAction;

function ReviewPrompt({ prompt, subject, questionId }: { prompt: string; subject?: string; questionId: string }) {
  const blocks = parseQuestionPrompt(prompt);
  const layout = promptLayout(blocks);
  const anchors = createPromptAnchorAllocator();
  const [expanded, setExpanded] = useState(false);
  useEffect(() => { setExpanded(false); }, [questionId]);
  const referenceId = `review-reference-${questionId}`;
  return (
    <div className="review-prompt-shell">
      {layout.stem && <p className="review-prompt-stem"><FormattedStem text={layout.stem} subject={subject} /></p>}
      {layout.isLongReference && <button className="prompt-reference-toggle" type="button" aria-controls={referenceId} aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>{expanded ? "Свернуть текст" : "Развернуть текст"}</button>}
      <div id={referenceId} tabIndex={-1} className={`prompt-reference${layout.isLongReference ? " prompt-reference-long" : ""}${expanded ? " is-expanded" : ""}`}>
        {layout.referenceBlocks.map((block, index) => {
          const id = `${referenceId}-${anchors.blockId(block) ?? `block-${index}`}`;
          if (block.kind === "heading") return <h2 id={id} className="question-section-title" key={index}>{block.text}</h2>;
          if (block.kind === "item") return <div id={id} className="question-list-item" key={index}><span>{block.marker}</span><p><FormattedMathText text={block.text} subject={subject} /></p></div>;
          if (block.kind === "table") return <div id={id} key={index}><PromptTable headerRows={block.headerRows} rows={block.rows} columns={block.columns} subject={subject} /></div>;
          return <p className="review-prompt" key={index}>{anchors.sentenceSegments(block.text).map((segment, segmentIndex) => <span id={segment.anchorId ? `${referenceId}-${segment.anchorId}` : undefined} key={segmentIndex}><FormattedMathText text={segment.text} subject={subject} /></span>)}</p>;
        })}
      </div>
      {layout.isLongReference && <button className="text-back review-reference-jump" type="button" onClick={() => focusPromptReference(referenceId)}>К тексту ↑</button>}
    </div>
  );
}

function topicName(topic: ServerTopic | string): string {
  return typeof topic === "string" ? topic : topic.topic;
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
  const recommendation = topicRecommendation(result.growth_topics);
  const incorrectCount = Math.max(
    0, result.question_count - result.correct_count - (result.skipped_count ?? 0),
  );
  const accuracy = result.question_count > 0 ? Math.round(result.correct_count / result.question_count * 100) : 0;
  const disclaimer = result.unassessed_part?.includes("не предсказывает")
    ? result.unassessed_part
    : `${result.unassessed_part ? `${result.unassessed_part}. ` : ""}Результат относится только к этим заданиям. Он не предсказывает балл на экзамене и не оценивает весь предмет.`;
  return (
    <section className="screen result-screen" aria-labelledby="result-title">
      <div className="result-hero">
        <p className="result-meta">{diagnostic.exam} · {diagnostic.subject}</p>
        <h1 id="result-title">Результат диагностики</h1>
        {result.question_count > 0 && (
          <div className="result-overview" aria-label="Итог тестовой части">
            {result.mode !== "quick" && <div className="result-score"><span>Точность ответов</span><strong>{accuracy}%</strong><small>в этой диагностике</small></div>}
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
      {result.per_question && result.per_question.length > 0 && (
        <section className="result-question-grid" aria-labelledby="result-question-grid-title">
          <h2 id="result-question-grid-title">Все задания</h2>
          <div className="result-question-grid-list">
            {result.per_question.map((question: PublicQuestionOutcome) => (
              <button
                key={question.question_id}
                type="button"
                className={`result-question-cell result-question-${question.status}`}
                aria-label={`Задание ${question.number}, ${question.topic}, ${question.status === "correct" ? "верно" : question.status === "skipped" ? "пропущено" : "ошибка"}`}
                onClick={() => onReview(question.question_id)}
              >
                {question.number}
              </button>
            ))}
          </div>
        </section>
      )}
      {(result.strong_topics.length > 0 || result.growth_topics.length > 0) && (
        <section className="topic-section" aria-labelledby="topic-heading">
          <h2 id="topic-heading">Проверенные задания</h2>
          <div className="topic-grid">
            {result.strong_topics.length > 0 && (
              <div className="topic-group topic-group-strong">
                <span><b aria-hidden="true">✓</b> Получилось в этой попытке</span>
                <ul>{result.strong_topics.map((topic) => <li key={topicName(topic)}>{topicName(topic)}</li>)}</ul>
              </div>
            )}
            {recommendation && (
              <div className="topic-group topic-group-growth">
                <span><b aria-hidden="true">↗</b> Задания для повторения</span>
                <ul>{recommendation.topics.map((topic) => <li key={topic}>{topic}</li>)}</ul>
              </div>
            )}
          </div>
        </section>
      )}
      <div className="scope-note">
        <strong>Результат сохранён здесь</strong>
        <span>Он останется в разделе «Мои результаты». Telegram присылает только короткое уведомление со ссылкой на этот экран.</span>
      </div>
      <div className="result-actions">
        <button className="primary-button" onClick={() => onReview()} type="button">Посмотреть, где ошибся ({result.per_question?.filter((question) => question.status !== "correct").length ?? incorrectCount}) <span aria-hidden="true">→</span></button>
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
  const mistakes = items.filter((item) => !item.is_correct);
  const selectedIndex = selectedQuestionId
    ? mistakes.findIndex((candidate) => candidate.question_id === selectedQuestionId)
    : -1;
  const activeIndex = Math.min(
    Math.max(selectedIndex >= 0 ? selectedIndex : index, 0),
    Math.max(mistakes.length - 1, 0),
  );
  const item = selectedQuestionId
    ? items.find((candidate) => candidate.question_id === selectedQuestionId)
    : mistakes[activeIndex];
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (item) {
      headingRef.current?.focus();
      headingRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    }
  }, [item?.question_id]);

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
        <h1 id="review-list-title">Где ошибся ({mistakes.length})</h1>
        {mistakes.length === 0 ? <p>Ни одной ошибки. Так держать!</p> : (
          <div className="review-mistake-list-items">
            {mistakes.map((mistake) => <button key={mistake.question_id} type="button" onClick={() => onSelectQuestion?.(mistake.question_id)} aria-label={`Открыть задание ${mistake.number}: ${mistake.topic}`}><strong>{mistake.number}</strong><span>{mistake.topic}</span></button>)}
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

  const imagePaths = [item.asset, ...(item.assets ?? [])]
    .filter((asset): asset is string => Boolean(asset));
  const isLast = mistakes.length === 0 || (!item.is_correct && activeIndex === mistakes.length - 1);
  const structuredPreview = item.answer_preview;
  const previewLabel = (value: string) => (structuredPreview?.option_labels?.[value] ?? value) || "—";
  const previewRows = structuredPreview?.kind === "multiple"
    ? Array.from(new Set([...structuredPreview.user, ...structuredPreview.expected])).map((marker) => ({ marker, user: structuredPreview.user.includes(marker) ? marker : "", expected: structuredPreview.expected.includes(marker) ? marker : "" }))
    : structuredPreview?.markers.map((marker, markerIndex) => ({ marker, user: structuredPreview.user[markerIndex] ?? "", expected: structuredPreview.expected[markerIndex] ?? "" })) ?? [];

  return (
    <section className="screen review-screen" aria-labelledby="review-title">
      <div className="review-topline">
        <button className="text-back" onClick={onList ?? onBack} type="button">К списку</button>
        <span>{item.is_correct ? "Выбранное задание" : `Разбор ошибок · ${activeIndex + 1} из ${mistakes.length}`}</span>
      </div>
      <div className="review-heading">
        <span className="mistake-status">
          <b aria-hidden="true">{item.status === "skipped" ? "−" : item.status === "correct" ? "✓" : "×"}</b>
          {item.status === "skipped" ? "Пропущено" : item.status === "correct" ? "Верно" : "Неверно"}
        </span>
        <span>{item.topic}</span>
        {hasApprovedPrimaryScore(item.source) && <PrimaryScoreBadge maxPrimaryScore={item.max_primary_score} earnedPrimaryScore={item.earned_primary_score} />}
      </div>
      <h1 id="review-title" ref={headingRef} tabIndex={-1}>{item.title}</h1>
      <ReviewPrompt prompt={item.prompt} subject={subject} questionId={item.question_id} />
      {imagePaths.length > 0 && (
        <ImageViewer
          className="review-media"
          assets={imagePaths.map((path) => ({ path, alt: item.asset_alt }))}
          fallbackAlt="Иллюстрация к заданию"
        />
      )}
      <dl className="answer-review">
        <div className="answer-review-user">
          <dt>Ваш ответ</dt>
          <dd><FormattedMathText text={item.user_answer} subject={subject} /></dd>
        </div>
        <div className="answer-review-expected">
          <dt>Правильный ответ</dt>
          <dd><FormattedMathText text={item.expected_answer} subject={subject} /></dd>
        </div>
      </dl>
      {structuredPreview && (
        <section className="review-answer-preview" aria-labelledby="review-answer-preview-title">
          <h2 id="review-answer-preview-title">Схема ответа</h2>
          <table className="review-answer-table">
            <caption className="sr-only">Сравнение ответа</caption>
            <thead><tr><th scope="col">Позиция</th><th scope="col">Твой</th><th scope="col">Верный</th></tr></thead>
            <tbody>{previewRows.map((row, rowIndex) => (
              <tr key={`${row.marker}-${rowIndex}`}><th scope="row">{row.marker}</th><td><FormattedMathText text={previewLabel(row.user)} subject={subject} /></td><td><FormattedMathText text={previewLabel(row.expected)} subject={subject} /></td></tr>
            ))}</tbody>
          </table>
        </section>
      )}
      <section className="guidance" aria-labelledby="guidance-title">
        <span>Как решать</span>
        <h2 id="guidance-title">Разберите ход решения</h2>
        <p><FormattedMathText text={item.learning_material_text || item.guidance} subject={subject} /></p>
      </section>
      <button className="primary-button" onClick={isLast ? onForecast : onNext} type="button">
          {isLast ? "Мой план подготовки" : "Следующая ошибка"} <span aria-hidden="true">→</span>
      </button>
      <div className="review-direct-actions">
        <button className="text-back" type="button" onClick={onList ?? onBack}>К списку</button>
        <button className="text-back" type="button" onClick={onForecast}>К плану</button>
        {onHome && <button className="text-back" type="button" onClick={onHome}>На главную</button>}
      </div>
    </section>
  );
}

export function ForecastEmptyScreen({ completedCount, onBack, onStart }: {
  completedCount: number;
  onBack: () => void;
  onStart: () => void;
}): ReactNode {
  const done = Math.min(Math.max(completedCount, 0), 2);
  return (
    <section className="screen centered-state forecast-empty-screen" aria-labelledby="forecast-empty-title">
      <button className="text-back" onClick={onBack} type="button">Назад</button>
      <span className="state-icon" aria-hidden="true">📈</span>
      <h1 id="forecast-empty-title">Пока мало данных</h1>
      <p>Прогноз появится после 2 диагностик. Сейчас у тебя {done === 1 ? "одна" : String(done)} — пройди ещё, и посчитаем траекторию.</p>
      <div className="forecast-empty-progress" aria-label={`Диагностик пройдено: ${done} из 2`}>
        <span className={`forecast-empty-dot${done >= 1 ? " is-done" : ""}`} aria-hidden="true" />
        <span className={`forecast-empty-dot${done >= 2 ? " is-done" : ""}`} aria-hidden="true" />
        <small>{done} из 2</small>
      </div>
      <button className="primary-button" onClick={onStart} type="button">Пройти диагностику <span aria-hidden="true">→</span></button>
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
      <p className="lead">Занимайся по маршруту регулярно — и вот куда придёшь к экзамену.</p>
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
      {next && <p className="forecast-explainer">Это ориентир на основе среднего прироста, а не личная гарантия. Он достижим при системной подготовке по вашему маршруту.</p>}
      {points.length === 0 && <p className="forecast-empty">Пока нет числового ориентира. Откройте маршрут: он уже собран по вашим темам.</p>}
      {offer && !offerDismissed && (
        <OfferSurface
          offer={offer}
          placement="forecast"
          onClose={() => onOfferDismiss?.()}
          onEvent={onOfferEvent}
        />
      )}
      <button className="primary-button" onClick={onRoute} type="button">Открыть маршрут <span aria-hidden="true">→</span></button>
    </section>
  );
}

export function RouteScreen({
  items,
  offers,
  onSubjects,
  onRepeat,
}: {
  items: RouteItem[];
  offers: SchoolLinks["offers"];
  onSubjects: () => void;
  onRepeat?: () => void;
}): ReactNode {
  return (
    <section className="screen route-screen" aria-labelledby="route-title">
      <span className="state-code">Персональный маршрут</span>
      <h1 id="route-title">Твой маршрут</h1>
      <p className="lead">Начни с заданий, в которых были ошибки. Этот план относится к пройденной диагностике.</p>
      <ol className="route-list">
        {items.map((item, index) => (
          <li key={`${item.id}-${index}`}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <div><strong>{item.title}</strong><p>{item.description}</p></div>
          </li>
        ))}
      </ol>
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
      {onRepeat && <button className="primary-button route-repeat" onClick={onRepeat} type="button">Пройти диагностику ещё раз <span aria-hidden="true">→</span></button>}
      <button className="secondary-button" onClick={onSubjects} type="button">Выбрать другой предмет</button>
    </section>
  );
}
