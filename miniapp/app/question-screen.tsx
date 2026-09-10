import { ActionBar } from "./action-bar";
import { answerReadiness } from "./answer-readiness";
import { AnswerEditor, type AnswerEditorLabels } from "./answer-editor";
import { AnswerPreview, MatchingAnswer, matchingModelFromSequence } from "./matching-answer";
import { isValidNumericInput, isValidTextInput, updateCompactAnswer } from "./answer-values";
import { hasApprovedPrimaryScore, PrimaryScoreBadge } from "./question-metadata";
import { answerTypeLabel } from "./question-prompt";
import { QuestionBody, questionBodyModel } from "./question-body";
import {
  isCompleteSequenceMatchingAnswer,
  parseSequenceMatchingPrompt,
} from "./sequence-matching";
import {
  isCompleteTableGapAnswer,
  parseTableGapPrompt,
  type TableGapPrompt,
} from "./table-gap-matching";
import { AssessmentHeader } from "./assessment-header";
import { focusPromptReference } from "./prompt-layout";
import type { AnswerValue, Brand, Question } from "./types";

export type QuestionScreenProps = {
  question: Question;
  subject?: string;
  index: number;
  total: number;
  answer: AnswerValue | undefined;
  labels: Brand["interface"];
  onAnswer: (value: AnswerValue) => void;
  onBack: () => void;
  onNext: () => void;
  onSkip?: () => void;
  onExit?: () => void;
  progressSaveState?: "idle" | "saving" | "saved" | "error";
  progressAnnouncement?: string | null;
  progressAnnouncementRole?: "status" | "alert";
  skipped?: boolean;
  skippedIndexes?: readonly number[];
  onJumpToQuestion?: (index: number) => void;
};

export function StructuredAnswerEditor({ question, subject, value, onChange, disabled = false, suppressAutoHint = false, labels, correctOptions }: {
  question: Question;
  subject?: string;
  value: AnswerValue | undefined;
  onChange: (value: AnswerValue) => void;
  disabled?: boolean;
  suppressAutoHint?: boolean;
  labels?: Partial<AnswerEditorLabels>;
  correctOptions?: readonly string[];
}) {
  const tableGap = question.type === "input" ? parseTableGapPrompt(question.prompt, question) : null;
  if (tableGap) {
    return <TableGapAnswer matching={tableGap} disabled={disabled} onChange={(next) => onChange(next)} value={typeof value === "string" ? value : ""} />;
  }
  const sequence = question.type === "input" ? parseSequenceMatchingPrompt(question.prompt, question) : null;
  if (sequence) {
    return <MatchingAnswer model={matchingModelFromSequence(sequence, subject)} subject={subject} disabled={disabled} onChange={onChange} value={typeof value === "string" ? value : ""} />;
  }
  return <AnswerEditor question={question} subject={subject} value={value} disabled={disabled} suppressAutoHint={suppressAutoHint} labels={labels} correctOptions={correctOptions} onChange={onChange} />;
}

export type QuestionProgress = {
  current: number;
  total: number;
  percent: number;
  message: string;
};

export function questionProgress(index: number, total: number): QuestionProgress {
  const current = index + 1;
  const percent = Math.round((current / total) * 100);
  const message = current === total
    ? "Последний рывок"
    : index === 0
      ? "Стартуем спокойно"
      : current <= total / 2
        ? "Набираем темп"
        : "Финиш рядом";

  return { current, total, percent, message };
}

export function QuestionView({
  question,
  subject,
  index,
  total,
  answer,
  labels,
  onAnswer,
  onBack,
  onNext,
  onSkip,
  onExit = () => undefined,
  progressSaveState = "idle",
  progressAnnouncement = null,
  progressAnnouncementRole = "status",
  skipped = false,
  skippedIndexes = [],
  onJumpToQuestion,
}: QuestionScreenProps) {
  const progress = questionProgress(index, total);
  const readiness = answerReadiness(question, answer, subject);
  const questionAnnouncement = progressAnnouncement || (
    skipped
      ? "Задание пропущено. Можно вернуться и ответить позже."
      : readiness.isAnswered ? "Готово, можно дальше" : readiness.reason
  );
  const body = questionBodyModel(question);
  const layout = body.layout;
  const focusReference = () => {
    focusPromptReference("question-reference");
  };
  const sequenceMatching = question.type === "input"
    ? parseSequenceMatchingPrompt(question.prompt, question)
    : null;
  const tableGap = question.type === "input"
    ? parseTableGapPrompt(question.prompt, question)
    : null;

  return (
    <section className="screen question-screen" aria-labelledby="question-title">
      <div className="question-shell">
        <AssessmentHeader model={{
          topic: `Задание ${progress.current} из ${progress.total} · ${question.topic || subject || "Диагностика"}`,
          current: progress.current,
          total: progress.total,
          backDisabled: index === 0,
          progressVariant: progress.total <= 12 ? "dots" : "bar",
          percent: progress.percent,
          showCount: false,
          backLabel: labels.back,
          saveState: progressSaveState,
          progressMessage: `${labels.task_label} ${progress.current} ${labels.of_label} ${progress.total}. ${progress.message}`,
          skippedIndexes,
          onJumpToQuestion,
          onBack,
          onExit,
          onReference: layout.isLongReference ? focusReference : undefined,
        }} />
      </div>
      <div className="question-worksheet">
      <QuestionBody
        question={question}
        subject={subject}
        model={body}
        idPrefix="question"
        illustrationAlt={labels.illustration_alt}
        meta={(
          <div className="question-meta">
            <span className="question-type-chip">{subject ?? question.topic} · {answerTypeLabel(question)}</span>
            {hasApprovedPrimaryScore(question.source) && <PrimaryScoreBadge maxPrimaryScore={question.max_primary_score} />}
          </div>
        )}
      />

      {tableGap ? (
        <TableGapAnswer matching={tableGap} onChange={onAnswer} value={typeof answer === "string" ? answer : ""} />
      ) : sequenceMatching ? (
        <MatchingAnswer model={matchingModelFromSequence(sequenceMatching, subject)} subject={subject} onChange={onAnswer} value={typeof answer === "string" ? answer : ""} />
      ) : (
        <StructuredAnswerEditor
          question={question}
          subject={subject}
          value={answer}
          onChange={onAnswer}
          suppressAutoHint={body.instructions.length > 0}
          labels={{
            answer: labels.answer_label,
            placeholder: labels.enter_answer,
            choose: labels.choose_option,
          }}
        />
      )}

      <ActionBar
        primaryLabel={index === total - 1 ? labels.get_result : labels.next_question}
        primaryDisabled={!readiness.isAnswered && !skipped}
        onPrimary={skipped && !readiness.isAnswered && onSkip ? onSkip : onNext}
        message={questionAnnouncement}
        messageRole={progressAnnouncementRole}
        skip={onSkip ? {
          label: "Пропустить",
          caption: "Отметим как пропущенное, вернуться можно в любой момент",
          available: !skipped,
          onSkip,
        } : undefined}
      />
      </div>
    </section>
  );
}

function TableGapAnswer({ matching, onChange, value, disabled = false }: {
  matching: TableGapPrompt;
  disabled?: boolean;
  onChange: (value: string) => void;
  value: string;
}) {
  const selected = [...value.slice(0, matching.markers.length)];
  const markerIndex = new Map(matching.markers.map((marker, index) => [marker, index]));

  return (
    <section className="table-gap" aria-labelledby="table-gap-title">
      <div className="sequence-matching-intro">
        <span>Таблица с пропусками</span>
        <h2 id="table-gap-title">Заполни пропуски</h2>
        <p>Каждая строка таблицы раскрыта в карточку. Ответ соберётся автоматически.</p>
      </div>
      <div className="table-gap-rows" aria-label="Таблица с пропусками">
        {matching.rows.map((row, rowIndex) => {
          const [head, ...rest] = row;
          const titleFromHead = head && !head.marker;
          const fields = titleFromHead ? rest : row;
          const fieldHeaders = titleFromHead ? matching.headers.slice(1) : matching.headers;
          return (
            <div className="table-gap-row" key={rowIndex}>
              <div className="table-gap-row-title">Строка {rowIndex + 1}{titleFromHead ? ` · ${head.text}` : " · ?"}</div>
              <div className="table-gap-fields">
                {fields.map((cell, cellIndex) => {
                  const header = fieldHeaders[cellIndex] ?? "";
                  if (!cell.marker) {
                    return (
                      <span className="table-gap-field" key={cellIndex}>
                        <small>{header}</small>
                        <span className="table-gap-cell">{cell.text}</span>
                      </span>
                    );
                  }
                  const currentIndex = markerIndex.get(cell.marker) ?? 0;
                  const used = new Set(selected.filter((choice, choiceIndex) => choiceIndex !== currentIndex));
                  const locked = currentIndex > selected.length;
                  return (
                    <label className={`table-gap-field table-gap-select${locked || disabled ? " locked" : ""}`} key={cell.marker}>
                      <small>{header}</small>
                      <select
                        aria-label={`${header || "Элемент"} для ячейки ${cell.marker}`}
                        disabled={locked || disabled}
                        value={selected[currentIndex] ?? ""}
                        onChange={(event) => onChange(
                          updateCompactAnswer(value, currentIndex, event.target.value),
                        )}
                      >
                        <option value="">Выбрать вариант</option>
                        {matching.options.map((option) => (
                          <option disabled={!matching.allowReuse && used.has(option.marker)} key={option.marker} value={option.marker}>
                            {option.marker} — {option.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
      <AnswerPreview markers={matching.markers} selected={selected} />
    </section>
  );
}
