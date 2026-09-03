import { answerInputConfig } from "./math-text";
import { FormattedMathText } from "./math-display";
import { updateMatchingAnswer } from "./answer-values";
import { cleanAnswerLabel } from "./question-prompt";
import { DEFAULT_TEXT_ANSWER_LENGTH } from "./answer-values";
import type {
  AnswerValue,
  InputQuestion,
  MatchingQuestion,
  MultipleQuestion,
  Question,
  SingleQuestion,
  TextQuestion,
} from "./types";

export type AnswerEditorLabels = {
  answer: string;
  placeholder: string;
  choose: string;
};

export type AnswerEditorProps = {
  question: Question;
  value: AnswerValue | undefined;
  onChange: (value: AnswerValue) => void;
  disabled?: boolean;
  labels?: Partial<AnswerEditorLabels>;
};

const DEFAULT_LABELS: AnswerEditorLabels = {
  answer: "Твой ответ",
  placeholder: "Введи ответ",
  choose: "Выберите",
};

export function AnswerEditor({ question, value, onChange, disabled = false, labels }: AnswerEditorProps) {
  const text = { ...DEFAULT_LABELS, ...labels };
  const asText = typeof value === "string" ? value : "";
  if (question.type === "single") {
    return <SingleEditor question={question} value={asText} disabled={disabled} onChange={onChange} />;
  }
  if (question.type === "multiple") {
    return <MultipleEditor question={question} value={Array.isArray(value) ? value : []} disabled={disabled} onChange={onChange} />;
  }
  if (question.type === "matching") {
    const pairs = value && typeof value === "object" && !Array.isArray(value) ? value : {};
    return <MatchingEditor question={question} value={pairs} disabled={disabled} chooseLabel={text.choose} onChange={onChange} />;
  }
  if (question.type === "text") {
    return <ShortTextEditor question={question} value={asText} disabled={disabled} label={text.answer} placeholder={text.placeholder} onChange={onChange} />;
  }
  return <InputEditor question={question} value={asText} disabled={disabled} label={text.answer} placeholder={text.placeholder} onChange={onChange} />;
}

function OptionButton({ label, marker, selected, disabled, square, onClick }: {
  label: string;
  marker: string;
  selected: boolean;
  disabled: boolean;
  square?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      {...(square ? { "aria-pressed": selected } : { role: "radio", "aria-checked": selected })}
      disabled={disabled}
      className={`answer-option${selected ? " selected" : ""}`}
      onClick={onClick}
    >
      <span className="option-letter">{marker}</span>
      <span><FormattedMathText text={cleanAnswerLabel(label)} /></span>
      <span className={square ? "selection-mark square" : "selection-mark"} aria-hidden="true" />
    </button>
  );
}

function SingleEditor({ question, value, disabled, onChange }: {
  question: SingleQuestion;
  value: string;
  disabled: boolean;
  onChange: (value: AnswerValue) => void;
}) {
  return (
    <div className="answer-list" role="radiogroup" aria-label="Выберите один вариант">
      {question.options.map((option, index) => (
        <OptionButton
          key={option.id}
          label={option.label}
          marker={String.fromCharCode(65 + index)}
          selected={value === option.id}
          disabled={disabled}
          onClick={() => onChange(option.id)}
        />
      ))}
    </div>
  );
}

function MultipleEditor({ question, value, disabled, onChange }: {
  question: MultipleQuestion;
  value: string[];
  disabled: boolean;
  onChange: (value: AnswerValue) => void;
}) {
  const toggle = (id: string) => {
    if (value.includes(id)) onChange(value.filter((item) => item !== id));
    else if (value.length < question.selection_limit) onChange([...value, id]);
  };

  return (
    <div className="answer-list" role="group" aria-label={`Выберите ${question.selection_limit} варианта`}>
      {question.options.map((option, index) => (
        <OptionButton
          key={option.id}
          label={option.label}
          marker={String.fromCharCode(65 + index)}
          selected={value.includes(option.id)}
          disabled={disabled}
          square
          onClick={() => toggle(option.id)}
        />
      ))}
    </div>
  );
}

function MatchingEditor({ question, value, disabled, chooseLabel, onChange }: {
  question: MatchingQuestion;
  value: Record<string, string>;
  disabled: boolean;
  chooseLabel: string;
  onChange: (value: AnswerValue) => void;
}) {
  return (
    <div className="matching-list">
      {question.items.map((item, index) => (
        <label className="matching-row" key={item.id}>
          <span className="matching-index">{index + 1}</span>
          <span><FormattedMathText text={cleanAnswerLabel(item.label)} /></span>
          <select
            aria-label={`Соответствие для ${item.label}`}
            disabled={disabled}
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

function InputEditor({ question, value, disabled, label, placeholder, onChange }: {
  question: InputQuestion;
  value: string;
  disabled: boolean;
  label: string;
  placeholder: string;
  onChange: (value: AnswerValue) => void;
}) {
  const config = answerInputConfig(question.prompt);
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
          disabled={disabled}
          maxLength={64}
          spellCheck={false}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
        />
        {value && <button type="button" disabled={disabled} onClick={() => onChange("")}>Очистить</button>}
      </span>
      <small>{config.hint}</small>
    </label>
  );
}

/** Free text: the same field as InputEditor, without the numeric mode or its digit hint. */
function ShortTextEditor({ question, value, disabled, label, placeholder, onChange }: {
  question: TextQuestion;
  value: string;
  disabled: boolean;
  label: string;
  placeholder: string;
  onChange: (value: AnswerValue) => void;
}) {
  return (
    <label className="short-answer">
      <span>{label}</span>
      <span className="short-answer-control">
        <input
          autoCapitalize="off"
          autoComplete="off"
          enterKeyHint="done"
          inputMode="text"
          disabled={disabled}
          maxLength={question.max_length ?? DEFAULT_TEXT_ANSWER_LENGTH}
          spellCheck={false}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
        />
        {value && <button type="button" disabled={disabled} onClick={() => onChange("")}>Очистить</button>}
      </span>
      <small>Введите только ответ — без пояснений и лишних слов.</small>
    </label>
  );
}
