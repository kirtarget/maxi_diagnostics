import { useEffect, useRef, useState } from "react";

import { FormattedMathText } from "./math-display";
import { updateCompactAnswer, updateMatchingAnswer } from "./answer-values";
import { cleanAnswerLabel } from "./question-prompt";
import type { AnswerValue, MatchingQuestion } from "./types";
import type { SequenceMatchingPrompt } from "./sequence-matching";

export type MatchingSource = "matching" | "sequence";

export type MatchingRow = {
  key: string;
  marker: string;
  label: string;
};

export type MatchingOption = {
  key: string;
  marker: string;
  label: string;
};

export type MatchingModel = {
  source: MatchingSource;
  rows: MatchingRow[];
  options: MatchingOption[];
  markers: string[];
  answerLength: number;
  allowReuse: boolean;
};

const MARKER = /^\s*([А-ЯЁA-Z0-9]+)(?:[).]|\s|$)/u;
const LOOKALIKE_CYRILLIC: Record<string, string> = {
  A: "А", B: "Б", C: "С", E: "Е", K: "К", M: "М", H: "Н", O: "О", P: "Р", T: "Т", X: "Х", Y: "У",
};
const SHEET_OPTION_LIMIT = 6;
const LONG_OPTION_LENGTH = 42;

function displayParts(label: string, fallback: string): { marker: string; text: string } {
  const match = MARKER.exec(label);
  return {
    marker: match?.[1] ?? fallback,
    text: cleanAnswerLabel(label),
  };
}

function normalizeMarker(marker: string, subject?: string): string {
  const language = subject?.toLocaleLowerCase();
  const english = language?.includes("english") || language?.includes("англий");
  return english ? marker : LOOKALIKE_CYRILLIC[marker] ?? marker;
}

export function matchingModelFromQuestion(question: MatchingQuestion, subject?: string): MatchingModel {
  const rows = question.items.map((item, index) => {
    const parts = displayParts(item.label, String(index + 1));
    return { key: item.id, marker: normalizeMarker(parts.marker, subject), label: parts.text };
  });
  const options = question.options.map((option, index) => {
    const parts = displayParts(option.label, String(index + 1));
    return { key: option.id, marker: normalizeMarker(parts.marker, subject), label: parts.text };
  });
  return {
    source: "matching",
    rows,
    options,
    markers: rows.map((row) => row.marker),
    answerLength: rows.length,
    allowReuse: true,
  };
}

export function matchingModelFromSequence(matching: SequenceMatchingPrompt, subject?: string): MatchingModel {
  const rows = matching.left.slice(0, matching.answerLength).map((item) => ({
    key: item.marker,
    marker: normalizeMarker(item.marker, subject),
    label: item.label,
  }));
  const options = matching.options.map((option) => ({
    key: option.marker,
    marker: option.marker,
    label: option.label,
  }));
  return {
    source: "sequence",
    rows,
    options,
    markers: rows.map((row) => row.marker),
    answerLength: matching.answerLength,
    allowReuse: matching.allowReuse,
  };
}

function mapAnswer(value: AnswerValue | undefined): Record<string, string> {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function selectedKey(model: MatchingModel, value: AnswerValue | undefined, sequenceSelections: string[], rowIndex: number): string {
  if (model.source === "matching") return mapAnswer(value)[model.rows[rowIndex]?.key] ?? "";
  return sequenceSelections[rowIndex] ?? "";
}

function selectedOptionMarker(model: MatchingModel, value: AnswerValue | undefined, sequenceSelections: string[], rowIndex: number): string {
  const key = selectedKey(model, value, sequenceSelections, rowIndex);
  return model.options.find((option) => option.key === key)?.marker ?? "";
}

function encodeSelection(
  model: MatchingModel,
  value: AnswerValue | undefined,
  sequenceSelections: string[],
  rowIndex: number,
  option: MatchingOption,
): AnswerValue {
  if (model.source === "matching") {
    return updateMatchingAnswer(mapAnswer(value), model.rows[rowIndex].key, option.key);
  }
  return updateCompactAnswer(typeof value === "string" ? value : sequenceSelections.slice(0, rowIndex).join(""), rowIndex, option.marker);
}

function clearSelection(
  model: MatchingModel,
  value: AnswerValue | undefined,
  sequenceSelections: string[],
  rowIndex: number,
): AnswerValue {
  if (model.source === "matching") {
    return updateMatchingAnswer(mapAnswer(value), model.rows[rowIndex].key, "");
  }
  return updateCompactAnswer(typeof value === "string" ? value : sequenceSelections.slice(0, rowIndex).join(""), rowIndex, "");
}

function compactPrefix(selections: string[]): string {
  const firstHole = selections.findIndex((selection) => !selection);
  return selections.slice(0, firstHole < 0 ? selections.length : firstHole).join("");
}

export function MatchingAnswer({ model, value, subject, disabled = false, onChange }: {
  model: MatchingModel;
  value: AnswerValue | undefined;
  subject?: string;
  disabled?: boolean;
  onChange: (value: AnswerValue) => void;
}) {
  const compactValue = typeof value === "string" ? value : "";
  const [sequenceSelections, setSequenceSelections] = useState(() => [...compactValue]);
  const [openRow, setOpenRow] = useState<number | null>(null);
  const triggerRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const lastEmittedSequence = useRef<string | undefined>(undefined);
  const sheetWasOpenedBy = openRow === null ? null : triggerRefs.current[openRow];

  useEffect(() => {
    if (model.source !== "sequence") return;
    if (lastEmittedSequence.current === compactValue) {
      lastEmittedSequence.current = undefined;
      return;
    }
    setSequenceSelections([...compactValue]);
  }, [compactValue, model.source]);

  useEffect(() => {
    if (openRow === null) return;
    const trigger = sheetWasOpenedBy;
    const sheet = document.querySelector<HTMLElement>(`[data-matching-sheet-row="${openRow}"]`);
    sheet?.querySelector<HTMLButtonElement>('button[role="radio"]:not([disabled])')?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpenRow(null);
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      trigger?.focus();
    };
  }, [openRow, sheetWasOpenedBy]);

  const selectedKeys = model.rows.map((_, index) => selectedKey(model, value, sequenceSelections, index));
  const usedBy = new Map<string, number>();
  selectedKeys.forEach((key, index) => {
    if (key && !usedBy.has(key)) usedBy.set(key, index);
  });
  const useSheet = model.options.length > SHEET_OPTION_LIMIT
    || model.options.some((option) => option.label.length > LONG_OPTION_LENGTH);
  const choose = (rowIndex: number, option: MatchingOption) => {
    const usedAt = usedBy.get(option.key);
    if (disabled || (usedAt !== undefined && usedAt !== rowIndex && !model.allowReuse)) return;
    if (model.source === "sequence") {
      const next = [...sequenceSelections];
      next[rowIndex] = option.marker;
      setSequenceSelections(next);
      const prefix = compactPrefix(next);
      lastEmittedSequence.current = prefix;
      onChange(prefix);
    } else {
      onChange(encodeSelection(model, value, sequenceSelections, rowIndex, option));
    }
    setOpenRow(null);
  };
  const clear = (rowIndex: number) => {
    if (disabled) return;
    if (model.source === "sequence") {
      const next = [...sequenceSelections];
      next[rowIndex] = "";
      setSequenceSelections(next);
      const prefix = compactPrefix(next);
      lastEmittedSequence.current = prefix;
      onChange(prefix);
    } else {
      onChange(clearSelection(model, value, sequenceSelections, rowIndex));
    }
  };
  const renderOption = (rowIndex: number, option: MatchingOption, inSheet = false) => {
    const selected = selectedKeys[rowIndex] === option.key;
    const usedAt = usedBy.get(option.key);
    const blocked = usedAt !== undefined && usedAt !== rowIndex && !model.allowReuse;
    return (
      <button
        aria-checked={selected}
        aria-label={`${option.marker} — ${option.label}${blocked ? `, в строке ${model.rows[usedAt]?.marker ?? ""}` : ""}`}
        className={`matching-answer-option${selected ? " selected" : ""}`}
        data-option-key={option.key}
        disabled={disabled || blocked}
        key={option.key}
        onClick={() => choose(rowIndex, option)}
        role="radio"
        type="button"
      >
        <strong>{option.marker}</strong>
        <span><FormattedMathText text={option.label} subject={subject} /></span>
        {blocked && <small>в строке {model.rows[usedAt]?.marker ?? ""}</small>}
        {inSheet && selected && <small>выбрано</small>}
      </button>
    );
  };

  return (
    <section className={`matching-answer matching-answer-${model.source}`} aria-labelledby="matching-answer-title">
      <div className="matching-answer-intro">
        <span>Ответ без ручного ввода</span>
        <h2 id="matching-answer-title">Составьте соответствие</h2>
        <p>Для каждого пункта выберите подходящий вариант.</p>
      </div>
      <div className="matching-answer-option-list" aria-label="Список вариантов" role="list">
        {model.options.map((option) => (
          <div className="matching-answer-option-reference" key={option.key} role="listitem">
            <strong>{option.marker}</strong>
            <span><FormattedMathText text={option.label} subject={subject} /></span>
          </div>
        ))}
      </div>
      <div className="matching-answer-rows">
        {model.rows.map((row, rowIndex) => {
          const selectedMarker = selectedOptionMarker(model, value, sequenceSelections, rowIndex);
          const duplicateAt = selectedKeys.findIndex((key, index) => index !== rowIndex && key && key === selectedKeys[rowIndex]);
          return (
            <div
              className={`matching-answer-row${selectedMarker ? " is-filled" : " is-empty"}`}
              data-state={selectedMarker ? "filled" : "empty"}
              key={row.key}
            >
              <div className="matching-answer-row-copy"><strong>{row.marker}</strong><span><FormattedMathText text={row.label} subject={subject} /></span></div>
              {useSheet ? (
                <button
                  aria-expanded={openRow === rowIndex}
                  aria-haspopup="dialog"
                  className="matching-answer-trigger"
                  disabled={disabled}
                  onClick={() => setOpenRow(rowIndex)}
                  ref={(element) => { triggerRefs.current[rowIndex] = element; }}
                  type="button"
                >
                  {selectedMarker ? <><strong>{selectedMarker}</strong> <span>{model.options.find((option) => option.marker === selectedMarker)?.label}</span></> : "Выберите вариант"}
                </button>
              ) : (
                <div className="matching-answer-options" aria-label={`Варианты для пункта ${row.marker}`} role="radiogroup">
                  {model.options.map((option) => renderOption(rowIndex, option))}
                </div>
              )}
              {selectedMarker && <button className="matching-answer-clear" disabled={disabled} onClick={() => clear(rowIndex)} type="button">Очистить</button>}
              {duplicateAt >= 0 && <small className="matching-answer-duplicate" role="alert">Вариант {selectedMarker} уже выбран в строке {model.rows[duplicateAt].marker}</small>}
              {useSheet && openRow === rowIndex && (
                <div className="matching-answer-sheet-backdrop" role="presentation" onClick={() => setOpenRow(null)}>
                  <section className="matching-answer-sheet" data-matching-sheet-row={rowIndex} role="dialog" aria-modal="true" aria-labelledby={`matching-answer-sheet-title-${rowIndex}`} onClick={(event) => event.stopPropagation()}>
                    <h3 id={`matching-answer-sheet-title-${rowIndex}`}>Варианты для {row.marker}</h3>
                    <div className="matching-answer-sheet-options" aria-label={`Варианты для пункта ${row.marker}`} role="radiogroup">
                      {model.options.map((option) => renderOption(rowIndex, option, true))}
                    </div>
                    <button className="secondary-button" onClick={() => setOpenRow(null)} type="button">Закрыть</button>
                  </section>
                </div>
              )}
            </div>
          );
        })}
      </div>
      <AnswerPreview markers={model.markers} selected={model.rows.map((_, index) => selectedOptionMarker(model, value, sequenceSelections, index))} />
    </section>
  );
}

export function AnswerPreview({ markers, selected, label = "Твой ответ" }: {
  markers: string[];
  selected: string[];
  label?: string;
}) {
  const values = markers.map((_, index) => selected[index] ?? "");
  return (
    <div className={`matching-answer-preview${values.length > 0 && values.every(Boolean) ? " complete" : ""}`} aria-live="polite">
      <span>{label}</span>
      <strong>
        {markers.map((marker, index) => (
          <span key={`${marker}-${index}`}>{values[index] || "—"}<small>{marker}</small></span>
        ))}
      </strong>
    </div>
  );
}
