import {
  answerInputConfig,
  isImportantPromptSentence,
  mathDisplayParts,
  splitPromptSentences,
  tokenizeMathText,
} from "./math-text";
import { isValidNumericInput, updateMatchingAnswer } from "./answer-values";
import { questionAssetPaths } from "./question-assets";
import {
  cleanAnswerLabel,
  parseQuestionPrompt,
  questionTitleClassName,
} from "./question-prompt";
import {
  isCompleteSequenceMatchingAnswer,
  parseSequenceMatchingPrompt,
  type SequenceMatchingPrompt,
} from "./sequence-matching";
import {
  isCompleteTableGapAnswer,
  parseTableGapPrompt,
  type TableGapPrompt,
} from "./table-gap-matching";
import type {
  AnswerValue,
  Brand,
  MatchingQuestion,
  MultipleQuestion,
  Question,
} from "./types";

export type QuestionScreenProps = {
  question: Question;
  index: number;
  total: number;
  answer: AnswerValue | undefined;
  labels: Brand["interface"];
  onAnswer: (value: AnswerValue) => void;
  onBack: () => void;
  onNext: () => void;
};

function isAnswered(question: Question, answer: AnswerValue | undefined): boolean {
  if (question.type === "single") return typeof answer === "string" && answer.length > 0;
  if (question.type === "multiple") {
    return Array.isArray(answer) && answer.length === question.selection_limit;
  }
  if (question.type === "matching") {
    return Boolean(
      answer
      && typeof answer === "object"
      && !Array.isArray(answer)
      && question.items.every((item) => Boolean(answer[item.id])),
    );
  }
  const tableGap = parseTableGapPrompt(question.prompt);
  if (tableGap) return isCompleteTableGapAnswer(tableGap, answer);
  const matching = parseSequenceMatchingPrompt(question.prompt);
  return matching
    ? isCompleteSequenceMatchingAnswer(matching, answer)
    : isValidNumericInput(answer);
}

function FormattedMathText({ text }: { text: string }) {
  return (
    <>
      {tokenizeMathText(text).map((part, partIndex) => (
        part.isMath
          ? (
            <span
              className={part.isVariable ? "math-expression math-variable" : "math-expression"}
              key={`${partIndex}-${part.text}`}
            >
              {mathDisplayParts(part.text).map((displayPart, displayIndex) => (
                displayPart.isSuperscript
                  ? <sup key={displayIndex}>{displayPart.text}</sup>
                  : displayPart.text
              ))}
            </span>
          )
          : part.text
      ))}
    </>
  );
}

function FormattedStem({ text }: { text: string }) {
  return (
    <>
      {splitPromptSentences(text).map((sentence, sentenceIndex) => (
        <span
          className={isImportantPromptSentence(sentence)
            ? "prompt-sentence prompt-sentence-important"
            : "prompt-sentence"}
          key={`${sentenceIndex}-${sentence}`}
        >
          <FormattedMathText text={sentence} />
        </span>
      ))}
    </>
  );
}

export function QuestionView({
  question,
  index,
  total,
  answer,
  labels,
  onAnswer,
  onBack,
  onNext,
}: QuestionScreenProps) {
  const progress = Math.round(((index + 1) / total) * 100);
  const imagePaths = questionAssetPaths(question);
  const promptBlocks = parseQuestionPrompt(question.prompt);
  const sequenceMatching = question.type === "input"
    ? parseSequenceMatchingPrompt(question.prompt)
    : null;
  const tableGap = question.type === "input"
    ? parseTableGapPrompt(question.prompt)
    : null;

  return (
    <section className="screen question-screen" aria-labelledby="question-title">
      <div className="question-topline">
        <button className="back-button" onClick={onBack} type="button" aria-label={labels.back}>{labels.back}</button>
        <div className="question-progress-copy" aria-live="polite">
          <span>{labels.task_label} {index + 1} {labels.of_label} {total}</span>
          <strong>{progress}%</strong>
        </div>
      </div>
      <div className="progress-track" role="progressbar" aria-label="Прогресс диагностики" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
        <span style={{ width: `${progress}%` }} />
      </div>
      <div className="question-meta"><span>{question.title}</span><span>{question.topic}</span></div>
      <div className="question-copy">
        {promptBlocks.map((block, blockIndex) => {
          if (tableGap && block.kind !== "stem") return null;
          if (sequenceMatching && (block.kind === "item" || block.kind === "heading" || block.kind === "instruction")) {
            return null;
          }
          if (
            sequenceMatching
            && block.kind === "paragraph"
            && sequenceMatching.left.some((item) => item.marker === block.text)
          ) return null;
          if (block.kind === "stem") {
            return (
              <h1 id="question-title" className={questionTitleClassName(block.text)} key={blockIndex}>
                <FormattedStem text={block.text} />
              </h1>
            );
          }
          if (block.kind === "heading") {
            return <h2 className="question-section-title" key={blockIndex}><FormattedMathText text={block.text} /></h2>;
          }
          if (block.kind === "item") {
            return (
              <div className="question-list-item" key={blockIndex}>
                <span>{block.marker}</span>
                <p><FormattedMathText text={block.text} /></p>
              </div>
            );
          }
          if (block.kind === "instruction") {
            return <p className="question-instruction" key={blockIndex}><FormattedMathText text={block.text} /></p>;
          }
          return <p className="question-paragraph" key={blockIndex}><FormattedMathText text={block.text} /></p>;
        })}
      </div>
      {imagePaths.length > 0 && (
        <div className="question-media">
          {imagePaths.map((imagePath, imageIndex) => (
            // School assets are mounted by the deployment image, never copied from a source school.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={imagePath}
              alt={imagePaths.length > 1
                ? `${labels.illustration_alt} ${imageIndex + 1}`
                : labels.illustration_alt}
              key={imagePath}
            />
          ))}
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
                <span><FormattedMathText text={cleanAnswerLabel(option.label)} /></span>
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
        tableGap ? (
          <TableGapAnswer matching={tableGap} onChange={onAnswer} value={typeof answer === "string" ? answer : ""} />
        ) : sequenceMatching ? (
          <SequenceMatchingAnswer matching={sequenceMatching} onChange={onAnswer} value={typeof answer === "string" ? answer : ""} />
        ) : (
          <ShortAnswer
            label={labels.answer_label}
            onChange={onAnswer}
            placeholder={labels.enter_answer}
            prompt={question.prompt}
            value={typeof answer === "string" ? answer : ""}
          />
        )
      )}

      <button className="primary-button question-next" disabled={!isAnswered(question, answer)} onClick={onNext} type="button">
        {index === total - 1 ? labels.get_result : labels.next_question}
        <span aria-hidden="true">→</span>
      </button>
    </section>
  );
}

function TableGapAnswer({ matching, onChange, value }: {
  matching: TableGapPrompt;
  onChange: (value: string) => void;
  value: string;
}) {
  const selected = [...value.slice(0, matching.markers.length)];
  const markerIndex = new Map(matching.markers.map((marker, index) => [marker, index]));

  return (
    <section className="table-gap" aria-labelledby="table-gap-title">
      <div className="sequence-matching-intro">
        <span>Таблица с пропусками</span>
        <h2 id="table-gap-title">Заполните ячейки</h2>
        <p>Выберите подходящий элемент прямо в каждой ячейке. Ответ соберётся автоматически.</p>
      </div>
      <div className="table-gap-grid" role="table" aria-label="Таблица с пропусками">
        <div className="table-gap-header" role="row">
          {matching.headers.map((header) => <strong role="columnheader" key={header}>{header}</strong>)}
        </div>
        {matching.rows.map((row, rowIndex) => (
          <div className="table-gap-row" role="row" key={rowIndex}>
            {row.map((cell, cellIndex) => {
              if (!cell.marker) return <span className="table-gap-cell" role="cell" key={cellIndex}>{cell.text}</span>;
              const currentIndex = markerIndex.get(cell.marker) ?? 0;
              const used = new Set(selected.filter((choice, choiceIndex) => choiceIndex !== currentIndex));
              const locked = currentIndex > selected.length;
              return (
                <label className={`table-gap-cell table-gap-select${locked ? " locked" : ""}`} role="cell" key={cell.marker}>
                  <strong>{cell.marker}</strong>
                  <select
                    aria-label={`Элемент для ячейки ${cell.marker}`}
                    disabled={locked}
                    value={selected[currentIndex] ?? ""}
                    onChange={(event) => {
                      const next = [...selected];
                      next[currentIndex] = event.target.value;
                      onChange(next.join(""));
                    }}
                  >
                    <option value="">Выберите</option>
                    {matching.options.map((option) => (
                      <option disabled={used.has(option.marker)} key={option.marker} value={option.marker}>
                        {option.marker} — {option.label}
                      </option>
                    ))}
                  </select>
                </label>
              );
            })}
          </div>
        ))}
      </div>
      <AnswerPreview markers={matching.markers} selected={selected} />
    </section>
  );
}

function SequenceMatchingAnswer({ matching, onChange, value }: {
  matching: SequenceMatchingPrompt;
  onChange: (value: string) => void;
  value: string;
}) {
  const selected = [...value.slice(0, matching.left.length)];
  return (
    <section className="sequence-matching" aria-labelledby="sequence-matching-title">
      <div className="sequence-matching-intro">
        <span>Ответ без ручного ввода</span>
        <h2 id="sequence-matching-title">Составьте соответствие</h2>
        <p>Для каждого пункта по очереди выберите подходящий вариант.</p>
      </div>
      <div className="sequence-matching-rows">
        {matching.left.map((item, index) => {
          const rowValue = selected[index] ?? "";
          const used = new Set(selected.filter((choice, choiceIndex) => choiceIndex !== index));
          const locked = index > selected.length;
          return (
            <label className={`sequence-matching-row${locked ? " locked" : ""}`} key={item.marker}>
              <span className="sequence-matching-row-copy"><strong>{item.marker}</strong><span>{item.label}</span></span>
              <select
                aria-label={`Вариант для пункта ${item.marker}`}
                disabled={locked}
                value={rowValue}
                onChange={(event) => {
                  const next = [...selected];
                  next[index] = event.target.value;
                  onChange(next.join(""));
                }}
              >
                <option value="">Выберите вариант</option>
                {matching.options.map((option) => (
                  <option
                    disabled={!matching.allowReuse && used.has(option.marker)}
                    key={option.marker}
                    value={option.marker}
                  >
                    {option.marker} — {option.label}
                  </option>
                ))}
              </select>
            </label>
          );
        })}
      </div>
      <AnswerPreview markers={matching.left.map((item) => item.marker)} selected={selected} />
    </section>
  );
}

function AnswerPreview({ markers, selected }: { markers: string[]; selected: string[] }) {
  return (
    <div className={`sequence-answer-preview${selected.length === markers.length ? " complete" : ""}`} aria-live="polite">
      <span>Получившийся ответ</span>
      <strong>
        {markers.map((marker, index) => (
          <span key={marker}>{selected[index] ?? "—"}<small>{marker}</small></span>
        ))}
      </strong>
    </div>
  );
}

function ShortAnswer({ label, onChange, placeholder, prompt, value }: {
  label: string;
  onChange: (value: string) => void;
  placeholder: string;
  prompt: string;
  value: string;
}) {
  const config = answerInputConfig(prompt);
  return (
    <label className="short-answer">
      <span>{label}</span>
      <span className="short-answer-control">
        <input
          autoCapitalize="off"
          autoComplete="off"
          enterKeyHint="done"
          inputMode={config.inputMode}
          className={config.inputMode === "text" ? undefined : "answer-numeric"}
          maxLength={64}
          spellCheck={false}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
        />
        {value && <button type="button" onClick={() => onChange("")}>Очистить</button>}
      </span>
      <small>{config.hint}</small>
    </label>
  );
}

function MultipleAnswers({ question, value, onChange }: {
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
            <span>{cleanAnswerLabel(option.label)}</span>
            <span className="selection-mark square" aria-hidden="true" />
          </button>
        );
      })}
    </div>
  );
}

function MatchingAnswers({ question, value, onChange, chooseLabel }: {
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
          <span>{cleanAnswerLabel(item.label)}</span>
          <select
            aria-label={`Соответствие для ${item.label}`}
            value={value[item.id] ?? ""}
            onChange={(event) => onChange(updateMatchingAnswer(value, item.id, event.target.value))}
          >
            <option value="">{chooseLabel}</option>
            {question.options.map((option) => (
              <option value={option.id} key={option.id}>{cleanAnswerLabel(option.label)}</option>
            ))}
          </select>
        </label>
      ))}
    </div>
  );
}
