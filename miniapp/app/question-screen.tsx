import { AnswerEditor, textAnswerGuidance, type AnswerEditorLabels } from "./answer-editor";
import { AnswerPreview, MatchingAnswer, matchingModelFromSequence } from "./matching-answer";
import { FormattedMathText, FormattedStem } from "./math-display";
import { isValidNumericInput, isValidTextInput, updateCompactAnswer } from "./answer-values";
import { questionAssetPaths } from "./question-assets";
import { ImageViewer } from "./image-viewer";
import { PromptTable } from "./prompt-table";
import { hasApprovedPrimaryScore, PrimaryScoreBadge } from "./question-metadata";
import {
  answerTypeLabel,
  parseQuestionPrompt,
  questionTitleClassName,
} from "./question-prompt";
import {
  isCompleteSequenceMatchingAnswer,
  parseSequenceMatchingPrompt,
} from "./sequence-matching";
import {
  isCompleteTableGapAnswer,
  parseTableGapPrompt,
  type TableGapPrompt,
} from "./table-gap-matching";
import { useEffect, useRef, useState } from "react";
import { AssessmentHeader } from "./assessment-header";
import { createPromptAnchorAllocator, focusPromptReference, promptLayout } from "./prompt-layout";
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
};

export function StructuredAnswerEditor({ question, subject, value, onChange, disabled = false, suppressAutoHint = false, labels }: {
  question: Question;
  subject?: string;
  value: AnswerValue | undefined;
  onChange: (value: AnswerValue) => void;
  disabled?: boolean;
  suppressAutoHint?: boolean;
  labels?: Partial<AnswerEditorLabels>;
}) {
  const tableGap = question.type === "input" ? parseTableGapPrompt(question.prompt, question) : null;
  if (tableGap) {
    return <TableGapAnswer matching={tableGap} disabled={disabled} onChange={(next) => onChange(next)} value={typeof value === "string" ? value : ""} />;
  }
  const sequence = question.type === "input" ? parseSequenceMatchingPrompt(question.prompt, question) : null;
  if (sequence) {
    return <MatchingAnswer model={matchingModelFromSequence(sequence, subject)} subject={subject} disabled={disabled} onChange={onChange} value={typeof value === "string" ? value : ""} />;
  }
  return <AnswerEditor question={question} subject={subject} value={value} disabled={disabled} suppressAutoHint={suppressAutoHint} labels={labels} onChange={onChange} />;
}

export type QuestionProgress = {
  current: number;
  total: number;
  percent: number;
  message: string;
};

type AnswerReadiness = {
  isAnswered: boolean;
  reason: string;
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

function answerReadiness(question: Question, answer: AnswerValue | undefined): AnswerReadiness {
  switch (question.type) {
    case "single":
      return typeof answer === "string" && answer.length > 0
        ? { isAnswered: true, reason: "" }
        : { isAnswered: false, reason: "Выбери вариант" };
    case "multiple": {
      const selected = Array.isArray(answer) ? answer.length : 0;
      return selected === question.selection_limit
        ? { isAnswered: true, reason: "" }
        : { isAnswered: false, reason: `Выбрано ${selected} из ${question.selection_limit}` };
    }
    case "matching": {
      const value = answer
        && typeof answer === "object"
        && !Array.isArray(answer)
          ? answer
          : {};
      const missing = question.items.flatMap((item, index) => {
        if (value[item.id]) return [];
        const marker = /^\s*([А-ЯЁA-Z0-9]+)(?:[).]|\s|$)/u.exec(item.label)?.[1];
        return [marker ?? String(index + 1)];
      });
      return missing.length === 0
        ? { isAnswered: true, reason: "" }
        : { isAnswered: false, reason: `Осталось заполнить: ${missing.join(", ")}` };
    }
    case "text":
      return isValidTextInput(answer, question.max_length)
        ? { isAnswered: true, reason: "" }
        : { isAnswered: false, reason: "Введи ответ" };
    case "input": {
      const tableGap = parseTableGapPrompt(question.prompt, question);
      if (tableGap) {
        if (isCompleteTableGapAnswer(tableGap, answer)) return { isAnswered: true, reason: "" };
        const selected = typeof answer === "string" ? [...answer] : [];
        const duplicate = selected.find((value, index) => selected.indexOf(value) !== index);
        return duplicate
          ? { isAnswered: false, reason: `Вариант ${duplicate} выбран дважды` }
          : {
            isAnswered: false,
            reason: `Осталось заполнить: ${tableGap.markers.slice(selected.length).join(", ")}`,
          };
      }
      const matching = parseSequenceMatchingPrompt(question.prompt, question);
      if (matching) {
        if (isCompleteSequenceMatchingAnswer(matching, answer)) return { isAnswered: true, reason: "" };
        const selected = typeof answer === "string" ? [...answer] : [];
        const duplicate = matching.allowReuse
          ? undefined
          : selected.find((value, index) => selected.indexOf(value) !== index);
        return duplicate
          ? { isAnswered: false, reason: `Вариант ${duplicate} выбран дважды` }
          : {
            isAnswered: false,
            reason: `Заполнено ${Math.min(selected.length, matching.answerLength)} из ${matching.answerLength}`,
          };
      }
      if (question.answer_format === "sequence" && question.answer_length) {
        // The server accepts exactly `answer_length` digits, so the button must
        // not promise a transition the completion request will refuse.
        const digits = typeof answer === "string" ? [...answer] : [];
        const wellFormed = digits.every((value) => /^\d$/u.test(value));
        const duplicate = question.allow_reuse === false
          ? digits.find((value, index) => digits.indexOf(value) !== index)
          : undefined;
        if (wellFormed && !duplicate && digits.length === question.answer_length) {
          return { isAnswered: true, reason: "" };
        }
        return duplicate
          ? { isAnswered: false, reason: `Вариант ${duplicate} выбран дважды` }
          : { isAnswered: false, reason: `Заполнено ${Math.min(digits.length, question.answer_length)} из ${question.answer_length}` };
      }
      return isValidNumericInput(answer)
        ? { isAnswered: true, reason: "" }
        : { isAnswered: false, reason: "Введи число" };
    }
    default: {
      const exhaustiveQuestion: never = question;
      return exhaustiveQuestion;
    }
  }
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
}: QuestionScreenProps) {
  const progress = questionProgress(index, total);
  const readiness = answerReadiness(question, answer);
  const questionAnnouncement = progressAnnouncement || (
    skipped
      ? "Задание пропущено. Можно вернуться и ответить позже."
      : !readiness.isAnswered ? readiness.reason : ""
  );
  const imagePaths = questionAssetPaths(question);
  const promptBlocks = parseQuestionPrompt(question.prompt);
  const layout = promptLayout(promptBlocks);
  const anchors = createPromptAnchorAllocator();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const referenceRef = useRef<HTMLDivElement>(null);
  const [referenceExpanded, setReferenceExpanded] = useState(false);
  useEffect(() => {
    setReferenceExpanded(false);
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    headingRef.current?.focus({ preventScroll: true });
  }, [question.id]);
  const focusReference = () => {
    focusPromptReference("question-reference");
  };
  const instructions = promptBlocks.flatMap((block) => block.kind === "instruction" ? [block.text] : []);
  const textGuidance = question.type === "text" ? textAnswerGuidance(question) : null;
  const renderedInstructions = textGuidance && instructions.length > 0
    ? [`${instructions.join(" ")} ${textGuidance}`]
    : instructions;
  const sequenceMatching = question.type === "input"
    ? parseSequenceMatchingPrompt(question.prompt, question)
    : null;
  const tableGap = question.type === "input"
    ? parseTableGapPrompt(question.prompt, question)
    : null;
  const questionMedia = imagePaths.length > 0 && (
    <ImageViewer
      className="question-media"
      assets={imagePaths.map((path) => ({ path, alt: question.asset_alt }))}
      fallbackAlt={labels.illustration_alt}
    />
  );

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
          onBack,
          onExit,
          onReference: layout.isLongReference ? focusReference : undefined,
        }} />
      </div>
      <div className="question-worksheet">
      <div className="question-meta">
        <span className="question-type-chip">{subject ?? question.topic} · {answerTypeLabel(question)}</span>
        {hasApprovedPrimaryScore(question.source) && <PrimaryScoreBadge maxPrimaryScore={question.max_primary_score} />}
      </div>
      <div className="question-copy">
        <h1 ref={headingRef} tabIndex={-1} id="question-title" className={layout.stem ? questionTitleClassName(layout.stem) : "question-title"}>
          <FormattedStem text={layout.stem ?? "Задание"} subject={subject} />
        </h1>
        {questionMedia}
        {layout.isLongReference && (
          <button className="prompt-reference-toggle" type="button" aria-controls="question-reference" aria-expanded={referenceExpanded} onClick={() => setReferenceExpanded((expanded) => !expanded)}>
            {referenceExpanded ? "Свернуть текст" : "Развернуть текст"}
          </button>
        )}
        <div id="question-reference" ref={referenceRef} tabIndex={-1} className={`prompt-reference${layout.isLongReference ? " prompt-reference-long" : ""}${referenceExpanded ? " is-expanded" : ""}`}>
        {layout.referenceBlocks.map((block, blockIndex) => {
          if (tableGap) return null;
          if (sequenceMatching && (block.kind === "item" || block.kind === "heading" || block.kind === "table")) {
            return null;
          }
          if (
            sequenceMatching
            && block.kind === "paragraph"
            && sequenceMatching.left.some((item) => item.marker === block.text)
          ) return null;
          if (block.kind === "heading") {
            return <h2 id={anchors.blockId(block)} className="question-section-title" key={blockIndex}><FormattedMathText text={block.text} subject={subject} /></h2>;
          }
          if (block.kind === "item") {
            return (
              <div className="question-list-item" id={anchors.blockId(block)} key={blockIndex}>
                <span>{block.marker}</span>
                <p><FormattedMathText text={block.text} subject={subject} /></p>
              </div>
            );
          }
          if (block.kind === "table") {
            return <div id={anchors.blockId(block)} key={blockIndex}><PromptTable headerRows={block.headerRows} rows={block.rows} columns={block.columns} subject={subject} /></div>;
          }
          return (
            <p className="question-paragraph" key={blockIndex}>
              {anchors.sentenceSegments(block.text).map((segment, segmentIndex) => (
                <span id={segment.anchorId} key={segmentIndex}><FormattedMathText text={segment.text} subject={subject} /></span>
              ))}
            </p>
          );
        })}
        </div>
      </div>

      {renderedInstructions.length > 0 && renderedInstructions.map((instruction, instructionIndex) => (
        <p className="question-instruction" key={`instruction-${instructionIndex}`}>
          <FormattedMathText text={instruction} subject={subject} />
        </p>
      ))}

      {layout.isLongReference && layout.stem && (
        <p className="question-stem-repeat" aria-hidden="true"><FormattedStem text={layout.stem} subject={subject} /></p>
      )}

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
          suppressAutoHint={renderedInstructions.length > 0}
          labels={{
            answer: labels.answer_label,
            placeholder: labels.enter_answer,
            choose: labels.choose_option,
          }}
        />
      )}

      <div className="question-action-bar">
        <button className="primary-button question-next" disabled={!readiness.isAnswered && !skipped} onClick={onNext} type="button">
          {index === total - 1 ? labels.get_result : labels.next_question}
          <span aria-hidden="true">→</span>
        </button>
        {!readiness.isAnswered && !skipped && onSkip && (
          <button className="question-skip" onClick={onSkip} type="button">
            {index === total - 1 ? "Не знаю, получить результат" : "Не знаю, дальше"}
          </button>
        )}
        <p
          className="question-announcement"
          role={progressAnnouncementRole}
          aria-live={progressAnnouncementRole === "alert" ? "assertive" : "polite"}
          aria-atomic="true"
        >
          {questionAnnouncement}
        </p>
      </div>
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
                        <option value="">Выбери…</option>
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
