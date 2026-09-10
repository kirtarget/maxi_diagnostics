import { useRef, type KeyboardEvent as ReactKeyboardEvent } from "react";

import { FormattedMathText } from "./math-display";
import { answerInputConfig } from "./math-text";
import { cleanAnswerLabel } from "./question-prompt";
import { DEFAULT_TEXT_ANSWER_LENGTH, normalizeNumericInput } from "./answer-values";
import { plural } from "./text-utils";
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
  /** Set once the answer is graded: the options the server called correct. */
  correctOptions?: readonly string[];
};

/** Undefined until the answer is graded, so an unanswered option carries no verdict. */
// Not the word correct: the production-output guard rejects that token followed by a
// colon, and a minified ternary produces exactly that from `? "…" : …`.
export type OptionOutcome = "right" | "wrong";

function optionOutcome(correctOptions: readonly string[] | undefined, optionId: string, selected: boolean): OptionOutcome | undefined {
  if (!correctOptions) return undefined;
  if (correctOptions.includes(optionId)) return "right";
  return selected ? "wrong" : undefined;
}

const DEFAULT_LABELS: AnswerEditorLabels = {
  answer: "Твой ответ",
  placeholder: "Введи ответ",
  choose: "Выбрать вариант",
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

// The КИМ numbers the choices of a single and multiple question 1..N and asks
// for those digits on the blank. A Latin letter here is a marker the student
// cannot write down anywhere.
function optionMarkers(options: { label: string }[]): string[] {
  return options.map((_, index) => String(index + 1));
}

// A choice list whose labels are exactly 1..N in order is the numbering of the
// sentences the student reads above, not a list of values. Printing the label
// next to the marker would then write the same number twice.
function optionsAreTheirOwnPosition(options: { label: string }[]): boolean {
  return options.length > 0
    && options.every((option, index) => option.label.trim() === String(index + 1));
}


export function AnswerEditor({ question, subject, value, onChange, disabled = false, suppressAutoHint = false, labels, correctOptions }: AnswerEditorProps) {
  const text = { ...DEFAULT_LABELS, ...labels };
  const asText = typeof value === "string" ? value : "";
  if (question.type === "single") {
    return <SingleEditor question={question} subject={subject} value={asText} disabled={disabled} correctOptions={correctOptions} onChange={onChange} />;
  }
  if (question.type === "multiple") {
    return <MultipleEditor question={question} subject={subject} value={Array.isArray(value) ? value : []} disabled={disabled} correctOptions={correctOptions} onChange={onChange} />;
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

type SelectionMode = "radio" | "checkbox";

function OptionButton({ label, stress, marker, selected, disabled, outcome, selectionMode, subject, tabIndex, describedBy, buttonRef, onClick, onKeyDown }: {
  label: string;
  stress?: string;
  marker: string;
  selected: boolean;
  disabled: boolean;
  outcome?: OptionOutcome;
  selectionMode: SelectionMode;
  subject?: string;
  tabIndex?: number;
  describedBy?: string;
  buttonRef?: (element: HTMLButtonElement | null) => void;
  onClick: () => void;
  onKeyDown?: (event: ReactKeyboardEvent<HTMLButtonElement>) => void;
}) {
  return (
    <button
      type="button"
      role={selectionMode}
      aria-checked={selected}
      aria-describedby={describedBy}
      tabIndex={tabIndex}
      ref={buttonRef}
      disabled={disabled}
      className={`answer-option${selected ? " selected" : ""}${outcome ? ` is-${outcome}` : ""}`}
      onClick={onClick}
      onKeyDown={onKeyDown}
    >
      <span className="option-letter">{marker}</span>
      <span><FormattedMathText text={cleanAnswerLabel(stress ?? label)} subject={subject} /></span>
      {outcome && <span className="answer-option-verdict">{outcome === "right" ? "Правильный ответ" : "Твой ответ"}</span>}
      <span className={selectionMode === "checkbox" ? "selection-mark square" : "selection-mark"} aria-hidden="true" />
    </button>
  );
}

function SingleEditor({ question, subject, value, disabled, correctOptions, onChange }: {
  question: SingleQuestion;
  subject?: string;
  value: string;
  disabled: boolean;
  correctOptions?: readonly string[];
  onChange: (value: AnswerValue) => void;
}) {
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const selectedIndex = question.options.findIndex((option) => option.id === value);
  const markers = optionMarkers(question.options);
  const move = (event: ReactKeyboardEvent<HTMLButtonElement>, index: number) => {
    const delta = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1
      : event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1
      : 0;
    if (!delta) return;
    event.preventDefault();
    const nextIndex = (index + delta + question.options.length) % question.options.length;
    onChange(question.options[nextIndex].id);
    optionRefs.current[nextIndex]?.focus();
  };
  return (
    <div className="answer-list" role="radiogroup" aria-label="Выбери один вариант">
      {question.options.map((option, index) => (
        <OptionButton
          key={option.id}
          label={option.label}
          stress={optionDisplay(question, option, subject)}
          marker={markers[index]}
          selected={value === option.id}
          disabled={disabled}
          outcome={optionOutcome(correctOptions, option.id, value === option.id)}
          selectionMode="radio"
          tabIndex={selectedIndex >= 0 ? (selectedIndex === index ? 0 : -1) : (index === 0 ? 0 : -1)}
          subject={subject}
          onClick={() => onChange(option.id)}
          onKeyDown={(event) => move(event, index)}
          buttonRef={(element) => { optionRefs.current[index] = element; }}
        />
      ))}
    </div>
  );
}

function MultipleEditor({ question, subject, value, disabled, correctOptions, onChange }: {
  question: MultipleQuestion;
  subject?: string;
  value: string[];
  disabled: boolean;
  correctOptions?: readonly string[];
  onChange: (value: AnswerValue) => void;
}) {
  const selectionCountId = `multiple-selection-count-${question.id}`;
  const toggle = (id: string) => {
    if (value.includes(id)) onChange(value.filter((item) => item !== id));
    else if (value.length < question.selection_limit) onChange([...value, id]);
  };

  const numbered = optionsAreTheirOwnPosition(question.options);
  const markers = optionMarkers(question.options);
  return (
    <>
      <div className="answer-list" role="group" aria-label={`Выбери ${question.selection_limit} ${plural(question.selection_limit, ["вариант", "варианта", "вариантов"])}`} aria-describedby={selectionCountId}>
        {question.options.map((option, index) => (
          <OptionButton
            key={option.id}
            label={numbered ? "" : option.label}
            stress={numbered ? undefined : optionDisplay(question, option, subject)}
            marker={markers[index]}
            selected={value.includes(option.id)}
            disabled={disabled}
            outcome={optionOutcome(correctOptions, option.id, value.includes(option.id))}
            subject={subject}
            selectionMode="checkbox"
            describedBy={selectionCountId}
            onClick={() => toggle(option.id)}
          />
        ))}
      </div>
      <p className="answer-selection-count" id={selectionCountId}>Выбрано {value.length} из {question.selection_limit}</p>
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
  const hint = textAnswerGuidance(question) ?? "Введи только ответ — без пояснений и лишних слов.";
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
