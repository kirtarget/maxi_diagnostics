import { FormattedMathText } from "./math-display";
import { answerInputConfig } from "./math-text";
import { cleanAnswerLabel } from "./question-prompt";
import { DEFAULT_TEXT_ANSWER_LENGTH, normalizeNumericInput } from "./answer-values";
import { AnswerPreview, MatchingAnswer, matchingModelFromQuestion } from "./matching-answer";
import type {
  AnswerValue,
  InputQuestion,
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
  subject?: string;
  value: AnswerValue | undefined;
  onChange: (value: AnswerValue) => void;
  disabled?: boolean;
  suppressAutoHint?: boolean;
  labels?: Partial<AnswerEditorLabels>;
};

const DEFAULT_LABELS: AnswerEditorLabels = {
  answer: "Твой ответ",
  placeholder: "Введи ответ",
  choose: "Выберите",
};

const STRESS_CONTEXT = /ошибк\p{L}*\s+в\s+постановк\p{L}*\s+ударени\p{L}*.*выделен\p{L}*\s+букв\p{L}*.*ударн\p{L}*\s+гласн/isu;
const CYRILLIC_STRESS_VOWELS = new Set("АЕЁИОУЫЭЮЯ");

function legacyStressDisplay(question: SingleQuestion | MultipleQuestion, label: string, subject?: string): string | undefined {
  if (!subject || !(/русский язык|russian-language/i.test(subject) && STRESS_CONTEXT.test(question.prompt))) return undefined;
  const characters = [...label];
  const positions = characters.flatMap((character, index) => (
    CYRILLIC_STRESS_VOWELS.has(character) && index > 0 ? [index] : []
  ));
  if (positions.length !== 1) return undefined;
  const lowered = label.toLocaleLowerCase("ru-RU");
  const position = positions[0];
  return lowered.slice(0, position + 1) + "\u0301" + lowered.slice(position + 1);
}

function optionDisplay(question: SingleQuestion | MultipleQuestion, option: { label: string; stress?: string }, subject?: string): string {
  return option.stress ?? legacyStressDisplay(question, option.label, subject) ?? option.label;
}

export function textAnswerGuidance(question: TextQuestion): string | null {
  if (question.answer_format === "words") return "Введи два слова. Регистр не важен, ё = е.";
  if (question.answer_format === "word" && question.lang === "en") return "Enter one word. Case does not matter.";
  if (question.answer_format === "word") return "Введи одно слово. Регистр не важен, ё = е.";
  return null;
}

export function AnswerEditor({ question, subject, value, onChange, disabled = false, suppressAutoHint = false, labels }: AnswerEditorProps) {
  const text = { ...DEFAULT_LABELS, ...labels };
  const asText = typeof value === "string" ? value : "";
  if (question.type === "single") {
    return <SingleEditor question={question} subject={subject} value={asText} disabled={disabled} onChange={onChange} />;
  }
  if (question.type === "multiple") {
    return <MultipleEditor question={question} subject={subject} value={Array.isArray(value) ? value : []} disabled={disabled} onChange={onChange} />;
  }
  if (question.type === "matching") {
    const pairs = value && typeof value === "object" && !Array.isArray(value) ? value : {};
    return <MatchingAnswer model={matchingModelFromQuestion(question, subject)} subject={subject} value={pairs} disabled={disabled} onChange={onChange} />;
  }
  if (question.type === "text") {
    return <ShortTextEditor question={question} value={asText} disabled={disabled} suppressAutoHint={suppressAutoHint} label={text.answer} placeholder={text.placeholder} onChange={onChange} />;
  }
  return <InputEditor question={question} value={asText} disabled={disabled} suppressAutoHint={suppressAutoHint} label={text.answer} placeholder={text.placeholder} onChange={onChange} />;
}

function OptionButton({ label, stress, marker, selected, disabled, square, subject, onClick }: {
  label: string;
  stress?: string;
  marker: string;
  selected: boolean;
  disabled: boolean;
  square?: boolean;
  subject?: string;
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
      <span><FormattedMathText text={cleanAnswerLabel(stress ?? label)} subject={subject} /></span>
      <span className={square ? "selection-mark square" : "selection-mark"} aria-hidden="true" />
    </button>
  );
}

function SingleEditor({ question, subject, value, disabled, onChange }: {
  question: SingleQuestion;
  subject?: string;
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
          stress={optionDisplay(question, option, subject)}
          marker={String.fromCharCode(65 + index)}
          selected={value === option.id}
          disabled={disabled}
          subject={subject}
          onClick={() => onChange(option.id)}
        />
      ))}
    </div>
  );
}

function MultipleEditor({ question, subject, value, disabled, onChange }: {
  question: MultipleQuestion;
  subject?: string;
  value: string[];
  disabled: boolean;
  onChange: (value: AnswerValue) => void;
}) {
  const toggle = (id: string) => {
    if (value.includes(id)) onChange(value.filter((item) => item !== id));
    else if (value.length < question.selection_limit) onChange([...value, id]);
  };

  const markers = question.options.map((_, index) => String.fromCharCode(65 + index));
  return (
    <>
      <div className="answer-list" role="group" aria-label={`Выберите ${question.selection_limit} варианта`}>
        {question.options.map((option, index) => (
          <OptionButton
            key={option.id}
            label={option.label}
            stress={optionDisplay(question, option, subject)}
            marker={markers[index]}
            selected={value.includes(option.id)}
            disabled={disabled}
            subject={subject}
            square
            onClick={() => toggle(option.id)}
          />
        ))}
      </div>
      <AnswerPreview
        markers={markers}
        selected={question.options.map((option, index) => value.includes(option.id) ? markers[index] : "")}
      />
    </>
  );
}

function InputEditor({ question, value, disabled, suppressAutoHint, label, placeholder, onChange }: {
  question: InputQuestion;
  value: string;
  disabled: boolean;
  suppressAutoHint: boolean;
  label: string;
  placeholder: string;
  onChange: (value: AnswerValue) => void;
}) {
  const config = question.answer_format !== "sequence"
    ? {
      ...answerInputConfig(question.prompt),
      inputMode: "decimal" as const,
      hint: "Введи число. Можно использовать знак «−», запятую или точку.",
    }
    : answerInputConfig(question.prompt);
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
          onChange={(event) => onChange(normalizeNumericInput(event.target.value))}
          placeholder={placeholder}
        />
        {question.answer_unit && <span className="answer-unit">{question.answer_unit}</span>}
        {value && <button type="button" disabled={disabled} onClick={() => onChange("")}>Очистить</button>}
      </span>
      {!suppressAutoHint && <small>{config.hint}</small>}
    </label>
  );
}

/** Free text: the same field as InputEditor, without the numeric mode or its digit hint. */
function ShortTextEditor({ question, value, disabled, suppressAutoHint, label, placeholder, onChange }: {
  question: TextQuestion;
  value: string;
  disabled: boolean;
  suppressAutoHint: boolean;
  label: string;
  placeholder: string;
  onChange: (value: AnswerValue) => void;
}) {
  const textPlaceholder = question.lang === "en" ? "Your answer" : placeholder;
  const hint = textAnswerGuidance(question) ?? "Введите только ответ — без пояснений и лишних слов.";
  return (
    <label className="short-answer">
      <span>{label}</span>
      <span className="short-answer-control">
        <input
          lang={question.lang}
          autoCapitalize={question.lang === "en" ? "none" : "off"}
          autoComplete="off"
          enterKeyHint="done"
          inputMode="text"
          disabled={disabled}
          maxLength={question.max_length ?? DEFAULT_TEXT_ANSWER_LENGTH}
          spellCheck={false}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={textPlaceholder}
        />
        {value && <button type="button" disabled={disabled} onClick={() => onChange("")}>Очистить</button>}
      </span>
      {!suppressAutoHint && <small>{hint}</small>}
    </label>
  );
}
